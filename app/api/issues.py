from django.utils import timezone
from rest_framework import permissions, serializers, viewsets

from app import models
from app.api.permissions import ProjectPermissionPolicy
from app.models.project_issue import validate_geojson_geometry


class ProjectIssueSerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source='created_by.username')
    assigned_to_username = serializers.ReadOnlyField(source='assigned_to.username')
    task_name = serializers.ReadOnlyField(source='task.name')

    class Meta:
        model = models.ProjectIssue
        fields = (
            'id',
            'project',
            'task',
            'task_name',
            'title',
            'description',
            'issue_type',
            'status',
            'priority',
            'geometry',
            'properties',
            'created_by',
            'assigned_to',
            'assigned_to_username',
            'created_at',
            'updated_at',
            'closed_at',
        )
        read_only_fields = ('project', 'created_by', 'created_at', 'updated_at', 'closed_at')

    def validate_task(self, task):
        project = self.context.get('project')
        if task is not None and project is not None and task.project_id != project.id:
            raise serializers.ValidationError("Task must belong to this project.")
        return task

    def validate_assigned_to(self, assigned_to):
        project = self.context.get('project')
        if assigned_to is not None and project is not None:
            if not assigned_to.has_perm('view_project', project):
                raise serializers.ValidationError("Assigned user must have access to this project.")
        return assigned_to

    def validate_geometry(self, geometry):
        if geometry in ('', None):
            return None
        try:
            validate_geojson_geometry(geometry)
        except Exception as e:
            raise serializers.ValidationError(str(e))
        return geometry


class ProjectIssueViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectIssueSerializer
    permission_classes = (permissions.AllowAny,)
    filter_backends = ()
    ordering_fields = ('created_at', 'updated_at', 'priority', 'status', 'issue_type')

    def paginate_queryset(self, queryset):
        if self.paginator and self.request.query_params.get(self.paginator.page_query_param, None) is None:
            return None
        return super().paginate_queryset(queryset)

    def get_project(self, change=False):
        perms = ProjectPermissionPolicy.CHANGE if change else ProjectPermissionPolicy.VIEW
        return ProjectPermissionPolicy.get_project(self.request, self.kwargs.get('project_pk'), perms)

    def get_queryset(self):
        project = self.get_project()
        queryset = models.ProjectIssue.objects.filter(project=project).select_related(
            'project', 'task', 'created_by', 'assigned_to'
        )

        task_id = self.request.query_params.get('task')
        if task_id:
            queryset = queryset.filter(task_id=task_id)

        issue_status = self.request.query_params.get('status')
        if issue_status:
            queryset = queryset.filter(status=issue_status)

        issue_type = self.request.query_params.get('issue_type')
        if issue_type:
            queryset = queryset.filter(issue_type=issue_type)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['project'] = self.get_project(change=self.request.method not in ('GET', 'HEAD', 'OPTIONS'))
        return context

    def perform_create(self, serializer):
        project = self.get_project(change=True)
        serializer.save(project=project, created_by=self.request.user)

    def perform_update(self, serializer):
        self.get_project(change=True)
        instance = serializer.save()
        if instance.status == models.ProjectIssue.STATUS_CLOSED and instance.closed_at is None:
            instance.closed_at = timezone.now()
            instance.save(update_fields=('closed_at', 'updated_at'))

    def destroy(self, request, *args, **kwargs):
        self.get_project(change=True)
        return super().destroy(request, *args, **kwargs)
