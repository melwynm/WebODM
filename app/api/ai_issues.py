from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app import models
from app.api.issues import ProjectIssueSerializer
from app.api.permissions import ProjectPermissionPolicy
from app.services.ai_issue_detection import (
    AIIssueDetectionError,
    CONFIRMATION_TOKEN_MAX_AGE,
    create_confirmation_token,
    create_review_issues,
    detect_ai_issue_candidates,
    load_confirmation_token,
)


class AIIssueDetection(APIView):
    permission_classes = (AllowAny,)

    def get_task(self, project, task_id, field_name="task"):
        if not task_id:
            return None
        try:
            return models.Task.objects.get(pk=task_id, project=project)
        except (models.Task.DoesNotExist, DjangoValidationError):
            raise exceptions.ValidationError({field_name: "Task must belong to this project."})

    def get_monitoring_run(self, project, run_id):
        if not run_id:
            return None
        try:
            return models.ProjectMonitoringRun.objects.get(pk=run_id, project=project)
        except (models.ProjectMonitoringRun.DoesNotExist, DjangoValidationError):
            raise exceptions.ValidationError({"monitoring_run": "Monitoring run must belong to this project."})

    def validate_monitoring_context(self, monitoring_run, task, compare_task):
        if monitoring_run is None:
            return
        if task is None or compare_task is None:
            raise exceptions.ValidationError("Monitoring run review requires current and baseline tasks.")
        if monitoring_run.current_task_id != task.id or monitoring_run.baseline_task_id != compare_task.id:
            raise exceptions.ValidationError("Tasks do not match the selected monitoring run.")
        if monitoring_run.status not in (
            models.ProjectMonitoringRun.STATUS_REVIEW,
            models.ProjectMonitoringRun.STATUS_PUBLISHED,
        ):
            raise exceptions.ValidationError("Monitoring run is not ready for AI review.")

    def post(self, request, project_pk=None):
        project = ProjectPermissionPolicy.get_project(request, project_pk, ProjectPermissionPolicy.CHANGE)

        create = request.data.get("create", True)
        if isinstance(create, str):
            create = create.lower() not in ("0", "false", "no")
        else:
            create = bool(create)

        confirmation_token = request.data.get("confirmation_token")
        task = None
        compare_task = None
        monitoring_run = None

        try:
            if confirmation_token:
                if not create:
                    raise AIIssueDetectionError("AI issue confirmation requires create=true.")
                result = load_confirmation_token(confirmation_token, project)
                task = self.get_task(project, result.pop("task_id", None))
                compare_task = self.get_task(
                    project,
                    result.pop("compare_task_id", None),
                    field_name="compare_task",
                )
                monitoring_run = self.get_monitoring_run(
                    project,
                    result.pop("monitoring_run_id", None),
                )
            else:
                task = self.get_task(project, request.data.get("task"))
                compare_task = self.get_task(
                    project,
                    request.data.get("compare_task"),
                    field_name="compare_task",
                )
                monitoring_run = self.get_monitoring_run(project, request.data.get("monitoring_run"))
                source = request.data.get("source", "auto")
                try:
                    max_images = int(request.data.get("max_images", 3))
                except (TypeError, ValueError):
                    raise exceptions.ValidationError({"max_images": "max_images must be an integer."})
                max_images = max(1, min(max_images, 8))
                self.validate_monitoring_context(monitoring_run, task, compare_task)
                result = detect_ai_issue_candidates(
                    project,
                    task=task,
                    compare_task=compare_task,
                    source=source,
                    max_images=max_images,
                )
            self.validate_monitoring_context(monitoring_run, task, compare_task)
        except AIIssueDetectionError as e:
            raise exceptions.ValidationError(str(e))

        issues = []
        created_count = 0
        if create and result["candidates"]:
            issues, created_count = create_review_issues(
                project,
                request.user,
                result["candidates"],
                task=task,
                model=result["model"],
                response_id=result.get("raw_response_id"),
                confirmation_id=result.get("confirmation_id"),
                extra_properties={
                    "monitoring_run_id": str(monitoring_run.id),
                    "monitoring_baseline_task_id": str(compare_task.id),
                } if monitoring_run is not None else None,
            )

        preview_token = None
        if not create and result["candidates"]:
            preview_token = create_confirmation_token(
                project,
                task,
                result,
                compare_task=compare_task,
                monitoring_run=monitoring_run,
            )

        return Response({
            "model": result["model"],
            "source_count": result["source_count"],
            "candidate_count": len(result["candidates"]),
            "candidates": result["candidates"],
            "created_count": created_count,
            "issues": ProjectIssueSerializer(issues, many=True, context={"request": request, "project": project}).data,
            "openai_response_id": result.get("raw_response_id"),
            "confirmation_token": preview_token,
            "confirmation_expires_in": CONFIRMATION_TOKEN_MAX_AGE if preview_token else None,
        })
