import datetime
import hashlib
import hmac
import json
import math
import os
import re
import uuid
from urllib.parse import quote

import rasterio
import requests
from django.conf import settings
from django.contrib.gis.gdal import SpatialReference
from django.db import transaction
from django.utils import timezone
from nodeodm import status_codes

from app.models import AirTwinWebhookDelivery, Task


MANIFEST_VERSION = 1
EVENT_NAME = "webodm.task.completed"
SUPPORTED_ASSETS = (
    "textured_model.glb",
    "orthophoto.tif",
    "shots.geojson",
    "report.pdf",
    "georeferenced_model.laz",
    "dsm.tif",
    "dtm.tif",
    "3d_tiles_model.zip",
    "3d_tiles_pointcloud.zip",
)
REQUIRED_ASSETS = (
    "textured_model.glb",
    "orthophoto.tif",
    "shots.geojson",
    "report.pdf",
)
TASK_NAME_PATTERN = re.compile(r"^\s*(?P<site>.+?)\s+-\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$")
SENSITIVE_PATTERN = re.compile(
    r"(?i)\b(authorization|api[-_ ]?key|token|secret|password)(\s*[:=]\s*)([^\s,;&]+)"
)
URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(https?://)([^/\s:@]+):([^@\s/]+)@")
SENSITIVE_QUERY_PATTERN = re.compile(r"(?i)([?&](?:api[-_]?key|token|secret|password)=)([^&\s]+)")


def get_webhook_config():
    return {
        "enabled": bool(getattr(settings, "AIRTWIN_WEBHOOK_ENABLED", False)),
        "url": str(getattr(settings, "AIRTWIN_WEBHOOK_URL", "") or "").strip(),
        "secret": str(getattr(settings, "AIRTWIN_WEBHOOK_SECRET", "") or ""),
        "timeout": max(0.1, float(getattr(settings, "AIRTWIN_WEBHOOK_TIMEOUT_SECONDS", 10.0))),
        "max_retries": max(0, int(getattr(settings, "AIRTWIN_WEBHOOK_MAX_RETRIES", 5))),
        "retry_base": max(1, int(getattr(settings, "AIRTWIN_WEBHOOK_RETRY_BASE_SECONDS", 5))),
    }


def discover_supported_assets(task, base_url=""):
    base_url = (base_url or "").rstrip("/")
    available = set(task.available_assets or [])
    assets = []
    for name in SUPPORTED_ASSETS:
        if name not in available:
            continue
        path = "/api/projects/{}/tasks/{}/download/{}".format(
            task.project_id,
            task.id,
            quote(name, safe=""),
        )
        if base_url:
            path = base_url + path
        if name == "shots.geojson":
            epsg = 4326
        elif name == "report.pdf":
            epsg = None
        else:
            epsg = task.epsg
        assets.append({"name": name, "downloadUrl": path, "epsg": epsg})
    return assets


def _asset_path(task, asset_name):
    relative = task.ASSETS_MAP.get(asset_name)
    if not isinstance(relative, str):
        return None
    return task.assets_path(relative)


def _coordinate_pairs(value):
    if not isinstance(value, (list, tuple)):
        return
    if len(value) >= 2 and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value[:2]):
        yield value[0], value[1]
        return
    for item in value:
        yield from _coordinate_pairs(item)


def _validate_wgs84_geojson(task, asset_name):
    result = {
        "asset": asset_name,
        "listed": asset_name in (task.available_assets or []),
        "exists": False,
        "valid": False,
        "coordinateCount": 0,
        "invalidCoordinateCount": 0,
        "error": "",
    }
    path = _asset_path(task, asset_name)
    if path is None or not os.path.isfile(path):
        result["error"] = "{} is not available on disk.".format(asset_name)
        return result

    result["exists"] = True
    try:
        with open(path, encoding="utf-8") as geojson_file:
            data = json.load(geojson_file)
    except (OSError, ValueError, TypeError) as error:
        result["error"] = "{} is not valid GeoJSON: {}".format(asset_name, str(error))
        return result

    if not isinstance(data, dict):
        result["error"] = "{} is not a GeoJSON object.".format(asset_name)
        return result

    if data.get("type") == "FeatureCollection":
        geometries = [feature.get("geometry") for feature in data.get("features", []) if isinstance(feature, dict)]
    elif data.get("type") == "Feature":
        geometries = [data.get("geometry")]
    else:
        geometries = [data]

    for geometry in geometries:
        if not isinstance(geometry, dict):
            continue
        for longitude, latitude in _coordinate_pairs(geometry.get("coordinates")):
            result["coordinateCount"] += 1
            if not (
                math.isfinite(longitude)
                and math.isfinite(latitude)
                and -180.0 <= longitude <= 180.0
                and -90.0 <= latitude <= 90.0
            ):
                result["invalidCoordinateCount"] += 1

    if result["coordinateCount"] == 0:
        result["error"] = "{} contains no usable longitude/latitude coordinates.".format(asset_name)
    elif result["invalidCoordinateCount"]:
        result["error"] = "{} contains coordinates outside WGS84 longitude/latitude ranges.".format(asset_name)
    else:
        result["valid"] = True
    return result


