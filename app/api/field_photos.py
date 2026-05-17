import json

from rest_framework import permissions, serializers, viewsets

from app import models
from app.api.permissions import ProjectPermissionPolicy
from app.models.project_field_photo import validate_point_geometry


class ProjectFieldPhotoSerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source='created_by.username')
    task_name = serializers.ReadOnlyField(source='task.name')
    image_url = serializers.SerializerMethodField()
    longitude = serializers.ReadOnlyField()
    latitude = serializers.ReadOnlyField()

    class Meta:
        model = models.ProjectFieldPhoto
        fields = (
            'id',
            'project',
            'task',
            'task_name',
            'name',
            'description',
            'image',
            'image_url',
            'source_filename',
            'location',
            'longitude',
            'latitude',
            'is_360',
            'captured_at',
            'altitude',
            'heading',
            'properties',
            'created_by',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'project',
            'image_url',
            'source_filename',
            'longitude',
            'latitude',
            'created_by',
            'created_at',
            'updated_at',
        )

    def get_image_url(self, obj):
        request = self.context.get('request')
        if not obj.image:
            return ''
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url

    def validate_task(self, task):
        project = self.context.get('project')
        if task is not None and project is not None and task.project_id != project.id:
            raise serializers.ValidationError("Task must belong to this project.")
        return task

    def validate_location(self, location):
        if isinstance(location, str):
            try:
                location = json.loads(location)
            except ValueError:
                raise serializers.ValidationError("Location must be valid GeoJSON.")
        try:
            validate_point_geometry(location)
        except Exception as e:
            raise serializers.ValidationError(str(e))
        return location

    def validate(self, attrs):
        image = attrs.get('image') or getattr(self.instance, 'image', None)
        if not attrs.get('name') and image:
            attrs['name'] = image.name.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        return attrs


class ProjectFieldPhotoViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectFieldPhotoSerializer
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
        queryset = models.ProjectFieldPhoto.objects.filter(project=project).select_related(
            'project', 'task', 'created_by'
        )

        task_id = self.request.query_params.get('task')
        if task_id:
            queryset = queryset.filter(task_id=task_id)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['project'] = self.get_project(change=self.request.method not in ('GET', 'HEAD', 'OPTIONS'))
        return context

    def perform_create(self, serializer):
        project = self.get_project(change=True)
        image = serializer.validated_data.get('image')
        serializer.save(
            project=project,
            created_by=self.request.user,
            source_filename=getattr(image, 'name', ''),
        )

    def perform_update(self, serializer):
        self.get_project(change=True)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        self.get_project(change=True)
        return super().destroy(request, *args, **kwargs)
