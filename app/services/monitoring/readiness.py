import os

from nodeodm import status_codes

from .cache import _load_cached_metadata, monitoring_cache_dir


ORTHOPHOTO_ASSET = "orthophoto.tif"
DSM_ASSET = "dsm.tif"
DTM_ASSET = "dtm.tif"


def task_has_asset(task, asset_name):
    return asset_name in (task.available_assets or []) and os.path.isfile(task.get_asset_download_path(asset_name))


def task_monitoring_readiness(task):
    has_orthophoto = task_has_asset(task, ORTHOPHOTO_ASSET)
    has_dsm = task_has_asset(task, DSM_ASSET)
    has_dtm = task_has_asset(task, DTM_ASSET)
    is_completed = task.status == status_codes.COMPLETED

    issues = []
    if not is_completed:
        issues.append("Task is not completed")
    if not has_orthophoto:
        issues.append("Task does not have an orthophoto")

    return {
        "is_completed": is_completed,
        "can_compare": is_completed and has_orthophoto,
        "assets": {
            "orthophoto": has_orthophoto,
            "dsm": has_dsm,
            "dtm": has_dtm,
        },
        "terrain_products": {
            "dsm_delta": has_dsm,
            "dtm_delta": has_dtm,
        },
        "issues": issues,
    }


def monitoring_pair_readiness(reference_task, compare_task):
    reference = task_monitoring_readiness(reference_task)
    compare = task_monitoring_readiness(compare_task)
    terrain_products = {
        "dsm_delta": reference["assets"]["dsm"] and compare["assets"]["dsm"],
        "dtm_delta": reference["assets"]["dtm"] and compare["assets"]["dtm"],
    }

    cache_dir = monitoring_cache_dir(reference_task.id, compare_task.id)
    metadata_path = os.path.join(cache_dir, "metadata.json")
    cached_metadata = _load_cached_metadata(cache_dir, metadata_path, reference_task, compare_task)

    issues = []
    if str(reference_task.id) == str(compare_task.id):
        issues.append("Please select a different task to compare")
    issues.extend(["Reference {}".format(issue.lower()) for issue in reference["issues"]])
    issues.extend(["Comparison {}".format(issue.lower()) for issue in compare["issues"]])

    return {
        "can_compare": not issues,
        "reference": reference,
        "compare": compare,
        "terrain_products": terrain_products,
        "cache": {
            "ready": cached_metadata is not None,
            "generated_at": cached_metadata.get("generated_at") if cached_metadata else None,
        },
        "issues": issues,
    }


def monitoring_task_summary(task, reference_task=None):
    data = {
        "id": str(task.id),
        "name": task.name,
        "created_at": task.created_at.isoformat(),
        "readiness": task_monitoring_readiness(task),
    }
    if reference_task is not None:
        data["pair_readiness"] = monitoring_pair_readiness(reference_task, task)
    return data
