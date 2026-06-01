import inspect
import sys
from types import ModuleType, SimpleNamespace
from unittest import mock

import numpy as np

from coreplugins.objdetect.api import (
    DEER_MODEL_URL,
    DEER_SIZE_FILTER_METERS,
    DOG_MODEL_URL,
    DOG_SIZE_FILTER_METERS,
    MAX_ONNX_OPSET,
    OBJECT_DETECTION_MODEL_MAP,
    _ensure_supported_onnx_opset,
    _filter_outputs_by_long_side_meters,
    detect,
    size_filter_for_classes,
)
from .classes import BootTestCase


class TestObjDetect(BootTestCase):
    def _run_serialized(self, func, *args, **kwargs):
        ns = {}
        code = compile(inspect.getsource(func), 'file', 'exec')
        eval(code, ns, ns)
        return ns[func.__name__](*args, **kwargs)

    def test_detect_can_run_when_serialized_for_cars_model(self):
        fake_geodeep = ModuleType('geodeep')
        fake_output = {'type': 'FeatureCollection', 'features': []}
        fake_geodeep.detect = mock.Mock(return_value=fake_output)
        fake_geodeep.models = SimpleNamespace(cache_dir=None)

        with mock.patch.dict(sys.modules, {'geodeep': fake_geodeep}):
            result = self._run_serialized(detect, 'C:\\fake\\orthophoto.tif', 'cars')

        self.assertEqual(result, {'output': fake_output})
        fake_geodeep.detect.assert_called_once_with(
            'C:\\fake\\orthophoto.tif',
            'cars',
            output_type='geojson',
            classes=None,
            max_threads=mock.ANY,
            progress_callback=None,
        )
        self.assertTrue(fake_geodeep.models.cache_dir.endswith('detection_models'))

    def test_detect_can_run_when_serialized_for_custom_models(self):
        fake_geodeep = ModuleType('geodeep')
        fake_output = {'type': 'FeatureCollection', 'features': []}
        fake_geodeep.detect = mock.Mock()
        fake_geodeep.models = SimpleNamespace(cache_dir=None)

        with mock.patch.dict(sys.modules, {'geodeep': fake_geodeep}):
            with mock.patch('coreplugins.objdetect.api._detect_with_custom_model', return_value=fake_output) as custom_detect:
                result = self._run_serialized(detect, 'C:\\fake\\orthophoto.tif', DOG_MODEL_URL, ['dog'])

        self.assertEqual(result, {'output': fake_output})
        custom_detect.assert_called_once_with(
            'C:\\fake\\orthophoto.tif',
            DOG_MODEL_URL,
            classes=['dog'],
            max_threads=mock.ANY,
            progress_callback=None,
            size_filter_meters=DOG_SIZE_FILTER_METERS,
        )
        fake_geodeep.detect.assert_not_called()
        self.assertTrue(fake_geodeep.models.cache_dir.endswith('detection_models'))

    def test_deer_detection_uses_custom_model_path_and_size_filter(self):
        fake_geodeep = ModuleType('geodeep')
        fake_output = {'type': 'FeatureCollection', 'features': []}
        fake_geodeep.detect = mock.Mock()
        fake_geodeep.models = SimpleNamespace(cache_dir=None)

        with mock.patch.dict(sys.modules, {'geodeep': fake_geodeep}):
            with mock.patch('coreplugins.objdetect.api._detect_with_custom_model', return_value=fake_output) as custom_detect:
                result = self._run_serialized(detect, 'C:\\fake\\orthophoto.tif', DEER_MODEL_URL, ['deer'])

        self.assertEqual(result, {'output': fake_output})
        custom_detect.assert_called_once_with(
            'C:\\fake\\orthophoto.tif',
            DEER_MODEL_URL,
            classes=['deer'],
            max_threads=mock.ANY,
            progress_callback=None,
            size_filter_meters=DEER_SIZE_FILTER_METERS,
        )
        fake_geodeep.detect.assert_not_called()
        self.assertTrue(fake_geodeep.models.cache_dir.endswith('detection_models'))

    def test_dog_size_filter_uses_gsd_to_reject_bad_scales(self):
        # At 2cm/px, the 0.5m-1.2m dog filter keeps long sides between 25px and 60px.
        outputs = np.array([
            [0, 0, 20, 20, 0.90, 0],   # too small
            [0, 0, 30, 12, 0.80, 0],   # expected dog scale
            [0, 0, 80, 30, 0.70, 0],   # too large
        ], dtype=float)

        filtered = _filter_outputs_by_long_side_meters(outputs, 2, DOG_SIZE_FILTER_METERS)

        self.assertEqual(filtered.shape[0], 1)
        self.assertEqual(filtered[0, 4], 0.80)

    def test_deer_size_filter_uses_gsd_to_reject_bad_scales(self):
        # At 5cm/px, the 0.8m-2.4m deer filter keeps long sides between 16px and 48px.
        outputs = np.array([
            [0, 0, 12, 12, 0.90, 0],   # too small
            [0, 0, 34, 16, 0.80, 0],   # expected deer scale
            [0, 0, 60, 30, 0.70, 0],   # too large
        ], dtype=float)

        filtered = _filter_outputs_by_long_side_meters(outputs, 5, DEER_SIZE_FILTER_METERS)

        self.assertEqual(filtered.shape[0], 1)
        self.assertEqual(filtered[0, 4], 0.80)

    def test_class_specific_size_filters_are_resolved(self):
        self.assertEqual(size_filter_for_classes(['dog']), DOG_SIZE_FILTER_METERS)
        self.assertEqual(size_filter_for_classes(['deer']), DEER_SIZE_FILTER_METERS)
        self.assertIsNone(size_filter_for_classes(['cow']))
        self.assertIsNone(size_filter_for_classes(None))

    def test_deer_is_a_supported_detection_model(self):
        self.assertEqual(OBJECT_DETECTION_MODEL_MAP['deer'], (DEER_MODEL_URL, ['deer']))

    def test_custom_model_opset_is_converted_once(self):
        model_proto = SimpleNamespace(opset_import=[SimpleNamespace(domain='', version=22)])
        converted_proto = object()
        fake_onnx = ModuleType('onnx')
        fake_onnx.load = mock.Mock(return_value=model_proto)
        fake_onnx.save = mock.Mock()
        fake_version_converter = ModuleType('onnx.version_converter')
        fake_version_converter.convert_version = mock.Mock(return_value=converted_proto)
        fake_onnx.version_converter = fake_version_converter

        def fake_isfile(path):
            return path == '/tmp/model.onnx'

        with mock.patch.dict(sys.modules, {'onnx': fake_onnx, 'onnx.version_converter': fake_version_converter}):
            with mock.patch('coreplugins.objdetect.api.os.path.isfile', side_effect=fake_isfile):
                converted = _ensure_supported_onnx_opset('/tmp/model.onnx')

        self.assertEqual(converted, f'/tmp/model-opset{MAX_ONNX_OPSET}.onnx')
        fake_version_converter.convert_version.assert_called_once_with(model_proto, MAX_ONNX_OPSET)
        fake_onnx.save.assert_called_once_with(converted_proto, f'/tmp/model-opset{MAX_ONNX_OPSET}.onnx')

    def test_existing_converted_model_is_reused(self):
        model_proto = SimpleNamespace(opset_import=[SimpleNamespace(domain='', version=22)])
        fake_onnx = ModuleType('onnx')
        fake_onnx.load = mock.Mock(return_value=model_proto)
        fake_onnx.save = mock.Mock()
        fake_version_converter = ModuleType('onnx.version_converter')
        fake_version_converter.convert_version = mock.Mock()
        fake_onnx.version_converter = fake_version_converter

        with mock.patch.dict(sys.modules, {'onnx': fake_onnx, 'onnx.version_converter': fake_version_converter}):
            with mock.patch('coreplugins.objdetect.api.os.path.isfile', return_value=True):
                converted = _ensure_supported_onnx_opset('/tmp/model.onnx')

        self.assertEqual(converted, f'/tmp/model-opset{MAX_ONNX_OPSET}.onnx')
        fake_version_converter.convert_version.assert_not_called()
        fake_onnx.save.assert_not_called()
