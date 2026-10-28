from django.http import HttpResponse
from rest_framework import exceptions, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer, StaticHTMLRenderer
from rest_framework.response import Response

from app import models
from app.api.issues import ProjectIssueSerializer
from app.api.permissions import ProjectPermissionPolicy
from app.services.monitoring import (
    MonitoringError,
    ensure_monitoring_products,
    monitoring_pair_readiness,
    render_layer_payload,
)
from app.services.monitoring_runs import (
    MonitoringRunError,
    create_monitoring_run,
    monitoring_run_issues,
    publish_monitoring_run,
    retry_monitoring_run,
)
from app.services.project_reports import REPORT_TEMPLATES, build_project_progress_report, render_progress_report_html
from worker import tasks as worker_tasks


def enqueue_monitoring_compare(current_task_id, baseline_task_id, run_id, attempt_id):
    worker_tasks.generate_monitoring_compare.apply_async(
        args=(current_task_id, baseline_task_id, run_id),
        task_id=attempt_id,
    )


class MonitoringRunCreateSerializer(serializers.Serializer):
    current_task = serializers.UUIDField(required=False, allow_null=True)
    baseline_task = serializers.UUIDField(required=False, allow_null=True)
    report_template = serializers.ChoiceField(choices=tuple(REPORT_TEMPLATES), required=False)


class MonitoringRunPublishSerializer(serializers.Serializer):
    client_share = serializers.IntegerField(required=False, allow_null=True)


class ProjectMonitoringRunSerializer(serializers.ModelSerializer):
    current_task_detail = serializers.SerializerMethodField()
    baseline_task_detail = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    comparison = serializers.SerializerMethodField()
    issues = serializers.SerializerMethodField()
    issue_count = serializers.SerializerMethodField()
    created_by = serializers.ReadOnlyField(source="created_by.username")
    client_share_name = serializers.ReadOnlyField(source="client_share.name")
    portal_url = serializers.SerializerMethodField()
    report_url = serializers.SerializerMethodField()
    can_publish = serializers.SerializerMethodField()
    can_retry = serializers.SerializerMethodField()

    class Meta:
        model = models.ProjectMonitoringRun
        fields = (
            "id",
            "project",
            "current_task",
            "current_task_detail",
            "baseline_task",
            "baseline_task_detail",
            "status",
            "status_label",
            "report_template",
            "celery_task_id",
            "last_error",
            "comparison",
            "issues",
            "issue_count",
            "client_share",
            "client_share_name",
            "portal_url",
            "report_url",
            "can_publish",
            "can_retry",
            "created_by",
            "comparison_generated_at",
            "published_at",
            "created_at",
            "updated_at",
        )

    def _task_detail(self, task):
        return {
            "id": str(task.id),
            "name": task.name or str(task.id),
            "created_at": task.created_at.isoformat(),
            "available_assets": task.available_assets or [],
        }

    def get_current_task_detail(self, obj):
        return self._task_detail(obj.current_task)

    def get_baseline_task_detail(self, obj):
        return self._task_detail(obj.baseline_task)

    def get_comparison(self, obj):
        readiness = monitoring_pair_readiness(obj.current_task, obj.baseline_task)
        data = {"readiness": readiness, "output": None}
        if readiness["cache"]["ready"]:
            try:
                metadata = ensure_monitoring_products(obj.current_task, obj.baseline_task)
                data["output"] = render_layer_payload(obj.current_task, obj.baseline_task, metadata)
            except MonitoringError as exc:
                data["readiness"]["cache"]["ready"] = False
                data["readiness"]["issues"].append(str(exc))
        return data

    def _issues(self, obj):
        cache = getattr(self, "_issue_cache", None)
        if cache is None:
            cache = self._issue_cache = {}
        if obj.pk not in cache:
            cache[obj.pk] = list(monitoring_run_issues(obj))
        return cache[obj.pk]

    def get_issues(self, obj):
        return ProjectIssueSerializer(
            self._issues(obj),
            many=True,
            context={"request": self.context.get("request"), "project": obj.project},
        ).data

    def get_issue_count(self, obj):
        return len(self._issues(obj))

    def get_portal_url(self, obj):
        if obj.client_share is None:
            return None
        path = obj.client_share.portal_path()
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path

    def get_report_url(self, obj):
        path = "/api/projects/{}/monitoring-runs/{}/report/?format=html".format(obj.project_id, obj.id)
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path

    def get_can_publish(self, obj):
        return obj.status == models.ProjectMonitoringRun.STATUS_REVIEW

    def get_can_retry(self, obj):
        return obj.status == models.ProjectMonitoringRun.STATUS_FAILED


class ProjectMonitoringRunViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectMonitoringRunSerializer
    permission_classes = (permissions.AllowAny,)
    filter_backends = ()
    http_method_names = ("get", "post", "delete", "head", "options")

    def paginate_queryset(self, queryset):
        if self.paginator and self.request.query_params.get(self.paginator.page_query_param) is None:
            return None
        return super().paginate_queryset(queryset)

    def get_project(self, change=False):
        perms = ProjectPermissionPolicy.CHANGE if change else ProjectPermissionPolicy.VIEW
        return ProjectPermissionPolicy.get_project(self.request, self.kwargs.get("project_pk"), perms)

    def get_queryset(self):
        project = self.get_project(change=self.request.method not in ("GET", "HEAD", "OPTIONS"))
        return models.ProjectMonitoringRun.objects.filter(project=project).select_related(
            "project",
            "current_task",
            "baseline_task",
            "created_by",
            "client_share",
        )

    def create(self, request, *args, **kwargs):
        project = self.get_project(change=True)
        serializer = MonitoringRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run, created = create_monitoring_run(
                project,
                request.user,
                current_task_id=serializer.validated_data.get("current_task"),
                baseline_task_id=serializer.validated_data.get("baseline_task"),
                report_template=serializer.validated_data.get("report_template"),
                enqueue_comparison=enqueue_monitoring_compare,
            )
        except MonitoringRunError as exc:
            raise exceptions.ValidationError(str(exc))

        output = self.get_serializer(run)
        return Response(output.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=("post",))
    def retry(self, request, project_pk=None, pk=None):
        run = self.get_object()
        try:
            run = retry_monitoring_run(run, enqueue_comparison=enqueue_monitoring_compare)
        except MonitoringRunError as exc:
            raise exceptions.ValidationError(str(exc))
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=("post",))
    def publish(self, request, project_pk=None, pk=None):
        run = self.get_object()
        serializer = MonitoringRunPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = publish_monitoring_run(
                run,
                request.user,
                client_share_id=serializer.validated_data.get("client_share"),
            )
        except MonitoringRunError as exc:
            raise exceptions.ValidationError(str(exc))
        return Response(self.get_serializer(run).data)

    @action(
        detail=True,
        methods=("get",),
        renderer_classes=(JSONRenderer, BrowsableAPIRenderer, StaticHTMLRenderer),
    )
    def report(self, request, project_pk=None, pk=None):
        run = self.get_object()
        report = run.report_snapshot or build_project_progress_report(
            run.project,
            template=run.report_template,
            monitoring_run=run,
        )
        if (request.query_params.get("format") or "").lower() == "html":
            return HttpResponse(render_progress_report_html(report), content_type="text/html; charset=utf-8")
        return Response(report)
