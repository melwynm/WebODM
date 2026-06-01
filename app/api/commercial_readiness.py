from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app import models
from app.api.permissions import ProjectPermissionPolicy
from app.services.commercial_readiness import (
    MANUAL_FIELDS,
    build_project_commercial_readiness,
    get_or_create_project_commercial_readiness,
    normalize_package,
)


class CommercialReadinessSerializer(serializers.Serializer):
    package = serializers.ChoiceField(
        choices=[choice[0] for choice in models.ProjectCommercialReadiness.PACKAGE_CHOICES],
        required=False,
    )
    deliverables_reviewed = serializers.BooleanField(required=False)
    human_reviewed = serializers.BooleanField(required=False)
    report_reviewed = serializers.BooleanField(required=False)
    client_share_reviewed = serializers.BooleanField(required=False)
    legal_disclaimer_reviewed = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class ProjectCommercialReadiness(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, project_pk=None):
        project = ProjectPermissionPolicy.get_project(request, project_pk, ProjectPermissionPolicy.VIEW)
        package = normalize_package(request.query_params.get("package")) if request.query_params.get("package") else None
        return Response(build_project_commercial_readiness(project, package=package))

    def patch(self, request, project_pk=None):
        project = ProjectPermissionPolicy.get_project(request, project_pk, ProjectPermissionPolicy.CHANGE)
        serializer = CommercialReadinessSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        readiness = get_or_create_project_commercial_readiness(project)
        for field in MANUAL_FIELDS:
            if field in serializer.validated_data:
                setattr(readiness, field, serializer.validated_data[field])
        if "package" in serializer.validated_data:
            readiness.package = serializer.validated_data["package"]
        if "notes" in serializer.validated_data:
            readiness.notes = serializer.validated_data["notes"]
        readiness.updated_by = request.user if request.user.is_authenticated else None
        readiness.save()

        return Response(build_project_commercial_readiness(project))
