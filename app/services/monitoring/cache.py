import json
import logging
import os
import shutil

from webodm import settings

from .common import MONITORING_CACHE_VERSION

logger = logging.getLogger("app.logger")

def monitoring_cache_dir(reference_task_id, compare_task_id):
    return os.path.join(
        settings.MEDIA_CACHE,
        "monitoring",
        str(reference_task_id),
        str(compare_task_id),
    )

def clear_monitoring_cache_for_task(task_id):
    monitoring_root = os.path.join(settings.MEDIA_CACHE, "monitoring")
    task_id = str(task_id)

    if not os.path.isdir(monitoring_root):
        return

    direct_reference_path = os.path.join(monitoring_root, task_id)
    if os.path.isdir(direct_reference_path):
        shutil.rmtree(direct_reference_path, ignore_errors=True)

    for reference_id in os.listdir(monitoring_root):
        reference_path = os.path.join(monitoring_root, reference_id)
        if not os.path.isdir(reference_path):
            continue

        compare_path = os.path.join(reference_path, task_id)
        if os.path.isdir(compare_path):
            shutil.rmtree(compare_path, ignore_errors=True)

        try:
            if reference_id != task_id and not os.listdir(reference_path):
                os.rmdir(reference_path)
        except OSError:
            continue

def monitoring_task_input(task):
    assets = {}
    for asset_name in ("orthophoto.tif", "dsm.tif", "dtm.tif"):
        asset_path = task.get_asset_download_path(asset_name)
        asset_mtime = None
        if os.path.isfile(asset_path):
            asset_mtime = round(float(os.path.getmtime(asset_path)), 6)
        assets[asset_name] = asset_mtime

    return {
        "task_id": str(task.id),
        "task_name": task.name,
        "task_created_at": task.created_at.isoformat() if task.created_at else None,
        "asset_mtime": assets["orthophoto.tif"],
        "assets": assets,
    }

def monitoring_inputs(reference_task, compare_task):
    return {
        "reference": monitoring_task_input(reference_task),
        "compare": monitoring_task_input(compare_task),
    }

def _load_cached_metadata(cache_dir, metadata_path, reference_task=None, compare_task=None):
    if not os.path.isfile(metadata_path):
        return None

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        if metadata.get("version") != MONITORING_CACHE_VERSION:
            return None

        aligned_path = os.path.join(cache_dir, metadata["aligned_overlay"]["path"])
        change_path = os.path.join(cache_dir, metadata["change_overlay"]["path"])
        if not os.path.isfile(aligned_path) or not os.path.isfile(change_path):
            return None

        for terrain in (metadata.get("terrain_deltas") or {}).values():
            terrain_path = os.path.join(cache_dir, terrain["path"])
            if not os.path.isfile(terrain_path):
                return None

        if reference_task is not None and compare_task is not None:
            if metadata.get("inputs") != monitoring_inputs(reference_task, compare_task):
                return None

        return metadata
    except Exception as e:
        logger.warning("Cannot load monitoring cache %s: %s", metadata_path, e)
        return None

def _with_paths(cache_dir, metadata):
    payload = json.loads(json.dumps(metadata))
    payload["aligned_overlay"]["absolute_path"] = os.path.join(cache_dir, payload["aligned_overlay"]["path"])
    payload["change_overlay"]["absolute_path"] = os.path.join(cache_dir, payload["change_overlay"]["path"])
    for terrain in (payload.get("terrain_deltas") or {}).values():
        terrain["absolute_path"] = os.path.join(cache_dir, terrain["path"])
    return payload
