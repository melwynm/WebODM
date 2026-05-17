import json
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from guardian.shortcuts import assign_perm

from app.models import Project, ProjectFieldPhoto, ProjectIssue, Setting

from .classes import BootTestCase


class FakeOpenAIResponse:
    status_code = 200

    def json(self):
        return {
            "id": "resp_test",
            "output": [{
                "content": [{
                    "type": "output_text",
                    "text": json.dumps([{
                        "title": "Check exposed rebar near entrance",
                        "description": "The field photo appears to show exposed material that should be reviewed.",
                        "issue_type": "defect",
                        "priority": "high",
                        "confidence": 0.72,
                        "location_hint": "near the image center",
                    }]),
                }]
            }],
        }


class TestAIIssueDetectionApi(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.get(username='testuser')
        self.other_user = User.objects.get(username='testuser2')
        self.project = Project.objects.get(owner=self.user)
        self.other_project = Project.objects.get(owner=self.other_user)
        for perm in ['view_project', 'add_project', 'change_project', 'delete_project']:
            assign_perm(perm, self.user, self.project)
        self.client.login(username='testuser', password='test1234')
        settings = Setting.objects.first()
        settings.openai_api_key = "sk-test"
        settings.openai_model = "gpt-test"
        settings.save()
        self.field_photo = ProjectFieldPhoto.objects.create(
            project=self.project,
            name="Entrance photo",
            image=SimpleUploadedFile("entrance.jpg", b"not real jpg"),
            location={"type": "Point", "coordinates": [57.468, -20.244]},
            created_by=self.user,
        )

    def detection_url(self):
        return f'/api/projects/{self.project.id}/ai/issue-detection'

    @mock.patch("app.services.ai_issue_detection._resize_image_bytes", return_value=b"preview")
    @mock.patch("app.services.ai_issue_detection.requests.post", return_value=FakeOpenAIResponse())
    def test_ai_issue_detection_creates_review_issue(self, post_mock, _resize_mock):
        response = self.client.post(
            self.detection_url(),
            json.dumps({
                "source": "field_photos",
                "create": True,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["model"], "gpt-test")
        self.assertEqual(payload["candidate_count"], 1)
        self.assertEqual(payload["created_count"], 1)
        self.assertEqual(payload["issues"][0]["status"], ProjectIssue.STATUS_IN_REVIEW)
        self.assertEqual(ProjectIssue.objects.filter(project=self.project, properties__ai_generated=True).count(), 1)
        self.assertEqual(post_mock.call_args.kwargs["headers"]["Authorization"], "Bearer sk-test")

    def test_requires_openai_api_key(self):
        settings = Setting.objects.first()
        settings.openai_api_key = ""
        settings.save()

        response = self.client.post(
            self.detection_url(),
            json.dumps({"source": "field_photos"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("OpenAI API key", response.json()[0])

    def test_project_permissions_are_enforced(self):
        response = self.client.post(
            f'/api/projects/{self.other_project.id}/ai/issue-detection',
            json.dumps({"source": "field_photos"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
