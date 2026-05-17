from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app import models
from app.api.issues import ProjectIssueSerializer
from app.api.permissions import ProjectPermissionPolicy
from app.services.ai_issue_detection import (
    AIIssueDetectionError,
    create_review_issues,
    detect_ai_issue_candidates,
)


class AIIssueDetection(APIView):
    permission_classes = (AllowAny,)

    def post(self, request, project_pk=None):
        project = ProjectPermissionPolicy.get_project(request, project_pk, ProjectPermissionPolicy.CHANGE)

        task = None
        task_id = request.data.get("task")
        if task_id:
            try:
                task = models.Task.objects.get(pk=task_id, project=project)
            except models.Task.DoesNotExist:
                raise exceptions.ValidationError({"task": "Task must belong to this project."})

        source = request.data.get("source", "auto")
        create = request.data.get("create", True)
        if isinstance(create, str):
            create = create.lower() not in ("0", "false", "no")

        try:
            max_images = int(request.data.get("max_images", 3))
        except (TypeError, ValueError):
            raise exceptions.ValidationError({"max_images": "max_images must be an integer."})
        max_images = max(1, min(max_images, 8))

        try:
            result = detect_ai_issue_candidates(
                project,
                task=task,
                source=source,
                max_images=max_images,
            )
        except AIIssueDetectionError as e:
            raise exceptions.ValidationError(str(e))

        issues = []
        if create and result["candidates"]:
            issues = create_review_issues(project, request.user, result["candidates"], task=task)

        return Response({
            "model": result["model"],
            "source_count": result["source_count"],
            "candidate_count": len(result["candidates"]),
            "candidates": result["candidates"],
            "created_count": len(issues),
            "issues": ProjectIssueSerializer(issues, many=True, context={"request": request, "project": project}).data,
            "openai_response_id": result.get("raw_response_id"),
        })
