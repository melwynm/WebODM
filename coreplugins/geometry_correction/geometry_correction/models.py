"""
geometry_correction/models.py

Django model for tracking correction job status.
"""

from django.db import models


class CorrectionJob(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    task_id = models.CharField(max_length=128, db_index=True)
    project_id = models.IntegerField()
    celery_task_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # Options snapshot (JSON)
    options = models.JSONField(default=dict)

    # Results / statistics (JSON)
    result = models.JSONField(default=dict, blank=True)

    error_message = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Correction Job"
        verbose_name_plural = "Correction Jobs"

    def __str__(self):
        return f"CorrectionJob(task={self.task_id}, status={self.status})"
