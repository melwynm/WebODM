import base64
import io
import json
import os

import requests
from PIL import Image
from django.conf import settings as django_settings
from django.core.exceptions import ObjectDoesNotExist

from app import models


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


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


def build_image_sources(project, task=None, source="auto", max_images=3):
    if source not in ("auto", "field_photos", "task_orthophoto"):
        raise AIIssueDetectionError("Unsupported source: {}".format(source))

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
    if payload.get("output_text"):
        return payload["output_text"]

    parts = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text") and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts)


def _parse_candidates(text):
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
    except ValueError as e:
        raise AIIssueDetectionError("OpenAI returned invalid JSON: {}".format(str(e)))

    if isinstance(data, dict):
        data = data.get("issues", [])
    if not isinstance(data, list):
        raise AIIssueDetectionError("OpenAI response must be a JSON array of issues.")

    candidates = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        candidates.append({
            "title": title[:255],
            "description": (item.get("description") or "").strip(),
            "issue_type": item.get("issue_type") if item.get("issue_type") in dict(models.ProjectIssue.ISSUE_TYPE_CHOICES) else models.ProjectIssue.ISSUE_TYPE_DEFECT,
            "priority": item.get("priority") if item.get("priority") in dict(models.ProjectIssue.PRIORITY_CHOICES) else models.ProjectIssue.PRIORITY_MEDIUM,
            "confidence": item.get("confidence"),
            "location_hint": item.get("location_hint") or "",
        })
    return candidates


def detect_ai_issue_candidates(project, task=None, source="auto", max_images=3, timeout=45):
    api_key, model = get_openai_config()
    if not api_key:
        raise AIIssueDetectionError("OpenAI API key is not configured in Settings.")

    sources = build_image_sources(project, task=task, source=source, max_images=max_images)
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

    if response.status_code >= 400:
        raise AIIssueDetectionError("OpenAI request failed with status {}.".format(response.status_code))

    payload = response.json()
    candidates = _parse_candidates(_extract_response_text(payload))
    return {
        "model": model,
        "source_count": len(sources),
        "candidates": candidates,
        "raw_response_id": payload.get("id"),
    }


def create_review_issues(project, user, candidates, task=None):
    issues = []
    for candidate in candidates:
        properties = {
            "ai_generated": True,
            "ai_provider": "openai",
            "confidence": candidate.get("confidence"),
            "location_hint": candidate.get("location_hint"),
        }
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
    return issues
