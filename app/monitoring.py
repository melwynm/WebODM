"""Compatibility facade for monitoring services.

New monitoring code should live under app.services.monitoring. Keep imports
here stable while API views, worker tasks, and model hooks migrate over time.
"""

from app.services.monitoring import (
    MonitoringError,
    aligned_dataset_transform,
    build_aligned_overlay,
    build_change_overlay,
    build_terrain_delta_overlay,
    clear_monitoring_cache_for_task,
    ensure_monitoring_products,
    estimate_alignment,
    monitoring_cache_dir,
    monitoring_inputs,
    monitoring_layer_path,
    monitoring_task_input,
    monitoring_tile_url,
    render_layer_payload,
)

__all__ = (
    "MonitoringError",
    "aligned_dataset_transform",
    "build_aligned_overlay",
    "build_change_overlay",
    "build_terrain_delta_overlay",
    "clear_monitoring_cache_for_task",
    "ensure_monitoring_products",
    "estimate_alignment",
    "monitoring_cache_dir",
    "monitoring_inputs",
    "monitoring_layer_path",
    "monitoring_task_input",
    "monitoring_tile_url",
    "render_layer_payload",
)
