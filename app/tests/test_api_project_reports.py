from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from app.models import Project, ProjectIssue, Task
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
        self.assertEqual(payload['summary']['tasks']['total'], 2)
        self.assertEqual(payload['summary']['tasks']['completed'], 1)
        self.assertEqual(payload['summary']['tasks']['processing'], 1)
        self.assertEqual(payload['summary']['issues']['open'], 1)
        self.assertEqual(payload['open_issues'][0]['title'], 'Review north stockpile')
        self.assertEqual(payload['latest_tasks'][0]['available_assets'], [])

    def test_progress_report_html_is_printable_for_pdf_export(self):
        response = self.client.get(f'/api/projects/{self.project.id}/reports/progress?format=html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response['Content-Type'])

        html = response.content.decode('utf-8')
        self.assertIn('Print / Save PDF', html)
        self.assertIn('April Capture', html)
        self.assertIn('Review north stockpile', html)

    def test_progress_report_permissions_are_project_scoped(self):
        response = self.client.get(f'/api/projects/{self.other_project.id}/reports/progress')
        self.assertEqual(response.status_code, 404)
