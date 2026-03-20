"""
Tests for webhook delivery and task-level notification wiring.
"""

import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webodm.settings")

import django

django.setup()

from nodeodm import status_codes

from geometry_correction import tasks as gc_tasks
from geometry_correction.algorithms.webhook import WebhookConfig, send_completion_webhook


class FakeTask:
    def __init__(self, root, task_id="task-123", project_id=7, status=status_codes.COMPLETED):
        self.id = task_id
        self.project = SimpleNamespace(id=project_id, public=False)
        self.public = False
        self.status = status
        self.root = Path(root)

    def data_path(self, *parts):
        return str(self.root.joinpath("data", *parts))

    def assets_path(self, *parts):
        return str(self.root.joinpath("assets", *parts))


class TestWebhookDelivery(unittest.TestCase):
    @mock.patch("geometry_correction.algorithms.webhook.requests.post")
    def test_send_completion_webhook_returns_true_on_200(self, mock_post):
        mock_post.return_value.status_code = 200
        config = WebhookConfig(url="https://example.com/hook")
        self.assertTrue(send_completion_webhook(config, "job-1", "COMPLETED", {"ok": True}))

    @mock.patch("geometry_correction.algorithms.webhook.requests.post")
    def test_send_completion_webhook_returns_false_on_4xx(self, mock_post):
        mock_post.return_value.status_code = 404
        config = WebhookConfig(url="https://example.com/hook")
        self.assertFalse(send_completion_webhook(config, "job-1", "COMPLETED", {"ok": True}))

    @mock.patch("geometry_correction.algorithms.webhook.requests.post", side_effect=RuntimeError("network down"))
    def test_send_completion_webhook_returns_false_on_exception(self, _mock_post):
        config = WebhookConfig(url="https://example.com/hook")
        self.assertFalse(send_completion_webhook(config, "job-1", "FAILED", {}, error="boom"))

    @mock.patch("geometry_correction.algorithms.webhook.requests.post")
    def test_send_completion_webhook_adds_signature_when_secret_present(self, mock_post):
        mock_post.return_value.status_code = 200
        config = WebhookConfig(url="https://example.com/hook", secret="top-secret")
        send_completion_webhook(config, "job-1", "COMPLETED", {"ok": True})
        headers = mock_post.call_args.kwargs["headers"]
        self.assertIn("X-GC-Signature", headers)

    @mock.patch("geometry_correction.algorithms.webhook.requests.post")
    def test_send_completion_webhook_omits_signature_when_secret_empty(self, mock_post):
        mock_post.return_value.status_code = 200
        config = WebhookConfig(url="https://example.com/hook")
        send_completion_webhook(config, "job-1", "COMPLETED", {"ok": True})
        headers = mock_post.call_args.kwargs["headers"]
        self.assertNotIn("X-GC-Signature", headers)

    @mock.patch("geometry_correction.algorithms.webhook.requests.post")
    def test_send_completion_webhook_signature_is_valid(self, mock_post):
        mock_post.return_value.status_code = 200
        config = WebhookConfig(url="https://example.com/hook", secret="verify-me")
        send_completion_webhook(config, "job-1", "COMPLETED", {"value": 3})
        body = mock_post.call_args.kwargs["data"]
        signature = mock_post.call_args.kwargs["headers"]["X-GC-Signature"]
        expected = "sha256=" + hmac.new(
            b"verify-me",
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(signature, expected)

    @mock.patch("geometry_correction.algorithms.webhook.requests.post")
    def test_send_completion_webhook_payload_contains_required_fields(self, mock_post):
        mock_post.return_value.status_code = 200
        config = WebhookConfig(url="https://example.com/hook")
        send_completion_webhook(config, "job-99", "FAILED", {"items": 1}, error="broken")
        payload = json.loads(mock_post.call_args.kwargs["data"])
        self.assertEqual(payload["job_id"], "job-99")
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["result"], {"items": 1})
        self.assertEqual(payload["error"], "broken")
        self.assertIn("timestamp", payload)


class TestWebhookTaskIntegration(unittest.TestCase):
    def _prepare_task_root(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        pointcloud_dir = root / "assets" / "odm_georeferencing"
        pointcloud_dir.mkdir(parents=True, exist_ok=True)
        (pointcloud_dir / "odm_georeferenced_model.ply").write_text("dummy", encoding="utf-8")
        return tmp

    @mock.patch("geometry_correction.algorithms.webhook.send_completion_webhook", return_value=True)
    @mock.patch("geometry_correction.algorithms.pointcloud.correct_pointcloud")
    @mock.patch("geometry_correction.tasks.Task.objects.get")
    def test_task_sends_webhook_on_completion(self, mock_get_task, mock_correct_pointcloud, mock_send_webhook):
        tmp = self._prepare_task_root()
        self.addCleanup(tmp.cleanup)

        fake_task = FakeTask(tmp.name)
        mock_get_task.return_value = fake_task
        mock_correct_pointcloud.return_value = {
            "original_points": 100,
            "planes_detected": 2,
            "corrected_point_cloud": "out.ply",
        }

        result = gc_tasks.run_geometry_correction.run(
            str(fake_task.id),
            int(fake_task.project.id),
            {
                "correct_pointcloud": True,
                "correct_mesh": False,
                "correct_orthophoto": False,
                "webhook_url": "https://example.com/hook",
            },
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(mock_send_webhook.call_args.kwargs["status"], "COMPLETED")
        self.assertEqual(mock_send_webhook.call_args.kwargs["job_id"], str(fake_task.id))

    @mock.patch("geometry_correction.algorithms.webhook.send_completion_webhook", return_value=True)
    @mock.patch("geometry_correction.algorithms.pointcloud.correct_pointcloud", side_effect=RuntimeError("plane failure"))
    @mock.patch("geometry_correction.tasks.Task.objects.get")
    def test_task_sends_webhook_on_failure(self, mock_get_task, _mock_correct_pointcloud, mock_send_webhook):
        tmp = self._prepare_task_root()
        self.addCleanup(tmp.cleanup)

        fake_task = FakeTask(tmp.name)
        mock_get_task.return_value = fake_task

        result = gc_tasks.run_geometry_correction.run(
            str(fake_task.id),
            int(fake_task.project.id),
            {
                "correct_pointcloud": True,
                "correct_mesh": False,
                "correct_orthophoto": False,
                "webhook_url": "https://example.com/hook",
            },
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(mock_send_webhook.call_args.kwargs["status"], "FAILED")
        self.assertEqual(mock_send_webhook.call_args.kwargs["error"], "plane failure")


if __name__ == "__main__":
    unittest.main()
