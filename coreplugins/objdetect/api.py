import os
import json
import ast
from rest_framework import status
from rest_framework.response import Response
from app.plugins.views import TaskView, GetTaskResult, TaskResultOutputError
from app.plugins.worker import run_function_async
from django.utils.translation import gettext_lazy as _

DOG_MODEL_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx"
MAX_ONNX_OPSET = 21


def _parse_class_names(raw_names):
    if not raw_names:
        return {}

    parsed = None
    try:
        parsed = json.loads(raw_names)
    except Exception:
        try:
            parsed = ast.literal_eval(raw_names)
        except Exception:
            return {}

    if isinstance(parsed, list):
        return {str(i): str(v) for i, v in enumerate(parsed)}

    if isinstance(parsed, dict):
        class_names = {}
        for key, value in parsed.items():
            try:
                key = str(int(key))
            except Exception:
                key = str(key)
            class_names[key] = str(value)
        return class_names

    return {}


def _ensure_supported_onnx_opset(model_file, progress_callback=None):
    try:
        import onnx
        from onnx import version_converter
    except ImportError:
        return model_file

    model_proto = onnx.load(model_file)
    opset_versions = [entry.version for entry in model_proto.opset_import if entry.domain in ('', 'ai.onnx')]
    if not opset_versions:
        return model_file

    current_opset = max(opset_versions)
    if current_opset <= MAX_ONNX_OPSET:
        return model_file

    converted_file = f"{os.path.splitext(model_file)[0]}-opset{MAX_ONNX_OPSET}.onnx"
    if os.path.isfile(converted_file):
        return converted_file

    if progress_callback is not None:
        progress_callback(f"Converting ONNX model from opset {current_opset} to {MAX_ONNX_OPSET}", 0)

    try:
        converted_proto = version_converter.convert_version(model_proto, MAX_ONNX_OPSET)
    except Exception as e:
        raise Exception(f"Cannot convert ONNX model from opset {current_opset} to {MAX_ONNX_OPSET}: {e}")

    onnx.save(converted_proto, converted_file)
    return converted_file


