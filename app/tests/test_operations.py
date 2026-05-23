import os
import tempfile

from django.contrib.auth.models import User
from django.test import Client

from app.models import Project, Task

from .classes import BootTestCase


class TestOperationsPage(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.get(username='testsuperuser')
        self.regular_user = User.objects.get(username='testuser')
        self.project = Project.objects.create(owner=self.admin_user, name='Ops Project')

    def test_staff_can_view_operations_page(self):
        self.client.login(username='testsuperuser', password='test1234')

        response = self.client.get('/operations/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Platform Audit')
        self.assertContains(response, 'OneDrive Folder Intake')
        self.assertContains(response, 'Operations dashboard')

    def test_regular_user_cannot_view_operations_page(self):
        self.client.login(username='testuser', password='test1234')

        response = self.client.get('/operations/')

        self.assertEqual(response.status_code, 302)

    def test_staff_can_dry_run_onedrive_intake_from_ui(self):
        self.client.login(username='testsuperuser', password='test1234')
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_dir = os.path.join(temp_dir, 'capture-a')
            os.makedirs(dataset_dir)
            for index in range(2):
                with open(os.path.join(dataset_dir, 'image-{}.jpg'.format(index)), 'wb') as image:
                    image.write(b'image')

            response = self.client.post(
                '/operations/',
                {
                    'project': self.project.id,
                    'folder': temp_dir,
                    'min_age': '0',
                    'dry_run': 'on',
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'capture-a')
        self.assertContains(response, 'ready')
        self.assertEqual(Task.objects.filter(project=self.project).count(), 0)
