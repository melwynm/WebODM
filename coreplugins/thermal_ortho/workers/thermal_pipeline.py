import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.plugins.worker import run_function_async
from worker.results import get_async_result

logger = logging.getLogger('app.logger')
STATUS_FILE = 'thermal_ortho_status.json'
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.tif', '.tiff', '.rjpeg'}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _status_path(task):
    return task.data_path(STATUS_FILE)


def read_pipeline_status(task):
    status_path = _status_path(task)
    if not os.path.isfile(status_path):
        return {}

    try:
        with open(status_path, 'r', encoding='utf-8') as status_file:
            return json.load(status_file)
    except (OSError, json.JSONDecodeError):
        return {}


def write_pipeline_status(task, payload):
    status = read_pipeline_status(task)
    status.update(payload)
    status['updated_at'] = _now_iso()

    os.makedirs(os.path.dirname(_status_path(task)), exist_ok=True)
    with open(_status_path(task), 'w', encoding='utf-8') as status_file:
        json.dump(status, status_file, indent=2)

    return status


def _iter_task_images(task_root):
    root = Path(task_root)
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if any(part in ('assets', 'data') for part in path.parts):
            continue
        if path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            yield str(path)


def _detect_from_filename(path):
    name = os.path.basename(path).upper()
    return any(token in name for token in ('_T.', '_T_', 'THERMAL', 'RJPEG', 'R.JPEG', '_IR'))


def _detect_from_metadata(path):
    try:
        from coreplugins.thermal_ortho.workers.radiometric import read_exif_metadata
    except Exception:
        return False

    try:
        metadata = read_exif_metadata(path, tags=['Make', 'Model', 'PlanckR1', 'PlanckB', 'RawThermalImageType'])
    except Exception:
        return False

    values = ' '.join(str(metadata.get(key, '')) for key in metadata.keys()).upper()
    return any(token in values for token in ('PLANCK', 'THERMAL', 'FLIR', 'M3T', 'H20T'))


def detect_thermal_images(task_root):
    rgb_paths = []
    thermal_paths = []

    for path in _iter_task_images(task_root):
        is_thermal = _detect_from_filename(path)
        if not is_thermal:
            is_thermal = _detect_from_metadata(path)

        if is_thermal:
            thermal_paths.append(path)
        else:
            rgb_paths.append(path)

    return rgb_paths, thermal_paths


def detect_input_summary(task_root):
    rgb_paths, thermal_paths = detect_thermal_images(task_root)
    return {
        'rgb_images': len(rgb_paths),
        'thermal_images': len(thermal_paths),
        'rgb_paths': rgb_paths,
        'thermal_paths': thermal_paths,
    }


def enqueue_thermal_pipeline(task, camera_type='auto', trigger='manual', summary=None):
    summary = summary or detect_input_summary(task.task_path())
    current = read_pipeline_status(task)
    if current.get('state') in ('queued', 'running') and current.get('celery_task_id'):
        return SimpleNamespace(task_id=current['celery_task_id'])

    celery_result = run_function_async(run_thermal_pipeline, task.id, camera_type=camera_type, with_progress=True)
    write_pipeline_status(task, {
        'state': 'queued',
        'progress': 0,
        'message': 'Queued thermal processing.',
        'celery_task_id': celery_result.task_id,
        'trigger': trigger,
        'rgb_images': summary['rgb_images'],
        'thermal_images': summary['thermal_images'],
    })
    return celery_result


def _download_url(task, asset_name):
    return f'/api/projects/{task.project.id}/tasks/{task.id}/download/{asset_name}'


def _asset_url(task, asset_path):
    return f'/api/projects/{task.project.id}/tasks/{task.id}/assets/{asset_path}'


def _query_worker_status(celery_task_id):
    if not celery_task_id:
        return None
    result = get_async_result(celery_task_id)
    if result.ready():
        return {'ready': True, 'result': result.get() or {}, 'state': getattr(result, 'state', 'SUCCESS')}
    return {'ready': False, 'info': getattr(result, 'info', None), 'state': getattr(result, 'state', 'PENDING')}


