import json
import os
import tempfile
import zipfile
from unittest import mock

from django.contrib.auth.models import User
from django.test import override_settings

from app.models import Project, Task
from app.onedrive_intake import discover_intake_datasets, intake_onedrive_folder
from nodeodm import status_codes

from .classes import BootTestCase


class TestOneDriveIntake(BootTestCase):
    def setUp(self):
        self.user = User.objects.get(username='testuser')
        self.project = Project.objects.get(owner=self.user)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.media_dir = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self.media_dir.name, 'state.json')

    def tearDown(self):
        self.temp_dir.cleanup()
        self.media_dir.cleanup()

    def make_dataset_dir(self, name='capture'):
        dataset_dir = os.path.join(self.temp_dir.name, name)
        os.makedirs(dataset_dir, exist_ok=True)
        for index in range(2):
            with open(os.path.join(dataset_dir, f'image-{index}.jpg'), 'wb') as image:
                image.write(b'image')
        return dataset_dir

    def make_zip_dataset(self, name='archive.zip'):
        zip_path = os.path.join(self.temp_dir.name, name)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('image-0.jpg', b'image')
            archive.writestr('image-1.jpg', b'image')
        return zip_path

    def test_discover_intake_datasets_finds_dirs_and_zips(self):
        self.make_dataset_dir('capture-a')
        self.make_zip_dataset('capture-b.zip')

        datasets = discover_intake_datasets(self.temp_dir.name, min_age_seconds=0)

        self.assertEqual([dataset['name'] for dataset in datasets], ['capture-a', 'capture-b.zip'])

    def test_intake_creates_import_task_and_skips_duplicate(self):
        self.make_dataset_dir('capture-a')

        with override_settings(MEDIA_ROOT=self.media_dir.name, MEDIA_CACHE=self.media_dir.name):
            with mock.patch('worker.tasks.process_task.delay') as delay:
                first = intake_onedrive_folder(
                    self.project,
                    self.temp_dir.name,
                    min_age_seconds=0,
                    state_path=self.state_path,
                )
                second = intake_onedrive_folder(
                    self.project,
                    self.temp_dir.name,
                    min_age_seconds=0,
                    state_path=self.state_path,
                )

        self.assertEqual(first[0]['status'], 'created')
        self.assertEqual(second[0]['status'], 'skipped')
        self.assertEqual(Task.objects.filter(project=self.project, import_url__startswith='file://').count(), 1)

        task = first[0]['task']
        self.assertEqual(task.status, status_codes.RUNNING)
        self.assertEqual(task.name, 'capture-a')
        self.assertTrue(task.import_url.startswith('file://onedrive-intake/'))
        delay.assert_called_once_with(task.id)

        zip_path = os.path.join(self.media_dir.name, 'imports', task.import_url.replace('file://', ''))
        with zipfile.ZipFile(zip_path) as archive:
            self.assertEqual(sorted(archive.namelist()), ['image-0.jpg', 'image-1.jpg'])

        with open(self.state_path, 'r', encoding='utf-8') as state_file:
            state = json.load(state_file)
        self.assertEqual(len(state['datasets']), 1)
