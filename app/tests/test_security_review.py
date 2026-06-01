import json
import os
from io import StringIO
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from app.services.security_review import run_security_review


class SecurityReviewTests(SimpleTestCase):
    def _secure_settings(self):
        return override_settings(
            DEBUG=False,
            ALLOWED_HOSTS=["webodm.example.com"],
            CORS_ORIGIN_ALLOW_ALL=False,
            SESSION_COOKIE_SECURE=True,
            CSRF_COOKIE_SECURE=True,
        )

    def _secure_env(self):
        return mock.patch.dict(os.environ, {
            "WO_SSL": "YES",
            "WO_ONEDRIVE_INTAKE_DIR": "/srv/webodm/onedrive-intake",
        }, clear=True)

    def test_security_review_passes_for_hardened_static_configuration(self):
        with TemporaryDirectory() as repo_root:
            os.makedirs(os.path.join(repo_root, "app", "templates"))
            with self._secure_settings(), self._secure_env():
                summary = run_security_review(include_runtime=False, repo_root=repo_root)

        self.assertTrue(summary.ok, summary.to_dict())
        self.assertEqual(summary.counts["error"], 0)

    def test_security_review_reports_risky_static_defaults(self):
        with override_settings(
            DEBUG=True,
            REST_FRAMEWORK={
                "DEFAULT_THROTTLE_CLASSES": (),
                "DEFAULT_THROTTLE_RATES": {},
            },
        ):
            with mock.patch.dict(os.environ, {"WO_SSL": "NO"}, clear=True):
                summary = run_security_review(include_runtime=False)

        error_names = {result.name for result in summary.errors}
        self.assertIn("Debug mode", error_names)
        self.assertIn("Secure cookies", error_names)
        self.assertIn("Allowed hosts", error_names)
        self.assertIn("CORS", error_names)
        self.assertIn("Rate limiting", error_names)

    def test_security_review_detects_frontend_openai_key_references(self):
        with TemporaryDirectory() as repo_root:
            template_dir = os.path.join(repo_root, "app", "templates")
            os.makedirs(template_dir)
            with open(os.path.join(template_dir, "leak.html"), "w", encoding="utf-8") as template:
                template.write("{{ openai_api_key }}")

            with self._secure_settings(), self._secure_env():
                summary = run_security_review(include_runtime=False, repo_root=repo_root)

        self.assertFalse(summary.ok)
        self.assertIn("OpenAI key exposure", {result.name for result in summary.errors})

    def test_securityreview_json_output_is_machine_readable(self):
        stdout = StringIO()
        with TemporaryDirectory() as repo_root:
            os.makedirs(os.path.join(repo_root, "app", "templates"))
            with self._secure_settings(), self._secure_env():
                call_command(
                    "securityreview",
                    "--skip-runtime",
                    "--json",
                    stdout=stdout,
                )

        payload = json.loads(stdout.getvalue())
        self.assertIn("counts", payload)
        self.assertIn("results", payload)

    def test_securityreview_command_fails_when_errors_exist(self):
        with override_settings(DEBUG=True):
            with mock.patch.dict(os.environ, {"WO_SSL": "NO"}, clear=True):
                with self.assertRaises(CommandError):
                    call_command("securityreview", "--skip-runtime")
