from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command

from app.models import Project, ProjectCommercialReadiness
from app.services.commercial_readiness import build_project_commercial_readiness

from .classes import BootTestCase


class DemoProjectsTests(BootTestCase):
    def setUp(self):
        self.owner = User.objects.get(username="testuser")

    def test_createdemoprojects_builds_ready_commercial_samples(self):
        stdout = StringIO()

        call_command("createdemoprojects", owner=self.owner.username, stdout=stdout)

        self.assertIn("Prepared 3 commercial demo project", stdout.getvalue())
        projects = Project.objects.filter(name__startswith="Demo - ").order_by("name")
        self.assertEqual(projects.count(), 3)

        expected_packages = {
            ProjectCommercialReadiness.PACKAGE_ARCHITECTURE_CAD,
            ProjectCommercialReadiness.PACKAGE_AGRICULTURE_FIELD,
            ProjectCommercialReadiness.PACKAGE_SOLAR_INSPECTION,
        }
        self.assertEqual(
            set(projects.values_list("commercial_readiness__package", flat=True)),
            expected_packages,
        )

        for project in projects:
            self.assertTrue(project.task_set.filter(available_assets__contains=["orthophoto.tif"]).exists())
            self.assertTrue(project.client_shares.filter(enabled=True, expires_at__isnull=False).exists())
            readiness = build_project_commercial_readiness(project)
            self.assertTrue(readiness["ready"], readiness)

    def test_createdemoprojects_is_idempotent_for_project_records(self):
        call_command("createdemoprojects", owner=self.owner.username, stdout=StringIO())
        call_command("createdemoprojects", owner=self.owner.username, stdout=StringIO())

        self.assertEqual(Project.objects.filter(name__startswith="Demo - ").count(), 3)
