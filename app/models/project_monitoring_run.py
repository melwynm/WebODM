import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ProjectMonitoringRun(models.Model):
    STATUS_GENERATING = "generating"
    STATUS_REVIEW = "review"
    STATUS_PUBLISHED = "published"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_GENERATING, _("Generating comparison")),
        (STATUS_REVIEW, _("Ready for review")),
        (STATUS_PUBLISHED, _("Published")),
        (STATUS_FAILED, _("Failed")),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "app.Project",
        related_name="monitoring_runs",
        on_delete=models.CASCADE,
    )
    current_task = models.ForeignKey(
        "app.Task",
        related_name="monitoring_runs_as_current",
        on_delete=models.CASCADE,
    )
    baseline_task = models.ForeignKey(
        "app.Task",
        related_name="monitoring_runs_as_baseline",
        on_delete=models.CASCADE,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_GENERATING,
        db_index=True,
    )
    report_template = models.CharField(max_length=40, default="general")
    celery_task_id = models.CharField(max_length=255, default="", blank=True)
    last_error = models.TextField(default="", blank=True)
    report_snapshot = models.JSONField(default=dict, blank=True)
    client_share = models.ForeignKey(
        "app.ProjectClientShare",
        related_name="monitoring_runs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_monitoring_runs",
        on_delete=models.PROTECT,
    )
    comparison_generated_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{}: {} vs {}".format(
            self.project,
            self.current_task.name or self.current_task_id,
            self.baseline_task.name or self.baseline_task_id,
        )

    class Meta:
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields=("project", "status", "-created_at"), name="app_monitor_project_4ff2a9_idx"),
        )
        verbose_name = _("Project monitoring run")
        verbose_name_plural = _("Project monitoring runs")