def _has_source_gcp(task):
    excluded = {"geo.txt", "image_groups.txt"}
    try:
        return any(
            filename.lower().endswith(".txt") and filename.lower() not in excluded
            for filename in os.listdir(task.task_path())
        )
    except OSError:
        return False


def _validate_epsg(epsg):
    if epsg is None:
        return False
    try:
        SpatialReference(int(epsg))
        return int(epsg) > 0
    except Exception:
        return False


def _raster_crs(task, asset_name):
    path = _asset_path(task, asset_name)
    if path is None or not os.path.isfile(path):
        return None
    try:
        with rasterio.open(path) as dataset:
            return dataset.crs.to_epsg() if dataset.crs is not None else None
    except (OSError, rasterio.errors.RasterioError):
        return None


def validate_task_geospatial(task):
    errors = []
    warnings = []
    epsg_valid = _validate_epsg(task.epsg)
    if not epsg_valid:
        errors.append("Task has no valid EPSG/CRS.")

    shots = _validate_wgs84_geojson(task, "shots.geojson")
    gcps = _validate_wgs84_geojson(task, "ground_control_points.geojson")
    has_gps = shots["valid"]
    has_gcp = gcps["valid"] or _has_source_gcp(task)

    if shots["listed"] and not shots["valid"]:
        errors.append(shots["error"])
    elif not shots["listed"]:
        warnings.append("shots.geojson is missing; camera GPS positions cannot be exported.")

    if gcps["listed"] and not gcps["valid"]:
        warnings.append(gcps["error"])

    if not has_gps and not has_gcp:
        errors.append("No usable GPS or GCP georeferencing evidence was found.")
    elif has_gps and not has_gcp:
        warnings.append("Georeferencing uses camera GPS only; use surveyed GCPs when higher accuracy is required.")

    raster_crs = {}
    for asset_name in ("orthophoto.tif", "dsm.tif", "dtm.tif"):
        if asset_name not in (task.available_assets or []):
            continue
        asset_epsg = _raster_crs(task, asset_name)
        if asset_epsg is not None:
            raster_crs[asset_name] = asset_epsg
            if epsg_valid and asset_epsg != task.epsg:
                errors.append("{} CRS does not match task EPSG {}.".format(asset_name, task.epsg))

    if has_gps and has_gcp:
        source = "gps_and_gcp"
    elif has_gcp:
        source = "gcp"
    elif has_gps:
        source = "gps"
    else:
        source = "none"

    return {
        "ready": not errors,
        "epsgValid": epsg_valid,
        "georeferencingSource": source,
        "hasGps": has_gps,
        "hasGcp": has_gcp,
        "shotsGeoJson": shots,
        "groundControlPointsGeoJson": gcps,
        "rasterCrs": raster_crs,
        "warnings": warnings,
        "errors": errors,
    }


def parse_recommended_task_name(name):
    match = TASK_NAME_PATTERN.match(name or "")
    if not match:
        return {"matchesRecommendedFormat": False, "siteIdentifier": None, "surveyDate": None}
    try:
        survey_date = datetime.date.fromisoformat(match.group("date"))
    except ValueError:
        return {"matchesRecommendedFormat": False, "siteIdentifier": None, "surveyDate": None}
    return {
        "matchesRecommendedFormat": True,
        "siteIdentifier": match.group("site").strip(),
        "surveyDate": survey_date.isoformat(),
    }


