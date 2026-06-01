from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from guardian.shortcuts import assign_perm

from app.models import Project, ProjectCommercialReadiness, ProjectIssue, Task
from nodeodm import status_codes

from .classes import BootTestCase


class TestProjectProgressReportsApi(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.client.login(username='testuser', password='test1234')
        self.user = User.objects.get(username='testuser')
        self.other_user = User.objects.get(username='testuser2')
        self.project = Project.objects.get(owner=self.user)
        self.other_project = Project.objects.get(owner=self.other_user)
        for perm in ['view_project', 'add_project', 'change_project', 'delete_project']:
            assign_perm(perm, self.user, self.project)
        self.completed_task = Task.objects.create(
            project=self.project,
            name='April Capture',
            status=status_codes.COMPLETED,
            available_assets=['orthophoto.tif', 'dsm.tif'],
            created_at=timezone.now(),
        )
        Task.objects.create(
            project=self.project,
            name='Processing Capture',
            status=status_codes.RUNNING,
            available_assets=[],
            created_at=timezone.now(),
        )
        ProjectIssue.objects.create(
            project=self.project,
            task=self.completed_task,
            title='Review north stockpile',
            issue_type=ProjectIssue.ISSUE_TYPE_CHANGE,
            priority=ProjectIssue.PRIORITY_HIGH,
            status=ProjectIssue.STATUS_OPEN,
            created_by=self.user,
        )

    def test_progress_report_json_summarizes_project(self):
        response = self.client.get(f'/api/projects/{self.project.id}/reports/progress')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload['project']['name'], self.project.name)
        self.assertEqual(payload['report_template']['key'], 'general')
        self.assertEqual(payload['summary']['tasks']['total'], 2)
        self.assertEqual(payload['summary']['tasks']['completed'], 1)
        self.assertEqual(payload['summary']['tasks']['processing'], 1)
        self.assertEqual(payload['summary']['issues']['open'], 1)
        self.assertEqual(payload['commercial_evidence']['completed_orthomosaic_tasks'], 1)
        self.assertEqual(payload['open_issues'][0]['title'], 'Review north stockpile')
        self.assertEqual(payload['latest_tasks'][0]['available_assets'], [])

    def test_progress_report_supports_architecture_template(self):
        response = self.client.get(f'/api/projects/{self.project.id}/reports/progress?template=architecture_cad')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload['report_template']['key'], 'architecture_cad')
        self.assertIn('CAD/design overlay comparison', payload['report_template']['focus'])
        self.assertIn('CAD/design comparison depends', payload['report_template']['caveats'][0])

    def test_progress_report_defaults_to_project_commercial_package_template(self):
        ProjectCommercialReadiness.objects.create(
            project=self.project,
            package=ProjectCommercialReadiness.PACKAGE_SOLAR_INSPECTION,
        )

        response = self.client.get(f'/api/projects/{self.project.id}/reports/progress')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload['report_template']['key'], 'solar_inspection')
        self.assertIn('Solar Inspection Report', payload['report_template']['label'])

    def test_progress_report_html_is_printable_for_pdf_export(self):
        response = self.client.get(f'/api/projects/{self.project.id}/reports/progress?format=html&template=agriculture_field')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response['Content-Type'])

        html = response.content.decode('utf-8')
        self.assertIn('Print / Save PDF', html)
        self.assertIn('Field Analysis Report', html)
        self.assertIn('Client Review Focus', html)
        self.assertIn('April Capture', html)
        self.assertIn('Review north stockpile', html)

    def test_progress_report_permissions_are_project_scoped(self):
        response = self.client.get(f'/api/projects/{self.other_project.id}/reports/progress')
        self.assertEqual(response.status_code, 404)
