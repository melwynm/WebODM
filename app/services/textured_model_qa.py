import os


MODEL_ASSETS = (
    'textured_model.glb',
    'textured_model.zip',
    'textured_model.fbx.zip',
    '3d_tiles_model.zip',
    'georeferenced_model.laz',
    'shots.geojson',
)


def _asset_status(task, asset):
    listed = asset in (task.available_assets or [])
    try:
        path = task.get_asset_download_path(asset)
    except Exception:
        path = None

    exists = bool(path and os.path.isfile(path))
    size = os.path.getsize(path) if exists else None
    return {
        'asset': asset,
        'listed': listed,
        'exists': exists,
        'size': size,
        'path': path if exists else '',
        'download_url': '/api/projects/{}/tasks/{}/download/{}'.format(task.project_id, task.id, asset),
    }


def build_textured_model_qa(task):
    assets = [_asset_status(task, asset) for asset in MODEL_ASSETS]
    asset_map = {asset['asset']: asset for asset in assets}
    has_glb = asset_map['textured_model.glb']['exists']
    has_zip = asset_map['textured_model.zip']['exists']
    has_point_cloud = asset_map['georeferenced_model.laz']['exists']
    warnings = []

    if not has_zip and not has_glb:
        warnings.append('No textured model asset was found. Reprocess with 3D mesh enabled.')
    if has_zip and not has_glb:
        warnings.append('Textured model ZIP exists, but GLB is missing. Browser loading may fall back to OBJ/MTL.')
    if not has_point_cloud:
        warnings.append('Point cloud asset is missing. The 3D viewer may not initialize fully.')
    if asset_map['textured_model.glb']['size'] and asset_map['textured_model.glb']['size'] > 150 * 1024 * 1024:
        warnings.append('GLB is larger than 150 MB. The safe textured model endpoint will downscale textures for browser viewing.')
    if 'use-3dmesh' not in {option.get('name') for option in (task.options or []) if isinstance(option, dict)}:
        warnings.append('Task options do not explicitly show use-3dmesh. Confirm the processing preset creates textured models.')

    status = 'ready' if (has_zip or has_glb) and has_point_cloud else 'needs_attention'
    if not has_zip and not has_glb and not has_point_cloud:
        status = 'missing'

    return {
        'task': str(task.id),
        'project': task.project_id,
        'task_name': task.name,
        'status': status,
        'available_assets': task.available_assets or [],
        'assets': assets,
        'warnings': warnings,
        'viewer_url': '/3d/project/{}/task/{}/'.format(task.project_id, task.id),
        'safe_glb_url': '/api/projects/{}/tasks/{}/textured_model/'.format(task.project_id, task.id),
    }
