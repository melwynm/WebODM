import os

from django.contrib.auth.models import User
from django.test import Client
from guardian.shortcuts import assign_perm

from app.models import Project, ProjectClientShare, Task
from nodeodm import status_codes

from .classes import BootTestCase


class TestTexturedModelQA(BootTestCase):
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
            name='Textured Model Flight',
            status=status_codes.COMPLETED,
            available_assets=['textured_model.zip', 'textured_model.glb', 'georeferenced_model.laz'],
            options=[{'name': 'use-3dmesh', 'value': True}],
        )
        self.task.create_task_directories()
        self._write_asset('odm_texturing/odm_textured_model_geo.glb', b'glb')
        self._write_asset('odm_texturing/odm_textured_model_geo.obj', b'obj')
        self._write_asset('odm_georeferencing/odm_georeferenced_model.laz', b'laz')

    def _write_asset(self, relative_path, content):
        path = self.task.assets_path(relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as asset:
            asset.write(content)

    def test_textured_model_qa_reports_ready_assets(self):
        response = self.client.get(f'/api/projects/{self.project.id}/tasks/{self.task.id}/3d/qa')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ready')
        self.assertEqual(data['task'], str(self.task.id))
        self.assertIn('safe_glb_url', data)
        glb = next(asset for asset in data['assets'] if asset['asset'] == 'textured_model.glb')
        self.assertTrue(glb['exists'])
        self.assertTrue(glb['listed'])

    def test_textured_model_qa_enforces_project_permissions(self):
        other_task = Task.objects.create(
            project=self.other_project,
            name='Other Model',
            status=status_codes.COMPLETED,
            available_assets=['textured_model.zip'],
        )

        response = self.client.get(f'/api/projects/{self.other_project.id}/tasks/{other_task.id}/3d/qa')

        self.assertEqual(response.status_code, 404)

    def test_client_share_exposes_tokenized_3d_page_and_qa(self):
        share = ProjectClientShare.objects.create(
            project=self.project,
            name='3D Client Review',
            role=ProjectClientShare.ROLE_VIEWER,
            created_by=self.user,
        )

        page = self.public_client.get(f'/client/projects/{share.token}/tasks/{self.task.id}/3d/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, str(share.token))
        self.assertContains(page, 'data-client-token')

        qa = self.public_client.get(f'/api/client-shares/{share.token}/tasks/{self.task.id}/3d/qa')
        self.assertEqual(qa.status_code, 200)
        self.assertEqual(qa.json()['status'], 'ready')

    def test_client_share_can_read_model_assets_without_login(self):
        share = ProjectClientShare.objects.create(
            project=self.project,
            name='3D Client Review',
            role=ProjectClientShare.ROLE_VIEWER,
            created_by=self.user,
        )

        response = self.public_client.get(
            f'/api/client-shares/{share.token}/tasks/{self.task.id}/assets/odm_texturing/odm_textured_model_geo.obj'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'obj')

        head = self.public_client.head(
            f'/api/client-shares/{share.token}/tasks/{self.task.id}/assets/odm_texturing/odm_textured_model_geo.obj'
        )
        self.assertEqual(head.status_code, 200)
