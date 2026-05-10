from django.http import HttpResponse
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer, StaticHTMLRenderer
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app.api.permissions import ProjectPermissionPolicy
from app.services.project_reports import build_project_progress_report, render_progress_report_html


class ProjectProgressReport(APIView):
    permission_classes = (AllowAny,)
    renderer_classes = (JSONRenderer, BrowsableAPIRenderer, StaticHTMLRenderer)

    def get(self, request, project_pk=None):
        project = ProjectPermissionPolicy.get_project(request, project_pk)
        report = build_project_progress_report(project)
        fmt = (request.query_params.get("format") or "").lower()

        if fmt == "html":
            return HttpResponse(render_progress_report_html(report), content_type="text/html; charset=utf-8")

        return Response(report)
