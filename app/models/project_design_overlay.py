import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


SUPPORTED_MAP_EXTENSIONS = ('.geojson', '.json', '.zip')


def design_overlay_upload_path(overlay, filename):
    return os.path.join('project', str(overlay.project_id), 'design_overlays', filename)


def validate_design_overlay_file(value):
    ext = os.path.splitext(value.name or '')[1].lower()
    if ext not in SUPPORTED_MAP_EXTENSIONS:
        raise ValidationError(_("Design overlays must be GeoJSON (.geojson/.json) or zipped Shapefiles (.zip)."))


class ProjectDesignOverlay(models.Model):
    project = models.ForeignKey('app.Project', related_name='design_overlays', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(default='', blank=True)
    file = models.FileField(upload_to=design_overlay_upload_path, validators=[validate_design_overlay_file])
    source_filename = models.CharField(max_length=255, default='', blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='created_design_overlays', on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def extension(self):
        return os.path.splitext(self.source_filename or self.file.name or '')[1].lower().lstrip('.')

    @property
    def is_map_overlay(self):
        return f'.{self.extension}' in SUPPORTED_MAP_EXTENSIONS

    def save(self, *args, **kwargs):
        if not self.source_filename and self.file:
            self.source_filename = os.path.basename(self.file.name)
        if not self.name and self.source_filename:
            self.name = os.path.splitext(self.source_filename)[0]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('-updated_at', '-created_at')
        verbose_name = _("Project Design Overlay")
        verbose_name_plural = _("Project Design Overlays")
