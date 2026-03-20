"""
API endpoints for geometry_correction.
"""

from __future__ import annotations

import json

from rest_framework import exceptions, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from app.api.common import get_and_check_project
from app.models import Task
from app.plugins.views import TaskView

from .tasks import build_status_payload, enqueue_geometry_correction


def _validate_options(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise exceptions.ValidationError("options must be a JSON object")
    return value


def _get_task(request, task_id, project_id=None):
    try:
        task_obj = Task.objects.select_related("project").get(pk=task_id)
    except Exception:
        raise exceptions.NotFound()

    if project_id is not None and int(task_obj.project.id) != int(project_id):
        raise exceptions.ValidationError("project_id does not match the task")

    if not (task_obj.public or task_obj.project.public):
        get_and_check_project(request, task_obj.project.id)

    return task_obj


class CorrectView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return Response({"error": "Invalid JSON body"}, status=status.HTTP_400_BAD_REQUEST)

        task_id = body.get("task_id")
        project_id = body.get("project_id")
        if not task_id or project_id in (None, ""):
            return Response({"error": "task_id and project_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        task_obj = _get_task(request, task_id=task_id, project_id=project_id)
        options = _validate_options(body.get("options", {}))

        result = enqueue_geometry_correction(task_obj, options=options)
        payload = build_status_payload(task_obj)

        return Response(
            {
                "job_id": result.task_id,
                "celery_task_id": result.celery_task_id,
                "status": payload["status"],
                "message": "Geometry correction queued",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class StatusView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, job_id: str):
        task_obj = _get_task(request, task_id=job_id)
        return Response(build_status_payload(task_obj), status=status.HTTP_200_OK)


class TaskCorrectView(TaskView):
    def post(self, request, pk=None):
        task_obj = self.get_and_check_task(request, pk)
        options = _validate_options(request.data.get("options", {}))
        result = enqueue_geometry_correction(task_obj, options=options)
        payload = build_status_payload(task_obj)
        return Response(
            {
                "job_id": result.task_id,
                "celery_task_id": result.celery_task_id,
                "status": payload["status"],
                "message": "Geometry correction queued",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class TaskStatusView(TaskView):
    def get(self, request, pk=None):
        task_obj = self.get_and_check_task(request, pk)
        return Response(build_status_payload(task_obj), status=status.HTTP_200_OK)