def task_completed_at(task):
    if task.completed_at is not None:
        return task.completed_at
    if task.processing_time is not None and task.processing_time >= 0:
        return task.created_at + datetime.timedelta(milliseconds=task.processing_time)
    return task.created_at


def build_manifest(task, base_url=""):
    assets = discover_supported_assets(task, base_url=base_url)
    asset_names = [asset["name"] for asset in assets]
    missing_assets = [asset for asset in REQUIRED_ASSETS if asset not in asset_names]
    geospatial = validate_task_geospatial(task)
    naming = parse_recommended_task_name(task.name)
    completed_at = task_completed_at(task)
    errors = list(geospatial["errors"])
    warnings = list(geospatial["warnings"])

    if task.status != status_codes.COMPLETED:
        errors.append("Task has not completed successfully.")
    if missing_assets:
        errors.append("Missing required AirTwin assets: {}.".format(", ".join(missing_assets)))
    if not naming["matchesRecommendedFormat"]:
        warnings.append("Recommended task name format is <site name> - <survey date>.")

    retention_days = max(0, int(getattr(settings, "AIRTWIN_OUTPUT_RETENTION_DAYS", 30)))
    manifest = {
        "version": MANIFEST_VERSION,
        "webOdmProjectId": task.project_id,
        "taskId": str(task.id),
        "taskName": task.name or "",
        "status": task.status,
        "statusLabel": task.get_status_display() if task.status is not None else None,
        "epsg": task.epsg,
        "createdAt": task.created_at.isoformat(),
        "completedAt": completed_at.isoformat() if completed_at else None,
        "availableAssets": asset_names,
        "assets": assets,
        "readyForAirTwin": not errors,
        "validation": {
            "errors": errors,
            "warnings": warnings,
            "missingRequiredAssets": missing_assets,
            "geospatial": geospatial,
            "taskNaming": naming,
        },
        "retentionDays": retention_days,
        "retainUntil": (completed_at + datetime.timedelta(days=retention_days)).isoformat() if completed_at else None,
    }
    if naming["surveyDate"]:
        manifest["surveyDate"] = naming["surveyDate"]
    if naming["siteIdentifier"]:
        manifest["siteIdentifier"] = naming["siteIdentifier"]
    return manifest


def stable_event_id(task):
    completion = task_completed_at(task)
    value = "urn:webodm:airtwin:{}:{}:{}".format(EVENT_NAME, task.id, completion.isoformat())
    return uuid.uuid5(uuid.NAMESPACE_URL, value)


def build_webhook_payload(task, event_id=None):
    event_id = event_id or stable_event_id(task)
    manifest = build_manifest(task)
    return {
        "version": MANIFEST_VERSION,
        "event": EVENT_NAME,
        "eventId": str(event_id),
        "webOdmProjectId": manifest["webOdmProjectId"],
        "taskId": manifest["taskId"],
        "taskName": manifest["taskName"],
        "status": manifest["status"],
        "epsg": manifest["epsg"],
        "availableAssets": manifest["availableAssets"],
        "createdAt": manifest["createdAt"],
        "completedAt": manifest["completedAt"],
        "readyForAirTwin": manifest["readyForAirTwin"],
        "validationWarnings": manifest["validation"]["warnings"],
    }


def serialize_payload(payload):
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode("utf-8")


def sign_payload(secret, timestamp, event_id, body):
    signing_input = "{}.{}.".format(timestamp, event_id).encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).hexdigest()


def webhook_headers(secret, timestamp, event_id, body):
    signature = sign_payload(secret, timestamp, event_id, body)
    return {
        "Content-Type": "application/json",
        "User-Agent": "WebODM-AirTwin/1",
        "X-AirTwin-Timestamp": str(timestamp),
        "X-AirTwin-Event-Id": str(event_id),
        "X-AirTwin-Signature": "sha256={}".format(signature),
    }


def sanitize_error(value, secret=""):
    text = str(value or "")
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]@", text)
    text = SENSITIVE_QUERY_PATTERN.sub(r"\1[REDACTED]", text)
    text = SENSITIVE_PATTERN.sub(lambda match: "{}{}[REDACTED]".format(match.group(1), match.group(2)), text)
    return text[:1000]


