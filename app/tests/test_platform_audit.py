import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import SimpleTestCase

from app.services.platform_audit import run_platform_audit


class PlatformAuditTests(SimpleTestCase):
    def test_platform_audit_passes_current_custom_surface(self):
        summary = run_platform_audit()

        self.assertTrue(summary.ok, summary.to_dict()["failures"])
        self.assertGreater(summary.counts["ok"], 50)

    def test_platformaudit_command_reports_summary(self):
        stdout = StringIO()

        call_command("platformaudit", stdout=stdout)

        self.assertIn("Platform audit complete", stdout.getvalue())

    def test_platform_audit_reports_missing_repo_files(self):
        with TemporaryDirectory() as tmp_dir:
            summary = run_platform_audit(repo_root=Path(tmp_dir))

        failures = [result.to_dict() for result in summary.failures]
        self.assertFalse(summary.ok)
        self.assertTrue(
            any(result["area"] == "docs" and result["name"] == "Pipeline source of truth" for result in failures)
        )

    def test_platformaudit_json_output_is_machine_readable(self):
        stdout = StringIO()

        call_command("platformaudit", json=True, stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertIn("counts", payload)
