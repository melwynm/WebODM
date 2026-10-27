from app.plugins import MountPoint, PluginBase

from .gaussian_splat.views import StatusView, TrainView


class Plugin(PluginBase):
    def include_js_files(self):
        # Keep the version in the URL so dashboard fixes are not hidden by a
        # browser's cached copy of this standalone plugin script.
        return ["main.js?v=0.2.0"]

    def include_css_files(self):
        return ["main.css?v=0.2.0"]

    def api_mount_points(self):
        return [
            MountPoint("task/(?P<pk>[^/.]+)/train$", TrainView.as_view()),
            MountPoint("task/(?P<pk>[^/.]+)/status$", StatusView.as_view()),
        ]
