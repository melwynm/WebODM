from copy import deepcopy

from django.contrib.auth.models import User
from django.utils import timezone
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient

from app.tests.classes import BootTestCase
from nodeodm.models import ProcessingNode


class TestProcessingNodeOptions(BootTestCase):
    def test_common_options_do_not_modify_available_options(self):
        user = User.objects.get(username="testuser")
        client = APIClient()
        self.assertTrue(client.login(username="testuser", password="test1234"))

        node1_options = [
            {"name": "common", "value": 1},
            {"name": "node1_only", "value": 2},
        ]
        node2_options = [
            {"name": "common", "value": 1},
            {"name": "node2_only", "value": 3},
        ]

        node1 = ProcessingNode.objects.create(
            hostname="node1", port=3001, available_options=deepcopy(node1_options)
        )
        node2 = ProcessingNode.objects.create(
            hostname="node2", port=3002, available_options=deepcopy(node2_options)
        )

        now = timezone.now()
        ProcessingNode.objects.filter(pk=node1.pk).update(last_refreshed=now)
        ProcessingNode.objects.filter(pk=node2.pk).update(last_refreshed=now)

        assign_perm("view_processingnode", user, node1)
        assign_perm("view_processingnode", user, node2)

        response = client.get("/api/processingnodes/options/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [node1_options[0]])

        node1.refresh_from_db()
        node2.refresh_from_db()
        self.assertEqual(node1.available_options, node1_options)
        self.assertEqual(node2.available_options, node2_options)
        client.logout()
