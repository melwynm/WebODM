import json
import os
from io import StringIO
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from app.services.production_readiness import run_production_readiness


class ProductionReadinessTests(SimpleTestCase):
    def _production_settings(self):
        return override_settings(
            DEBUG=False,
            ALLOWED_HOSTS=["webodm.example.com"],
            CORS_ORIGIN_ALLOW_ALL=False,
            SESSION_COOKIE_SECURE=True,
            CSRF_COOKIE_SECURE=True,
        )

    def _production_env(self, backup_dir):
        return mock.patch.dict(os.environ, {
            "WO_SECRET_KEY": "test-production-secret-key",
            "WO_SSL": "YES",
            "WO_BACKUP_DIR": backup_dir,
            "WO_BACKUP_RETENTION_DAYS": "14",
            "WO_MEDIA_DIR": "/srv/webodm/media",
            "WO_DB_DIR": "/srv/webodm/postgres",
        }, clear=True)

    def test_static_readiness_passes_for_hardened_configuration(self):
        with TemporaryDirectory() as backup_dir:
            with self._production_settings(), self._production_env(backup_dir):
                summary = run_production_readiness(include_runtime=False)

        self.assertTrue(summary.ok, summary.to_dict())
        self.assertEqual(summary.counts["error"], 0)

    def test_static_readiness_reports_risky_defaults(self):
        with override_settings(DEBUG=True):
            with mock.patch.dict(os.environ, {"WO_SSL": "NO"}, clear=True):
                summary = run_production_readiness(include_runtime=False)

        error_names = {result.name for result in summary.errors}
        self.assertFalse(summary.ok)
        self.assertIn("Debug mode", error_names)
        self.assertIn("Secret key", error_names)
        self.assertIn("HTTPS cookies", error_names)
        self.assertIn("Allowed hosts", error_names)
        self.assertIn("CORS", error_names)
        self.assertIn("Backup directory", error_names)

    def test_productionreadiness_json_output_is_machine_readable(self):
        stdout = StringIO()
        with TemporaryDirectory() as backup_dir:
            with self._production_settings(), self._production_env(backup_dir):
                call_command("productionreadiness", "--skip-runtime", "--json", stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["counts"]["error"], 0)

    def test_productionreadiness_command_fails_when_errors_exist(self):
        with override_settings(DEBUG=True):
            with mock.patch.dict(os.environ, {"WO_SSL": "NO"}, clear=True):
                with self.assertRaises(CommandError):
                    call_command("productionreadiness", "--skip-runtime")

    def test_enabled_airtwin_webhook_requires_url_and_secret(self):
        with TemporaryDirectory() as backup_dir:
            with self._production_settings(), self._production_env(backup_dir), override_settings(
                AIRTWIN_WEBHOOK_ENABLED=True,
                AIRTWIN_WEBHOOK_URL="",
                AIRTWIN_WEBHOOK_SECRET="",
            ):
                summary = run_production_readiness(include_runtime=False)

        self.assertIn("AirTwin webhook", {result.name for result in summary.errors})

    def test_enabled_airtwin_webhook_passes_with_complete_configuration(self):
        with TemporaryDirectory() as backup_dir:
            with self._production_settings(), self._production_env(backup_dir), override_settings(
                AIRTWIN_WEBHOOK_ENABLED=True,
                AIRTWIN_WEBHOOK_URL="http://airtwin:8080/events",
                AIRTWIN_WEBHOOK_SECRET="test-only-secret",
                AIRTWIN_OUTPUT_RETENTION_DAYS=30,
            ):
                summary = run_production_readiness(include_runtime=False)

        self.assertNotIn("AirTwin webhook", {result.name for result in summary.errors})
        result = next(item for item in summary.results if item.name == "AirTwin webhook")
        self.assertEqual(result.status, "ok")