def _detect_with_custom_model(orthophoto, model, classes=None, max_threads=None, progress_callback=None):
    import logging
    import numpy as np
    import rasterio
    from geodeep.models import get_model_file
    from geodeep.inference import create_session
    from geodeep.slidingwindow import generate_for_size
    from geodeep.detection import execute, non_max_suppression_fast, non_max_kdtree, sort_by_area, to_geojson
    from geodeep.utils import estimate_raster_resolution, cls_names_map

    logger = logging.getLogger("objdetect")
    current_progress = 0

    def p(text, perc=0):
        nonlocal current_progress
        current_progress += perc
        if progress_callback is not None:
            progress_callback(text, current_progress)

    p("Loading model")
    model_file = model if os.path.isfile(model) else get_model_file(model, progress_callback)
    model_file = _ensure_supported_onnx_opset(model_file, progress_callback)
    session, config = create_session(model_file, max_threads=max_threads)
    p("Model loaded", 5)

    meta = session.get_modelmeta().custom_metadata_map
    if not config.get('class_names'):
        class_names = _parse_class_names(meta.get('class_names') or meta.get('names'))
        if class_names:
            config['class_names'] = class_names

    # Some exported models use symbolic input shape names (for example width/height).
    # In that case we fallback to metadata or a safe default.
    if not isinstance(config.get('tiles_size'), int):
        parsed_imgsz = None
        imgsz = meta.get('imgsz')
        if imgsz:
            try:
                parsed_imgsz = json.loads(imgsz)
            except Exception:
                try:
                    parsed_imgsz = ast.literal_eval(imgsz)
                except Exception:
                    parsed_imgsz = None

        if isinstance(parsed_imgsz, list) and len(parsed_imgsz) > 0:
            config['tiles_size'] = int(max(parsed_imgsz))
        elif isinstance(parsed_imgsz, (int, float)):
            config['tiles_size'] = int(parsed_imgsz)
        else:
            config['tiles_size'] = 640

    # Generic YOLO exports (for example YOLOv8/11) usually expose [1, channels, boxes] output.
    # GeoDeep defaults to YOLOv5/v7 parsing unless explicit metadata is present.
    if config.get('det_type') == 'YOLO_v5_or_v7_default':
        out_shape = session.get_outputs()[0].shape
        if len(out_shape) == 3 and isinstance(out_shape[1], int) and (not isinstance(out_shape[2], int) or out_shape[1] < out_shape[2]):
            config['det_type'] = 'YOLO_v8'

    if classes is not None:
        cn_map = cls_names_map(config.get('class_names', {}))
        if cn_map:
            config['det_classes'] = [cn_map[cls_name] for cls_name in cn_map if cls_name in classes]
        else:
            raise Exception("Cannot filter classes: model does not provide class names metadata")

    with rasterio.open(orthophoto, 'r') as raster:
        if not raster.is_tiled:
            logger.warning("%s is not tiled. I/O performance will be affected.", orthophoto)

        # cm/px
        input_res = round(max(abs(raster.transform[0]), abs(raster.transform[4])), 4) * 100
        if input_res <= 0:
            input_res = estimate_raster_resolution(raster)

        model_res = config['resolution']
        scale_factor = 1
        if input_res < model_res:
            scale_factor = int(model_res // input_res)

        height = raster.shape[0]
        width = raster.shape[1]
        windows = generate_for_size(width, height, config['tiles_size'] * scale_factor, config['tiles_overlap'] / 100.0, clip=False)
        outputs = []

        indexes = raster.indexes
        if len(indexes) > 1 and raster.colorinterp[-1] == rasterio.enums.ColorInterp.alpha:
            indexes = indexes[:-1]

        num_wins = len(windows)
        progress_per_win = 90 / num_wins if num_wins > 0 else 0

        for idx, w in enumerate(windows):
            p(f"Processing tile {idx}/{num_wins}", progress_per_win)
            img = raster.read(indexes=indexes, window=w, boundless=True, fill_value=0, out_shape=(
                len(indexes),
                config['tiles_size'],
                config['tiles_size'],
            ), resampling=rasterio.enums.Resampling.bilinear)

            res = execute(img, session, config)
            if len(res):
                res[:, 0:4] = res[:, 0:4] * scale_factor + np.array([w.col_off, w.row_off, w.col_off, w.row_off])
                outputs.append(res)

        p("Finalizing", 5)
        if len(outputs):
            outputs = np.vstack(outputs)
            outputs = non_max_suppression_fast(outputs, config)
            outputs = sort_by_area(outputs, reverse=True)
            outputs = non_max_kdtree(outputs, config['det_iou_thresh'])
        else:
            outputs = np.array([])

        return to_geojson(raster, outputs, config)


def detect(orthophoto, model, classes=None, crop=None, progress_callback=None):
    # This function is serialized and executed by app.plugins.worker.eval_async,
    # so it must import its dependencies inside the function body.
    import os
    import subprocess
    import shutil
    import tempfile
    from coreplugins.objdetect.api import _detect_with_custom_model
    from webodm import settings
    from django.contrib.gis.geos import GEOSGeometry

    try:
        from geodeep import detect as gdetect, models
        models.cache_dir = os.path.join(settings.MEDIA_CACHE, "detection_models")
    except ImportError:
        return {'error': "GeoDeep library is missing"}

    try:
        if crop is not None:
            # Make a VRT with the crop area
            gdalwarp_bin = shutil.which("gdalwarp")
            if gdalwarp_bin is None:
                return {'error': 'Cannot find gdalwarp'}

            tmpdir = os.path.join(settings.MEDIA_TMP, os.path.basename(tempfile.mkdtemp('_objdetect', dir=settings.MEDIA_TMP)))

            crop_geojson = os.path.join(tmpdir, "crop.geojson")
            ortho_vrt = os.path.join(tmpdir, "orthophoto.vrt")
            with open(crop_geojson, "w", encoding="utf-8") as f:
                f.write(GEOSGeometry(crop).geojson)
            p = subprocess.Popen([gdalwarp_bin, "-cutline", crop_geojson,
                                  '--config', 'GDALWARP_DENSIFY_CUTLINE', 'NO',
                                  '-crop_to_cutline', '-of', 'VRT',
                                  orthophoto, ortho_vrt], cwd=tmpdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = p.communicate()
            out = out.decode('utf-8').strip()
            err = err.decode('utf-8').strip()
            if p.returncode != 0:
                return {'error': f'Error calling gdalwarp: {str(err)}'}

            orthophoto = ortho_vrt

        if model.startswith("http://") or model.startswith("https://"):
            output = _detect_with_custom_model(
                orthophoto,
                model,
                classes=classes,
                max_threads=settings.WORKERS_MAX_THREADS,
                progress_callback=progress_callback,
            )
        else:
            output = gdetect(
                orthophoto,
                model,
                output_type='geojson',
                classes=classes,
                max_threads=settings.WORKERS_MAX_THREADS,
                progress_callback=progress_callback,
            )

        return {'output': output}
    except Exception as e:
        return {'error': str(e)}


class TaskObjDetect(TaskView):
    def post(self, request, pk=None):
        task = self.get_and_check_task(request, pk)

        if task.orthophoto_extent is None:
            return Response({'error': _('No orthophoto is available.')})

        orthophoto = os.path.abspath(task.get_asset_download_path("orthophoto.tif"))
        model = request.data.get('model', 'cars')

        # model --> (modelID, classes)
        model_map = {
            'cars': ('cars', None),
            'trees': ('trees', None),
            'athletic': ('aerovision', ['tennis-court', 'track-field', 'soccer-field', 'baseball-field', 'swimming-pool', 'basketball-court']),
            'boats': ('aerovision', ['boat']),
            'planes': ('aerovision', ['plane']),
            'cattle': ('aerovision', ['cow']),
            'dogs': (DOG_MODEL_URL, ['dog']),
        }

        if model not in model_map:
            return Response({'error': 'Invalid model'}, status=status.HTTP_200_OK)

        model_id, classes = model_map[model]
        celery_task_id = run_function_async(detect, orthophoto, model_id, classes, task.crop.wkt if task.crop is not None else None, with_progress=True).task_id

        return Response({'celery_task_id': celery_task_id}, status=status.HTTP_200_OK)


class TaskObjDownload(GetTaskResult):
    def handle_output(self, output, result, **kwargs):
        try:
            return json.loads(output)
        except Exception:
            raise TaskResultOutputError("Invalid GeoJSON")
