"""
geometry_correction/tasks.py

Celery async tasks that drive the correction pipeline.
WebODM already runs Celery, so these tasks integrate naturally.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from celery import shared_task

from .models import CorrectionJob
from . import config

logger = logging.getLogger(__name__)


def _asset_base(project_id: int | str, task_id: str) -> Path:
    """Return the path to a WebODM task's asset directory."""
    webodm_data = os.environ.get("ODM_DATA_PATH", "/var/www/data")
    return Path(webodm_data) / str(project_id) / "task" / task_id / "assets"


@shared_task(bind=True, max_retries=0)
def run_geometry_correction(self, job_pk: int) -> dict:
    """
    Main Celery task.  Loads a CorrectionJob by PK, runs the full pipeline,
    and updates job status + results.
    """
    job = CorrectionJob.objects.get(pk=job_pk)
    job.status = CorrectionJob.Status.RUNNING
    job.celery_task_id = self.request.id
    job.save(update_fields=["status", "celery_task_id", "updated_at"])

    opts = job.options
    plane_threshold = float(opts.get("plane_threshold", config.PLANE_DISTANCE_THRESHOLD))
    snap_threshold = float(opts.get("snap_threshold", config.SNAP_DEVIATION_THRESHOLD))
    line_tolerance = float(opts.get("line_tolerance", config.LINE_ANGLE_TOLERANCE))
    correct_cloud = bool(opts.get("correct_pointcloud", True))
    correct_mesh = bool(opts.get("correct_mesh", True))
    correct_ortho = bool(opts.get("correct_orthophoto", True))

    base = _asset_base(job.project_id, job.task_id)
    results: dict = {}

    try:
        # ── Point Cloud ────────────────────────────────────────────────────
        if correct_cloud:
            pc_dir = base / "odm_pointcloud"
            # Try .laz first, fall back to .ply
            for fname in ("odm_filterpoint.laz", "odm_filterpoint.ply"):
                pc_in = pc_dir / fname
                if pc_in.exists():
                    suffix = pc_in.suffix
                    pc_out = pc_dir / f"odm_filterpoint_corrected{suffix}"
                    mesh_out = base / "odm_mesh" / "odm_mesh_corrected.ply"

                    from .algorithms.pointcloud import correct_pointcloud
                    stats = correct_pointcloud(
                        pc_in, pc_out,
                        output_mesh_path=mesh_out if correct_mesh else None,
                        plane_distance_threshold=plane_threshold,
                        snap_threshold=snap_threshold,
                    )
                    results["pointcloud"] = stats
                    break
            else:
                logger.warning("No point cloud found in %s", pc_dir)

        # ── Mesh (direct vertex correction without re-mesh) ────────────────
        if correct_mesh and "pointcloud" not in results:
            # Fallback: correct the OBJ mesh directly if no point cloud
            mesh_in = base / "odm_mesh" / "odm_mesh.obj"
            if mesh_in.exists():
                mesh_out = base / "odm_mesh" / "odm_mesh_corrected.obj"
                from .algorithms.mesh import correct_mesh as do_correct_mesh
                stats = do_correct_mesh(
                    mesh_in, mesh_out,
                    plane_distance_threshold=plane_threshold,
                    snap_threshold=snap_threshold,
                )
                results["mesh"] = stats

        # ── Orthomosaic ────────────────────────────────────────────────────
        if correct_ortho:
            ortho_in = base / "odm_orthophoto" / "odm_orthophoto.tif"
            if ortho_in.exists():
                ortho_out = base / "odm_orthophoto" / "odm_orthophoto_corrected.tif"
                from .algorithms.orthophoto import correct_orthophoto
                stats = correct_orthophoto(
                    ortho_in, ortho_out,
                    angle_tolerance=line_tolerance,
                )
                results["orthophoto"] = stats
            else:
                logger.warning("Orthophoto not found: %s", ortho_in)

        job.status = CorrectionJob.Status.COMPLETED
        job.result = results
        job.save(update_fields=["status", "result", "updated_at"])
        logger.info("CorrectionJob %d completed: %s", job_pk, results)

    except Exception as exc:
        logger.exception("CorrectionJob %d failed", job_pk)
        job.status = CorrectionJob.Status.FAILED
        job.error_message = str(exc)
        job.save(update_fields=["status", "error_message", "updated_at"])
        raise

    return results
