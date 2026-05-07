import json

from django.contrib.auth.models import User
from django.test import Client
from guardian.shortcuts import assign_perm

from app.models import Project, ProjectIssue, Task
from nodeodm import status_codes

from .classes import BootTestCase


class TestProjectIssuesApi(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.get(username='testuser')
        self.other_user = User.objects.get(username='testuser2')
        self.project = Project.objects.get(owner=self.user)
        self.other_project = Project.objects.get(owner=self.other_user)
        for perm in ['view_project', 'add_project', 'change_project', 'delete_project']:
            assign_perm(perm, self.user, self.project)
        self.client.login(username='testuser', password='test1234')
        self.task = Task.objects.create(
            project=self.project,
            name='Progress Flight',
            status=status_codes.COMPLETED,
            available_assets=['orthophoto.tif'],
        )
        self.other_task = Task.objects.create(
            project=self.other_project,
            name='Other Flight',
            status=status_codes.COMPLETED,
            available_assets=['orthophoto.tif'],
        )

    def issue_url(self, issue_id=None):
        base = f'/api/projects/{self.project.id}/issues/'
        return base if issue_id is None else f'{base}{issue_id}/'

    def test_create_list_update_and_close_project_issue(self):
        response = self.client.post(
            self.issue_url(),
            json.dumps({
                'task': str(self.task.id),
                'title': 'Check stockpile change',
                'description': 'Visible change in the north stockpile.',
                'issue_type': ProjectIssue.ISSUE_TYPE_CHANGE,
                'priority': ProjectIssue.PRIORITY_HIGH,
                'geometry': {
                    'type': 'Point',
                    'coordinates': [57.5, -20.2],
                },
                'properties': {
                    'source': 'monitoring-change-overlay',
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        created = response.json()
        self.assertEqual(created['title'], 'Check stockpile change')
        self.assertEqual(created['created_by'], self.user.username)
        self.assertEqual(created['task'], str(self.task.id))
        self.assertEqual(created['geometry']['type'], 'Point')

        list_response = self.client.get(self.issue_url())
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        close_response = self.client.patch(
            self.issue_url(created['id']),
            json.dumps({
                'status': ProjectIssue.STATUS_CLOSED,
                'priority': ProjectIssue.PRIORITY_CRITICAL,
            }),
            content_type='application/json',
        )
        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(close_response.json()['status'], ProjectIssue.STATUS_CLOSED)
        self.assertIsNotNone(close_response.json()['closed_at'])

    def test_issue_task_must_belong_to_project(self):
        response = self.client.post(
            self.issue_url(),
            json.dumps({
                'task': str(self.other_task.id),
                'title': 'Wrong task',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('task', response.json())

    def test_issue_geometry_requires_geojson_object(self):
        response = self.client.post(
            self.issue_url(),
            json.dumps({
                'title': 'Bad geometry',
                'geometry': {
                    'type': 'Circle',
                    'coordinates': [0, 0],
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('geometry', response.json())

    def test_project_permissions_are_enforced(self):
        response = self.client.get(f'/api/projects/{self.other_project.id}/issues/')
        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            f'/api/projects/{self.other_project.id}/issues/',
            json.dumps({'title': 'No access'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
