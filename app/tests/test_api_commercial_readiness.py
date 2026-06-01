import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from guardian.shortcuts import assign_perm

from app.models import (
    Project,
    ProjectClientShare,
    ProjectCommercialReadiness,
    ProjectDesignOverlay,
    ProjectIssue,
    Task,
)
from nodeodm import status_codes

from .classes import BootTestCase


class TestCommercialReadinessApi(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.client.login(username="testuser", password="test1234")
        self.user = User.objects.get(username="testuser")
        self.other_user = User.objects.get(username="testuser2")
        self.project = Project.objects.get(owner=self.user)
        self.other_project = Project.objects.get(owner=self.other_user)
        for perm in ["view_project", "add_project", "change_project", "delete_project"]:
            assign_perm(perm, self.user, self.project)

    def readiness_url(self, project=None):
        project = project or self.project
        return "/api/projects/{}/commercial/readiness".format(project.id)

    def create_delivery_task(self, assets=None):
        return Task.objects.create(
            project=self.project,
            name="Client Delivery Flight",
            status=status_codes.COMPLETED,
            available_assets=assets or ["orthophoto.tif", "dsm.tif", "dtm.tif"],
            created_at=timezone.now(),
        )

    def create_expiring_share(self):
        return ProjectClientShare.objects.create(
            project=self.project,
            name="Client Delivery",
            role=ProjectClientShare.ROLE_REVIEWER,
            expires_at=timezone.now() + timezone.timedelta(days=14),
            created_by=self.user,
        )

    def create_design_overlay(self):
        return ProjectDesignOverlay.objects.create(
            project=self.project,
            name="Site Plan",
            file=SimpleUploadedFile("site-plan.geojson", b'{"type":"FeatureCollection","features":[]}'),
            source_filename="site-plan.geojson",
            created_by=self.user,
        )

    def test_architecture_package_is_ready_after_assets_share_overlay_and_signoff(self):
        self.create_delivery_task()
        self.create_expiring_share()
        self.create_design_overlay()

        response = self.client.patch(
            self.readiness_url(),
            json.dumps({
                "package": ProjectCommercialReadiness.PACKAGE_ARCHITECTURE_CAD,
                "deliverables_reviewed": True,
                "human_reviewed": True,
                "report_reviewed": True,
                "client_share_reviewed": True,
                "legal_disclaimer_reviewed": True,
                "notes": "Reviewed for client handoff.",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["package"]["key"], ProjectCommercialReadiness.PACKAGE_ARCHITECTURE_CAD)
        self.assertEqual(payload["counts"]["blocked"], 0)
        self.assertEqual(payload["counts"]["manual"], 0)
        self.assertTrue(any(item["key"] == "design_overlay" and item["status"] == "ok" for item in payload["checklist"]))
        self.assertEqual(payload["manual_signoff"]["updated_by"], self.user.username)

    def test_readiness_blocks_missing_share_open_issues_and_manual_signoff(self):
        task = self.create_delivery_task(assets=["orthophoto.tif", "dsm.tif"])
        ProjectIssue.objects.create(
            project=self.project,
            task=task,
            title="Panel row needs review",
            issue_type=ProjectIssue.ISSUE_TYPE_DEFECT,
            status=ProjectIssue.STATUS_OPEN,
            created_by=self.user,
        )
        ProjectClientShare.objects.create(
            project=self.project,
            name="No Expiry",
            created_by=self.user,
        )

        response = self.client.get(
            "{}?package={}".format(
                self.readiness_url(),
                ProjectCommercialReadiness.PACKAGE_SOLAR_INSPECTION,
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["package"]["key"], ProjectCommercialReadiness.PACKAGE_SOLAR_INSPECTION)
        self.assertGreaterEqual(payload["counts"]["blocked"], 2)
        self.assertEqual(payload["counts"]["manual"], 5)
        self.assertTrue(any(item["key"] == "client_share" and item["status"] == "blocked" for item in payload["checklist"]))
        self.assertTrue(any(item["key"] == "open_issue_review" and item["status"] == "blocked" for item in payload["checklist"]))

    def test_project_permissions_are_scoped_for_commercial_readiness(self):
        response = self.client.get(self.readiness_url(self.other_project))
        self.assertEqual(response.status_code, 404)

        response = self.client.patch(
            self.readiness_url(self.other_project),
            json.dumps({"human_reviewed": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
