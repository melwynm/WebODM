import json
import os
import shutil
from datetime import datetime

from .alignment import estimate_alignment
from .cache import _load_cached_metadata, _with_paths, monitoring_cache_dir, monitoring_inputs
from .common import MONITORING_CACHE_VERSION, MonitoringError, _progress
from .overlays import build_aligned_overlay, build_change_overlay, build_terrain_delta_overlay

def ensure_monitoring_products(reference_task, compare_task, progress_callback=None):
    cache_dir = monitoring_cache_dir(reference_task.id, compare_task.id)
    metadata_path = os.path.join(cache_dir, "metadata.json")
    current_inputs = monitoring_inputs(reference_task, compare_task)

    metadata = _load_cached_metadata(cache_dir, metadata_path, reference_task, compare_task)
    if metadata is not None:
        return _with_paths(cache_dir, metadata)

    if os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)
    os.makedirs(cache_dir, exist_ok=True)

    reference_path = reference_task.get_asset_download_path("orthophoto.tif")
    compare_path = compare_task.get_asset_download_path("orthophoto.tif")

    if not os.path.isfile(reference_path):
        raise MonitoringError("Reference task does not have an orthophoto")
    if not os.path.isfile(compare_path):
        raise MonitoringError("Comparison task does not have an orthophoto")

    _progress(progress_callback, "Estimating alignment", 0.15)
    alignment = estimate_alignment(reference_path, compare_path)

    aligned_path = os.path.join(cache_dir, "aligned_overlay.tif")
    change_path = os.path.join(cache_dir, "change_overlay.tif")

    _progress(progress_callback, "Generating aligned overlay", 0.45)
    aligned_info = build_aligned_overlay(reference_path, compare_path, alignment, aligned_path)

    _progress(progress_callback, "Generating change heatmap", 0.7)
    build_change_overlay(reference_path, aligned_path, alignment, change_path)

    terrain_deltas = {}
    for asset_name, label, progress in (
        ("dsm.tif", "DSM", 0.82),
        ("dtm.tif", "DTM", 0.92),
    ):
        reference_dem_path = reference_task.get_asset_download_path(asset_name)
        compare_dem_path = compare_task.get_asset_download_path(asset_name)
        if not os.path.isfile(reference_dem_path) or not os.path.isfile(compare_dem_path):
            continue

        _progress(progress_callback, f"Generating {label} delta", progress)
        layer_type = asset_name.split(".")[0]
        output_path = os.path.join(cache_dir, f"{layer_type}_delta.tif")
        terrain_deltas[layer_type] = build_terrain_delta_overlay(
            reference_dem_path,
            compare_dem_path,
            alignment,
            output_path,
        )
        terrain_deltas[layer_type]["path"] = os.path.basename(output_path)

    metadata = {
        "version": MONITORING_CACHE_VERSION,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "inputs": current_inputs,
        "alignment": alignment,
        "aligned_overlay": {
            "path": os.path.basename(aligned_path),
            "bounds": aligned_info["bounds"],
            "rescale": aligned_info["rescale"],
        },
        "change_overlay": {
            "path": os.path.basename(change_path),
            "bounds": aligned_info["bounds"],
        },
        "terrain_deltas": terrain_deltas,
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    _progress(progress_callback, "Monitoring comparison ready", 1.0)
    return _with_paths(cache_dir, metadata)
