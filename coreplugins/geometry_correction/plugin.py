from pathlib import Path
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

from app.plugins import MountPoint, PluginBase
from app.plugins.pyutils import compute_file_md5, requirements_installed
from packaging.requirements import InvalidRequirement, Requirement

from .geometry_correction.views import CorrectView, StatusView, TaskCorrectView, TaskStatusView


def runtime_requirements_installed(requirements_file):
    for raw_line in Path(requirements_file).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            requirement = Requirement(line)
        except InvalidRequirement:
            return False

        if requirement.marker and not requirement.marker.evaluate():
            continue

        try:
            installed_version = package_version(requirement.name)
        except PackageNotFoundError:
            return False

        if requirement.specifier and not requirement.specifier.contains(installed_version, prereleases=True):
            return False

    return True


class Plugin(PluginBase):
    def check_requirements(self):
        req_file = Path(self.get_path("requirements.txt"))
        if not req_file.exists():
            return

        md5_file = Path(self.get_python_packages_path("install_md5"))
        req_md5 = compute_file_md5(str(req_file))

        if runtime_requirements_installed(req_file) or requirements_installed(str(req_file), self.get_python_packages_path()):
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
