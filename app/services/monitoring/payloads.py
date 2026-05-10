import os

from .cache import monitoring_cache_dir
from .common import MonitoringError

def render_layer_payload(reference_task, compare_task, metadata):
    aligned = metadata["aligned_overlay"]
    change = metadata["change_overlay"]
    alignment = metadata["alignment"]
    terrain_deltas = metadata.get("terrain_deltas") or {}
    layers = {
        "aligned_overlay": {
            "name": f"Aligned: {compare_task.name or compare_task.id}",
            "icon": "fa fa-layer-group fa-fw",
            "bounds": aligned["bounds"],
            "rescale": aligned["rescale"],
            "url": monitoring_tile_url(reference_task, compare_task, "aligned"),
            "maxzoom": 24,
            "side_by_side": True,
            "opacity": 1.0,
        },
        "change_overlay": {
            "name": f"Change Heatmap: {compare_task.name or compare_task.id}",
            "icon": "fa fa-fire fa-fw",
            "bounds": change["bounds"],
            "url": monitoring_tile_url(reference_task, compare_task, "change"),
            "maxzoom": 24,
            "side_by_side": False,
            "opacity": 0.8,
        },
    }

    for terrain_type, label in (("dsm", "DSM Delta"), ("dtm", "DTM Delta")):
        terrain = terrain_deltas.get(terrain_type)
        if not terrain:
            continue
        layers[f"{terrain_type}_delta"] = {
            "name": f"{label}: {compare_task.name or compare_task.id}",
            "icon": "fa fa-mountain fa-fw",
            "bounds": terrain["bounds"],
            "url": monitoring_tile_url(reference_task, compare_task, f"{terrain_type}_delta"),
            "maxzoom": 24,
            "side_by_side": False,
            "opacity": 0.75,
            "stats": terrain["stats"],
        }

    return {
        "reference_task": {
            "id": str(reference_task.id),
            "project": reference_task.project.id,
            "name": reference_task.name,
            "created_at": reference_task.created_at.isoformat(),
        },
        "compare_task": {
            "id": str(compare_task.id),
            "project": compare_task.project.id,
            "name": compare_task.name,
            "created_at": compare_task.created_at.isoformat(),
        },
        "timeline": {
            "generated_at": metadata.get("generated_at"),
            "reference_task_id": str(reference_task.id),
            "compare_task_id": str(compare_task.id),
        },
        "alignment": alignment,
        "terrain": terrain_deltas,
        "layers": layers,
    }

def monitoring_tile_url(reference_task, compare_task, layer_type):
    return (
        f"/api/projects/{reference_task.project.id}/tasks/{reference_task.id}/"
        f"monitoring/{compare_task.id}/{layer_type}/tiles/{{z}}/{{x}}/{{y}}.png"
    )

def monitoring_layer_path(reference_task, compare_task, layer_type):
    cache_dir = monitoring_cache_dir(reference_task.id, compare_task.id)
    filename = {
        "aligned": "aligned_overlay.tif",
        "change": "change_overlay.tif",
        "dsm_delta": "dsm_delta.tif",
        "dtm_delta": "dtm_delta.tif",
    }.get(layer_type)
    if filename is None:
        raise MonitoringError("Invalid monitoring layer requested")

    path = os.path.join(cache_dir, filename)
    if not os.path.isfile(path):
        raise MonitoringError("Monitoring layer is not available yet")
    return path
