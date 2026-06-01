import json
import os
from io import BytesIO
from zipfile import ZipFile

from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from guardian.shortcuts import assign_perm

from app.models import Project, ProjectIssue, Task
from nodeodm import status_codes

from .classes import BootTestCase


class TestProjectDeliveryExportApi(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.client.login(username="testuser", password="test1234")
        self.user = User.objects.get(username="testuser")
        self.other_user = User.objects.get(username="testuser2")
        self.project = Project.objects.get(owner=self.user)
        self.other_project = Project.objects.get(owner=self.other_user)
        for perm in ["view_project", "add_project", "change_project", "delete_project"]:
            assign_perm(perm, self.user, self.project)

        self.task = Task.objects.create(
            project=self.project,
            name="Delivery Flight",
            status=status_codes.COMPLETED,
            available_assets=["orthophoto.tif", "dsm.tif"],
            created_at=timezone.now(),
        )
        for asset, content in (
            ("orthophoto.tif", b"demo orthophoto"),
            ("dsm.tif", b"demo dsm"),
        ):
            path = self.task.get_asset_download_path(asset)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)

        ProjectIssue.objects.create(
            project=self.project,
            task=self.task,
            title="Resolved delivery issue",
            issue_type=ProjectIssue.ISSUE_TYPE_PROGRESS,
            status=ProjectIssue.STATUS_RESOLVED,
            created_by=self.user,
        )

    def export_url(self, project=None):
        project = project or self.project
        return "/api/projects/{}/delivery/export".format(project.id)

    def test_delivery_export_packages_report_readiness_issues_and_assets(self):
        response = self.client.get(self.export_url() + "?template=solar_inspection")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/zip", response["Content-Type"])
        self.assertIn("delivery-bundle.zip", response["Content-Disposition"])

        with ZipFile(BytesIO(response.content)) as bundle:
            names = set(bundle.namelist())
            self.assertIn("manifest.json", names)
            self.assertIn("progress_report.json", names)
            self.assertIn("commercial_readiness.json", names)
            self.assertIn("commercial_disclaimers.md", names)
            self.assertIn("issues.json", names)
            self.assertTrue(any(name.endswith("/orthophoto.tif") for name in names))
            self.assertTrue(any(name.endswith("/dsm.tif") for name in names))

            manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
            self.assertEqual(manifest["project"]["id"], self.project.id)
            self.assertEqual(manifest["report_template"], "solar_inspection")
            self.assertEqual(manifest["counts"]["issues"], 1)
            self.assertGreaterEqual(len(manifest["assets"]), 2)

            report = json.loads(bundle.read("progress_report.json").decode("utf-8"))
            self.assertEqual(report["report_template"]["key"], "solar_inspection")

    def test_delivery_export_permissions_are_project_scoped(self):
        response = self.client.get(self.export_url(self.other_project))
        self.assertEqual(response.status_code, 404)
