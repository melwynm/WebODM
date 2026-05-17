from django.urls import include, re_path

from app.api.presets import PresetViewSet
from app.plugins.views import api_view_handler
from .projects import ProjectViewSet
from .tasks import TaskViewSet, TaskDownloads, TaskThumbnail, TaskAssets, TaskBackup, TaskAssetsImport, TaskSafeTexturedModel
from .imageuploads import Thumbnail, ImageDownload
from .processingnodes import ProcessingNodeViewSet, ProcessingNodeOptionsView
from .admin import AdminUserViewSet, AdminGroupViewSet, AdminProfileViewSet
from rest_framework_nested import routers
from .token import ObtainJSONWebTokenView, TokenView, TokenRegenerateView
from .tiler import TileJson, Bounds, Metadata, Tiles, Export
from .potree import Scene, CameraView
from .monitoring import MonitoringCandidates, MonitoringCompare, MonitoringTiles, MonitoringTimeline
from .issues import ProjectIssueViewSet
from .design_overlays import ProjectDesignOverlayViewSet
from .field_photos import ProjectFieldPhotoViewSet
from .client_portal import ClientPortalAPIView, ClientPortalCommentsAPIView, ProjectClientShareViewSet
from .feature_validation import FeatureValidationViewSet
from .reports import ProjectProgressReport
from .ai_issues import AIIssueDetection
from .workers import CheckTask, GetTaskResult
from .status import APIStatus
from .users import UsersList
from .externalauth import ExternalTokenAuth
from webodm import settings

router = routers.DefaultRouter()
router.register(r'projects', ProjectViewSet)
router.register(r'processingnodes', ProcessingNodeViewSet)
router.register(r'presets', PresetViewSet, basename='presets')
router.register(r'feature-validations', FeatureValidationViewSet, basename='feature-validations')

tasks_router = routers.NestedSimpleRouter(router, r'projects', lookup='project')
tasks_router.register(r'tasks', TaskViewSet, basename='projects-tasks')
tasks_router.register(r'issues', ProjectIssueViewSet, basename='projects-issues')
tasks_router.register(r'design-overlays', ProjectDesignOverlayViewSet, basename='projects-design-overlays')
tasks_router.register(r'field-photos', ProjectFieldPhotoViewSet, basename='projects-field-photos')
tasks_router.register(r'client-shares', ProjectClientShareViewSet, basename='projects-client-shares')

admin_router = routers.DefaultRouter()
admin_router.register(r'admin/users', AdminUserViewSet, basename='admin-users')
admin_router.register(r'admin/groups', AdminGroupViewSet, basename='admin-groups')
admin_router.register(r'admin/profiles', AdminProfileViewSet, basename='admin-profiles')

urlpatterns = [
    re_path(r'^status/$', APIStatus.as_view(), name='api_status'),
    re_path(r'processingnodes/options/$', ProcessingNodeOptionsView.as_view()),

    re_path(r'^', include(router.urls)),
    re_path(r'^', include(tasks_router.urls)),
    re_path(r'^', include(admin_router.urls)),

    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/(?P<tile_type>orthophoto|thermal|dsm|dtm)/tiles\.json$', TileJson.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/(?P<tile_type>orthophoto|thermal|dsm|dtm)/bounds$', Bounds.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/(?P<tile_type>orthophoto|thermal|dsm|dtm)/metadata$', Metadata.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/(?P<tile_type>orthophoto|thermal|dsm|dtm)/tiles/(?P<z>[\d]+)/(?P<x>[\d]+)/(?P<y>[\d]+)\.?(?P<ext>png|jpg|webp)?$', Tiles.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/(?P<tile_type>orthophoto|thermal|dsm|dtm)/tiles/(?P<z>[\d]+)/(?P<x>[\d]+)/(?P<y>[\d]+)@(?P<scale>[\d]+)x\.?(?P<ext>png|jpg|webp)?$', Tiles.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/(?P<asset_type>orthophoto|dsm|dtm|georeferenced_model)/export$', Export.as_view()),

    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/download/(?P<asset>.+)$', TaskDownloads.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/textured_model/$', TaskSafeTexturedModel.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/assets/(?P<unsafe_asset_path>.+)$', TaskAssets.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/import$', TaskAssetsImport.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/thumbnail$', TaskThumbnail.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/backup$', TaskBackup.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/images/thumbnail/(?P<image_filename>.+)$', Thumbnail.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/images/download/(?P<image_filename>.+)$', ImageDownload.as_view()),

    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/3d/scene$', Scene.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/3d/cameraview$', CameraView.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/monitoring/timeline$', MonitoringTimeline.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/reports/progress$', ProjectProgressReport.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/ai/issue-detection$', AIIssueDetection.as_view()),
    re_path(r'client-shares/(?P<token>[^/.]+)/$', ClientPortalAPIView.as_view(), name='api_client_portal'),
    re_path(r'client-shares/(?P<token>[^/.]+)/comments/$', ClientPortalCommentsAPIView.as_view(), name='api_client_portal_comments'),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/monitoring/candidates$', MonitoringCandidates.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/monitoring/compare$', MonitoringCompare.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/monitoring/(?P<compare_task_pk>[^/.]+)/(?P<layer_type>aligned|change|dsm_delta|dtm_delta)/tiles/(?P<z>[\d]+)/(?P<x>[\d]+)/(?P<y>[\d]+)\.(?P<ext>png|jpg|webp)$', MonitoringTiles.as_view()),
    re_path(r'projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/monitoring/(?P<compare_task_pk>[^/.]+)/(?P<layer_type>aligned|change|dsm_delta|dtm_delta)/tiles/(?P<z>[\d]+)/(?P<x>[\d]+)/(?P<y>[\d]+)@(?P<scale>[\d]+)x\.(?P<ext>png|jpg|webp)$', MonitoringTiles.as_view()),

    re_path(r'workers/check/(?P<celery_task_id>.+)', CheckTask.as_view()),
    re_path(r'workers/get/(?P<celery_task_id>.+)', GetTaskResult.as_view()),

    re_path(r'^auth/', include('rest_framework.urls')),
    re_path(r'^token/$', TokenView.as_view(), name='api_token'),
    re_path(r'^token/regenerate/$', TokenRegenerateView.as_view(), name='api_token_regenerate'),
    re_path(r'^token-auth/', ObtainJSONWebTokenView.as_view()),

    re_path(r'^plugins/(?P<plugin_name>[^/.]+)/(.*)$', api_view_handler),
]

if settings.ENABLE_USERS_API:
    urlpatterns.append(re_path(r'users', UsersList.as_view()))

if settings.EXTERNAL_AUTH_ENDPOINT != '':
    urlpatterns.append(re_path(r'^external-token-auth/', ExternalTokenAuth.as_view()))
