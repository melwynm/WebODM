"""
Tests for WebODM plugin packaging and server-side loading.
"""

import os
from pathlib import Path
import unittest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webodm.settings")

import django

django.setup()

from app.plugins.functions import valid_plugin
from coreplugins.geometry_correction.plugin import Plugin


class TestPluginRuntime(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
