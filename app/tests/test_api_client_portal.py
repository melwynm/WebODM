import json

from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from guardian.shortcuts import assign_perm

from app.models import Project, ProjectClientComment, ProjectClientShare, ProjectIssue, Task
from nodeodm import status_codes

from .classes import BootTestCase


class TestClientPortalApi(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.public_client = Client()
        self.user = User.objects.get(username='testuser')
        self.other_user = User.objects.get(username='testuser2')
        self.project = Project.objects.get(owner=self.user)
        self.other_project = Project.objects.get(owner=self.other_user)
        for perm in ['view_project', 'add_project', 'change_project', 'delete_project']:
            assign_perm(perm, self.user, self.project)
        self.client.login(username='testuser', password='test1234')
        self.task = Task.objects.create(
            project=self.project,
            name='Review Flight',
            status=status_codes.COMPLETED,
            available_assets=['orthophoto.tif'],
        )
        self.issue = ProjectIssue.objects.create(
            project=self.project,
            task=self.task,
            title='Review edge condition',
            issue_type=ProjectIssue.ISSUE_TYPE_DEFECT,
            priority=ProjectIssue.PRIORITY_HIGH,
            created_by=self.user,
        )

    def share_url(self, project=None):
        project = project or self.project
        return f'/api/projects/{project.id}/client-shares/'

    def test_editor_can_create_and_list_client_share(self):
        response = self.client.post(
            self.share_url(),
            json.dumps({
                'name': 'Client Review',
                'role': ProjectClientShare.ROLE_REVIEWER,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['name'], 'Client Review')
        self.assertEqual(data['role'], ProjectClientShare.ROLE_REVIEWER)
        self.assertIn('/client/projects/', data['portal_url'])
        self.assertEqual(data['created_by'], self.user.username)

        list_response = self.client.get(self.share_url())
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

    def test_project_permissions_are_enforced_for_share_management(self):
        response = self.client.get(self.share_url(self.other_project))
        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            self.share_url(self.other_project),
            json.dumps({'name': 'No access'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)

    def test_token_portal_data_is_available_without_login(self):
        share = ProjectClientShare.objects.create(
            project=self.project,
            name='Client Viewer',
            role=ProjectClientShare.ROLE_VIEWER,
            created_by=self.user,
        )

        response = self.public_client.get(f'/api/client-shares/{share.token}/')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['project']['id'], self.project.id)
        self.assertEqual(data['share']['role'], ProjectClientShare.ROLE_VIEWER)
        self.assertEqual(data['tasks'][0]['name'], self.task.name)
        self.assertEqual(data['issues'][0]['title'], self.issue.title)

    def test_reviewer_share_can_add_comment(self):
        share = ProjectClientShare.objects.create(
            project=self.project,
            name='Client Reviewer',
            role=ProjectClientShare.ROLE_REVIEWER,
            created_by=self.user,
        )

        response = self.public_client.post(
            f'/api/client-shares/{share.token}/comments/',
            json.dumps({
                'author_name': 'Client User',
                'author_email': 'client@example.com',
                'body': 'Looks ready for sign-off.',
                'task': str(self.task.id),
                'issue': self.issue.id,
                'geometry': {
                    'type': 'Point',
                    'coordinates': [57.5, -20.2],
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProjectClientComment.objects.count(), 1)
        comment = ProjectClientComment.objects.first()
        self.assertEqual(comment.project, self.project)
        self.assertEqual(comment.share, share)
        self.assertEqual(comment.issue, self.issue)

    def test_viewer_share_cannot_add_comment(self):
        share = ProjectClientShare.objects.create(
            project=self.project,
            name='Client Viewer',
            role=ProjectClientShare.ROLE_VIEWER,
            created_by=self.user,
        )

        response = self.public_client.post(
            f'/api/client-shares/{share.token}/comments/',
            json.dumps({
                'author_name': 'Client User',
                'body': 'Please change this.',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ProjectClientComment.objects.count(), 0)

    def test_disabled_or_expired_share_is_not_available(self):
        disabled_share = ProjectClientShare.objects.create(
            project=self.project,
            name='Disabled',
            enabled=False,
            created_by=self.user,
        )
        expired_share = ProjectClientShare.objects.create(
            project=self.project,
            name='Expired',
            expires_at=timezone.now() - timezone.timedelta(days=1),
            created_by=self.user,
        )

        self.assertEqual(self.public_client.get(f'/api/client-shares/{disabled_share.token}/').status_code, 404)
        self.assertEqual(self.public_client.get(f'/api/client-shares/{expired_share.token}/').status_code, 404)

    def test_portal_page_renders_for_active_share(self):
        share = ProjectClientShare.objects.create(
            project=self.project,
            name='Client Portal',
            role=ProjectClientShare.ROLE_REVIEWER,
            created_by=self.user,
        )

        response = self.public_client.get(f'/client/projects/{share.token}/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.name)
        self.assertContains(response, 'Add Comment')
