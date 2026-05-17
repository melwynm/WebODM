import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client

from app.models import FeatureValidation

from .classes import BootTestCase


class TestFeatureValidationApi(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.get(username='testsuperuser')
        self.regular_user = User.objects.get(username='testuser')
        self.client.login(username='testsuperuser', password='test1234')

    def test_admin_can_create_and_mark_feature_tested(self):
        response = self.client.post(
            '/api/feature-validations/',
            json.dumps({
                'key': 'client-sharing-portal',
                'name': 'Client Sharing Portal',
                'area': 'P3',
                'status': FeatureValidation.STATUS_TESTED,
                'test_notes': 'Created reviewer link and submitted a comment.',
                'maintenance_notes': 'Keep route and anonymous comment permissions covered.',
                'evidence_url': 'http://localhost:8000/client/projects/example/',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['status'], FeatureValidation.STATUS_TESTED)
        self.assertEqual(data['last_tested_by_username'], self.admin_user.username)
        self.assertIsNotNone(data['last_tested_at'])

        feature = FeatureValidation.objects.get(key='client-sharing-portal')
        self.assertEqual(feature.last_tested_by, self.admin_user)

    def test_regular_user_cannot_manage_feature_validations(self):
        self.client.logout()
        self.client.login(username='testuser', password='test1234')

        response = self.client.get('/api/feature-validations/')

        self.assertEqual(response.status_code, 403)

    def test_status_and_area_filters(self):
        FeatureValidation.objects.create(
            key='ai-issue-detection',
            name='AI Issue Detection',
            area='P2',
            status=FeatureValidation.STATUS_TESTED,
        )
        FeatureValidation.objects.create(
            key='future-workflow',
            name='Future Workflow',
            area='Backlog',
            status=FeatureValidation.STATUS_UNTESTED,
        )

        response = self.client.get('/api/feature-validations/?status=untested&area=Backlog')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['key'], 'future-workflow')

    def test_status_update_is_logged(self):
        feature = FeatureValidation.objects.create(
            key='field-photo-capture',
            name='Field Photo Capture',
            area='P1',
            status=FeatureValidation.STATUS_UNTESTED,
        )

        with patch('app.services.feature_validation.logger.info') as logger_info:
            response = self.client.patch(
                f'/api/feature-validations/{feature.key}/',
                json.dumps({
                    'status': FeatureValidation.STATUS_FAILING,
                    'test_notes': 'Upload button failed during smoke test.',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        logger_info.assert_called_once()
        self.assertIn('Feature validation changed', logger_info.call_args[0][0])