def is_retryable_status(status_code):
    return status_code in (408, 429) or status_code >= 500


def _finish_failure(delivery, message, retryable, now, config):
    delivery.last_error = sanitize_error(message, config["secret"])
    delivery.delivered_at = None
    total_attempts = config["max_retries"] + 1
    retry = retryable and delivery.attempts < total_attempts
    if retry:
        delay = min(config["retry_base"] * (2 ** max(delivery.attempts - 1, 0)), 3600)
        delivery.status = AirTwinWebhookDelivery.STATUS_RETRYING
        delivery.next_attempt_at = now + datetime.timedelta(seconds=delay)
    else:
        delay = None
        delivery.status = AirTwinWebhookDelivery.STATUS_FAILED
        delivery.next_attempt_at = None
    delivery.save(update_fields=[
        "status", "attempts", "response_status", "last_error", "next_attempt_at",
        "delivered_at", "updated_at",
    ])
    return {"retry": retry, "delay": delay, "status": delivery.status}


def deliver_webhook_attempt(delivery_id, sender=None, now=None):
    delivery = AirTwinWebhookDelivery.objects.select_related("task").get(pk=delivery_id)
    if delivery.status == AirTwinWebhookDelivery.STATUS_DELIVERED:
        return {"retry": False, "delay": None, "status": delivery.status}

    config = get_webhook_config()
    now = now or timezone.now()
    delivery.attempts += 1
    delivery.response_status = None

    if not config["enabled"]:
        return _finish_failure(delivery, "AirTwin webhook is disabled.", False, now, config)
    if not config["url"] or not config["secret"]:
        return _finish_failure(delivery, "AirTwin webhook URL or secret is not configured.", False, now, config)

    body = serialize_payload(delivery.payload)
    timestamp = str(int(now.timestamp()))
    headers = webhook_headers(config["secret"], timestamp, delivery.event_id, body)
    sender = sender or requests.post
    try:
        response = sender(config["url"], data=body, headers=headers, timeout=config["timeout"])
    except Exception as error:
        return _finish_failure(delivery, "AirTwin webhook request failed: {}".format(error), True, now, config)

    delivery.response_status = int(response.status_code)
    if 200 <= response.status_code < 300:
        delivery.status = AirTwinWebhookDelivery.STATUS_DELIVERED
        delivery.last_error = ""
        delivery.next_attempt_at = None
        delivery.delivered_at = now
        delivery.save(update_fields=[
            "status", "attempts", "response_status", "last_error", "next_attempt_at",
            "delivered_at", "updated_at",
        ])
        return {"retry": False, "delay": None, "status": delivery.status}

    return _finish_failure(
        delivery,
        "AirTwin webhook returned HTTP {}.".format(response.status_code),
        is_retryable_status(response.status_code),
        now,
        config,
    )


def schedule_task_completed_webhook(task_id, enqueue=None):
    config = get_webhook_config()
    if not config["enabled"]:
        return None
    try:
        task = Task.objects.select_related("project").get(pk=task_id, status=status_codes.COMPLETED)
    except Task.DoesNotExist:
        return None

    if task.completed_at is None:
        task.completed_at = timezone.now()
        task.save(update_fields=["completed_at"])

    event_id = stable_event_id(task)
    delivery, created = AirTwinWebhookDelivery.objects.get_or_create(
        event_id=event_id,
        defaults={
            "task": task,
            "event": EVENT_NAME,
            "payload": build_webhook_payload(task, event_id=event_id),
        },
    )
    if not created:
        return delivery

    if not config["url"] or not config["secret"]:
        delivery.status = AirTwinWebhookDelivery.STATUS_FAILED
        delivery.last_error = "AirTwin webhook URL or secret is not configured."
        delivery.save(update_fields=["status", "last_error", "updated_at"])
        return delivery

    def enqueue_delivery():
        try:
            enqueue(delivery.id)
        except Exception as error:
            AirTwinWebhookDelivery.objects.filter(pk=delivery.id).update(
                status=AirTwinWebhookDelivery.STATUS_FAILED,
                last_error=sanitize_error("Could not enqueue AirTwin webhook: {}".format(error), config["secret"]),
            )

    if enqueue is not None:
        transaction.on_commit(enqueue_delivery)
    return delivery
