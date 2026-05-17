import os

from django.core.exceptions import SuspiciousFileOperation, ValidationError
from django.http import Http404
from rest_framework import permissions, serializers, status, viewsets
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from app import models
from app.api.issues import ProjectIssueSerializer
from app.api.permissions import ProjectPermissionPolicy
from app.api.tasks import download_file_response
from app.models.project_issue import validate_geojson_geometry
from app.security import path_traversal_check
from app.services.textured_model_qa import build_textured_model_qa


def get_active_share(token):
    try:
        share = models.ProjectClientShare.objects.select_related('project', 'created_by').get(token=token)
    except models.ProjectClientShare.DoesNotExist:
        raise Http404

    if not share.is_active():
        raise Http404

    return share


def get_share_task(share, task_pk):
    try:
        return models.Task.objects.get(pk=task_pk, project=share.project)
    except (models.Task.DoesNotExist, ValidationError):
        raise Http404


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


class ClientPortalTaskQAAPIView(ClientPortalMixin, APIView):
    def get(self, request, token, task_pk):
        share = self.get_share()
        task = get_share_task(share, task_pk)
        data = build_textured_model_qa(task)
        data['viewer_url'] = '/client/projects/{}/tasks/{}/3d/'.format(share.token, task.id)
        data['safe_glb_url'] = '/api/client-shares/{}/tasks/{}/textured_model/'.format(share.token, task.id)
        return Response(data)


class ClientPortalTaskSceneAPIView(ClientPortalMixin, APIView):
    def get(self, request, token, task_pk):
        share = self.get_share()
        task = get_share_task(share, task_pk)
        return Response(task.potree_scene)

    def head(self, request, token, task_pk):
        self.get(request, token, task_pk)
        return Response(status=status.HTTP_200_OK)

    def post(self, request, token, task_pk):
        return Response({'detail': 'Client shares are read-only.'}, status=status.HTTP_403_FORBIDDEN)


class ClientPortalTaskTexturedModelAPIView(ClientPortalMixin, APIView):
    def get(self, request, token, task_pk):
        share = self.get_share()
        task = get_share_task(share, task_pk)
        try:
            model_file = task.get_safe_textured_model()
            return download_file_response(request, model_file, 'attachment')
        except FileNotFoundError:
            raise exceptions.NotFound("Asset does not exist")

    def head(self, request, token, task_pk):
        return self.get(request, token, task_pk)


class ClientPortalTaskAssetsAPIView(ClientPortalMixin, APIView):
    def get(self, request, token, task_pk, unsafe_asset_path):
        share = self.get_share()
        task = get_share_task(share, task_pk)

        try:
            asset_path = path_traversal_check(task.assets_path(unsafe_asset_path), task.assets_path(""))
        except SuspiciousFileOperation:
            raise exceptions.NotFound("Asset does not exist")

        if (not asset_path) or (not os.path.exists(asset_path)) or os.path.isdir(asset_path):
            raise exceptions.NotFound("Asset does not exist")

        return download_file_response(request, asset_path, 'inline')

    def head(self, request, token, task_pk, unsafe_asset_path):
        return self.get(request, token, task_pk, unsafe_asset_path)
