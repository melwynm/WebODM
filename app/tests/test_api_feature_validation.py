import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
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
        self.assertFalse(data['needs_attention'])
        self.assertEqual(data['attention_reason'], '')
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

    def test_attention_filter_returns_unstable_validation_records(self):
        FeatureValidation.objects.create(
            key='tested-workflow',
            name='Tested Workflow',
            area='P1',
            status=FeatureValidation.STATUS_TESTED,
        )
        FeatureValidation.objects.create(
            key='blocked-workflow',
            name='Blocked Workflow',
            area='P2',
            status=FeatureValidation.STATUS_BLOCKED,
        )
        FeatureValidation.objects.create(
            key='failing-workflow',
            name='Failing Workflow',
            area='P3',
            status=FeatureValidation.STATUS_FAILING,
        )

        response = self.client.get('/api/feature-validations/?attention=1')

        self.assertEqual(response.status_code, 200)
        keys = {item['key'] for item in response.json()}
        self.assertEqual(keys, {'blocked-workflow', 'failing-workflow'})

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

    def test_staff_validation_page_renders_and_updates_feature(self):
        feature = FeatureValidation.objects.create(
            key='client-sharing-portal',
            name='Client Sharing Portal',
            area='P3',
            status=FeatureValidation.STATUS_UNTESTED,
        )

        response = self.client.get('/feature-validations/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client Sharing Portal')
        self.assertContains(response, 'Add Feature')
        self.assertContains(response, 'System Health')
        self.assertContains(response, 'Test Coverage')
        self.assertContains(response, 'Need Attention')
        self.assertContains(response, 'P3')

        response = self.client.post(
            '/feature-validations/',
            {
                'feature_id': feature.id,
                'key': feature.key,
                'name': feature.name,
                'area': feature.area,
                'status': FeatureValidation.STATUS_TESTED,
                'test_notes': 'Checked from the browser page.',
                'maintenance_notes': 'Keep this visible for staff.',
                'evidence_url': '',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        feature.refresh_from_db()
        self.assertEqual(feature.status, FeatureValidation.STATUS_TESTED)
        self.assertEqual(feature.last_tested_by, self.admin_user)
        self.assertIsNotNone(feature.last_tested_at)

    def test_regular_user_cannot_view_validation_page(self):
        self.client.logout()
        self.client.login(username='testuser', password='test1234')

        response = self.client.get('/feature-validations/')

        self.assertEqual(response.status_code, 302)

    def test_staff_validation_page_filters_attention_records(self):
        FeatureValidation.objects.create(
            key='tested-workflow',
            name='Tested Workflow',
            area='P1',
            status=FeatureValidation.STATUS_TESTED,
        )
        FeatureValidation.objects.create(
            key='untested-workflow',
            name='Untested Workflow',
            area='P2',
            status=FeatureValidation.STATUS_UNTESTED,
        )

        response = self.client.get('/feature-validations/?attention=1')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Untested Workflow')
        self.assertNotContains(response, 'Tested Workflow')

    def test_reconcile_command_creates_pipeline_validation_records(self):
        call_command('reconcilefeaturevalidations', '--tested', '--user', self.admin_user.username)

        features = FeatureValidation.objects.order_by('area')
        self.assertEqual(features.count(), 14)
        self.assertEqual(
            set(features.values_list('area', flat=True)),
            {'P{}'.format(index) for index in range(1, 15)},
        )
        self.assertEqual(
            FeatureValidation.objects.filter(status=FeatureValidation.STATUS_TESTED).count(),
            14,
        )
        self.assertTrue(
            FeatureValidation.objects.filter(
                key='textured-model-qa-sharing',
                test_notes__icontains='Browser smoke confirmed',
            ).exists()
        )
        self.assertTrue(
            FeatureValidation.objects.filter(
                key='core-platform-hardening',
                maintenance_notes__icontains='Run platformaudit',
                last_tested_by=self.admin_user,
            ).exists()
        )

    def test_reconcile_command_preserves_existing_notes_by_default(self):
        FeatureValidation.objects.create(
            key='monitoring-compare-mvp',
            name='Monitoring Compare MVP',
            area='P7',
            status=FeatureValidation.STATUS_UNTESTED,
            test_notes='Manual note',
        )

        call_command('reconcilefeaturevalidations', '--tested')

        feature = FeatureValidation.objects.get(key='monitoring-compare-mvp')
        self.assertEqual(feature.status, FeatureValidation.STATUS_TESTED)
        self.assertEqual(feature.test_notes, 'Manual note')

    def test_reconcile_command_backfills_tested_timestamp(self):
        feature = FeatureValidation.objects.create(
            key='monitoring-compare-mvp',
            name='Monitoring Compare MVP',
            area='P7',
            status=FeatureValidation.STATUS_UNTESTED,
        )
        FeatureValidation.objects.filter(pk=feature.pk).update(
            status=FeatureValidation.STATUS_TESTED,
            last_tested_at=None,
            last_tested_by_id=self.admin_user.id,
        )

        call_command('reconcilefeaturevalidations', '--tested', '--user', self.admin_user.username)

        feature.refresh_from_db()
        self.assertEqual(feature.status, FeatureValidation.STATUS_TESTED)
        self.assertEqual(feature.last_tested_by, self.admin_user)
        self.assertIsNotNone(feature.last_tested_at)

    def test_reconcile_command_rejects_conflicting_status_options(self):
        with self.assertRaises(CommandError):
            call_command(
                'reconcilefeaturevalidations',
                '--tested',
                '--status',
                FeatureValidation.STATUS_FAILING,
            )
