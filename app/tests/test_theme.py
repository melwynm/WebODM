from django.test import Client
from django.template import Context
from django.core.cache import cache

from .classes import BootTestCase
from app.contexts.settings import load as load_settings
from app.templatetags import settings as settings_tags
from app.models import Theme, Setting

class TestSettings(BootTestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_settings(self):
        c = Client()
        c.login(username="testuser", password="test1234")

        # Get a page
        res = c.get('/dashboard/', follow=True)
        body = res.content.decode("utf-8")

        # There shouldn't be a footer by default
        self.assertFalse("<footer>" in body)

        # A strong purple color is not part of the default theme
        purple = "#8400ff"
        self.assertNotIn(purple, body.lower())

        # But colors from the theme are
        theme = load_settings()["SETTINGS"].theme
        self.assertIn(theme.primary.lower(), body.lower())

        # Let's change the theme
        theme.primary = purple # add color
        theme.html_footer = "<p>hello</p>"
        theme.save()
        cache.clear()

        # Get a page
        res = c.get('/dashboard/', follow=True)
        body = res.content.decode("utf-8")

        # We now have a footer
        self.assertTrue("<footer><p>hello</p></footer>" in body)

        # Purple is in body also
        self.assertIn(purple, body.lower())

    def test_default_theme_used_when_settings_missing(self):
        Setting.objects.all().delete()
        Theme.objects.all().delete()

        ctx = Context({})
        default_theme = Theme()

        self.assertEqual(
            settings_tags.theme(ctx, "primary"),
            default_theme.primary
        )



