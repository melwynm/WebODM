import logging
import os
from pathlib import Path

from django.db.models import signals
from django.db import models
from colorfield.fields import ColorField
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key

from webodm import settings

logger = logging.getLogger('app.logger')

ACCESSIBLE_THEME_DEFAULTS = {
    'primary': '#1f2937',
    'secondary': '#f8fafc',
    'tertiary': '#0f62fe',
    'button_primary': '#0b63ce',
    'button_default': '#475569',
    'button_danger': '#b91c1c',
    'header_background': '#0b63ce',
    'header_primary': '#ffffff',
    'border': '#d1d5db',
    'highlight': '#eef2f7',
    'dialog_warning': '#b45309',
    'failed': '#fee2e2',
    'success': '#dcfce7',
}


class Theme(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False, help_text=_("Name of theme"), verbose_name=_("Name"))

    # Similar to how discourse.org does it
    primary = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['primary'], help_text=_("Most text, icons, and borders."), verbose_name=_("Primary"))
    secondary = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['secondary'], help_text=_("The main background color, and text color of some buttons."), verbose_name=_("Secondary"))
    tertiary = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['tertiary'], help_text=_("Navigation links."), verbose_name=_("Tertiary"))

    button_primary = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['button_primary'], help_text=_("Primary button color."), verbose_name=_("Button Primary"))
    button_default = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['button_default'], help_text=_("Default button color."), verbose_name=_("Button Default"))
    button_danger = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['button_danger'], help_text=_("Delete button color."), verbose_name=_("Button Danger"))

    header_background = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['header_background'], help_text=_("Background color of the site's header."), verbose_name=_("Header Background"))
    header_primary = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['header_primary'], help_text=_("Text and icons in the site's header."), verbose_name=_("Header Primary"))

    border = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['border'], help_text=_("The color of most borders."), verbose_name=_("Border"))
    highlight = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['highlight'], help_text=_("The background color of panels and some borders."), verbose_name=_("Highlight"))

    dialog_warning = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['dialog_warning'], help_text=_("The border color of warning dialogs."), verbose_name=_("Dialog Warning"))

    failed = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['failed'], help_text=_("The background color of failed notifications."), verbose_name=_("Failed"))
    success = ColorField(default=ACCESSIBLE_THEME_DEFAULTS['success'], help_text=_("The background color of success notifications."), verbose_name=_("Success"))

    css = models.TextField(default='', blank=True, verbose_name=_("CSS"))
    html_before_header = models.TextField(default='', blank=True, verbose_name=_("HTML (before header)"))
    html_after_header = models.TextField(default='', blank=True, verbose_name=_("HTML (after header)"))
    html_after_body = models.TextField(default='', blank=True, verbose_name=_("HTML (after body)"))
    html_footer = models.TextField(default='', blank=True, verbose_name=_("HTML (footer)"))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Theme")
        verbose_name_plural = _("Theme")


@receiver(signals.post_save, sender=Theme, dispatch_uid="theme_post_save")
def theme_post_save(sender, instance, created, **kwargs):
    update_theme_css()


def update_theme_css():
    key = make_template_fragment_key("theme_css")
    cache.delete(key)
