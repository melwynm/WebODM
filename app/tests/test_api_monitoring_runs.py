import json
import os
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import numpy as np
import rasterio
from django.contrib.auth.models import User
from django.db import close_old_connections, transaction
from django.test import Client
from django.utils import timezone
from guardian.shortcuts import assign_perm
from rasterio.enums import ColorInterp
from rasterio.transform import from_origin

from app.models import Project, ProjectClientShare, ProjectIssue, ProjectMonitoringRun, Setting, Task
from nodeodm import status_codes

from .classes import BootTransactionTestCase


class FakeMonitoringAIResponse:
    status_code = 200

    def json(self):
        return {
            "id": "resp_monitoring",
            "output_text": json.dumps([{
                "title": "Review new surface change",
                "description": "The change heatmap shows a concentrated difference.",
                "issue_type": "change",
                "priority": "high",
                "confidence": 0.84,
                "location_hint": "east side",
            }]),
        }


class TestMonitoringRunApi(BootTransactionTestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.public_client = Client()
        self.user = User.objects.get(username="testuser")
        self.other_user = User.objects.get(username="testuser2")
        self.project = Project.objects.get(owner=self.user)
        self.other_project = Project.objects.get(owner=self.other_user)
        for perm in ("view_project", "add_project", "change_project", "delete_project"):
            assign_perm(perm, self.user, self.project)
        self.client.login(username="testuser", password="test1234")

        self.baseline = self.create_orthophoto_task("Baseline", 500000, 1000)
        self.current = self.create_orthophoto_task("Current", 500002, 999)

    def create_orthophoto_task(self, name, west, north):
        task = Task.objects.create(
            project=self.project,
            name=name,
            status=status_codes.COMPLETED,
            available_assets=["orthophoto.tif"],
            created_at=timezone.now(),
        )
        path = task.get_asset_download_path("orthophoto.tif")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        grid_y, grid_x = np.indices((48, 48))
        pattern = ((grid_x * 4 + grid_y * 7) % 255).astype("uint8")
        pattern[12:28, 17:35] = 230 if name == "Current" else 90
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=48,
            height=48,
            count=3,
            dtype="uint8",
            crs="EPSG:32615",
            transform=from_origin(west, north, 1, 1),
            nodata=0,
        ) as output:
            output.write(pattern, 1)
            output.write((255 - pattern), 2)
            output.write((pattern // 2), 3)
            output.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue)
        return task

    def runs_url(self, project=None):
        return "/api/projects/{}/monitoring-runs/".format((project or self.project).id)

    def start_run(self):
        return self.client.post(
            self.runs_url(),
            json.dumps({
                "current_task": str(self.current.id),
                "baseline_task": str(self.baseline.id),
            }),
            content_type="application/json",
        )

    def test_editor_starts_resumable_monitoring_run(self):
        response = self.start_run()

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], ProjectMonitoringRun.STATUS_REVIEW)
        self.assertEqual(payload["current_task"], str(self.current.id))
        self.assertEqual(payload["baseline_task"], str(self.baseline.id))
        self.assertTrue(payload["comparison"]["readiness"]["cache"]["ready"])
        self.assertIn("change_overlay", payload["comparison"]["output"]["layers"])
        self.assertTrue(payload["can_publish"])

        replay = self.start_run()
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["id"], payload["id"])
        self.assertEqual(ProjectMonitoringRun.objects.filter(project=self.project).count(), 1)

    @mock.patch("app.services.monitoring_runs.monitoring_pair_readiness")
    @mock.patch("worker.tasks.generate_monitoring_compare.apply_async")
    def test_comparison_dispatch_waits_for_commit_and_uses_saved_attempt_id(
        self,
        apply_async,
        readiness,
    ):
        readiness.return_value = {
            "can_compare": True,
            "cache": {"ready": False},
            "issues": [],
        }
        run = ProjectMonitoringRun.objects.create(
            project=self.project,
            current_task=self.current,
            baseline_task=self.baseline,
            status=ProjectMonitoringRun.STATUS_FAILED,
            created_by=self.user,
        )

        with transaction.atomic():
            response = self.client.post(
                "{}{}/retry/".format(self.runs_url(), run.id),
                "{}",
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], ProjectMonitoringRun.STATUS_GENERATING)
            apply_async.assert_not_called()

        run.refresh_from_db()
        apply_async.assert_called_once_with(
            args=(str(self.current.id), str(self.baseline.id), str(run.id)),
            task_id=run.celery_task_id,
        )

    @mock.patch("app.services.monitoring_runs.monitoring_pair_readiness")
    @mock.patch("worker.tasks.generate_monitoring_compare.apply_async")
    def test_rolled_back_retry_is_not_dispatched(self, apply_async, readiness):
        from app.services.monitoring_runs import retry_monitoring_run

        readiness.return_value = {
            "can_compare": True,
            "cache": {"ready": False},
            "issues": [],
        }
        run = ProjectMonitoringRun.objects.create(
            project=self.project,
            current_task=self.current,
            baseline_task=self.baseline,
            status=ProjectMonitoringRun.STATUS_FAILED,
            created_by=self.user,
        )

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                retry_monitoring_run(run)
                raise RuntimeError("roll back")

        apply_async.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(run.status, ProjectMonitoringRun.STATUS_FAILED)
        self.assertEqual(run.celery_task_id, "")

    @mock.patch("app.services.monitoring_runs.monitoring_pair_readiness")
    @mock.patch("worker.tasks.generate_monitoring_compare.apply_async")
    def test_concurrent_starts_reuse_one_active_run(self, apply_async, readiness):
        from app.services.monitoring_runs import create_monitoring_run

        readiness.return_value = {
            "can_compare": True,
            "cache": {"ready": False},
            "issues": [],
        }
        project_id = self.project.id
        user_id = self.user.id
        current_id = self.current.id
        baseline_id = self.baseline.id

        def start():
            close_old_connections()
            try:
                project = Project.objects.get(pk=project_id)
                user = User.objects.get(pk=user_id)
                run, created = create_monitoring_run(
                    project,
                    user,
                    current_task_id=current_id,
                    baseline_task_id=baseline_id,
                )
                return str(run.id), created
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: start(), range(2)))

        self.assertEqual(len({run_id for run_id, _created in results}), 1)
        self.assertEqual(sorted(created for _run_id, created in results), [False, True])
        self.assertEqual(ProjectMonitoringRun.objects.filter(project=self.project).count(), 1)
        self.assertEqual(apply_async.call_count, 1)

    @mock.patch("app.services.monitoring_runs.monitoring_pair_readiness")
    @mock.patch(
        "worker.tasks.generate_monitoring_compare.apply_async",
        side_effect=RuntimeError("broker unavailable"),
    )
    def test_queue_failure_marks_only_the_current_attempt_failed(self, _apply_async, readiness):
        readiness.return_value = {
            "can_compare": True,
            "cache": {"ready": False},
            "issues": [],
        }
        run = ProjectMonitoringRun.objects.create(
            project=self.project,
            current_task=self.current,
            baseline_task=self.baseline,
            status=ProjectMonitoringRun.STATUS_FAILED,
            created_by=self.user,
        )

        response = self.client.post(
            "{}{}/retry/".format(self.runs_url(), run.id),
            "{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        run.refresh_from_db()
        self.assertEqual(run.status, ProjectMonitoringRun.STATUS_FAILED)
        self.assertIn("broker unavailable", run.last_error)

    @mock.patch("app.services.monitoring_runs.monitoring_pair_readiness")
    @mock.patch("worker.tasks.generate_monitoring_compare.apply_async")
    def test_retry_does_not_dispatch_again_while_attempt_is_generating(self, apply_async, readiness):
        readiness.return_value = {
            "can_compare": True,
            "cache": {"ready": False},
            "issues": [],
        }
        run = ProjectMonitoringRun.objects.create(
            project=self.project,
            current_task=self.current,
            baseline_task=self.baseline,
            status=ProjectMonitoringRun.STATUS_FAILED,
            created_by=self.user,
        )
        retry_url = "{}{}/retry/".format(self.runs_url(), run.id)

        first = self.client.post(retry_url, "{}", content_type="application/json")
        second = self.client.post(retry_url, "{}", content_type="application/json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], ProjectMonitoringRun.STATUS_GENERATING)
        apply_async.assert_called_once()

    @mock.patch("worker.tasks.store_task_result")
    @mock.patch("app.services.monitoring.render_layer_payload", return_value={"layers": {}})
    @mock.patch("app.services.monitoring.ensure_monitoring_products", return_value={})
    def test_late_worker_result_does_not_replace_newer_run_state(
        self,
        _ensure_products,
        _render_payload,
        _store_result,
    ):
        from worker.tasks import generate_monitoring_compare

        run = ProjectMonitoringRun.objects.create(
            project=self.project,
            current_task=self.current,
            baseline_task=self.baseline,
            status=ProjectMonitoringRun.STATUS_GENERATING,
            celery_task_id="new-attempt",
            created_by=self.user,
        )

        result = generate_monitoring_compare.apply(
            args=(str(self.current.id), str(self.baseline.id), str(run.id)),
            task_id="old-attempt",
        ).get()

        self.assertIn("output", result)
        run.refresh_from_db()
        self.assertEqual(run.status, ProjectMonitoringRun.STATUS_GENERATING)
        self.assertEqual(run.celery_task_id, "new-attempt")

    @mock.patch("app.services.monitoring.ensure_monitoring_products", side_effect=RuntimeError("late failure"))
    def test_late_worker_failure_does_not_replace_published_state(self, _ensure_products):
        from worker.tasks import generate_monitoring_compare

        run = ProjectMonitoringRun.objects.create(
            project=self.project,
            current_task=self.current,
            baseline_task=self.baseline,
            status=ProjectMonitoringRun.STATUS_PUBLISHED,
            celery_task_id="published-attempt",
            published_at=timezone.now(),
            created_by=self.user,
        )

        result = generate_monitoring_compare.apply(
            args=(str(self.current.id), str(self.baseline.id), str(run.id)),
            task_id="published-attempt",
        ).get()

        self.assertEqual(result, {"error": "late failure"})
        run.refresh_from_db()
        self.assertEqual(run.status, ProjectMonitoringRun.STATUS_PUBLISHED)
        self.assertEqual(run.last_error, "")

    @mock.patch("app.services.ai_issue_detection._resize_image_bytes", return_value=b"change-preview")
    @mock.patch("app.services.ai_issue_detection.requests.post", return_value=FakeMonitoringAIResponse())
    def test_signed_ai_review_is_attached_to_exact_run(self, post_mock, _resize_mock):
        run = self.start_run().json()
        settings = Setting.objects.first()
        settings.openai_api_key = "sk-test"
        settings.openai_model = "gpt-test"
        settings.save()

        preview = self.client.post(
            "/api/projects/{}/ai/issue-detection".format(self.project.id),
            json.dumps({
                "source": "monitoring_change",
                "task": str(self.current.id),
                "compare_task": str(self.baseline.id),
                "monitoring_run": run["id"],
                "create": False,
            }),
            content_type="application/json",
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["candidate_count"], 1)

        confirmation = self.client.post(
            "/api/projects/{}/ai/issue-detection".format(self.project.id),
            json.dumps({
                "confirmation_token": preview.json()["confirmation_token"],
                "create": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(post_mock.call_count, 1)
        issue = ProjectIssue.objects.get(project=self.project, properties__monitoring_run_id=run["id"])
        self.assertEqual(issue.task, self.current)
        self.assertEqual(issue.properties["monitoring_baseline_task_id"], str(self.baseline.id))

        detail = self.client.get("{}{}{}".format(self.runs_url(), run["id"], "/"))
        self.assertEqual(detail.json()["issue_count"], 1)

    def test_publish_snapshots_report_and_exposes_it_through_client_portal(self):
        run = self.start_run().json()
        publish_url = "{}{}/publish/".format(self.runs_url(), run["id"])

        response = self.client.post(publish_url, "{}", content_type="application/json")

        self.assertEqual(response.status_code, 200)
        published = response.json()
        self.assertEqual(published["status"], ProjectMonitoringRun.STATUS_PUBLISHED)
        self.assertTrue(published["portal_url"])
        self.assertEqual(ProjectClientShare.objects.filter(project=self.project).count(), 1)
        saved_run = ProjectMonitoringRun.objects.get(pk=run["id"])
        self.assertEqual(saved_run.report_snapshot["monitoring_run"]["status"], "published")

        replay = self.client.post(publish_url, "{}", content_type="application/json")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(ProjectClientShare.objects.filter(project=self.project).count(), 1)

        portal = self.public_client.get("/api/client-shares/{}/".format(saved_run.client_share.token))
        self.assertEqual(portal.status_code, 200)
        self.assertEqual(portal.json()["monitoring_runs"][0]["id"], run["id"])

        report = self.public_client.get(
            "/api/client-shares/{}/monitoring-runs/{}/report/?format=html".format(
                saved_run.client_share.token,
                run["id"],
            )
        )
        self.assertEqual(report.status_code, 200)
        self.assertContains(report, "Monitoring Review")
        self.assertContains(report, self.current.name)
        self.assertContains(report, self.baseline.name)

    def test_permissions_and_pair_validation_are_enforced(self):
        denied = self.client.post(self.runs_url(self.other_project), "{}", content_type="application/json")
        self.assertEqual(denied.status_code, 404)

        same_task = self.client.post(
            self.runs_url(),
            json.dumps({
                "current_task": str(self.current.id),
                "baseline_task": str(self.current.id),
            }),
            content_type="application/json",
        )
        self.assertEqual(same_task.status_code, 400)
        self.assertIn("different", same_task.json()[0])
