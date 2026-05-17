from django.core.exceptions import ValidationError
from rest_framework import exceptions, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from app import models
from app.api.permissions import ProjectPermissionPolicy
from app.services.textured_model_qa import build_textured_model_qa


class TexturedModelQA(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, project_pk, pk):
        project = ProjectPermissionPolicy.get_project(request, project_pk, ProjectPermissionPolicy.VIEW)
        try:
            task = models.Task.objects.get(pk=pk, project=project)
        except (models.Task.DoesNotExist, ValidationError):
            raise exceptions.NotFound()
        return Response(build_textured_model_qa(task))
