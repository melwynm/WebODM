import hashlib
import hmac
import json
import os
from unittest import mock

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from guardian.shortcuts import assign_perm
from nodeodm import status_codes
from rest_framework.test import APIClient

from app.models import AirTwinWebhookDelivery, Project, Task
from app.plugins.signals import task_completed
from app.services.airtwin import (
    build_manifest,
    build_webhook_payload,
    deliver_webhook_attempt,
    discover_supported_assets,
    is_retryable_status,
    sanitize_error,
    schedule_task_completed_webhook,
    serialize_payload,
    sign_payload,
    stable_event_id,
    validate_task_geospatial,
    webhook_headers,
)
from app.tests.classes import BootTestCase


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class TestAirTwinIntegration(BootTestCase):
    def setUp(self):
        self.user = User.objects.get(username="testuser")
        self.other_user = User.objects.get(username="testuser2")
        self.project = Project.objects.get(owner=self.user)
        for permission in ("view_project", "add_project", "change_project", "delete_project"):
            assign_perm(permission, self.user, self.project)
        self.task = Task.objects.create(
            project=self.project,
            name="Port Louis Warehouse - 2026-06-22",
            status=status_codes.COMPLETED,
            epsg=32740,
            created_at=timezone.now() - timezone.timedelta(minutes=5),
            completed_at=timezone.now(),
            available_assets=[
                "textured_model.glb",
                "orthophoto.tif",
                "shots.geojson",
                "report.pdf",
                "georeferenced_model.laz",
                "dsm.tif",
                "dtm.tif",
                "3d_tiles_model.zip",
                "all.zip",
            ],
        )
        self.task.create_task_directories()
        self._write_geojson("shots.geojson", [[57.4989, -20.1609, 120.0], [57.4992, -20.1605, 121.0]])

    def _write_asset(self, asset_name, content=b"asset"):
        relative_path = self.task.ASSETS_MAP[asset_name]
        path = self.task.assets_path(relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as asset_file:
            asset_file.write(content)
        return path

    def _write_geojson(self, asset_name, coordinates):
        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Point", "coordinates": coordinate},
                }
                for coordinate in coordinates
            ],
        }
        self._write_asset(asset_name, json.dumps(data).encode("utf-8"))

    def test_manifest_generation_and_supported_asset_discovery(self):
        manifest = build_manifest(self.task, base_url="https://webodm.example")

        self.assertEqual(manifest["version"], 1)
        self.assertEqual(manifest["webOdmProjectId"], self.project.id)
        self.assertEqual(manifest["taskId"], str(self.task.id))
        self.assertEqual(manifest["epsg"], 32740)
        self.assertEqual(manifest["surveyDate"], "2026-06-22")
        self.assertEqual(manifest["siteIdentifier"], "Port Louis Warehouse")
        self.assertTrue(manifest["readyForAirTwin"])
        self.assertNotIn("all.zip", manifest["availableAssets"])
        self.assertEqual(
            manifest["availableAssets"],
            [asset["name"] for asset in discover_supported_assets(self.task)],
        )
        glb = next(asset for asset in manifest["assets"] if asset["name"] == "textured_model.glb")
        self.assertEqual(
            glb["downloadUrl"],
            "https://webodm.example/api/projects/{}/tasks/{}/download/textured_model.glb".format(
                self.project.id, self.task.id
            ),
        )
        self.assertEqual(glb["epsg"], 32740)

    def test_geospatial_validation_rejects_missing_crs_and_invalid_wgs84(self):
        self.task.epsg = None
        self.task.save(update_fields=["epsg"])
        self._write_geojson("shots.geojson", [[200.0, 95.0]])

        validation = validate_task_geospatial(self.task)

        self.assertFalse(validation["ready"])
        self.assertFalse(validation["epsgValid"])
        self.assertEqual(validation["georeferencingSource"], "none")
        self.assertGreater(validation["shotsGeoJson"]["invalidCoordinateCount"], 0)
        self.assertTrue(any("EPSG" in error for error in validation["errors"]))
        self.assertTrue(any("WGS84" in error for error in validation["errors"]))

    def test_valid_gcp_is_accepted_as_georeferencing_evidence(self):
        self.task.available_assets.append("ground_control_points.geojson")
        self.task.save(update_fields=["available_assets"])
        self._write_geojson("ground_control_points.geojson", [[57.5, -20.16]])
        os.remove(self.task.assets_path(self.task.ASSETS_MAP["shots.geojson"]))
        self.task.available_assets.remove("shots.geojson")
        self.task.save(update_fields=["available_assets"])

        validation = validate_task_geospatial(self.task)

        self.assertTrue(validation["ready"])
        self.assertTrue(validation["hasGcp"])
        self.assertEqual(validation["georeferencingSource"], "gcp")

    def test_webhook_payload_signature_and_headers_are_deterministic(self):
        event_id = stable_event_id(self.task)
        payload = build_webhook_payload(self.task, event_id=event_id)
        body = serialize_payload(payload)
        timestamp = "1782115200"
        expected = hmac.new(
            b"integration-secret",
            (timestamp + "." + str(event_id) + ".").encode("utf-8") + body,
            hashlib.sha256,
        ).hexdigest()

        self.assertEqual(sign_payload("integration-secret", timestamp, event_id, body), expected)
        headers = webhook_headers("integration-secret", timestamp, event_id, body)
        self.assertEqual(headers["X-AirTwin-Event-Id"], str(event_id))
        self.assertEqual(headers["X-AirTwin-Signature"], "sha256=" + expected)
        self.assertNotIn("integration-secret", json.dumps(payload))

    def test_event_id_is_stable_for_duplicate_completion_and_changes_for_reprocessing(self):
        first = stable_event_id(self.task)
        self.assertEqual(first, stable_event_id(self.task))

        self.task.completed_at += timezone.timedelta(seconds=1)
        self.assertNotEqual(first, stable_event_id(self.task))

    @override_settings(
        AIRTWIN_WEBHOOK_ENABLED=True,
        AIRTWIN_WEBHOOK_URL="https://airtwin.example/events",
        AIRTWIN_WEBHOOK_SECRET="integration-secret",
        AIRTWIN_WEBHOOK_MAX_RETRIES=2,
        AIRTWIN_WEBHOOK_RETRY_BASE_SECONDS=3,
        AIRTWIN_WEBHOOK_TIMEOUT_SECONDS=4,
    )
    def test_retry_behavior_and_permanent_failure(self):
        delivery = AirTwinWebhookDelivery.objects.create(
            task=self.task,
            event_id=stable_event_id(self.task),
            payload=build_webhook_payload(self.task),
        )
        sender = mock.Mock(return_value=FakeResponse(500))

        transient = deliver_webhook_attempt(delivery.id, sender=sender, now=timezone.now())
        self.assertTrue(transient["retry"])
        self.assertEqual(transient["delay"], 3)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, AirTwinWebhookDelivery.STATUS_RETRYING)
        self.assertEqual(delivery.attempts, 1)
        self.assertEqual(delivery.response_status, 500)

        sender.return_value = FakeResponse(400)
        permanent = deliver_webhook_attempt(delivery.id, sender=sender, now=timezone.now())
        self.assertFalse(permanent["retry"])
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, AirTwinWebhookDelivery.STATUS_FAILED)
        self.assertEqual(delivery.attempts, 2)
        self.assertEqual(delivery.response_status, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, status_codes.COMPLETED)
        self.assertTrue(is_retryable_status(408))
        self.assertTrue(is_retryable_status(429))
        self.assertFalse(is_retryable_status(422))

    @override_settings(
        AIRTWIN_WEBHOOK_ENABLED=True,
        AIRTWIN_WEBHOOK_URL="https://airtwin.example/events",
        AIRTWIN_WEBHOOK_SECRET="integration-secret",
    )
    def test_successful_delivery_records_completion(self):
        delivery = AirTwinWebhookDelivery.objects.create(
            task=self.task,
            event_id=stable_event_id(self.task),
            payload=build_webhook_payload(self.task),
        )
        sender = mock.Mock(return_value=FakeResponse(204))

        result = deliver_webhook_attempt(delivery.id, sender=sender, now=timezone.now())

        self.assertFalse(result["retry"])
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, AirTwinWebhookDelivery.STATUS_DELIVERED)
        self.assertEqual(delivery.response_status, 204)
        self.assertIsNotNone(delivery.delivered_at)
        self.assertEqual(delivery.last_error, "")

    @override_settings(AIRTWIN_WEBHOOK_ENABLED=False)
    def test_disabled_webhook_never_creates_or_sends_delivery(self):
        self.assertIsNone(schedule_task_completed_webhook(self.task.id))
        self.assertEqual(AirTwinWebhookDelivery.objects.count(), 0)

        delivery = AirTwinWebhookDelivery.objects.create(
            task=self.task,
            event_id=stable_event_id(self.task),
            payload=build_webhook_payload(self.task),
        )
        sender = mock.Mock()
        result = deliver_webhook_attempt(delivery.id, sender=sender)
        self.assertFalse(result["retry"])
        sender.assert_not_called()

    @override_settings(
        AIRTWIN_WEBHOOK_ENABLED=True,
        AIRTWIN_WEBHOOK_URL="https://airtwin.example/events",
        AIRTWIN_WEBHOOK_SECRET="integration-secret",
    )
    def test_duplicate_completion_creates_one_delivery_and_one_job(self):
        delay = mock.Mock()
        with self.captureOnCommitCallbacks(execute=True):
            first = schedule_task_completed_webhook(self.task.id, enqueue=delay)
        second = schedule_task_completed_webhook(self.task.id, enqueue=delay)

        self.assertEqual(first.id, second.id)
        self.assertEqual(AirTwinWebhookDelivery.objects.count(), 1)
        delay.assert_called_once_with(first.id)

    @override_settings(
        AIRTWIN_WEBHOOK_ENABLED=True,
        AIRTWIN_WEBHOOK_URL="https://airtwin.example/events",
        AIRTWIN_WEBHOOK_SECRET="integration-secret",
    )
    def test_successful_task_completion_signal_queues_one_delivery(self):
        with mock.patch("worker.tasks.deliver_airtwin_webhook.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                responses = task_completed.send_robust(sender=Task, task_id=self.task.id)

        self.assertTrue(all(error is None or not isinstance(error, Exception) for _, error in responses))
        delivery = AirTwinWebhookDelivery.objects.get(task=self.task)
        self.assertEqual(delivery.event, "webodm.task.completed")
        self.assertEqual(delivery.status, AirTwinWebhookDelivery.STATUS_PENDING)
        delay.assert_called_once_with(delivery.id)

    def test_secret_redaction(self):
        message = (
            "token=abc secret=integration-secret Authorization: Bearer-value password=hunter2 "
            "https://user:pass@example.test/hook?api_key=query-value"
        )
        sanitized = sanitize_error(message, "integration-secret")
        self.assertNotIn("abc", sanitized)
        self.assertNotIn("integration-secret", sanitized)
        self.assertNotIn("Bearer-value", sanitized)
        self.assertNotIn("hunter2", sanitized)
        self.assertNotIn("query-value", sanitized)
        self.assertNotIn("user:pass", sanitized)
        self.assertGreaterEqual(sanitized.count("[REDACTED]"), 4)

    def test_persistent_api_key_manifest_and_existing_task_routes(self):
        self._write_asset("report.pdf", b"pdf-report")
        client = APIClient(HTTP_AUTHORIZATION="Token {}".format(self.user.profile.api_key))

        detail = client.get("/api/projects/{}/tasks/{}/".format(self.project.id, self.task.id))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["id"], str(self.task.id))

        download = client.get(
            "/api/projects/{}/tasks/{}/download/report.pdf".format(self.project.id, self.task.id)
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"pdf-report")

        manifest = client.get(
            "/api/projects/{}/tasks/{}/airtwin/manifest".format(self.project.id, self.task.id)
        )
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.data["taskId"], str(self.task.id))

        other_client = APIClient(HTTP_AUTHORIZATION="Token {}".format(self.other_user.profile.api_key))
        denied = other_client.get(
            "/api/projects/{}/tasks/{}/airtwin/manifest".format(self.project.id, self.task.id)
        )
        self.assertEqual(denied.status_code, 404)
