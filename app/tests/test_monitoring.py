import os

import numpy as np
import rasterio
from rasterio.enums import ColorInterp
from rasterio.transform import from_origin
from django.contrib.auth.models import User
from django.test import Client

from app.monitoring import estimate_alignment
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

    def create_task_with_orthophoto(self, name, transform):
        task = Task.objects.create(
            project=self.project,
            name=name,
            status=status_codes.COMPLETED,
            available_assets=['orthophoto.tif']
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

    def test_monitoring_compare_api_generates_layers(self):
        reference = self.create_task_with_orthophoto('Current', from_origin(500000, 1000, 1, 1))
        compare = self.create_task_with_orthophoto('Previous', from_origin(500002, 999, 1, 1))

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

        self.assertEqual(output['compare_task']['id'], str(compare.id))
        self.assertIn('/monitoring/', output['layers']['aligned_overlay']['url'])
        self.assertIn('/monitoring/', output['layers']['change_overlay']['url'])

        aligned_tile_url = output['layers']['aligned_overlay']['url'].replace('{z}', '0').replace('{x}', '0').replace('{y}', '0')
        tile_response = self.client.get(aligned_tile_url + '?size=256')
        self.assertEqual(tile_response.status_code, 200)
        self.assertEqual(tile_response['Content-Type'], 'image/png')
