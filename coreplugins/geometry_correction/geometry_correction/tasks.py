"""
Async execution and status helpers for geometry_correction.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from app.models import Task
from app.plugins.worker import task
from nodeodm import status_codes
from webodm import settings
from worker.tasks import TestSafeAsyncResult

from . import config

logger = logging.getLogger("app.logger")

STATUS_FILE = "geometry_correction_status.json"
POINTCLOUD_CANDIDATES = (
    ("odm_georeferencing", "odm_georeferenced_model.laz"),
    ("odm_georeferencing", "odm_georeferenced_model.las"),
    ("odm_georeferencing", "odm_georeferenced_model.ply"),
)
MESH_CANDIDATES = (
    ("odm_texturing", "odm_textured_model_geo.obj"),
    ("odm_mesh", "odm_mesh.obj"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_path(task_obj: Task) -> Path:
    return Path(task_obj.data_path(STATUS_FILE))


def read_job_status(task_obj: Task) -> dict:
    path = _status_path(task_obj)
    if not path.is_file():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_job_status(task_obj: Task, payload: dict) -> dict:
    path = _status_path(task_obj)
    current = read_job_status(task_obj)
    current.update(payload)
    current.setdefault("created_at", _now_iso())
    current["updated_at"] = _now_iso()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
    return current


def _coerce_bool(value, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


def _output_base(task_obj: Task) -> Path:
    path = Path(task_obj.assets_path(config.OUTPUT_DIRNAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _existing_asset(task_obj: Task, *parts: str) -> Optional[Path]:
    candidate = Path(task_obj.assets_path(*parts))
    return candidate if candidate.exists() else None


def _first_existing_asset(task_obj: Task, candidates) -> Optional[Path]:
    for parts in candidates:
        candidate = _existing_asset(task_obj, *parts)
        if candidate is not None:
            return candidate
    return None


def _webhook_config_from_options(options: dict):
    from .algorithms.webhook import WebhookConfig

    url = str(options.get("webhook_url", "") or "").strip()
    if not url:
        return None

    return WebhookConfig(
        url=url,
        secret=str(options.get("webhook_secret", "") or ""),
        timeout_s=int(options.get("webhook_timeout_s", config.WEBHOOK_TIMEOUT_S) or config.WEBHOOK_TIMEOUT_S),
    )


def _notify_completion(task_obj: Task, options: dict, status: str, result: dict, error: Optional[str] = None) -> None:
    webhook_config = _webhook_config_from_options(options)
    if webhook_config is None:
        return

    try:
        from .algorithms.webhook import send_completion_webhook

        send_completion_webhook(
            config=webhook_config,
            job_id=str(task_obj.id),
            status=status,
            result=result,
            error=error,
        )
    except Exception:
        logger.exception("Geometry correction webhook dispatch failed for task %s", task_obj.id)


def _query_worker_status(celery_task_id: Optional[str]):
    if not celery_task_id:
        return None

    result = TestSafeAsyncResult(celery_task_id)
    if result.ready():
        return {
            "ready": True,
            "result": result.get() or {},
            "state": getattr(result, "state", "SUCCESS"),
        }

    return {
        "ready": False,
        "info": getattr(result, "info", None),
        "state": getattr(result, "state", "PENDING"),
    }


def build_status_payload(task_obj: Task) -> dict:
    stored = read_job_status(task_obj)
    worker_status = _query_worker_status(stored.get("celery_task_id"))

    if worker_status and not worker_status["ready"]:
        info = worker_status.get("info") or {}
        stored["status"] = "running" if worker_status["state"] == "PROGRESS" else stored.get("status", "pending")
        if "progress" in info:
            stored["progress"] = int(info.get("progress") or 0)
        if info.get("status"):
            stored["message"] = info["status"]
    elif worker_status and worker_status["ready"]:
        result = worker_status.get("result") or {}
        output = result.get("output")
        if isinstance(output, dict):
            stored.update(output)
        if result.get("error"):
            stored["status"] = "failed"
            stored["error_message"] = result["error"]

    payload = {
        "job_id": str(task_obj.id),
        "task_id": str(task_obj.id),
        "project_id": task_obj.project.id,
        "status": stored.get("status", "pending"),
        "progress": int(stored.get("progress", 0) or 0),
        "message": stored.get("message", ""),
        "result": stored.get("result", {}),
        "error_message": stored.get("error_message"),
        "created_at": stored.get("created_at"),
        "updated_at": stored.get("updated_at"),
        "celery_task_id": stored.get("celery_task_id"),
    }

    return payload


def enqueue_geometry_correction(task_obj: Task, options: Optional[dict] = None):
    options = options or {}
    current = build_status_payload(task_obj)

    if current.get("status") in ("pending", "running") and current.get("celery_task_id"):
        return SimpleNamespace(task_id=str(task_obj.id), celery_task_id=current["celery_task_id"])

    write_job_status(
        task_obj,
        {
            "status": "pending",
            "progress": 0,
            "message": "Queued geometry correction.",
            "result": {},
            "error_message": "",
            "options": options,
        },
    )

    async_result = run_geometry_correction.delay(str(task_obj.id), int(task_obj.project.id), options)
    write_job_status(task_obj, {"celery_task_id": async_result.id})
    return SimpleNamespace(task_id=str(task_obj.id), celery_task_id=async_result.id)


@task(bind=True, time_limit=settings.WORKERS_MAX_TIME_LIMIT)
def run_geometry_correction(self, task_id: str, project_id: int, options: Optional[dict] = None) -> dict:
    """
    Execute geometry correction for a WebODM task and persist task-local status.
    """
    from .algorithms.mesh import correct_mesh as correct_mesh_file
    from .algorithms.orthophoto import correct_orthophoto
    from .algorithms.pointcloud import correct_pointcloud

    task_obj = Task.objects.get(pk=task_id, project=project_id)
    opts = options if isinstance(options, dict) else {}

    plane_threshold = float(opts.get("plane_threshold", config.PLANE_DISTANCE_THRESHOLD))
    snap_threshold = float(
        opts.get(
            "snap_threshold",
            opts.get("correction_threshold", config.SNAP_DEVIATION_THRESHOLD),
        )
    )
    line_tolerance = float(
        opts.get(
            "line_tolerance",
            opts.get("line_angle_tolerance", config.LINE_ANGLE_TOLERANCE),
        )
    )
    correct_cloud = _coerce_bool(opts.get("correct_pointcloud", True), True)
    correct_mesh_output = _coerce_bool(opts.get("correct_mesh", True), True)
    correct_ortho = _coerce_bool(opts.get("correct_orthophoto", True), True)
    use_semantic_profiles = _coerce_bool(opts.get("use_semantic_profiles", config.USE_SEMANTIC_PROFILES), config.USE_SEMANTIC_PROFILES)
    generate_confidence_map_enabled = _coerce_bool(
        opts.get("generate_confidence_map", config.GENERATE_CONFIDENCE_MAP),
        config.GENERATE_CONFIDENCE_MAP,
    )
    profile_overrides = opts.get("profile_overrides") if isinstance(opts.get("profile_overrides"), dict) else None

    results: dict = {}

    def update_progress(message: str, progress: int) -> None:
        write_job_status(
            task_obj,
            {
                "status": "running",
                "progress": int(progress),
                "message": message,
                "result": results,
                "error_message": "",
            },
        )
        request = getattr(self, "request", None)
        if getattr(request, "id", None):
            self.update_state(state="PROGRESS", meta={"status": message, "progress": int(progress)})

    try:
        if task_obj.status != status_codes.COMPLETED:
            raise RuntimeError("Task must be completed before geometry correction can run.")

        output_dir = _output_base(task_obj)
        write_job_status(task_obj, {"status": "running", "progress": 0, "message": "Preparing geometry correction.", "result": {}})

        if correct_cloud:
            update_progress("Correcting point cloud geometry.", 15)
            pointcloud_input = _first_existing_asset(task_obj, POINTCLOUD_CANDIDATES)
            if pointcloud_input is not None:
                pointcloud_output = output_dir / ("odm_georeferenced_model_corrected" + pointcloud_input.suffix)
                pointcloud_mesh_output = output_dir / "odm_georeferenced_model_mesh_corrected.ply" if correct_mesh_output else None
                results["pointcloud"] = correct_pointcloud(
                    pointcloud_input,
                    pointcloud_output,
                    output_mesh_path=pointcloud_mesh_output,
                    plane_distance_threshold=plane_threshold,
                    snap_threshold=snap_threshold,
                    use_semantic_profiles=use_semantic_profiles,
                    profile_overrides=profile_overrides,
                )
                if results["pointcloud"].get("corrected_mesh"):
                    results["mesh"] = {
                        "input_mesh": str(pointcloud_input),
                        "output_mesh": results["pointcloud"]["corrected_mesh"],
                        "planes_detected": results["pointcloud"].get("planes_detected", 0),
                        "vertices": results["pointcloud"].get("mesh_vertices", 0),
                        "triangles": results["pointcloud"].get("mesh_triangles", 0),
                    }
            else:
                logger.warning("No georeferenced point cloud asset found for task %s", task_obj.id)

        if correct_mesh_output and "pointcloud" not in results:
            update_progress("Correcting mesh geometry.", 45)
            mesh_input = _first_existing_asset(task_obj, MESH_CANDIDATES)
            if mesh_input is not None:
                mesh_output = output_dir / (mesh_input.stem + "_corrected" + mesh_input.suffix)
                results["mesh"] = correct_mesh_file(
                    mesh_input,
                    mesh_output,
                    plane_distance_threshold=plane_threshold,
                    snap_threshold=snap_threshold,
                )
            else:
                logger.warning("No compatible OBJ mesh asset found for task %s", task_obj.id)

        if correct_ortho:
            update_progress("Correcting orthophoto geometry.", 75)
            orthophoto_input = _existing_asset(task_obj, "odm_orthophoto", "odm_orthophoto.tif")
            if orthophoto_input is not None:
                orthophoto_output = output_dir / "odm_orthophoto_corrected.tif"
                results["orthophoto"] = correct_orthophoto(
                    orthophoto_input,
                    orthophoto_output,
                    angle_tolerance=line_tolerance,
                    generate_confidence_map=generate_confidence_map_enabled,
                )
            else:
                logger.warning("No orthophoto asset found for task %s", task_obj.id)

        final_payload = {
            "status": "completed",
            "progress": 100,
            "message": "Geometry correction completed.",
            "result": results,
            "error_message": "",
        }
        write_job_status(task_obj, final_payload)
        _notify_completion(task_obj, opts, "COMPLETED", results)

        result = {"output": final_payload, "status": "completed"}
        if settings.TESTING:
            TestSafeAsyncResult.set(self.request.id, result)
        return result
    except Exception as exc:
        logger.exception("Geometry correction failed for task %s", task_obj.id)
        failure_payload = {
            "status": "failed",
            "progress": 100,
            "message": str(exc),
            "result": results,
            "error_message": str(exc),
        }
        write_job_status(task_obj, failure_payload)
        _notify_completion(task_obj, opts, "FAILED", results, error=str(exc))

        result = {"error": str(exc), "output": failure_payload, "status": "failed"}
        if settings.TESTING:
            TestSafeAsyncResult.set(self.request.id, result)
        return result
