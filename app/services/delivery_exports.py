import json
import os
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.services.commercial_readiness import build_project_commercial_readiness
from app.services.project_reports import build_project_progress_report
from nodeodm import status_codes


DELIVERY_ASSETS = (
    "orthophoto.tif",
    "dsm.tif",
    "dtm.tif",
    "thermal_orthophoto.tif",
    "orthophoto.kmz",
    "report.pdf",
)


def safe_bundle_name(value, fallback="item"):
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value or "").strip("-._")
    return value[:80] or fallback


def _json_bytes(payload):
    return json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")


def _issue_payload(issue):
    return {
        "id": issue.id,
        "title": issue.title,
        "description": issue.description,
        "issue_type": issue.issue_type,
        "status": issue.status,
        "priority": issue.priority,
        "task": issue.task.name if issue.task else None,
        "geometry": issue.geometry,
        "properties": issue.properties,
        "created_by": issue.created_by.username if issue.created_by else None,
        "assigned_to": issue.assigned_to.username if issue.assigned_to else None,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
    }


def _add_file_if_exists(bundle, path, arcname, manifest_assets):
    if path and os.path.isfile(path):
        bundle.write(path, arcname)
        manifest_assets.append({
            "path": arcname,
            "bytes": os.path.getsize(path),
        })
        return True
    return False


def _repo_root():
    return Path(__file__).resolve().parents[2]


def _task_asset_folder(task):
    return "{}-{}".format(task.id, safe_bundle_name(task.name, "task"))


def build_project_delivery_bundle(project, template=None):
    report = build_project_progress_report(project, template=template)
    readiness = build_project_commercial_readiness(project)
    issues = [
        _issue_payload(issue)
        for issue in project.issues.select_related("task", "created_by", "assigned_to").order_by("-created_at", "-id")
    ]

    manifest = {
        "project": {
            "id": project.id,
            "name": project.name,
        },
        "report_template": report["report_template"]["key"],
        "ready": readiness["ready"],
        "assets": [],
        "counts": {
            "tasks": project.task_set.count(),
            "issues": len(issues),
            "client_shares": project.client_shares.count(),
            "design_overlays": project.design_overlays.count(),
            "field_photos": project.field_photos.count(),
        },
    }

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as bundle:
        bundle.writestr("progress_report.json", _json_bytes(report))
        bundle.writestr("commercial_readiness.json", _json_bytes(readiness))
        bundle.writestr("issues.json", _json_bytes({"results": issues}))

        for task in project.task_set.filter(status=status_codes.COMPLETED).order_by("-created_at", "-id"):
            folder = "tasks/{}/".format(_task_asset_folder(task))
            for asset in DELIVERY_ASSETS:
                if asset not in (task.available_assets or []):
                    continue
                try:
                    asset_path = task.get_asset_download_path(asset)
                except Exception:
                    continue
                _add_file_if_exists(bundle, asset_path, folder + asset, manifest["assets"])

        for overlay in project.design_overlays.all():
            filename = safe_bundle_name(overlay.source_filename or os.path.basename(overlay.file.name), "design-overlay")
            _add_file_if_exists(
                bundle,
                getattr(overlay.file, "path", None),
                "design_overlays/{}-{}".format(overlay.id, filename),
                manifest["assets"],
            )

        for photo in project.field_photos.all():
            filename = safe_bundle_name(photo.source_filename or os.path.basename(photo.image.name), "field-photo")
            _add_file_if_exists(
                bundle,
                getattr(photo.image, "path", None),
                "field_photos/{}-{}".format(photo.id, filename),
                manifest["assets"],
            )

        disclaimer_path = _repo_root() / "COMMERCIAL_DISCLAIMERS.md"
        if disclaimer_path.exists():
            _add_file_if_exists(
                bundle,
                str(disclaimer_path),
                "commercial_disclaimers.md",
                manifest["assets"],
            )

        bundle.writestr("manifest.json", _json_bytes(manifest))

    filename = "{}-delivery-bundle.zip".format(safe_bundle_name(project.name, "project"))
    return filename, buffer.getvalue(), manifest
