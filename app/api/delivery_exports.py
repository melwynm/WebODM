from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from app.api.permissions import ProjectPermissionPolicy
from app.services.delivery_exports import build_project_delivery_bundle


class ProjectDeliveryExport(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, project_pk=None):
        project = ProjectPermissionPolicy.get_project(request, project_pk, ProjectPermissionPolicy.VIEW)
        filename, payload, _manifest = build_project_delivery_bundle(
            project,
            template=request.query_params.get("template"),
        )
        response = HttpResponse(payload, content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response
