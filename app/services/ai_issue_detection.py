import base64
import io
import json
import math
import os
import uuid

import requests
from PIL import Image
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from app import models
from app.services.monitoring import monitoring_layer_path, monitoring_pair_readiness


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_AI_ISSUE_CANDIDATES = 12
MAX_AI_DESCRIPTION_LENGTH = 4000
MAX_AI_LOCATION_HINT_LENGTH = 500
MAX_AI_RESPONSE_TEXT_LENGTH = 256000
CONFIRMATION_TOKEN_MAX_AGE = 15 * 60
CONFIRMATION_TOKEN_SALT = "app.ai_issue_detection.confirmation"


class AIIssueDetectionError(Exception):
    pass


def get_openai_config():
    app_settings = models.Setting.objects.first()
    api_key = (getattr(app_settings, "openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")).strip()
    model = (getattr(app_settings, "openai_model", "") or os.environ.get("OPENAI_MODEL", "") or "gpt-4.1-mini").strip()
    return api_key, model


def _resize_image_bytes(image_path, max_size=1280):
    with Image.open(image_path) as image:
        image.thumbnail((max_size, max_size))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        elif image.mode == "L":
            image = image.convert("RGB")

        output = io.BytesIO()
        image.save(output, format="JPEG", quality=86)
        return output.getvalue()


def _task_orthophoto_preview(task, max_size=1280):
    try:
        image_path = task.get_asset_download_path("orthophoto.tif")
    except (FileNotFoundError, ObjectDoesNotExist):
        return None

    if not os.path.isfile(image_path):
        return None

    return {
        "name": "{} orthophoto preview".format(task.name),
        "kind": "task_orthophoto",
        "task": task,
        "image_bytes": _resize_image_bytes(image_path, max_size=max_size),
    }


def _field_photo_sources(project, task=None, max_images=3, max_size=1280):
    photos = models.ProjectFieldPhoto.objects.filter(project=project).order_by("-captured_at", "-updated_at", "-created_at")
    if task is not None:
        photos = photos.filter(task=task)

    sources = []
    for photo in photos[:max_images]:
        if not photo.image or not os.path.isfile(photo.image.path):
            continue
        sources.append({
            "name": photo.name,
            "kind": "field_photo",
            "field_photo": photo,
            "task": photo.task,
            "image_bytes": _resize_image_bytes(photo.image.path, max_size=max_size),
        })
    return sources


def _monitoring_change_source(task, compare_task, max_size=1280):
    if task is None or compare_task is None:
        raise AIIssueDetectionError("Monitoring change review requires current and baseline tasks.")
    readiness = monitoring_pair_readiness(task, compare_task)
    if not readiness["cache"]["ready"]:
        raise AIIssueDetectionError("Monitoring comparison is not ready yet.")
    try:
        image_path = monitoring_layer_path(task, compare_task, "change")
    except Exception:
        raise AIIssueDetectionError("Monitoring change heatmap is not available yet.")
    return {
        "name": "{} vs {} change heatmap".format(task.name or task.id, compare_task.name or compare_task.id),
        "kind": "monitoring_change",
        "task": task,
        "compare_task": compare_task,
        "image_bytes": _resize_image_bytes(image_path, max_size=max_size),
    }


def build_image_sources(project, task=None, compare_task=None, source="auto", max_images=3):
    if source not in ("auto", "field_photos", "task_orthophoto", "monitoring_change"):
        raise AIIssueDetectionError("Unsupported source: {}".format(source))

    if source == "monitoring_change":
        return [_monitoring_change_source(task, compare_task)]

    sources = []
    if source in ("auto", "field_photos"):
        sources.extend(_field_photo_sources(project, task=task, max_images=max_images))

    if not sources and task is not None and source in ("auto", "task_orthophoto"):
        orthophoto = _task_orthophoto_preview(task)
        if orthophoto:
            sources.append(orthophoto)

    if not sources:
        raise AIIssueDetectionError("No field photos or orthophoto preview are available for AI review.")

    return sources


