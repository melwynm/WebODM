from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from types import SimpleNamespace
from typing import Callable, Optional

from app.models import Task
from app.plugins.worker import task
from nodeodm import status_codes
from webodm import settings
from worker.results import get_async_result

from . import config

logger = logging.getLogger("app.logger")

ITERATION_RE = re.compile(r"(?:iter(?:ation)?\D*)?(\d+)\s*/\s*(\d+)", re.IGNORECASE)
STEP_RE = re.compile(r"\bstep\s+(\d+)\b", re.IGNORECASE)
PERCENT_RE = re.compile(r"\[\s*(\d+(?:\.\d+)?)\s*%\s*\]", re.IGNORECASE)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".tif", ".tiff", ".png"}
PRESERVED_OPENSFM_FILES = ("reconstruction.json", "camera_models.json", "reference_lla.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_path(task_obj: Task) -> Path:
    return Path(task_obj.data_path(config.STATUS_FILE))


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


def _query_worker_status(celery_task_id: Optional[str]):
    if not celery_task_id:
        return None

    result = get_async_result(celery_task_id)
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

    return {
        "job_id": str(task_obj.id),
        "task_id": str(task_obj.id),
        "project_id": task_obj.project.id,
        # A task without a status record has never been queued. Reporting it as
        # pending makes the dashboard disable the Train Splat button forever.
        "status": stored.get("status", "idle"),
        "progress": int(stored.get("progress", 0) or 0),
        "message": stored.get("message", ""),
        "result": stored.get("result", {}),
        "error_message": stored.get("error_message"),
        "created_at": stored.get("created_at"),
        "updated_at": stored.get("updated_at"),
        "celery_task_id": stored.get("celery_task_id"),
    }


def _int_option(options: dict, name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(options.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _output_dir(task_obj: Task) -> Path:
    path = Path(task_obj.assets_path(config.OUTPUT_DIRNAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_link_or_copy(source: Path, dest: Path) -> None:
    # A link left by an earlier run can dangle once its source is cleaned up;
    # replace it instead of letting the trainer fail on a missing file.
    if dest.is_symlink() and not dest.exists():
        dest.unlink()
    if dest.exists():
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.symlink_to(source, target_is_directory=source.is_dir())
    except OSError:
        if source.is_dir():
            shutil.copytree(source, dest, dirs_exist_ok=True)
        else:
            try:
                os.link(source, dest)
            except OSError:
                shutil.copy2(source, dest)


def _find_opensfm_dir(task_obj: Task) -> Path:
    """Locate OpenSfM data from WebODM assets or the shared NodeODM volume."""
    local_dir = Path(task_obj.assets_path("opensfm"))
    if (local_dir / "reconstruction.json").is_file():
        return local_dir

    nodeodm_root = os.environ.get(
        config.NODEODM_DATA_ROOT_ENV,
        config.DEFAULT_NODEODM_DATA_ROOT,
    ).strip()
    if nodeodm_root:
        shared_dir = Path(nodeodm_root) / str(task_obj.uuid) / "opensfm"
        if (shared_dir / "reconstruction.json").is_file():
            # NodeODM deletes finished task data after a retention period, so
            # keep the small reconstruction files with the task's own assets
            # to allow retraining later.
            local_dir.mkdir(parents=True, exist_ok=True)
            for filename in PRESERVED_OPENSFM_FILES:
                source = shared_dir / filename
                if source.is_file():
                    shutil.copy2(source, local_dir / filename)
            return local_dir

    raise RuntimeError(
        "No OpenSfM reconstruction was found for this task. Reprocess with the "
        "Gaussian Splat Source preset and keep NodeODM task data available."
    )


def prepare_opensplat_input(task_obj: Task) -> Path:
    """
    Create a compact OpenSplat input folder that exposes WebODM's OpenSfM
    reconstruction and original images in a predictable project layout.
    """
    opensfm_dir = _find_opensfm_dir(task_obj)
    reconstruction = opensfm_dir / "reconstruction.json"

    input_dir = _output_dir(task_obj) / "opensplat_input"
    images_dir = input_dir / "images"
    input_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    _safe_link_or_copy(opensfm_dir, input_dir / "opensfm")
    _safe_link_or_copy(reconstruction, input_dir / "reconstruction.json")

    image_paths = []
    for image_name in task_obj.scan_images():
        source = Path(task_obj.task_path(image_name))
        if source.suffix.lower() not in IMAGE_EXTENSIONS or not source.is_file():
            continue
        _safe_link_or_copy(source, images_dir / source.name)
        input_image = input_dir / source.name
        _safe_link_or_copy(source, input_image)
        image_paths.append(str(input_image))

    if not image_paths:
        raise RuntimeError("No source images were found for Gaussian Splat training.")

    # OpenSplat's OpenSfM loader requires this manifest beside
    # reconstruction.json. Generate paths that resolve identically in the web
    # and worker containers instead of reusing NodeODM-specific paths.
    (input_dir / "image_list.txt").write_text(
        "\n".join(image_paths) + "\n",
        encoding="utf-8",
    )

    return input_dir


def build_opensplat_command(
    input_dir: Path,
    output_path: Path,
    iterations: int,
    downscale_factor: int = 1,
) -> list:
    command_template = os.environ.get(config.TRAINER_COMMAND_ENV, "").strip()
    if command_template:
        formatted = command_template.format(
            input=str(input_dir),
            output=str(output_path),
            iterations=str(iterations),
            downscale=str(downscale_factor),
        )
        command = shlex.split(formatted)
        if downscale_factor > 1 and "{downscale}" not in command_template:
            command.extend(["-d", str(downscale_factor)])
        return command

    opensplat_bin = shutil.which("opensplat")
    if not opensplat_bin:
        raise RuntimeError(
            "OpenSplat is not installed in the worker container. Install OpenSplat or set GAUSSIAN_SPLAT_TRAINER_COMMAND."
        )

    command = [opensplat_bin, str(input_dir), "-n", str(iterations), "-o", str(output_path)]
    if downscale_factor > 1:
        command.extend(["-d", str(downscale_factor)])
    return command


def _progress_from_line(line: str, fallback_total: int) -> Optional[int]:
    percent_match = PERCENT_RE.search(line)
    if percent_match:
        training_percent = max(0.0, min(100.0, float(percent_match.group(1))))
        return max(10, min(95, 10 + int(training_percent * 0.85)))

    match = ITERATION_RE.search(line)
    if match:
        current = int(match.group(1))
        total = int(match.group(2) or fallback_total)
    else:
        step_match = STEP_RE.search(line)
        if not step_match:
            return None
        current = int(step_match.group(1))
        total = fallback_total

    if total <= 0:
        total = fallback_total
    if total <= 0:
        return None
    training_percent = max(0.0, min(1.0, current / total))
    return max(10, min(95, 10 + int(training_percent * 85)))


def train_gaussian_splat(task_obj: Task, options: Optional[dict] = None, progress_callback: Optional[Callable[[str, int], None]] = None) -> dict:
    opts = options if isinstance(options, dict) else {}
    iterations = _int_option(opts, "iterations", config.DEFAULT_ITERATIONS, 100, 100000)
    downscale_factor = _int_option(
        opts,
        "downscale",
        config.DEFAULT_DOWNSCALE_FACTOR,
        1,
        8,
    )

    output_dir = _output_dir(task_obj)
    output_path = output_dir / config.OUTPUT_FILENAME
    if output_path.exists() and not opts.get("force", False):
        return {
            "output": str(output_path),
            "iterations": iterations,
            "reused_existing": True,
        }

    def progress(message: str, value: int) -> None:
        if progress_callback:
            progress_callback(message, value)

    progress("Preparing OpenSplat input.", 5)
    input_dir = prepare_opensplat_input(task_obj)
    command = build_opensplat_command(input_dir, output_path, iterations, downscale_factor)

    current_progress = 10
    progress("Training Gaussian Splat.", current_progress)
    log_lines = []
    process = subprocess.Popen(
        command,
        cwd=str(output_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        log_lines.append(line)
        log_lines = log_lines[-120:]
        parsed_progress = _progress_from_line(line, iterations)
        if parsed_progress is not None:
            current_progress = max(current_progress, parsed_progress)
            progress(line[:180], current_progress)
        else:
            progress(line[:180], current_progress)

    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError("OpenSplat failed with exit code {}. {}".format(return_code, "\n".join(log_lines[-20:])))

    fallback_output = output_dir / "splat.ply"
    if not output_path.is_file() and fallback_output.is_file():
        shutil.move(str(fallback_output), str(output_path))

    if not output_path.is_file():
        raise RuntimeError("OpenSplat completed but did not produce {}".format(output_path))

    task_obj.update_available_assets_field(commit=True)
    task_obj.update_size(commit=True)

    return {
        "output": str(output_path),
        "download_asset": "gaussian_splat.ply",
        "download_url": "/api/projects/{}/tasks/{}/download/gaussian_splat.ply".format(task_obj.project.id, task_obj.id),
        "iterations": iterations,
        "downscale_factor": downscale_factor,
        "log_tail": log_lines[-40:],
    }


def enqueue_gaussian_splat(task_obj: Task, options: Optional[dict] = None):
    options = options or {}
    current = build_status_payload(task_obj)

    if current.get("status") in ("pending", "running") and current.get("celery_task_id"):
        return SimpleNamespace(task_id=str(task_obj.id), celery_task_id=current["celery_task_id"])

    write_job_status(
        task_obj,
        {
            "status": "pending",
            "progress": 0,
            "message": "Queued Gaussian Splat training.",
            "result": {},
            "error_message": "",
            "options": options,
        },
    )

    async_result = run_gaussian_splat.delay(str(task_obj.id), int(task_obj.project.id), options)
    write_job_status(task_obj, {"celery_task_id": async_result.id})
    return SimpleNamespace(task_id=str(task_obj.id), celery_task_id=async_result.id)


@task(bind=True, time_limit=settings.WORKERS_MAX_TIME_LIMIT)
def run_gaussian_splat(self, task_id: str, project_id: int, options: Optional[dict] = None) -> dict:
    task_obj = Task.objects.get(pk=task_id, project=project_id)
    opts = options if isinstance(options, dict) else {}
    result = {}

    def update_progress(message: str, progress: int) -> None:
        write_job_status(
            task_obj,
            {
                "status": "running",
                "progress": int(progress),
                "message": message,
                "result": result,
                "error_message": "",
            },
        )
        self.update_state(state="PROGRESS", meta={"progress": int(progress), "status": message})

    try:
        if task_obj.status != status_codes.COMPLETED:
            raise RuntimeError("Task must be completed before training a Gaussian Splat.")

        update_progress("Starting Gaussian Splat training.", 1)
        result = train_gaussian_splat(task_obj, opts, progress_callback=update_progress)
        final_payload = {
            "status": "completed",
            "progress": 100,
            "message": "Gaussian Splat training complete.",
            "result": result,
            "error_message": "",
        }
        write_job_status(task_obj, final_payload)
        return {"output": final_payload}
    except Exception as exc:
        logger.exception("Gaussian Splat training failed for task %s", task_obj.id)
        failure_payload = {
            "status": "failed",
            "progress": int(read_job_status(task_obj).get("progress", 0) or 0),
            "message": "Gaussian Splat training failed.",
            "result": result,
            "error_message": str(exc),
        }
        write_job_status(task_obj, failure_payload)
        return {"output": failure_payload, "error": str(exc)}
