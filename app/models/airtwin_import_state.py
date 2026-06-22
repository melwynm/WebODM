from django.db import models
from django.utils.translation import gettext_lazy as _


class AirTwinImportState(models.Model):
    STATUS_PENDING = "pending"
    STATUS_IMPORTING = "importing"
    STATUS_IMPORTED = "imported"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_PENDING, _("Pending")),
        (STATUS_IMPORTING, _("Importing")),
        (STATUS_IMPORTED, _("Imported")),
        (STATUS_FAILED, _("Failed")),
    )

    task = models.OneToOneField(
        "app.Task",
        related_name="airtwin_import_state",
        on_delete=models.CASCADE,
    )
    event_id = models.UUIDField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    imported_assets = models.JSONField(default=list, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(default="", blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "AirTwin import {} ({})".format(self.task_id, self.status)

    class Meta:
        verbose_name = _("AirTwin import state")
        verbose_name_plural = _("AirTwin import states")
