from django.test import Client

from .classes import BootTestCase


class TestHelpCenter(BootTestCase):
    def test_help_requires_login(self):
        response = Client().get('/help/')

        self.assertRedirects(response, '/login/?next=/help/')

    def test_help_renders_searchable_guides_for_user(self):
        client = Client()
        self.assertTrue(client.login(username='testuser', password='test1234'))

        response = client.get('/help/')
        content = response.content.decode('utf-8')

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'app/help.html')
        self.assertContains(response, 'id="help-search"')
        self.assertContains(response, 'Create a Gaussian Splat')
        self.assertContains(response, 'Manage processing nodes and GPU work')
        self.assertContains(response, 'id="help-menu"')
        self.assertNotIn('Validate production readiness', content)

        help_position = content.index('id="help-menu"')
        about_position = content.index('id="about-menu"')
        self.assertLess(help_position, about_position)

    def test_help_includes_administration_guides_for_staff(self):
        client = Client()
        self.assertTrue(client.login(username='testsuperuser', password='test1234'))

        response = client.get('/help/')

        self.assertContains(response, 'Administer users, access, and appearance')
        self.assertContains(response, 'Validate production readiness')
