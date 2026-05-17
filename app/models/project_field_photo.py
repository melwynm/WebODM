import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


SUPPORTED_FIELD_PHOTO_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff')


def field_photo_upload_path(field_photo, filename):
    return os.path.join('project', str(field_photo.project_id), 'field_photos', filename)


def validate_field_photo_file(value):
    ext = os.path.splitext(value.name or '')[1].lower()
    if ext not in SUPPORTED_FIELD_PHOTO_EXTENSIONS:
        raise ValidationError(_("Field photos must be image files (.jpg, .jpeg, .png, .webp, .tif, or .tiff)."))


def validate_point_geometry(value):
    if not isinstance(value, dict):
        raise ValidationError(_("Location must be a GeoJSON point."))
    if value.get('type') != 'Point':
        raise ValidationError(_("Location must be a GeoJSON point."))
    coordinates = value.get('coordinates')
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
        raise ValidationError(_("Location requires longitude and latitude coordinates."))
    try:
        longitude = float(coordinates[0])
        latitude = float(coordinates[1])
    except (TypeError, ValueError):
        raise ValidationError(_("Location coordinates must be numeric."))
    if longitude < -180 or longitude > 180 or latitude < -90 or latitude > 90:
        raise ValidationError(_("Location coordinates are outside valid longitude/latitude bounds."))


class ProjectFieldPhoto(models.Model):
    project = models.ForeignKey('app.Project', related_name='field_photos', on_delete=models.CASCADE)
    task = models.ForeignKey('app.Task', related_name='field_photos', on_delete=models.SET_NULL, blank=True, null=True)
    name = models.CharField(max_length=255)
    description = models.TextField(default='', blank=True)
    image = models.FileField(upload_to=field_photo_upload_path, validators=[validate_field_photo_file])
    source_filename = models.CharField(max_length=255, default='', blank=True)
    location = models.JSONField(validators=[validate_point_geometry])
    is_360 = models.BooleanField(default=False)
    captured_at = models.DateTimeField(blank=True, null=True)
    altitude = models.FloatField(blank=True, null=True)
    heading = models.FloatField(blank=True, null=True)
    properties = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='created_field_photos', on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def longitude(self):
        return self.location['coordinates'][0]

    @property
    def latitude(self):
        return self.location['coordinates'][1]

    def save(self, *args, **kwargs):
        if not self.source_filename and self.image:
            self.source_filename = os.path.basename(self.image.name)
        if not self.name and self.source_filename:
            self.name = os.path.splitext(self.source_filename)[0]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('-captured_at', '-updated_at', '-created_at')
        verbose_name = _("Project Field Photo")
        verbose_name_plural = _("Project Field Photos")
