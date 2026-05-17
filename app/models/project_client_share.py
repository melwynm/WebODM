import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from app.models.project_issue import validate_geojson_geometry


class ProjectClientShare(models.Model):
    ROLE_VIEWER = 'viewer'
    ROLE_REVIEWER = 'reviewer'

    ROLE_CHOICES = (
        (ROLE_VIEWER, _("Viewer")),
        (ROLE_REVIEWER, _("Reviewer")),
    )

    project = models.ForeignKey('app.Project', related_name='client_shares', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    role = models.CharField(max_length=24, choices=ROLE_CHOICES, default=ROLE_VIEWER, db_index=True)
    enabled = models.BooleanField(default=True, db_index=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='created_client_shares', on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_active(self):
        return self.enabled and (self.expires_at is None or self.expires_at > timezone.now())

    def portal_path(self):
        return reverse('client_portal', kwargs={'token': str(self.token)})

    def __str__(self):
        return "{} ({})".format(self.name, self.project.name)

    class Meta:
        ordering = ('-updated_at', '-created_at')
        verbose_name = _("Project Client Share")
        verbose_name_plural = _("Project Client Shares")


class ProjectClientComment(models.Model):
    share = models.ForeignKey('app.ProjectClientShare', related_name='comments', on_delete=models.CASCADE)
    project = models.ForeignKey('app.Project', related_name='client_comments', on_delete=models.CASCADE)
    task = models.ForeignKey('app.Task', related_name='client_comments', on_delete=models.SET_NULL, blank=True, null=True)
    issue = models.ForeignKey('app.ProjectIssue', related_name='client_comments', on_delete=models.SET_NULL, blank=True, null=True)
    author_name = models.CharField(max_length=255)
    author_email = models.EmailField(default='', blank=True)
    body = models.TextField()
    geometry = models.JSONField(blank=True, null=True, validators=[validate_geojson_geometry])
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    def __str__(self):
        return "{} on {}".format(self.author_name, self.project.name)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = _("Project Client Comment")
        verbose_name_plural = _("Project Client Comments")
