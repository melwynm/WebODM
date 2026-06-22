from django.core.exceptions import ValidationError
from rest_framework import exceptions, permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from app import models
from app.api.permissions import ProjectPermissionPolicy
from app.services.airtwin import (
    SUPPORTED_ASSETS,
    acknowledge_import,
    build_manifest,
    get_or_create_import_state,
    serialize_import_state,
)


class AirTwinImportAcknowledgmentSerializer(serializers.Serializer):
    version = serializers.ChoiceField(choices=(1,))
    eventId = serializers.UUIDField()
    status = serializers.ChoiceField(choices=(
        models.AirTwinImportState.STATUS_IMPORTING,
        models.AirTwinImportState.STATUS_IMPORTED,
        models.AirTwinImportState.STATUS_FAILED,
    ))
    importedAssets = serializers.ListField(
        child=serializers.ChoiceField(choices=SUPPORTED_ASSETS),
        required=False,
        default=list,
    )
    message = serializers.CharField(required=False, allow_blank=True, default="", max_length=4000)


def get_task(project, pk):
    try:
        return models.Task.objects.select_related("airtwin_import_state").get(pk=pk, project=project)
    except (models.Task.DoesNotExist, ValidationError):
        raise exceptions.NotFound()


class AirTwinTaskManifest(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, project_pk, pk):
        project = ProjectPermissionPolicy.get_project(request, project_pk, ProjectPermissionPolicy.VIEW)
        task = get_task(project, pk)
        get_or_create_import_state(task)
        base_url = request.build_absolute_uri("/").rstrip("/")
        return Response(build_manifest(task, base_url=base_url))


class AirTwinTaskImportStatus(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, project_pk, pk):
        project = ProjectPermissionPolicy.get_project(request, project_pk, ProjectPermissionPolicy.VIEW)
        task = get_task(project, pk)
        return Response(serialize_import_state(task))

    def post(self, request, project_pk, pk):
        project = ProjectPermissionPolicy.get_project(request, project_pk, ProjectPermissionPolicy.VIEW)
        if request.user != project.owner and not request.user.has_perm(
            ProjectPermissionPolicy.AIRTWIN_ACKNOWLEDGE[0], project
        ):
            raise exceptions.NotFound()
        task = get_task(project, pk)
        serializer = AirTwinImportAcknowledgmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            state = acknowledge_import(
                task,
                event_id=serializer.validated_data["eventId"],
                status=serializer.validated_data["status"],
                imported_assets=serializer.validated_data["importedAssets"],
                message=serializer.validated_data["message"],
            )
        except ValidationError as error:
            detail = getattr(error, "message_dict", None) or error.messages
            raise exceptions.ValidationError(detail=detail)
        return Response(serialize_import_state(task, state=state))
