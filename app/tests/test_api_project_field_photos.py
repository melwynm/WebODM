import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from guardian.shortcuts import assign_perm

from app.models import Project, ProjectFieldPhoto

from .classes import BootTestCase


class TestProjectFieldPhotosApi(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.get(username='testuser')
        self.other_user = User.objects.get(username='testuser2')
        self.project = Project.objects.get(owner=self.user)
        self.other_project = Project.objects.get(owner=self.other_user)
        for perm in ['view_project', 'add_project', 'change_project', 'delete_project']:
            assign_perm(perm, self.user, self.project)
        self.client.login(username='testuser', password='test1234')

    def field_photo_url(self, field_photo_id=None):
        base = f'/api/projects/{self.project.id}/field-photos/'
        return base if field_photo_id is None else f'{base}{field_photo_id}/'

    def test_create_list_and_delete_field_photo(self):
        response = self.client.post(
            self.field_photo_url(),
            {
                'name': 'Gate condition',
                'description': 'Ground context from site walk.',
                'location': json.dumps({
                    'type': 'Point',
                    'coordinates': [57.468, -20.244],
                }),
                'is_360': 'true',
                'image': SimpleUploadedFile(
                    'gate.jpg',
                    b'field photo bytes',
                    content_type='image/jpeg',
                ),
            },
        )

        self.assertEqual(response.status_code, 201)
        created = response.json()
        self.assertEqual(created['name'], 'Gate condition')
        self.assertEqual(created['created_by'], self.user.username)
        self.assertEqual(created['source_filename'], 'gate.jpg')
        self.assertEqual(created['longitude'], 57.468)
        self.assertEqual(created['latitude'], -20.244)
        self.assertTrue(created['is_360'])
        self.assertTrue(created['image_url'])

        list_response = self.client.get(self.field_photo_url())
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        delete_response = self.client.delete(self.field_photo_url(created['id']))
        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(ProjectFieldPhoto.objects.filter(project=self.project).count(), 0)

    def test_rejects_bad_file_and_location(self):
        response = self.client.post(
            self.field_photo_url(),
            {
                'name': 'Not an image',
                'location': json.dumps({'type': 'Point', 'coordinates': [57.468, -20.244]}),
                'image': SimpleUploadedFile('notes.txt', b'not an image'),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('image', response.json())

        response = self.client.post(
            self.field_photo_url(),
            {
                'name': 'Bad location',
                'location': json.dumps({'type': 'LineString', 'coordinates': [[57.468, -20.244], [57.469, -20.245]]}),
                'image': SimpleUploadedFile('field.jpg', b'field photo bytes', content_type='image/jpeg'),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('location', response.json())

    def test_project_permissions_are_enforced(self):
        response = self.client.get(f'/api/projects/{self.other_project.id}/field-photos/')
        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            f'/api/projects/{self.other_project.id}/field-photos/',
            {
                'name': 'No access',
                'location': json.dumps({'type': 'Point', 'coordinates': [57.468, -20.244]}),
                'image': SimpleUploadedFile('field.jpg', b'field photo bytes', content_type='image/jpeg'),
            },
        )
        self.assertEqual(response.status_code, 404)
