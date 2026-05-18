from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class FeatureValidation(models.Model):
    STATUS_UNTESTED = 'untested'
    STATUS_TESTING = 'testing'
    STATUS_TESTED = 'tested'
    STATUS_FAILING = 'failing'
    STATUS_BLOCKED = 'blocked'

    STATUS_CHOICES = (
        (STATUS_UNTESTED, _("Untested")),
        (STATUS_TESTING, _("Testing")),
        (STATUS_TESTED, _("Tested")),
        (STATUS_FAILING, _("Failing")),
        (STATUS_BLOCKED, _("Blocked")),
    )

    key = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=255)
    area = models.CharField(max_length=120, default='', blank=True, db_index=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_UNTESTED, db_index=True)
    test_notes = models.TextField(default='', blank=True)
    maintenance_notes = models.TextField(default='', blank=True)
    evidence_url = models.URLField(default='', blank=True)
    last_tested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='feature_validations_tested',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    last_tested_at = models.DateTimeField(blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_TESTED and self.last_tested_at is None:
            self.last_tested_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return "{} ({})".format(self.name, self.status)

    @property
    def needs_attention(self):
        return self.status in (
            self.STATUS_UNTESTED,
            self.STATUS_FAILING,
            self.STATUS_BLOCKED,
        )

    @property
    def attention_reason(self):
        if self.status == self.STATUS_UNTESTED:
            return _("Needs first validation pass")
        if self.status == self.STATUS_FAILING:
            return _("Failing validation")
        if self.status == self.STATUS_BLOCKED:
            return _("Blocked validation")
        if self.status == self.STATUS_TESTING:
            return _("Validation in progress")
        return ""

    class Meta:
        ordering = ('area', 'name')
        verbose_name = _("Feature Validation")
        verbose_name_plural = _("Feature Validations")