def _image_content_item(source):
    encoded = base64.b64encode(source["image_bytes"]).decode("ascii")
    return {
        "type": "input_image",
        "image_url": "data:image/jpeg;base64,{}".format(encoded),
        "detail": "high",
    }


def _extract_response_text(payload):
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text[:MAX_AI_RESPONSE_TEXT_LENGTH]

    parts = []
    for item in payload.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") in ("output_text", "text") and content.get("text"):
                text = content["text"]
                if isinstance(text, str):
                    parts.append(text)
    return "\n".join(parts)[:MAX_AI_RESPONSE_TEXT_LENGTH]


def _bounded_text(value, max_length):
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]


def _normalized_confidence(value):
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(confidence):
        return None
    return max(0.0, min(confidence, 1.0))


def normalize_ai_issue_candidates(data):
    if isinstance(data, dict):
        data = data.get("issues", [])
    if not isinstance(data, list):
        raise AIIssueDetectionError("OpenAI response must be a JSON array of issues.")

    candidates = []
    for item in data[:MAX_AI_ISSUE_CANDIDATES]:
        if not isinstance(item, dict):
            continue
        title = _bounded_text(item.get("title"), 255)
        if not title:
            continue
        candidates.append({
            "title": title,
            "description": _bounded_text(item.get("description"), MAX_AI_DESCRIPTION_LENGTH),
            "issue_type": item.get("issue_type") if item.get("issue_type") in dict(models.ProjectIssue.ISSUE_TYPE_CHOICES) else models.ProjectIssue.ISSUE_TYPE_DEFECT,
            "priority": item.get("priority") if item.get("priority") in dict(models.ProjectIssue.PRIORITY_CHOICES) else models.ProjectIssue.PRIORITY_MEDIUM,
            "confidence": _normalized_confidence(item.get("confidence")),
            "location_hint": _bounded_text(item.get("location_hint"), MAX_AI_LOCATION_HINT_LENGTH),
        })
    return candidates


def _parse_candidates(text):
    cleaned = text.strip() if isinstance(text, str) else ""
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
    except ValueError as e:
        raise AIIssueDetectionError("OpenAI returned invalid JSON: {}".format(str(e)))

    return normalize_ai_issue_candidates(data)


def detect_ai_issue_candidates(project, task=None, compare_task=None, source="auto", max_images=3, timeout=45):
    api_key, model = get_openai_config()
    if not api_key:
        raise AIIssueDetectionError("OpenAI API key is not configured in Settings.")

    sources = build_image_sources(
        project,
        task=task,
        compare_task=compare_task,
        source=source,
        max_images=max_images,
    )
    source_names = ["{}: {}".format(s["kind"], s["name"]) for s in sources]

    prompt = (
        "You are reviewing construction monitoring imagery for possible project issues. "
        "Identify only visible, review-worthy issues. Return JSON only as an array. "
        "Each item must include title, description, issue_type, priority, confidence, and location_hint. "
        "Allowed issue_type values: annotation, change, defect, progress. "
        "Allowed priority values: low, medium, high, critical. "
        "If nothing needs review, return []. "
        "Sources: {}".format("; ".join(source_names))
    )

    content = [{"type": "input_text", "text": prompt}]
    content.extend(_image_content_item(source) for source in sources)

    try:
        response = requests.post(
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": "Bearer {}".format(api_key),
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": [{
                    "role": "user",
                    "content": content,
                }],
            },
            timeout=timeout,
        )
    except requests.RequestException:
        raise AIIssueDetectionError("OpenAI request could not be completed.")

    if response.status_code >= 400:
        raise AIIssueDetectionError("OpenAI request failed with status {}.".format(response.status_code))

    try:
        payload = response.json()
    except (TypeError, ValueError):
        raise AIIssueDetectionError("OpenAI returned an invalid response payload.")
    if not isinstance(payload, dict):
        raise AIIssueDetectionError("OpenAI returned an invalid response payload.")

    candidates = _parse_candidates(_extract_response_text(payload))
    return {
        "model": model,
        "source_count": len(sources),
        "candidates": candidates,
        "raw_response_id": payload.get("id"),
    }


