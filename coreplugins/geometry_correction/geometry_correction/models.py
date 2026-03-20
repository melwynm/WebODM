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
        app_label = "geometry_correction"
        ordering = ["-created_at"]
        verbose_name = "Correction Job"
        verbose_name_plural = "Correction Jobs"

    def __str__(self):
        return f"CorrectionJob(task={self.task_id}, status={self.status})"

    def mark_running(self, celery_task_id=""):
        self.status = self.Status.RUNNING
        self.celery_task_id = celery_task_id or self.celery_task_id
        self.error_message = ""
        self.save(update_fields=["status", "celery_task_id", "error_message", "updated_at"])

    def mark_completed(self, result):
        self.status = self.Status.COMPLETED
        self.result = result or {}
        self.error_message = ""
        self.save(update_fields=["status", "result", "error_message", "updated_at"])

    def mark_failed(self, error_message, result=None):
        self.status = self.Status.FAILED
        self.error_message = str(error_message)
        if result is not None:
            self.result = result
            self.save(update_fields=["status", "result", "error_message", "updated_at"])
        else:
            self.save(update_fields=["status", "error_message", "updated_at"])