def build_status_payload(task):
    stored = read_pipeline_status(task)
    output_path = task.assets_path('thermal_orthophoto', 'thermal_orthophoto.tif')
    preview_path = task.assets_path('thermal_orthophoto', 'thermal_preview.png')
    output_available = os.path.isfile(output_path)
    preview_available = os.path.isfile(preview_path)

    worker_status = _query_worker_status(stored.get('celery_task_id'))
    if worker_status and not worker_status['ready']:
        info = worker_status.get('info') or {}
        stored['state'] = 'running' if worker_status['state'] == 'PROGRESS' else 'queued'
        stored['progress'] = int(info.get('progress', stored.get('progress', 0)) or 0)
        stored['message'] = info.get('status') or info.get('message') or stored.get('message', '')
    elif worker_status and worker_status['ready']:
        result = worker_status.get('result') or {}
        if isinstance(result.get('output'), dict):
            stored.update(result['output'])
        if result.get('error'):
            stored['state'] = 'failed'
            stored['error'] = result['error']
            stored['message'] = result['error']

    if stored.get('rgb_images') is None or stored.get('thermal_images') is None:
        summary = detect_input_summary(task.task_path())
        stored.setdefault('rgb_images', summary['rgb_images'])
        stored.setdefault('thermal_images', summary['thermal_images'])

    supported = output_available or stored.get('thermal_images', 0) > 0
    can_process = task.status == 40 and stored.get('thermal_images', 0) > 0 and stored.get('rgb_images', 0) > 0

    if output_available and stored.get('state') not in ('queued', 'running', 'failed'):
        stored['state'] = 'completed'
        stored.setdefault('message', 'Thermal orthophoto ready.')
        stored.setdefault('progress', 100)
    elif supported and task.status != 40 and stored.get('state') not in ('queued', 'running', 'failed'):
        stored['state'] = 'waiting_for_odm'
        stored['message'] = 'Thermal imagery detected. Generation will start after ODM finishes.'
    elif supported and task.status == 40 and stored.get('state') not in ('queued', 'running', 'completed', 'failed'):
        stored['state'] = 'idle'
        stored['message'] = 'Thermal imagery detected. Generate the thermal orthophoto when ready.'
    elif not supported:
        stored['state'] = stored.get('state', 'unavailable')
        stored.setdefault('message', 'No thermal imagery detected for this task.')

    payload = {
        'supported': supported,
        'can_process': can_process,
        'state': stored.get('state', 'unavailable'),
        'message': stored.get('message', ''),
        'progress': int(stored.get('progress', 0) or 0),
        'error': stored.get('error'),
        'celery_task_id': stored.get('celery_task_id'),
        'rgb_images': int(stored.get('rgb_images', 0) or 0),
        'thermal_images': int(stored.get('thermal_images', 0) or 0),
        'matched_pairs': int(stored.get('matched_pairs', 0) or 0),
        'output_available': output_available,
        'task_completed': task.status == 40,
        'updated_at': stored.get('updated_at'),
        'stats': stored.get('stats'),
        'trigger': stored.get('trigger'),
    }

    if output_available:
        payload['output_url'] = _download_url(task, 'thermal_orthophoto.tif')
        payload['map_url'] = f'/map/project/{task.project.id}/task/{task.id}/?t=plant'
    if preview_available:
        payload['preview_url'] = _asset_url(task, 'thermal_orthophoto/thermal_preview.png')

    return payload


def _float_value(value, default=None):
    if value in (None, ''):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(str(value).split(' ')[0])
        except (TypeError, ValueError):
            return default


def _read_image_metadata(path, tags):
    from coreplugins.thermal_ortho.workers.radiometric import read_exif_metadata

    try:
        return read_exif_metadata(path, tags=tags)
    except Exception:
        return {}


def _estimate_image_bounds(rgb_path, image_shape):
    metadata = _read_image_metadata(
        rgb_path,
        ['GPSLatitude', 'GPSLongitude', 'RelativeAltitude', 'GPSAltitude', 'FOV', 'ImageWidth', 'ImageHeight'],
    )
    latitude = _float_value(metadata.get('GPSLatitude'))
    longitude = _float_value(metadata.get('GPSLongitude'))
    if latitude is None or longitude is None:
        raise ValueError(f'Missing GPS data for {rgb_path}')

    altitude = _float_value(metadata.get('RelativeAltitude'), _float_value(metadata.get('GPSAltitude'), 50.0))
    fov = _float_value(metadata.get('FOV'), 84.0)
    width = _float_value(metadata.get('ImageWidth'), image_shape[1])
    height = _float_value(metadata.get('ImageHeight'), image_shape[0])
    aspect = max(width / max(height, 1.0), 1e-3)

    half_width = altitude * math.tan(math.radians(fov / 2.0))
    vertical_fov = math.degrees(2.0 * math.atan(math.tan(math.radians(fov / 2.0)) / aspect))
    half_height = altitude * math.tan(math.radians(vertical_fov / 2.0))

    deg_per_meter_lat = 1.0 / 111320.0
    deg_per_meter_lon = 1.0 / (111320.0 * max(math.cos(math.radians(latitude)), 1e-6))

    return {
        'left': longitude - (half_width * deg_per_meter_lon),
        'right': longitude + (half_width * deg_per_meter_lon),
        'bottom': latitude - (half_height * deg_per_meter_lat),
        'top': latitude + (half_height * deg_per_meter_lat),
    }


def _estimate_nadir_weight(rgb_path):
    metadata = _read_image_metadata(rgb_path, ['GimbalPitchDegree', 'CameraElevationAngle'])
    pitch = _float_value(metadata.get('GimbalPitchDegree'), _float_value(metadata.get('CameraElevationAngle'), -90.0))
    off_nadir = abs(pitch + 90.0)
    return max(0.1, math.cos(math.radians(min(off_nadir, 89.0))))