def create_confirmation_token(project, task, result, compare_task=None, monitoring_run=None):
    return signing.dumps(
        {
            "project_id": str(project.pk),
            "task_id": str(task.pk) if task is not None else None,
            "compare_task_id": str(compare_task.pk) if compare_task is not None else None,
            "monitoring_run_id": str(monitoring_run.pk) if monitoring_run is not None else None,
            "model": _bounded_text(result.get("model"), 80),
            "source_count": max(0, int(result.get("source_count", 0))),
            "candidates": normalize_ai_issue_candidates(result.get("candidates", [])),
            "raw_response_id": _bounded_text(result.get("raw_response_id"), 255),
            "confirmation_id": uuid.uuid4().hex,
        },
        salt=CONFIRMATION_TOKEN_SALT,
        compress=True,
    )


def load_confirmation_token(token, project):
    try:
        payload = signing.loads(
            token,
            salt=CONFIRMATION_TOKEN_SALT,
            max_age=CONFIRMATION_TOKEN_MAX_AGE,
        )
    except signing.SignatureExpired:
        raise AIIssueDetectionError("AI issue preview expired. Run the preview again.")
    except signing.BadSignature:
        raise AIIssueDetectionError("AI issue preview is invalid. Run the preview again.")

    if not isinstance(payload, dict) or payload.get("project_id") != str(project.pk):
        raise AIIssueDetectionError("AI issue preview does not belong to this project.")

    candidates = normalize_ai_issue_candidates(payload.get("candidates", []))
    if not candidates:
        raise AIIssueDetectionError("AI issue preview has no candidates to create.")

    return {
        "task_id": payload.get("task_id"),
        "compare_task_id": payload.get("compare_task_id"),
        "monitoring_run_id": payload.get("monitoring_run_id"),
        "model": _bounded_text(payload.get("model"), 80),
        "source_count": max(0, int(payload.get("source_count", 0))),
        "candidates": candidates,
        "raw_response_id": _bounded_text(payload.get("raw_response_id"), 255),
        "confirmation_id": _bounded_text(payload.get("confirmation_id"), 64),
    }


@transaction.atomic
def create_review_issues(
    project,
    user,
    candidates,
    task=None,
    model="",
    response_id="",
    confirmation_id="",
    extra_properties=None,
):
    if confirmation_id:
        models.Project.objects.select_for_update().get(pk=project.pk)
        existing = list(models.ProjectIssue.objects.filter(
            project=project,
            properties__ai_confirmation_id=confirmation_id,
        ))
        if existing:
            return existing, 0

    issues = []
    for candidate in normalize_ai_issue_candidates(candidates):
        properties = {
            "ai_generated": True,
            "ai_provider": "openai",
            "confidence": candidate.get("confidence"),
            "location_hint": candidate.get("location_hint"),
        }
        if model:
            properties["ai_model"] = model
        if response_id:
            properties["ai_response_id"] = response_id
        if confirmation_id:
            properties["ai_confirmation_id"] = confirmation_id
        if extra_properties:
            properties.update(extra_properties)
        issue = models.ProjectIssue.objects.create(
            project=project,
            task=task,
            title=candidate["title"],
            description=candidate.get("description", ""),
            issue_type=candidate.get("issue_type") or models.ProjectIssue.ISSUE_TYPE_DEFECT,
            priority=candidate.get("priority") or models.ProjectIssue.PRIORITY_MEDIUM,
            status=models.ProjectIssue.STATUS_IN_REVIEW,
            properties=properties,
            created_by=user,
        )
        issues.append(issue)
    return issues, len(issues)
