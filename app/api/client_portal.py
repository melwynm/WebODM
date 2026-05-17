from django.http import Http404
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from app import models
from app.api.issues import ProjectIssueSerializer
from app.api.permissions import ProjectPermissionPolicy
from app.models.project_issue import validate_geojson_geometry


def get_active_share(token):
    try:
        share = models.ProjectClientShare.objects.select_related('project', 'created_by').get(token=token)
    except models.ProjectClientShare.DoesNotExist:
        raise Http404

    if not share.is_active():
        raise Http404

    return share


class ProjectClientShareSerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source='created_by.username')
    portal_url = serializers.SerializerMethodField()

    class Meta:
        model = models.ProjectClientShare
        fields = (
            'id',
            'project',
            'name',
            'token',
            'role',
            'enabled',
            'expires_at',
            'portal_url',
            'created_by',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('project', 'token', 'portal_url', 'created_by', 'created_at', 'updated_at')

    def get_portal_url(self, obj):
        request = self.context.get('request')
        path = obj.portal_path()
        return request.build_absolute_uri(path) if request else path


class ProjectClientShareViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectClientShareSerializer
    permission_classes = (permissions.AllowAny,)
    filter_backends = ()

    def paginate_queryset(self, queryset):
        if self.paginator and self.request.query_params.get(self.paginator.page_query_param, None) is None:
            return None
        return super().paginate_queryset(queryset)

    def get_project(self, change=False):
        perms = ProjectPermissionPolicy.CHANGE if change else ProjectPermissionPolicy.VIEW
        return ProjectPermissionPolicy.get_project(self.request, self.kwargs.get('project_pk'), perms)

    def get_queryset(self):
        project = self.get_project(change=self.request.method not in ('GET', 'HEAD', 'OPTIONS'))
        return models.ProjectClientShare.objects.filter(project=project).select_related('project', 'created_by')

    def perform_create(self, serializer):
        project = self.get_project(change=True)
        serializer.save(project=project, created_by=self.request.user)

    def perform_update(self, serializer):
        self.get_project(change=True)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        self.get_project(change=True)
        return super().destroy(request, *args, **kwargs)


class ProjectClientCommentSerializer(serializers.ModelSerializer):
    task_name = serializers.ReadOnlyField(source='task.name')
    issue_title = serializers.ReadOnlyField(source='issue.title')

    class Meta:
        model = models.ProjectClientComment
        fields = (
            'id',
            'project',
            'share',
            'task',
            'task_name',
            'issue',
            'issue_title',
            'author_name',
            'author_email',
            'body',
            'geometry',
            'created_at',
        )
        read_only_fields = ('project', 'share', 'created_at')

    def validate_task(self, task):
        project = self.context.get('project')
        if task is not None and project is not None and task.project_id != project.id:
            raise serializers.ValidationError("Task must belong to this project.")
        return task

    def validate_issue(self, issue):
        project = self.context.get('project')
        if issue is not None and project is not None and issue.project_id != project.id:
            raise serializers.ValidationError("Issue must belong to this project.")
        return issue

    def validate_geometry(self, geometry):
        if geometry in ('', None):
            return None
        try:
            validate_geojson_geometry(geometry)
        except Exception as e:
            raise serializers.ValidationError(str(e))
        return geometry


class ClientPortalMixin:
    permission_classes = (permissions.AllowAny,)

    def get_share(self):
        return get_active_share(self.kwargs.get('token'))


class ClientPortalAPIView(ClientPortalMixin, APIView):
    def get(self, request, token):
        share = self.get_share()
        project = share.project
        tasks = project.task_set.order_by('-created_at').values(
            'id', 'name', 'created_at', 'processing_time', 'status'
        )
        issues = models.ProjectIssue.objects.filter(project=project).exclude(
            status=models.ProjectIssue.STATUS_CLOSED
        ).select_related('project', 'task', 'created_by', 'assigned_to')
        comments = models.ProjectClientComment.objects.filter(project=project, share=share).select_related(
            'task', 'issue'
        )

        return Response({
            'share': ProjectClientShareSerializer(share, context={'request': request}).data,
            'project': project.get_public_info(),
            'tasks': list(tasks),
            'issues': ProjectIssueSerializer(
                issues,
                many=True,
                context={'request': request, 'project': project},
            ).data,
            'comments': ProjectClientCommentSerializer(comments, many=True).data,
        })


class ClientPortalCommentsAPIView(ClientPortalMixin, APIView):
    def get(self, request, token):
        share = self.get_share()
        comments = models.ProjectClientComment.objects.filter(project=share.project, share=share).select_related(
            'task', 'issue'
        )
        return Response(ProjectClientCommentSerializer(comments, many=True).data)

    def post(self, request, token):
        share = self.get_share()
        if share.role != models.ProjectClientShare.ROLE_REVIEWER:
            return Response(
                {'detail': 'This client share is read-only.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ProjectClientCommentSerializer(data=request.data, context={'project': share.project})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(project=share.project, share=share)
        return Response(ProjectClientCommentSerializer(comment).data, status=status.HTTP_201_CREATED)
