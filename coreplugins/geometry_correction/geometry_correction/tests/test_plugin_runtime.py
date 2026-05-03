"""
Tests for WebODM plugin packaging and server-side loading.
"""

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from importlib.metadata import PackageNotFoundError

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webodm.settings")

import django

django.setup()

from app.plugins import PluginBase
from app.plugins.functions import valid_plugin
from coreplugins.geometry_correction.plugin import Plugin
from coreplugins.geometry_correction.plugin import runtime_requirements_installed


class TestPluginRuntime(unittest.TestCase):
    def test_plugin_package_exports_plugin_class(self):
        from coreplugins.geometry_correction import Plugin as PackagePlugin

        self.assertIs(PackagePlugin, Plugin)

    def test_plugin_root_matches_webodm_plugin_layout(self):
        plugin_root = Path(__file__).resolve().parents[2]
        self.assertTrue(valid_plugin(str(plugin_root)))

    def test_plugin_registers_expected_api_mount_points(self):
        plugin = Plugin()
        mount_points = plugin.api_mount_points()
        self.assertEqual(len(mount_points), 4)
        urls = [mount_point.url for mount_point in mount_points]
        self.assertIn("correct/$", urls)
        self.assertIn("status/(?P<job_id>[^/.]+)/$", urls)

    def test_plugin_serves_main_js(self):
        plugin = Plugin()
        self.assertEqual(plugin.include_js_files(), ["main.js"])

    def test_plugin_marks_baked_requirements_when_marker_missing(self):
        plugin = Plugin()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            req_file = root / "requirements.txt"
            packages_dir = root / "site-packages"
            req_file.write_text("open3d>=0.17.0\n", encoding="utf-8")

            with mock.patch("coreplugins.geometry_correction.plugin.requirements_installed", return_value=True), \
                 mock.patch("coreplugins.geometry_correction.plugin.compute_file_md5", return_value="abc123"), \
                 mock.patch.object(PluginBase, "check_requirements") as base_check, \
                 mock.patch.object(plugin, "get_path", side_effect=lambda *parts: str(root.joinpath(*parts))), \
                 mock.patch.object(plugin, "get_python_packages_path", side_effect=lambda *parts: str(packages_dir.joinpath(*parts))):
                plugin.check_requirements()

            self.assertTrue((packages_dir / "install_md5").exists())
            self.assertEqual((packages_dir / "install_md5").read_text(encoding="utf-8"), "abc123")
            base_check.assert_not_called()

    def test_plugin_falls_back_to_base_install_when_marker_is_stale(self):
        plugin = Plugin()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            req_file = root / "requirements.txt"
            packages_dir = root / "site-packages"
            packages_dir.mkdir(parents=True, exist_ok=True)
            req_file.write_text("open3d>=0.17.0\n", encoding="utf-8")
            (packages_dir / "install_md5").write_text("stale", encoding="utf-8")

            with mock.patch("coreplugins.geometry_correction.plugin.requirements_installed", return_value=True), \
                 mock.patch("coreplugins.geometry_correction.plugin.compute_file_md5", return_value="fresh"), \
                 mock.patch.object(PluginBase, "check_requirements") as base_check, \
                 mock.patch.object(plugin, "get_path", side_effect=lambda *parts: str(root.joinpath(*parts))), \
                 mock.patch.object(plugin, "get_python_packages_path", side_effect=lambda *parts: str(packages_dir.joinpath(*parts))):
                plugin.check_requirements()

            base_check.assert_called_once()

    def test_runtime_requirements_installed_handles_extras(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "requirements.txt"
            req_file.write_text("laspy[lazrs]>=2.4.0\n", encoding="utf-8")

            with mock.patch("coreplugins.geometry_correction.plugin.package_version", return_value="2.6.1"):
                self.assertTrue(runtime_requirements_installed(req_file))

    def test_runtime_requirements_installed_rejects_missing_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "requirements.txt"
            req_file.write_text("open3d>=0.17.0\n", encoding="utf-8")

            with mock.patch("coreplugins.geometry_correction.plugin.package_version", side_effect=PackageNotFoundError):
                self.assertFalse(runtime_requirements_installed(req_file))


if __name__ == "__main__":
    unittest.main()
