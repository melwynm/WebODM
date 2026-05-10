from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from guardian.shortcuts import assign_perm

from app.models import Project, ProjectDesignOverlay

from .classes import BootTestCase


class TestProjectDesignOverlaysApi(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.get(username='testuser')
        self.other_user = User.objects.get(username='testuser2')
        self.project = Project.objects.get(owner=self.user)
        self.other_project = Project.objects.get(owner=self.other_user)
        for perm in ['view_project', 'add_project', 'change_project', 'delete_project']:
            assign_perm(perm, self.user, self.project)
        self.client.login(username='testuser', password='test1234')

    def overlay_url(self, overlay_id=None):
        base = f'/api/projects/{self.project.id}/design-overlays/'
        return base if overlay_id is None else f'{base}{overlay_id}/'

    def test_create_list_and_delete_design_overlay(self):
        response = self.client.post(
            self.overlay_url(),
            {
                'name': 'Approved grading plan',
                'description': 'Design reference for earthworks.',
                'file': SimpleUploadedFile(
                    'grading.geojson',
                    b'{"type":"FeatureCollection","features":[]}',
                    content_type='application/geo+json',
                ),
            },
        )

        self.assertEqual(response.status_code, 201)
        created = response.json()
        self.assertEqual(created['name'], 'Approved grading plan')
        self.assertEqual(created['created_by'], self.user.username)
        self.assertEqual(created['extension'], 'geojson')
        self.assertTrue(created['is_map_overlay'])
        self.assertTrue(created['file_url'])

        list_response = self.client.get(self.overlay_url())
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        delete_response = self.client.delete(self.overlay_url(created['id']))
        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(ProjectDesignOverlay.objects.filter(project=self.project).count(), 0)

    def test_rejects_unsupported_overlay_file(self):
        response = self.client.post(
            self.overlay_url(),
            {
                'name': 'Raw CAD',
                'file': SimpleUploadedFile('drawing.dwg', b'not supported'),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.json())

    def test_project_permissions_are_enforced(self):
        response = self.client.get(f'/api/projects/{self.other_project.id}/design-overlays/')
        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            f'/api/projects/{self.other_project.id}/design-overlays/',
            {
                'name': 'No access',
                'file': SimpleUploadedFile('overlay.geojson', b'{"type":"FeatureCollection","features":[]}'),
            },
        )
        self.assertEqual(response.status_code, 404)
