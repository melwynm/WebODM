import json
import os
from datetime import timedelta

import numpy as np
import rasterio
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from rasterio.enums import ColorInterp
from rasterio.transform import from_origin

from app.monitoring import ensure_monitoring_products, estimate_alignment, monitoring_cache_dir
from app.models import Project, Task
from nodeodm import status_codes

from .classes import BootTestCase


class TestMonitoring(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.client.login(username='testuser', password='test1234')
        self.user = User.objects.get(username='testuser')
        self.project = Project.objects.get(owner=self.user)

    def synthetic_pattern(self, height, width):
        grid_y, grid_x = np.indices((height, width))
        pattern = (grid_x * 3 + grid_y * 5).astype('uint8')
        pattern[12:28, 18:42] = 220
        pattern[34:52, 10:24] = 40
        return pattern

    def create_task_with_orthophoto(self, name, transform, created_at=None, with_dem=False, dem_offset=0):
        available_assets = ['orthophoto.tif']
        if with_dem:
            available_assets += ['dsm.tif', 'dtm.tif']

        task = Task.objects.create(
            project=self.project,
            name=name,
            status=status_codes.COMPLETED,
            available_assets=available_assets,
            created_at=created_at or timezone.now(),
        )

        path = task.get_asset_download_path('orthophoto.tif')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        base = self.synthetic_pattern(64, 64)

        with rasterio.open(
            path,
            'w',
            driver='GTiff',
            width=64,
            height=64,
            count=3,
            dtype='uint8',
            crs='EPSG:32615',
            transform=transform,
            nodata=0,
        ) as dst:
            dst.write(base, 1)
            dst.write((base * 0.8).astype('uint8'), 2)
            dst.write((255 - base).astype('uint8'), 3)
            dst.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue)

        if with_dem:
            grid_y, grid_x = np.indices((64, 64))
            dsm = (100 + grid_x * 0.1 + grid_y * 0.05 + dem_offset).astype('float32')
            dtm = (95 + grid_x * 0.08 + grid_y * 0.03 + dem_offset).astype('float32')
            for asset_name, values in (('dsm.tif', dsm), ('dtm.tif', dtm)):
                dem_path = task.get_asset_download_path(asset_name)
                os.makedirs(os.path.dirname(dem_path), exist_ok=True)
                with rasterio.open(
                    dem_path,
                    'w',
                    driver='GTiff',
                    width=64,
                    height=64,
                    count=1,
                    dtype='float32',
                    crs='EPSG:32615',
                    transform=transform,
                    nodata=-9999,
                ) as dst:
                    dst.write(values, 1)

        return task

    def test_estimate_alignment_detects_georeferencing_shift(self):
        reference = self.create_task_with_orthophoto('Reference', from_origin(500000, 1000, 1, 1))
        compare = self.create_task_with_orthophoto('Compare', from_origin(500002, 999, 1, 1))

        alignment = estimate_alignment(
            reference.get_asset_download_path('orthophoto.tif'),
            compare.get_asset_download_path('orthophoto.tif')
        )

        self.assertAlmostEqual(alignment['shift_units']['x'], -2.0, delta=0.35)
        self.assertAlmostEqual(alignment['shift_units']['y'], 1.0, delta=0.35)
        self.assertGreater(alignment['confidence'], 0.4)

    def test_monitoring_timeline_api_returns_project_tasks_in_created_order(self):
        start = timezone.now() - timedelta(days=3)
        oldest = self.create_task_with_orthophoto('Oldest', from_origin(500000, 1000, 1, 1), created_at=start)
        middle = self.create_task_with_orthophoto('Middle', from_origin(500001, 1000, 1, 1), created_at=start + timedelta(days=1))
        newest = self.create_task_with_orthophoto('Newest', from_origin(500002, 1000, 1, 1), created_at=start + timedelta(days=2))

        response = self.client.get(f'/api/projects/{self.project.id}/monitoring/timeline?task={newest.id}')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual([result['id'] for result in payload['results']], [str(oldest.id), str(middle.id), str(newest.id)])
        self.assertEqual(payload['default_reference_task_id'], str(newest.id))
        self.assertEqual(payload['default_compare_task_id'], str(middle.id))
        self.assertEqual(payload['results'][1]['previous_task_id'], str(oldest.id))
        self.assertEqual(payload['results'][1]['next_task_id'], str(newest.id))

    def test_monitoring_compare_api_generates_layers(self):
        reference = self.create_task_with_orthophoto('Current', from_origin(500000, 1000, 1, 1), with_dem=True, dem_offset=2)
        compare = self.create_task_with_orthophoto('Previous', from_origin(500002, 999, 1, 1), with_dem=True, dem_offset=0)

        candidates = self.client.get(f'/api/projects/{self.project.id}/tasks/{reference.id}/monitoring/candidates')
        self.assertEqual(candidates.status_code, 200)
        self.assertEqual(candidates.json()['results'][0]['id'], str(compare.id))

        response = self.client.post(
            f'/api/projects/{self.project.id}/tasks/{reference.id}/monitoring/compare',
            {'compare_task': str(compare.id)}
        )
        self.assertEqual(response.status_code, 200)
        celery_task_id = response.json()['celery_task_id']

        result = self.client.get(f'/api/workers/get/{celery_task_id}')
        self.assertEqual(result.status_code, 200)
        output = result.json()['output']

        self.assertEqual(output['reference_task']['id'], str(reference.id))
        self.assertEqual(output['compare_task']['id'], str(compare.id))
        self.assertIn('/monitoring/', output['layers']['aligned_overlay']['url'])
        self.assertIn('/monitoring/', output['layers']['change_overlay']['url'])
        self.assertIn('/monitoring/', output['layers']['dsm_delta']['url'])
        self.assertIn('/monitoring/', output['layers']['dtm_delta']['url'])
        self.assertGreater(output['layers']['dsm_delta']['stats']['positive_volume'], 0)
        self.assertAlmostEqual(output['layers']['dsm_delta']['stats']['negative_volume'], 0, delta=0.001)

        aligned_tile_url = output['layers']['aligned_overlay']['url'].replace('{z}', '0').replace('{x}', '0').replace('{y}', '0')
        tile_response = self.client.get(aligned_tile_url + '?size=256')
        self.assertEqual(tile_response.status_code, 200)
        self.assertEqual(tile_response['Content-Type'], 'image/png')

        dsm_tile_url = output['layers']['dsm_delta']['url'].replace('{z}', '0').replace('{x}', '0').replace('{y}', '0')
        dsm_tile_response = self.client.get(dsm_tile_url + '?size=256')
        self.assertEqual(dsm_tile_response.status_code, 200)
        self.assertEqual(dsm_tile_response['Content-Type'], 'image/png')

    def test_monitoring_keeps_working_without_terrain_assets(self):
        reference = self.create_task_with_orthophoto('Current', from_origin(500000, 1000, 1, 1))
        compare = self.create_task_with_orthophoto('Previous', from_origin(500002, 999, 1, 1))

        metadata = ensure_monitoring_products(reference, compare)

        self.assertIn('aligned_overlay', metadata)
        self.assertIn('change_overlay', metadata)
        self.assertEqual(metadata['terrain_deltas'], {})

    def test_monitoring_cache_invalidates_when_input_timestamp_changes(self):
        reference = self.create_task_with_orthophoto('Current', from_origin(500000, 1000, 1, 1))
        compare = self.create_task_with_orthophoto('Previous', from_origin(500002, 999, 1, 1))

        ensure_monitoring_products(reference, compare)
        metadata_path = os.path.join(monitoring_cache_dir(reference.id, compare.id), 'metadata.json')
        with open(metadata_path, 'r', encoding='utf-8') as src:
            before = json.load(src)

        compare_path = compare.get_asset_download_path('orthophoto.tif')
        compare_stat = os.stat(compare_path)
        os.utime(compare_path, (compare_stat.st_atime + 5, compare_stat.st_mtime + 5))

        ensure_monitoring_products(reference, compare)
        with open(metadata_path, 'r', encoding='utf-8') as src:
            after = json.load(src)

        self.assertNotEqual(before['generated_at'], after['generated_at'])
        self.assertNotEqual(before['inputs']['compare']['asset_mtime'], after['inputs']['compare']['asset_mtime'])

    def test_monitoring_cache_is_removed_when_a_task_is_deleted(self):
        reference = self.create_task_with_orthophoto('Current', from_origin(500000, 1000, 1, 1))
        compare = self.create_task_with_orthophoto('Previous', from_origin(500002, 999, 1, 1))

        ensure_monitoring_products(reference, compare)
        cache_dir = monitoring_cache_dir(reference.id, compare.id)
        self.assertTrue(os.path.isdir(cache_dir))

        compare.delete()

        self.assertFalse(os.path.exists(cache_dir))
