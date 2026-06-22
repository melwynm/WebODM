from django.db import models
from django.utils.translation import gettext_lazy as _


class AirTwinWebhookDelivery(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RETRYING = "retrying"
    STATUS_DELIVERED = "delivered"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_PENDING, _("Pending")),
        (STATUS_RETRYING, _("Retrying")),
        (STATUS_DELIVERED, _("Delivered")),
        (STATUS_FAILED, _("Failed")),
    )

    task = models.ForeignKey(
        "app.Task",
        related_name="airtwin_webhook_deliveries",
        on_delete=models.CASCADE,
    )
    event_id = models.UUIDField(unique=True, db_index=True)
    event = models.CharField(max_length=80, default="webodm.task.completed")
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    response_status = models.PositiveIntegerField(null=True, blank=True)
    last_error = models.TextField(default="", blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{} {} ({})".format(self.event, self.task_id, self.status)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("AirTwin webhook delivery")
        verbose_name_plural = _("AirTwin webhook deliveries")
