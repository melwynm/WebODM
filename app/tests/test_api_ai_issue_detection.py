import json
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from guardian.shortcuts import assign_perm

from app.models import Project, ProjectFieldPhoto, ProjectIssue, Setting
from app.services.ai_issue_detection import (
    MAX_AI_DESCRIPTION_LENGTH,
    MAX_AI_ISSUE_CANDIDATES,
    MAX_AI_LOCATION_HINT_LENGTH,
    _parse_candidates,
)

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


class InvalidJSONOpenAIResponse:
    status_code = 200

    def json(self):
        raise ValueError("not json")


class MalformedOpenAIResponse:
    status_code = 200

    def json(self):
        return {
            "id": "resp_malformed",
            "output": [None, {"content": [None, {"type": "output_text", "text": {"not": "text"}}]}],
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
        issue = ProjectIssue.objects.get(project=self.project, properties__ai_generated=True)
        self.assertEqual(issue.properties["ai_model"], "gpt-test")
        self.assertEqual(issue.properties["ai_response_id"], "resp_test")

    @mock.patch("app.services.ai_issue_detection._resize_image_bytes", return_value=b"preview")
    @mock.patch("app.services.ai_issue_detection.requests.post", return_value=FakeOpenAIResponse())
    def test_preview_token_creates_exact_candidates_without_second_model_call(self, post_mock, _resize_mock):
        preview = self.client.post(
            self.detection_url(),
            json.dumps({
                "source": "field_photos",
                "create": False,
            }),
            content_type="application/json",
        )

        self.assertEqual(preview.status_code, 200)
        preview_payload = preview.json()
        self.assertEqual(preview_payload["candidate_count"], 1)
        self.assertEqual(preview_payload["created_count"], 0)
        self.assertTrue(preview_payload["confirmation_token"])
        self.assertEqual(ProjectIssue.objects.filter(project=self.project).count(), 0)

        confirmation = self.client.post(
            self.detection_url(),
            json.dumps({
                "confirmation_token": preview_payload["confirmation_token"],
                "create": True,
            }),
            content_type="application/json",
        )

        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(confirmation.json()["created_count"], 1)
        self.assertEqual(post_mock.call_count, 1)
        issue = ProjectIssue.objects.get(project=self.project)
        self.assertEqual(issue.title, preview_payload["candidates"][0]["title"])
        self.assertEqual(issue.status, ProjectIssue.STATUS_IN_REVIEW)

        replay = self.client.post(
            self.detection_url(),
            json.dumps({
                "confirmation_token": preview_payload["confirmation_token"],
                "create": True,
            }),
            content_type="application/json",
        )

        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["created_count"], 0)
        self.assertEqual(len(replay.json()["issues"]), 1)
        self.assertEqual(ProjectIssue.objects.filter(project=self.project).count(), 1)
        self.assertEqual(post_mock.call_count, 1)

    def test_rejects_tampered_preview_token(self):
        response = self.client.post(
            self.detection_url(),
            json.dumps({
                "confirmation_token": "tampered-token",
                "create": True,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("preview is invalid", response.json()[0])
        self.assertEqual(ProjectIssue.objects.filter(project=self.project).count(), 0)

    @mock.patch("app.services.ai_issue_detection._resize_image_bytes", return_value=b"preview")
    @mock.patch("app.services.ai_issue_detection.requests.post", return_value=InvalidJSONOpenAIResponse())
    def test_invalid_openai_payload_is_reported_without_server_error(self, _post_mock, _resize_mock):
        response = self.client.post(
            self.detection_url(),
            json.dumps({"source": "field_photos", "create": False}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid response payload", response.json()[0])

    @mock.patch("app.services.ai_issue_detection._resize_image_bytes", return_value=b"preview")
    @mock.patch("app.services.ai_issue_detection.requests.post", return_value=MalformedOpenAIResponse())
    def test_malformed_openai_output_is_reported_without_server_error(self, _post_mock, _resize_mock):
        response = self.client.post(
            self.detection_url(),
            json.dumps({"source": "field_photos", "create": False}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid JSON", response.json()[0])

    @mock.patch("app.services.ai_issue_detection._resize_image_bytes", return_value=b"preview")
    @mock.patch("app.services.ai_issue_detection.requests.post", side_effect=requests.Timeout())
    def test_openai_timeout_is_reported_without_server_error(self, _post_mock, _resize_mock):
        response = self.client.post(
            self.detection_url(),
            json.dumps({"source": "field_photos", "create": False}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("could not be completed", response.json()[0])

    def test_candidates_are_bounded_and_normalized(self):
        raw_candidates = [{
            "title": "Issue {}".format(index),
            "description": "d" * (MAX_AI_DESCRIPTION_LENGTH + 20),
            "issue_type": "unknown",
            "priority": "urgent",
            "confidence": 4.2,
            "location_hint": "l" * (MAX_AI_LOCATION_HINT_LENGTH + 20),
        } for index in range(MAX_AI_ISSUE_CANDIDATES + 5)]

        candidates = _parse_candidates(json.dumps(raw_candidates))

        self.assertEqual(len(candidates), MAX_AI_ISSUE_CANDIDATES)
        self.assertEqual(len(candidates[0]["description"]), MAX_AI_DESCRIPTION_LENGTH)
        self.assertEqual(len(candidates[0]["location_hint"]), MAX_AI_LOCATION_HINT_LENGTH)
        self.assertEqual(candidates[0]["issue_type"], ProjectIssue.ISSUE_TYPE_DEFECT)
        self.assertEqual(candidates[0]["priority"], ProjectIssue.PRIORITY_MEDIUM)
        self.assertEqual(candidates[0]["confidence"], 1.0)

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
