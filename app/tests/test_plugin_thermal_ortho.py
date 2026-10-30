import ast
import builtins
import inspect
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import rasterio
from django.contrib.auth.models import User
from PIL import Image
from rasterio.transform import from_bounds
from nodeodm import status_codes

from app.models import Project, Task
from app.tests.classes import BootTestCase
from app.tests.utils import clear_test_media_root
from coreplugins.thermal_ortho.workers import thermal_pipeline
from coreplugins.thermal_ortho.workers.radiometric import (
    DJI_IRP_COMMAND_ENV,
    THERMAL_NODATA,
    UnsupportedThermalImage,
    decode_dji,
    decode_radiometric,
)
from coreplugins.thermal_ortho.workers.thermal_texturing import blend_thermal_orthomosaic
from coreplugins.thermal_ortho.workers.thermal_pipeline import (
    STALE_WORKER_SECONDS,
    STATUS_FILE,
    build_status_payload,
    detect_input_summary,
    enqueue_thermal_pipeline,
    is_pipeline_active,
    read_pipeline_status,
    run_thermal_pipeline,
    write_pipeline_status,
)
from worker.results import store_task_result


def _unbound_names(func):
    """
    Names a function loads that it neither binds itself nor finds in builtins.
    run_function_async evaluates the function's source in an empty namespace,
    so any such name raises NameError on the worker.
    """
    tree = ast.parse(inspect.getsource(func))
    fn = tree.body[0]

    bound = {arg.arg for arg in fn.args.args + fn.args.kwonlyargs}
    if fn.args.vararg:
        bound.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        bound.add(fn.args.kwarg.arg)

    loaded = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                bound.add(node.id)
            else:
                loaded.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split('.')[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)

    return sorted(name for name in loaded if name not in bound and not hasattr(builtins, name))


