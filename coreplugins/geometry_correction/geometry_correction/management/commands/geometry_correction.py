"""
Management command:
  python manage.py geometry_correction \
      --task-id <uuid> \
      --project-id <int> \
      [--plane-threshold 0.05] \
      [--snap-threshold 0.05] \
      [--line-angle-tolerance 2.0] \
      [--no-pointcloud] \
      [--no-mesh] \
      [--no-orthophoto]
"""

import json
import logging

from django.core.management.base import BaseCommand, CommandError

from geometry_correction.models import CorrectionJob
from geometry_correction.tasks import run_geometry_correction
from geometry_correction import config

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run AI-assisted geometry correction on a WebODM task (synchronous)"

    def add_arguments(self, parser):
        parser.add_argument("--task-id", required=True, help="WebODM task UUID")
        parser.add_argument("--project-id", required=True, type=int, help="WebODM project ID")
        parser.add_argument(
            "--plane-threshold",
            type=float,
            default=config.PLANE_DISTANCE_THRESHOLD,
            help="RANSAC inlier distance threshold (metres)",
        )
        parser.add_argument(
            "--snap-threshold",
            type=float,
            default=config.SNAP_DEVIATION_THRESHOLD,
            help="Max deviation for point snapping (metres)",
        )
        parser.add_argument(
            "--line-angle-tolerance",
            type=float,
            default=config.LINE_ANGLE_TOLERANCE,
            help="Angle tolerance for axis-aligned line detection (degrees)",
        )
        parser.add_argument("--no-pointcloud", action="store_true")
        parser.add_argument("--no-mesh", action="store_true")
        parser.add_argument("--no-orthophoto", action="store_true")

    def handle(self, *args, **options):
        opts = {
            "plane_threshold": options["plane_threshold"],
            "snap_threshold": options["snap_threshold"],
            "line_tolerance": options["line_angle_tolerance"],
            "correct_pointcloud": not options["no_pointcloud"],
            "correct_mesh": not options["no_mesh"],
            "correct_orthophoto": not options["no_orthophoto"],
        }

        job = CorrectionJob.objects.create(
            task_id=options["task_id"],
            project_id=options["project_id"],
            options=opts,
        )

        self.stdout.write(f"Created CorrectionJob #{job.pk} — running synchronously…")

        try:
            # Run synchronously (bypass Celery) for management command
            result = run_geometry_correction(job.pk)
            self.stdout.write(self.style.SUCCESS(
                f"Completed!\n{json.dumps(result, indent=2)}"
            ))
        except Exception as exc:
            raise CommandError(f"Correction failed: {exc}") from exc
