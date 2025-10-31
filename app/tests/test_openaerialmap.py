import json
from unittest import mock

from django.test import SimpleTestCase

from app.models import Project, Task
from app.tests.classes import BootTestCase
from coreplugins.openaerialmap.api import get_task_info, normalize_tags


class NormalizeTagsTests(SimpleTestCase):
    def test_returns_empty_list_for_empty_values(self):
        self.assertEqual(normalize_tags(None), [])
        self.assertEqual(normalize_tags([]), [])
        self.assertEqual(normalize_tags(''), [])

    def test_splits_comma_separated_strings(self):
        self.assertEqual(normalize_tags('one,two, three'), ['one', 'two', 'three'])

    def test_trims_and_filters_items(self):
        self.assertEqual(normalize_tags([' alpha ', 'beta', '']), ['alpha', 'beta'])
        self.assertEqual(normalize_tags(('gamma', 42)), ['gamma', '42'])


class ShareViewTagTests(BootTestCase):
    def setUp(self):
        super().setUp()
        logged_in = self.client.login(username='testsuperuser', password='test1234')
        self.assertTrue(logged_in)
        self.project = Project.objects.filter(owner__username='testsuperuser').first()
        self.assertIsNotNone(self.project)
        self.task = Task.objects.create(project=self.project)

    def test_share_normalizes_and_persists_tags(self):
        payload = {
            'oamParams': {
                'token': 'abc',
                'sensor': 'DJI',
                'acquisition_start': '2020-01-01T00:00:00',
                'acquisition_end': '2020-01-01T01:00:00',
                'title': 'Demo',
                'provider': 'Test Org',
                'tags': 'alpha, beta , ,gamma'
            }
        }

        with mock.patch('coreplugins.openaerialmap.api.upload_orthophoto_to_oam.delay') as mocked:
            response = self.client.post(
                f'/api/plugins/openaerialmap/task/{self.task.id}/share',
                data=json.dumps(payload),
                content_type='application/json'
            )

        self.assertEqual(response.status_code, 200)
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(args[0], self.task.id)
        self.assertEqual(args[2]['tags'], ['alpha', 'beta', 'gamma'])
        self.assertEqual(get_task_info(self.task.id)['tags'], ['alpha', 'beta', 'gamma'])

    def test_share_omits_empty_tags(self):
        payload = {
            'oamParams': {
                'token': 'abc',
                'sensor': 'DJI',
                'acquisition_start': '2020-01-01T00:00:00',
                'acquisition_end': '2020-01-01T01:00:00',
                'title': 'Demo',
                'provider': 'Test Org',
                'tags': '   '
            }
        }

        with mock.patch('coreplugins.openaerialmap.api.upload_orthophoto_to_oam.delay') as mocked:
            response = self.client.post(
                f'/api/plugins/openaerialmap/task/{self.task.id}/share',
                data=json.dumps(payload),
                content_type='application/json'
            )

        self.assertEqual(response.status_code, 200)
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(args[0], self.task.id)
        self.assertNotIn('tags', args[2])
        self.assertEqual(get_task_info(self.task.id)['tags'], [])
