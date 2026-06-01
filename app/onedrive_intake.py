import hashlib
import json
import os
import shutil
import time
import zipfile

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify

from app import pending_actions
from app.models import Task
from nodeodm import status_codes
from worker import tasks as worker_tasks


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".png",
}


class OneDriveIntakeError(Exception):
    pass


def configured_intake_root():
    return os.environ.get("WO_ONEDRIVE_INTAKE_DIR", "").strip()


def validate_intake_folder(root_path):
    root_path = os.path.abspath(root_path)
    allowed_root = configured_intake_root()
    if not allowed_root:
        return root_path

    allowed_root = os.path.abspath(allowed_root)
    try:
        common_path = os.path.commonpath([os.path.realpath(root_path), os.path.realpath(allowed_root)])
    except ValueError:
        raise OneDriveIntakeError("Intake folder is outside the configured OneDrive intake root.")

    if common_path != os.path.realpath(allowed_root):
        raise OneDriveIntakeError("Intake folder is outside the configured OneDrive intake root.")
    return root_path


def intake_state_path():
    return os.path.join(settings.MEDIA_CACHE, "onedrive_intake_state.json")


def load_intake_state(path=None):
    path = path or intake_state_path()
    if not os.path.isfile(path):
        return {"datasets": {}}

    try:
        with open(path, "r", encoding="utf-8") as state_file:
            state = json.load(state_file)
    except (OSError, ValueError):
        return {"datasets": {}}

    if not isinstance(state, dict) or not isinstance(state.get("datasets"), dict):
        return {"datasets": {}}
    return state


def save_intake_state(state, path=None):
    path = path or intake_state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def discover_intake_datasets(root_path, min_age_seconds=60):
    root_path = validate_intake_folder(root_path)
    if not os.path.isdir(root_path):
        raise OneDriveIntakeError(f"Intake folder does not exist: {root_path}")

    datasets = []
    now = time.time()
    for entry in sorted(os.scandir(root_path), key=lambda item: item.name.lower()):
        if entry.name.startswith("."):
            continue
        if entry.name.endswith((".tmp", ".partial", ".uploading")):
            continue
        if entry.is_file() and entry.name.lower().endswith(".zip"):
            fingerprint = file_fingerprint(entry.path)
            if now - fingerprint["mtime"] >= min_age_seconds:
                datasets.append(dataset_record(entry.path, "zip", fingerprint))
        elif entry.is_dir():
            fingerprint = directory_fingerprint(entry.path)
            if fingerprint["image_count"] >= 2 and now - fingerprint["mtime"] >= min_age_seconds:
                datasets.append(dataset_record(entry.path, "directory", fingerprint))
    return datasets


def dataset_record(path, dataset_type, fingerprint):
    digest_source = f"{os.path.abspath(path)}|{fingerprint['mtime']}|{fingerprint['size']}"
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    return {
        "path": os.path.abspath(path),
        "type": dataset_type,
        "name": os.path.basename(path),
        "fingerprint": fingerprint,
        "key": digest,
    }


def file_fingerprint(path):
    stat = os.stat(path)
    return {
        "mtime": round(float(stat.st_mtime), 6),
        "size": int(stat.st_size),
        "image_count": 0,
    }


def directory_fingerprint(path):
    total_size = 0
    latest_mtime = 0.0
    image_count = 0
    for root, _dirs, files in os.walk(path):
        for filename in files:
            file_path = os.path.join(root, filename)
            try:
                stat = os.stat(file_path)
            except OSError:
                continue
            total_size += int(stat.st_size)
            latest_mtime = max(latest_mtime, float(stat.st_mtime))
            if os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS:
                image_count += 1

    return {
        "mtime": round(latest_mtime, 6),
        "size": total_size,
        "image_count": image_count,
    }


def import_destination(dataset):
    imports_dir = os.path.join(settings.MEDIA_ROOT, "imports", "onedrive-intake")
    os.makedirs(imports_dir, exist_ok=True)
    base = slugify(os.path.splitext(dataset["name"])[0]) or "dataset"
    return os.path.join(imports_dir, f"{base}-{dataset['key'][:12]}.zip")


def prepare_import_zip(dataset):
    destination = import_destination(dataset)
    if os.path.isfile(destination):
        return destination

    tmp_destination = destination + ".tmp"
    if os.path.isfile(tmp_destination):
        os.unlink(tmp_destination)

    if dataset["type"] == "zip":
        shutil.copyfile(dataset["path"], tmp_destination)
    else:
        zip_directory(dataset["path"], tmp_destination)

    os.replace(tmp_destination, destination)
    return destination


def zip_directory(source_dir, destination):
    source_dir = os.path.abspath(source_dir)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _dirs, files in os.walk(source_dir):
            for filename in sorted(files):
                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, source_dir)
                archive.write(file_path, arcname)


def import_url_for_path(path):
    imports_dir = os.path.join(settings.MEDIA_ROOT, "imports")
    relative = os.path.relpath(path, imports_dir)
    return "file://" + relative.replace(os.sep, "/")


def create_task_from_dataset(project, dataset, auto_process=True):
    zip_path = prepare_import_zip(dataset)
    task_name = os.path.splitext(dataset["name"])[0]

    with transaction.atomic():
        task = Task.objects.create(
            project=project,
            auto_processing_node=False,
            name=task_name,
            import_url=import_url_for_path(zip_path),
            status=status_codes.RUNNING,
            pending_action=pending_actions.IMPORT,
        )
        task.create_task_directories()

    if auto_process:
        worker_tasks.process_task.delay(task.id)

    return task


def intake_onedrive_folder(project, root_path, min_age_seconds=60, dry_run=False, auto_process=True, state_path=None):
    state = load_intake_state(state_path)
    results = []

    for dataset in discover_intake_datasets(root_path, min_age_seconds=min_age_seconds):
        if dataset["key"] in state["datasets"]:
            results.append({"dataset": dataset, "status": "skipped"})
            continue

        if dry_run:
            results.append({"dataset": dataset, "status": "ready"})
            continue

        task = create_task_from_dataset(project, dataset, auto_process=auto_process)
        state["datasets"][dataset["key"]] = {
            "path": dataset["path"],
            "name": dataset["name"],
            "task_id": str(task.id),
            "fingerprint": dataset["fingerprint"],
        }
        results.append({"dataset": dataset, "status": "created", "task": task})

    if not dry_run:
        save_intake_state(state, state_path)

    return results
