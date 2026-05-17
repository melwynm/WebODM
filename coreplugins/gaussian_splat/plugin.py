from app.plugins import MountPoint, PluginBase

from .gaussian_splat.views import StatusView, TrainView


class Plugin(PluginBase):
    def include_js_files(self):
        return ["main.js"]

    def api_mount_points(self):
        return [
            MountPoint("task/(?P<pk>[^/.]+)/train$", TrainView.as_view()),
            MountPoint("task/(?P<pk>[^/.]+)/status$", StatusView.as_view()),
        ]
