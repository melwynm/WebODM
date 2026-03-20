from pathlib import Path

from app.plugins import MountPoint, PluginBase
from app.plugins.pyutils import compute_file_md5, requirements_installed

from .geometry_correction.views import CorrectView, StatusView, TaskCorrectView, TaskStatusView


class Plugin(PluginBase):
    def check_requirements(self):
        req_file = Path(self.get_path("requirements.txt"))
        if not req_file.exists():
            return

        md5_file = Path(self.get_python_packages_path("install_md5"))
        req_md5 = compute_file_md5(str(req_file))

        if requirements_installed(str(req_file), self.get_python_packages_path()):
            try:
                if not md5_file.exists():
                    md5_file.parent.mkdir(parents=True, exist_ok=True)
                    md5_file.write_text(req_md5, encoding="utf-8")
                    return

                if md5_file.read_text(encoding="utf-8").strip() == req_md5:
                    return
            except OSError:
                pass

        super().check_requirements()

    def include_js_files(self):
        return ["main.js"]

    def api_mount_points(self):
        return [
            MountPoint("correct/$", CorrectView.as_view()),
            MountPoint("status/(?P<job_id>[^/.]+)/$", StatusView.as_view()),
            MountPoint("task/(?P<pk>[^/.]+)/correct$", TaskCorrectView.as_view()),
            MountPoint("task/(?P<pk>[^/.]+)/status$", TaskStatusView.as_view()),
        ]
