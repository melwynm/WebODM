from __future__ import annotations

from rest_framework import exceptions, status
from rest_framework.response import Response

from app.plugins.views import TaskView

from .tasks import build_status_payload, enqueue_gaussian_splat


def _validate_options(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise exceptions.ValidationError("options must be a JSON object")
    return value


class TrainView(TaskView):
    def post(self, request, pk=None):
        task_obj = self.get_and_check_task(request, pk)
        options = _validate_options(request.data.get("options", {}))
        result = enqueue_gaussian_splat(task_obj, options=options)
        payload = build_status_payload(task_obj)
        return Response(
            {
                "job_id": result.task_id,
                "celery_task_id": result.celery_task_id,
                "status": payload["status"],
                "message": "Gaussian Splat training queued",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class StatusView(TaskView):
    def get(self, request, pk=None):
        task_obj = self.get_and_check_task(request, pk)
        return Response(build_status_payload(task_obj), status=status.HTTP_200_OK)
