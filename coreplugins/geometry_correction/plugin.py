from app.plugins import MountPoint, PluginBase

from .geometry_correction.views import CorrectView, StatusView, TaskCorrectView, TaskStatusView


class Plugin(PluginBase):
    def include_js_files(self):
        return ["main.js"]

    def api_mount_points(self):
        return [
            MountPoint("correct/$", CorrectView.as_view()),
            MountPoint("status/(?P<job_id>[^/.]+)/$", StatusView.as_view()),
            MountPoint("task/(?P<pk>[^/.]+)/correct$", TaskCorrectView.as_view()),
            MountPoint("task/(?P<pk>[^/.]+)/status$", TaskStatusView.as_view()),
        ]
