from rest_framework import permissions, serializers, viewsets

from app import models
from app.api.permissions import ProjectPermissionPolicy


class ProjectDesignOverlaySerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source='created_by.username')
    file_url = serializers.SerializerMethodField()
    extension = serializers.ReadOnlyField()
    is_map_overlay = serializers.ReadOnlyField()

    class Meta:
        model = models.ProjectDesignOverlay
        fields = (
            'id',
            'project',
            'name',
            'description',
            'file',
            'file_url',
            'source_filename',
            'extension',
            'is_map_overlay',
            'created_by',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'project',
            'file_url',
            'source_filename',
            'extension',
            'is_map_overlay',
            'created_by',
            'created_at',
            'updated_at',
        )

    def get_file_url(self, obj):
        request = self.context.get('request')
        if not obj.file:
            return ''
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url

    def validate(self, attrs):
        file_obj = attrs.get('file') or getattr(self.instance, 'file', None)
        name = attrs.get('name')
        if not name and file_obj:
            attrs['name'] = file_obj.name.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        return attrs


class ProjectDesignOverlayViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectDesignOverlaySerializer
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
        project = self.get_project()
        return models.ProjectDesignOverlay.objects.filter(project=project).select_related('project', 'created_by')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['project'] = self.get_project(change=self.request.method not in ('GET', 'HEAD', 'OPTIONS'))
        return context

    def perform_create(self, serializer):
        project = self.get_project(change=True)
        file_obj = serializer.validated_data.get('file')
        serializer.save(
            project=project,
            created_by=self.request.user,
            source_filename=getattr(file_obj, 'name', ''),
        )

    def perform_update(self, serializer):
        self.get_project(change=True)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        self.get_project(change=True)
        return super().destroy(request, *args, **kwargs)
