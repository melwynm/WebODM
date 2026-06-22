from django.contrib.auth.models import User, Group
from rest_framework import status
from rest_framework.test import APIClient
import uuid

from app.models import AirTwinImportState, Task, Project
from nodeodm.models import ProcessingNode
from worker.tasks import check_quotas
from .classes import BootTestCase

class TestQuota(BootTestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_quota(self):
        c = APIClient()
        c.login(username="testuser", password="test1234")

        user = User.objects.get(username="testuser")
        self.assertEqual(user.profile.quota, -1)

        # There should be no quota panel
        res = c.get('/dashboard/', follow=True)
        body = res.content.decode("utf-8")

        # There should be no quota panel
        self.assertFalse('<div class="info-item quotas">' in body)

        user.profile.quota = 2000
        user.save()

        res = c.get('/dashboard/', follow=True)
        body = res.content.decode("utf-8")

        # There should be a quota panel
        self.assertTrue('<div class="info-item quotas">' in body)

        # There should be no warning
        self.assertFalse("disk quota is being exceeded" in body)

        self.assertEqual(user.profile.used_quota(), 0)
        self.assertEqual(user.profile.used_quota_cached(), 0)
        
        # Create a task with size
        p = Project.objects.create(owner=user, name='Test')
        p.save()
        t = Task.objects.create(project=p, name='Test', size=1005)
        t.save()
        t = Task.objects.create(project=p, name='Test2', size=1010)
        t.save()

        # Simulate call to task.update_size which calls clear_used_quota_cache
        user.profile.clear_used_quota_cache()

        self.assertTrue(user.profile.has_exceeded_quota())
        self.assertTrue(user.profile.has_exceeded_quota_cached())
        
        res = c.get('/dashboard/', follow=True)
        body = res.content.decode("utf-8")

        self.assertTrue("disk quota is being exceeded" in body)
        self.assertTrue("in 8 hours" in body)

        # Running the workers check_quota function will not remove tasks
        check_quotas()
        self.assertEqual(len(Task.objects.filter(project__owner=user)), 2)

        # Update grace period
        def check_quota_warning(hours, text):
            user.profile.set_quota_deadline(hours)
            res = c.get('/dashboard/', follow=True)
            body = res.content.decode("utf-8")
            self.assertTrue(text in body)
        
        check_quota_warning(73, "in 3 days")
        check_quota_warning(71, "in 2 days")
        check_quota_warning(47.9, "in 47 hours")
        check_quota_warning(3.1, "in 3 hours")
        check_quota_warning(1.51, "in 90 minutes")
        check_quota_warning(0.99, "in 59 minutes")
        check_quota_warning(0, "very soon")

        # Running the check_quotas function should remove the last task only
        check_quotas()
        tasks = Task.objects.filter(project__owner=user)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "Test")

    def test_quota_cleanup_skips_active_airtwin_imports(self):
        user = User.objects.get(username="testuser")
        user.profile.quota = 100
        user.profile.save(update_fields=["quota"])
        project = Project.objects.create(owner=user, name="AirTwin retention")
        unprotected = Task.objects.create(project=project, name="Unprotected", size=75)
        protected = Task.objects.create(project=project, name="Protected", size=75)
        AirTwinImportState.objects.create(
            task=protected,
            event_id=uuid.uuid4(),
            status=AirTwinImportState.STATUS_PENDING,
        )
        user.profile.clear_used_quota_cache()
        user.profile.set_quota_deadline(0)

        check_quotas()

        self.assertFalse(Task.objects.filter(pk=unprotected.pk).exists())
        self.assertTrue(Task.objects.filter(pk=protected.pk).exists())
