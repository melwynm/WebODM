from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ProjectCommercialReadiness(models.Model):
    PACKAGE_BASIC_ORTHOMOSAIC = "basic_orthomosaic"
    PACKAGE_ARCHITECTURE_CAD = "architecture_cad"
    PACKAGE_AGRICULTURE_FIELD = "agriculture_field"
    PACKAGE_SOLAR_INSPECTION = "solar_inspection"

    PACKAGE_CHOICES = (
        (PACKAGE_BASIC_ORTHOMOSAIC, _("Basic Orthomosaic")),
        (PACKAGE_ARCHITECTURE_CAD, _("Architecture CAD Orthomosaic")),
        (PACKAGE_AGRICULTURE_FIELD, _("Agriculture Field Analysis")),
        (PACKAGE_SOLAR_INSPECTION, _("Solar Panel Inspection")),
    )

    project = models.OneToOneField(
        "app.Project",
        related_name="commercial_readiness",
        on_delete=models.CASCADE,
    )
    package = models.CharField(
        max_length=40,
        choices=PACKAGE_CHOICES,
        default=PACKAGE_BASIC_ORTHOMOSAIC,
        db_index=True,
    )
    deliverables_reviewed = models.BooleanField(default=False)
    human_reviewed = models.BooleanField(default=False)
    report_reviewed = models.BooleanField(default=False)
    client_share_reviewed = models.BooleanField(default=False)
    legal_disclaimer_reviewed = models.BooleanField(default=False)
    notes = models.TextField(default="", blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="updated_commercial_readiness_records",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{} commercial readiness".format(self.project.name)

    class Meta:
        verbose_name = _("Project Commercial Readiness")
        verbose_name_plural = _("Project Commercial Readiness")
