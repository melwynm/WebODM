from app.plugins import PluginBase, MountPoint
from . import api


class Plugin(PluginBase):
    def include_js_files(self):
        return ['main.js']

    def include_css_files(self):
        return ['main.css']

    def api_mount_points(self):
        return [
            MountPoint('project/(?P<project_pk>[^/.]+)/missions$', api.ProjectMissionListView.as_view()),
            MountPoint('project/(?P<project_pk>[^/.]+)/missions/(?P<mission_id>[^/.]+)$', api.ProjectMissionDetailView.as_view()),
        ]