class TestThermalOrthoPlugin(BootTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.get(username='testuser')
        self.project = Project.objects.create(owner=self.user, name='Thermal Project')

    def tearDown(self):
        clear_test_media_root()

    def _create_task(self, status=status_codes.COMPLETED):
        task = Task.objects.create(project=self.project, name='Thermal Task', status=status)
        Path(task.task_path()).mkdir(parents=True, exist_ok=True)
        return task

    def _write_images(self, task, names):
        for name in names:
            Path(task.task_path(name)).write_bytes(b'not really an image')

    def _write_raw_status(self, task, payload):
        # write_pipeline_status always stamps updated_at with "now"; tests that
        # need an old timestamp write the file directly.
        status_path = task.data_path(STATUS_FILE)
        os.makedirs(os.path.dirname(status_path), exist_ok=True)
        with open(status_path, 'w', encoding='utf-8') as status_file:
            json.dump(payload, status_file)

    # --- Celery entry point -------------------------------------------------

    def test_worker_entry_point_is_self_contained(self):
        self.assertEqual([], _unbound_names(run_thermal_pipeline))

    def test_worker_entry_point_runs_from_an_empty_namespace(self):
        # Mirror app.plugins.worker.eval_async: only the source text travels to the worker.
        namespace = {}
        exec(compile(inspect.getsource(run_thermal_pipeline), 'file', 'exec'), namespace, namespace)
        entry_point = namespace['run_thermal_pipeline']

        callback = mock.Mock()
        with mock.patch.object(thermal_pipeline, 'execute_thermal_pipeline', return_value={'status': 'ok'}) as execute:
            result = entry_point(42, camera_type='dji', progress_callback=callback)

        execute.assert_called_once_with(42, camera_type='dji', progress_callback=callback)
        self.assertEqual({'status': 'ok'}, result)

    # --- Image classification ----------------------------------------------

    def test_dji_dual_lens_filenames_classify_without_reading_exif(self):
        task = self._create_task()
        self._write_images(task, [
            'DJI_20260101120000_0001_W.JPG',
            'DJI_20260101120000_0001_T.JPG',
            'DJI_20260101120005_0002_W.JPG',
            'DJI_20260101120005_0002_T.JPG',
            'DJI_20260101120005_0002_Z.JPG',
        ])

        with mock.patch('coreplugins.thermal_ortho.workers.radiometric.read_exif_metadata') as read_exif:
            summary = detect_input_summary(task.task_path())

        read_exif.assert_not_called()
        self.assertEqual(3, summary['rgb_images'])
        self.assertEqual(2, summary['thermal_images'])
        self.assertEqual(
            ['DJI_20260101120000_0001_T.JPG', 'DJI_20260101120005_0002_T.JPG'],
            sorted(os.path.basename(path) for path in summary['thermal_paths']),
        )

    def test_camera_model_alone_does_not_mark_a_frame_as_thermal(self):
        task = self._create_task()
        metadata_by_name = {
            # Mavic 3T wide frame: same Model tag as the thermal lens.
            'IMG_0001.JPG': {'Make': 'DJI', 'Model': 'M3T'},
            'IMG_0002.JPG': {'Make': 'DJI', 'Model': 'M3T', 'ImageSource': 'InfraredCamera'},
            'IMG_0003.JPG': {'Make': 'DJI', 'Model': 'ZH20T', 'ImageSource': 'WideCamera'},
            'IMG_0004.JPG': {'Make': 'FLIR Systems', 'Model': 'Vue Pro R', 'PlanckR1': 17096.453},
            'IMG_0005.JPG': {'Make': 'FLIR', 'Model': 'Duo'},
            'IMG_0006.JPG': {'Make': 'DJI', 'Model': 'FC3582'},
        }
        self._write_images(task, metadata_by_name.keys())

        def fake_read_exif(path, tags=None):
            return dict(metadata_by_name[os.path.basename(path)])

        with mock.patch('coreplugins.thermal_ortho.workers.radiometric.read_exif_metadata', side_effect=fake_read_exif):
            summary = detect_input_summary(task.task_path())

        self.assertEqual(
            ['IMG_0001.JPG', 'IMG_0003.JPG', 'IMG_0006.JPG'],
            sorted(os.path.basename(path) for path in summary['rgb_paths']),
        )
        self.assertEqual(
            ['IMG_0002.JPG', 'IMG_0004.JPG', 'IMG_0005.JPG'],
            sorted(os.path.basename(path) for path in summary['thermal_paths']),
        )

    def test_image_scan_ignores_odm_outputs_but_not_media_root_folders(self):
        task = self._create_task()
        self._write_images(task, ['DJI_0001_W.JPG', 'DJI_0001_T.JPG'])
        Path(task.assets_path('odm_orthophoto')).mkdir(parents=True, exist_ok=True)
        Path(task.assets_path('odm_orthophoto', 'odm_orthophoto.tif')).write_bytes(b'tif')
        Path(task.data_path()).mkdir(parents=True, exist_ok=True)
        Path(task.data_path('preview_T.jpg')).write_bytes(b'jpg')

        summary = detect_input_summary(task.task_path())

        self.assertEqual(1, summary['rgb_images'])
        self.assertEqual(1, summary['thermal_images'])

        # A media root that itself contains a "data" folder must not hide the images.
        parent = Path(task.task_path()).parent
        nested_root = parent / 'data' / 'images'
        nested_root.mkdir(parents=True, exist_ok=True)
        (nested_root / 'DJI_0002_W.JPG').write_bytes(b'jpg')
        (nested_root / 'DJI_0002_T.JPG').write_bytes(b'jpg')

        nested_summary = detect_input_summary(str(nested_root))

        self.assertEqual(1, nested_summary['rgb_images'])
        self.assertEqual(1, nested_summary['thermal_images'])

    # --- Worker result handling --------------------------------------------

    def test_failed_worker_result_is_reported_instead_of_raised(self):
        task = self._create_task()
        write_pipeline_status(task, {
            'state': 'running',
            'progress': 40,
            'celery_task_id': 'thermal-worker-raised',
            'rgb_images': 2,
            'thermal_images': 2,
        })
        store_task_result('thermal-worker-raised', RuntimeError('exiftool failed for DJI_0001_T.JPG'))

        payload = build_status_payload(task)

        self.assertEqual('failed', payload['state'])
        self.assertIn('exiftool failed', payload['error'])
        self.assertEqual(100, payload['progress'])
        self.assertTrue(payload['can_process'])
        self.assertEqual('failed', read_pipeline_status(task)['state'])
        self.assertFalse(is_pipeline_active(task))

    def test_worker_error_result_is_persisted_as_failed(self):
        task = self._create_task()
        write_pipeline_status(task, {
            'state': 'running',
            'celery_task_id': 'thermal-worker-error',
            'rgb_images': 2,
            'thermal_images': 2,
        })
        store_task_result('thermal-worker-error', {
            'status': 'failed',
            'error': 'Could not match thermal images to RGB captures.',
            'output': {'state': 'failed', 'message': 'Could not match thermal images to RGB captures.'},
        })

        payload = build_status_payload(task)

        self.assertEqual('failed', payload['state'])
        self.assertEqual('Could not match thermal images to RGB captures.', payload['error'])
        self.assertEqual('failed', read_pipeline_status(task)['state'])

    def test_lost_worker_job_is_marked_failed_after_the_stale_timeout(self):
        task = self._create_task()
        stale = datetime.now(timezone.utc) - timedelta(seconds=STALE_WORKER_SECONDS + 60)
        self._write_raw_status(task, {
            'state': 'queued',
            'progress': 0,
            'celery_task_id': 'bogus',  # the in-memory result backend knows nothing about it
            'rgb_images': 2,
            'thermal_images': 2,
            'updated_at': stale.isoformat(),
        })

        payload = build_status_payload(task)

        self.assertEqual('failed', payload['state'])
        self.assertIn('stopped responding', payload['error'])
        self.assertTrue(payload['can_process'])
        self.assertFalse(is_pipeline_active(task))

    def test_recently_queued_job_stays_queued(self):
        task = self._create_task()
        write_pipeline_status(task, {
            'state': 'queued',
            'progress': 0,
            'celery_task_id': 'bogus',
            'rgb_images': 2,
            'thermal_images': 2,
        })

        payload = build_status_payload(task)

        self.assertEqual('queued', payload['state'])
        self.assertIsNone(payload['error'])
        self.assertTrue(is_pipeline_active(task))

    # --- Enqueueing ----------------------------------------------------------

    def test_enqueue_reuses_a_live_job_and_restarts_after_failure(self):
        task = self._create_task()
        summary = {'rgb_images': 2, 'thermal_images': 2, 'rgb_paths': [], 'thermal_paths': []}
        write_pipeline_status(task, {'state': 'queued', 'celery_task_id': 'bogus', 'rgb_images': 2, 'thermal_images': 2})

        with mock.patch.object(thermal_pipeline, 'run_function_async', return_value=SimpleNamespace(task_id='new-job')) as dispatch:
            reused = enqueue_thermal_pipeline(task, summary=summary)

            self.assertEqual('bogus', reused.task_id)
            dispatch.assert_not_called()

            write_pipeline_status(task, {'state': 'failed', 'error': 'boom', 'message': 'boom'})
            restarted = enqueue_thermal_pipeline(task, camera_type='dji', summary=summary)

        self.assertEqual('new-job', restarted.task_id)
        dispatch.assert_called_once_with(run_thermal_pipeline, task.id, camera_type='dji', with_progress=True)

        stored = read_pipeline_status(task)
        self.assertEqual('queued', stored['state'])
        self.assertEqual('new-job', stored['celery_task_id'])
        self.assertIsNone(stored['error'])
        self.assertEqual('manual', stored['trigger'])

    def test_enqueue_dispatch_failure_is_recorded(self):
        task = self._create_task()
        summary = {'rgb_images': 2, 'thermal_images': 2, 'rgb_paths': [], 'thermal_paths': []}

        with mock.patch.object(thermal_pipeline, 'run_function_async', side_effect=RuntimeError('broker down')):
            with self.assertRaises(RuntimeError):
                enqueue_thermal_pipeline(task, summary=summary)

        stored = read_pipeline_status(task)
        self.assertEqual('failed', stored['state'])
        self.assertIn('broker down', stored['error'])
        self.assertFalse(is_pipeline_active(task))

    # --- Cached input counts -------------------------------------------------

    def test_status_requests_scan_the_images_once(self):
        task = self._create_task()
        self._write_images(task, ['DJI_0001_W.JPG', 'DJI_0001_T.JPG'])

        with mock.patch.object(thermal_pipeline, 'detect_input_summary', wraps=thermal_pipeline.detect_input_summary) as detect:
            first = build_status_payload(task)
            second = build_status_payload(task)

        self.assertEqual(1, detect.call_count)
        self.assertEqual((1, 1), (first['rgb_images'], first['thermal_images']))
        self.assertEqual((1, 1), (second['rgb_images'], second['thermal_images']))
        self.assertEqual(task.images_count, read_pipeline_status(task)['scanned_images_count'])

    def test_status_rescans_when_the_task_image_count_changes(self):
        task = self._create_task()
        self._write_images(task, ['DJI_0001_W.JPG', 'DJI_0001_T.JPG'])
        self.assertEqual(1, build_status_payload(task)['thermal_images'])

        self._write_images(task, ['DJI_0002_W.JPG', 'DJI_0002_T.JPG'])
        task.images_count = 4
        task.save()

        self.assertEqual(2, build_status_payload(task)['thermal_images'])

    # --- DJI decoding --------------------------------------------------------

    def _write_jpeg(self, path, size=(4, 3)):
        Image.new('RGB', size, color=(200, 30, 30)).save(path, 'JPEG')

    def test_dji_rjpeg_is_refused_without_the_thermal_sdk(self):
        task = self._create_task()
        path = task.task_path('DJI_0001_T.JPG')
        self._write_jpeg(path)

        with mock.patch.dict(os.environ, {DJI_IRP_COMMAND_ENV: ''}):
            with self.assertRaises(UnsupportedThermalImage) as raised:
                decode_dji(path)

        self.assertIn(DJI_IRP_COMMAND_ENV, str(raised.exception))

    def test_dji_rjpeg_decodes_through_a_configured_dji_irp_command(self):
        task = self._create_task()
        path = task.task_path('DJI_0001_T.JPG')
        self._write_jpeg(path, size=(4, 3))

        script = Path(task.task_path('fake_dji_irp.py'))
        script.write_text(
            "import struct, sys\n"
            "assert sys.argv[sys.argv.index('-s') + 1].endswith('DJI_0001_T.JPG')\n"
            "out = sys.argv[sys.argv.index('-o') + 1]\n"
            "open(out, 'wb').write(struct.pack('<12f', *[20.0 + i for i in range(12)]))\n",
            encoding='utf-8',
        )

        with mock.patch.dict(os.environ, {DJI_IRP_COMMAND_ENV: '{} {}'.format(sys.executable, script)}):
            celsius, profile = decode_dji(path)

        self.assertEqual((3, 4), celsius.shape)
        self.assertAlmostEqual(20.0, float(celsius[0, 0]), places=4)
        self.assertAlmostEqual(31.0, float(celsius[2, 3]), places=4)
        self.assertEqual((4, 3), (profile['width'], profile['height']))

    def test_visual_tiff_export_is_refused(self):
        task = self._create_task()
        path = task.task_path('DJI_0001_T.tif')
        data = np.random.default_rng(1).integers(0, 255, size=(3, 8, 8), dtype=np.uint8)
        with rasterio.open(path, 'w', driver='GTiff', width=8, height=8, count=3, dtype='uint8') as dst:
            dst.write(data)

        with self.assertRaises(UnsupportedThermalImage):
            decode_dji(path)

    def test_radiometric_tiff_temperatures_are_kept(self):
        task = self._create_task()
        float_path = task.task_path('DJI_0001_T.tif')
        with rasterio.open(float_path, 'w', driver='GTiff', width=8, height=8, count=1, dtype='float32') as dst:
            dst.write(np.full((8, 8), 31.5, dtype=np.float32), 1)

        celsius, _profile = decode_dji(float_path)
        self.assertAlmostEqual(31.5, float(celsius.mean()), places=3)

        deci_kelvin_path = task.task_path('DJI_0002_T.tif')
        with rasterio.open(deci_kelvin_path, 'w', driver='GTiff', width=8, height=8, count=1, dtype='uint16') as dst:
            dst.write(np.full((8, 8), 3046, dtype=np.uint16), 1)  # 304.6 K

        celsius, _profile = decode_dji(deci_kelvin_path)
        self.assertAlmostEqual(31.45, float(celsius.mean()), delta=0.01)

    def test_flir_container_is_decoded_as_flir_even_on_dji_cameras(self):
        metadata = {'Make': 'DJI', 'Model': 'ZENMUSE XT', 'PlanckR1': 17096.453}
        with mock.patch('coreplugins.thermal_ortho.workers.radiometric.read_exif_metadata', return_value=metadata):
            with mock.patch('coreplugins.thermal_ortho.workers.radiometric.decode_flir', return_value=('flir', {})) as flir:
                self.assertEqual(('flir', {}), decode_radiometric('/tmp/DJI_0001.jpg'))

        flir.assert_called_once_with('/tmp/DJI_0001.jpg')

    # --- Blending ------------------------------------------------------------

    def test_blending_downsamples_to_thermal_resolution_and_averages_overlaps(self):
        task = self._create_task()
        reference = Path(task.assets_path('odm_orthophoto', 'odm_orthophoto.tif'))
        reference.parent.mkdir(parents=True, exist_ok=True)
        # 1000x1000 reference at 1e-6 degrees per pixel.
        ref_transform = from_bounds(10.0, 45.0, 10.001, 45.001, 1000, 1000)
        with rasterio.open(str(reference), 'w', driver='GTiff', width=1000, height=1000, count=4, dtype='uint8',
                           crs='EPSG:4326', transform=ref_transform) as dst:
            dst.write(np.zeros((4, 1000, 1000), dtype=np.uint8))

        def frame(value, left, right, bottom, top):
            return {
                'array': np.full((10, 10), value, dtype=np.float32),
                'native_shape': (10, 10),
                'bounds': {'left': left, 'right': right, 'bottom': bottom, 'top': top},
                'crs': 'EPSG:4326',
                'weight': 1.0,
            }

        # Each 10x10 frame spans 0.0005 degrees: 5e-5 degrees per pixel, 50x the reference GSD.
        frames = [
            frame(20.0, 10.0, 10.0005, 45.0005, 45.001),
            frame(30.0, 10.00025, 10.00075, 45.0005, 45.001),
        ]
        output_path = task.assets_path('thermal_orthophoto', 'thermal_orthophoto.tif')

        result = blend_thermal_orthomosaic(frames, str(reference), output_path)

        self.assertEqual(50, result['scale'])
        self.assertEqual((20, 20), result['shape'])
        with rasterio.open(output_path) as src:
            self.assertEqual((20, 20), (src.height, src.width))
            self.assertEqual(('LWIR',), src.descriptions)
            self.assertEqual(THERMAL_NODATA, src.nodata)
            data = src.read(1)

        self.assertAlmostEqual(20.0, float(data[2, 2]), places=3)   # first frame only
        self.assertAlmostEqual(25.0, float(data[2, 7]), places=3)   # overlap, averaged
        self.assertAlmostEqual(30.0, float(data[2, 12]), places=3)  # second frame only
        self.assertEqual(THERMAL_NODATA, float(data[15, 15]))      # untouched
        self.assertEqual(20.0, result['stats']['min'])
        self.assertEqual(30.0, result['stats']['max'])
        self.assertTrue(Path(result['preview_path']).is_file())