def _update_progress(task, progress_callback, progress, message, extra=None):
    payload = {
        'state': 'running',
        'progress': int(progress),
        'message': message,
    }
    if extra:
        payload.update(extra)
    write_pipeline_status(task, payload)
    if callable(progress_callback):
        progress_callback(message, int(progress))


def run_thermal_pipeline(task_id, camera_type='auto', progress_callback=None):
    from app.cogeo import assure_cogeo
    from app.models import Task
    from coreplugins.thermal_ortho.workers.coregistration import coregister_thermal_to_rgb, match_rgb_thermal_pairs
    from coreplugins.thermal_ortho.workers.radiometric import decode_radiometric
    from coreplugins.thermal_ortho.workers.thermal_texturing import blend_thermal_orthomosaic

    task = Task.objects.get(pk=task_id)
    summary = detect_input_summary(task.task_path())
    write_pipeline_status(task, {
        'state': 'running',
        'progress': 0,
        'message': 'Scanning task imagery.',
        'rgb_images': summary['rgb_images'],
        'thermal_images': summary['thermal_images'],
    })

    try:
        if summary['thermal_images'] == 0:
            payload = {
                'state': 'skipped',
                'progress': 100,
                'message': 'No thermal images were detected.',
                'rgb_images': 0,
                'thermal_images': 0,
            }
            write_pipeline_status(task, payload)
            return {'output': payload, 'status': 'skipped'}

        if summary['rgb_images'] == 0:
            raise RuntimeError('Thermal images were found, but no RGB images are available for geometry.')

        reference_orthophoto = task.get_asset_download_path('orthophoto.tif')
        if not os.path.isfile(reference_orthophoto):
            raise RuntimeError('ODM orthophoto not found. Process the task normally first.')

        _update_progress(task, progress_callback, 10, 'Matching RGB and thermal images.')
        pairs = match_rgb_thermal_pairs(summary['rgb_paths'], summary['thermal_paths'])
        if not pairs:
            raise RuntimeError('Could not match thermal images to RGB captures.')

        aligned_thermals = []
        total_pairs = len(pairs)
        for index, (rgb_path, thermal_path) in enumerate(pairs, start=1):
            progress = 10 + int((index - 1) * 55 / max(total_pairs, 1))
            _update_progress(
                task,
                progress_callback,
                progress,
                f'Processing pair {index}/{total_pairs}: {os.path.basename(thermal_path)}',
                extra={'matched_pairs': total_pairs},
            )

            celsius, _profile = decode_radiometric(thermal_path, camera_type=camera_type)
            aligned = coregister_thermal_to_rgb(rgb_path, celsius)
            bounds = _estimate_image_bounds(rgb_path, aligned.shape)
            weight = _estimate_nadir_weight(rgb_path)
            aligned_thermals.append({
                'array': aligned,
                'bounds': bounds,
                'crs': 'EPSG:4326',
                'weight': weight,
            })

        if not aligned_thermals:
            raise RuntimeError('No thermal/RGB pairs could be aligned successfully.')

        _update_progress(task, progress_callback, 75, 'Blending thermal orthophoto.', extra={'matched_pairs': len(aligned_thermals)})
        output_path = task.assets_path('thermal_orthophoto', 'thermal_orthophoto.tif')
        result = blend_thermal_orthomosaic(aligned_thermals, reference_orthophoto, output_path)
        assure_cogeo(result['output_path'])

        task.update_available_assets_field(commit=False)
        task.update_size(commit=False)
        task.save(update_fields=['available_assets', 'size'])

        payload = {
            'state': 'completed',
            'progress': 100,
            'message': 'Thermal orthophoto ready.',
            'rgb_images': summary['rgb_images'],
            'thermal_images': summary['thermal_images'],
            'matched_pairs': len(aligned_thermals),
            'stats': result['stats'],
        }
        write_pipeline_status(task, payload)
        payload.update({
            'output_available': True,
            'output_url': _download_url(task, 'thermal_orthophoto.tif'),
            'preview_url': _asset_url(task, 'thermal_orthophoto/thermal_preview.png'),
            'map_url': f'/map/project/{task.project.id}/task/{task.id}/?t=plant',
        })
        return {'output': payload, 'status': 'completed'}
    except Exception as exc:
        logger.exception('Thermal orthophoto generation failed for task %s', task_id)
        payload = {
            'state': 'failed',
            'progress': 100,
            'message': str(exc),
            'error': str(exc),
            'rgb_images': summary['rgb_images'],
            'thermal_images': summary['thermal_images'],
        }
        write_pipeline_status(task, payload)
        return {'error': str(exc), 'output': payload, 'status': 'failed'}
