from django.core.exceptions import ValidationError
from rest_framework import exceptions, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from app import models
from app.api.permissions import ProjectPermissionPolicy
from app.services.airtwin import build_manifest


class AirTwinTaskManifest(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, project_pk, pk):
        project = ProjectPermissionPolicy.get_project(request, project_pk, ProjectPermissionPolicy.VIEW)
        try:
            task = models.Task.objects.get(pk=pk, project=project)
        except (models.Task.DoesNotExist, ValidationError):
            raise exceptions.NotFound()
        base_url = request.build_absolute_uri("/").rstrip("/")
        return Response(build_manifest(task, base_url=base_url))
