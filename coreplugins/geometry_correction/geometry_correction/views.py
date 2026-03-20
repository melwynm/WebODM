"""
geometry_correction/views.py

REST API endpoints for the geometry correction plugin.

POST /api/plugins/geometry_correction/correct/
  Body: {task_id, project_id, options: {...}}
  Returns: {job_id, status, message}

GET /api/plugins/geometry_correction/status/<job_id>/
  Returns: {job_id, status, result, error_message, created_at, updated_at}
"""

from __future__ import annotations

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.urls import path
import json

from .models import CorrectionJob
from .tasks import run_geometry_correction


@method_decorator(csrf_exempt, name="dispatch")
class CorrectView(View):

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        task_id = body.get("task_id")
        project_id = body.get("project_id")
        if not task_id or not project_id:
            return JsonResponse(
                {"error": "task_id and project_id are required"}, status=400
            )

        options = body.get("options", {})

        job = CorrectionJob.objects.create(
            task_id=str(task_id),
            project_id=int(project_id),
            options=options,
        )

        # Dispatch async Celery task
        async_result = run_geometry_correction.delay(job.pk)
        job.celery_task_id = async_result.id
        job.save(update_fields=["celery_task_id", "updated_at"])

        return JsonResponse(
            {
                "job_id": job.pk,
                "status": job.status,
                "message": "Correction job queued",
            },
            status=202,
        )


@method_decorator(csrf_exempt, name="dispatch")
class StatusView(View):

    def get(self, request, job_id: int):
        try:
            job = CorrectionJob.objects.get(pk=job_id)
        except CorrectionJob.DoesNotExist:
            return JsonResponse({"error": "Job not found"}, status=404)

        return JsonResponse(
            {
                "job_id": job.pk,
                "task_id": job.task_id,
                "project_id": job.project_id,
                "status": job.status,
                "result": job.result,
                "error_message": job.error_message,
                "created_at": job.created_at.isoformat(),
                "updated_at": job.updated_at.isoformat(),
            }
        )


# URL router used by plugin.py → api_mount_points()
router = [
    path("correct/", CorrectView.as_view(), name="gc_correct"),
    path("status/<int:job_id>/", StatusView.as_view(), name="gc_status"),
]
