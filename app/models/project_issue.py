from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def validate_geojson_geometry(value):
    if value in (None, ''):
        return
    if not isinstance(value, dict):
        raise ValidationError(_("Geometry must be a GeoJSON object."))
    if value.get('type') not in ('Point', 'LineString', 'Polygon', 'MultiPoint', 'MultiLineString', 'MultiPolygon'):
        raise ValidationError(_("Unsupported GeoJSON geometry type."))
    if 'coordinates' not in value:
        raise ValidationError(_("GeoJSON geometry requires coordinates."))


class ProjectIssue(models.Model):
    ISSUE_TYPE_ANNOTATION = 'annotation'
    ISSUE_TYPE_CHANGE = 'change'
    ISSUE_TYPE_DEFECT = 'defect'
    ISSUE_TYPE_PROGRESS = 'progress'

    ISSUE_TYPE_CHOICES = (
        (ISSUE_TYPE_ANNOTATION, _("Annotation")),
        (ISSUE_TYPE_CHANGE, _("Change")),
        (ISSUE_TYPE_DEFECT, _("Defect")),
        (ISSUE_TYPE_PROGRESS, _("Progress")),
    )

    STATUS_OPEN = 'open'
    STATUS_IN_REVIEW = 'in_review'
    STATUS_RESOLVED = 'resolved'
    STATUS_CLOSED = 'closed'

    STATUS_CHOICES = (
        (STATUS_OPEN, _("Open")),
        (STATUS_IN_REVIEW, _("In Review")),
        (STATUS_RESOLVED, _("Resolved")),
        (STATUS_CLOSED, _("Closed")),
    )

    PRIORITY_LOW = 'low'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_HIGH = 'high'
    PRIORITY_CRITICAL = 'critical'

    PRIORITY_CHOICES = (
        (PRIORITY_LOW, _("Low")),
        (PRIORITY_MEDIUM, _("Medium")),
        (PRIORITY_HIGH, _("High")),
        (PRIORITY_CRITICAL, _("Critical")),
    )

    project = models.ForeignKey('app.Project', related_name='issues', on_delete=models.CASCADE)
    task = models.ForeignKey('app.Task', related_name='issues', on_delete=models.SET_NULL, blank=True, null=True)
    title = models.CharField(max_length=255)
    description = models.TextField(default='', blank=True)
    issue_type = models.CharField(max_length=24, choices=ISSUE_TYPE_CHOICES, default=ISSUE_TYPE_ANNOTATION)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    priority = models.CharField(max_length=24, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM, db_index=True)
    geometry = models.JSONField(blank=True, null=True, validators=[validate_geojson_geometry])
    properties = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='created_project_issues', on_delete=models.PROTECT)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='assigned_project_issues', on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_CLOSED and self.closed_at is None:
            self.closed_at = timezone.now()
        elif self.status != self.STATUS_CLOSED:
            self.closed_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ('-updated_at', '-created_at')
        verbose_name = _("Project Issue")
        verbose_name_plural = _("Project Issues")
