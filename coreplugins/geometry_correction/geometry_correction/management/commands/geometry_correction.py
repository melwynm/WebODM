"""
Management command for geometry_correction.
"""

import json
import logging

from django.core.management.base import BaseCommand, CommandError

from geometry_correction import config
from geometry_correction.tasks import build_status_payload, run_geometry_correction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run geometry correction on a completed WebODM task"

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
        parser.add_argument("--disable-semantic-profiles", action="store_true")
        parser.add_argument("--disable-confidence-map", action="store_true")

    def handle(self, *args, **options):
        opts = {
            "plane_threshold": options["plane_threshold"],
            "snap_threshold": options["snap_threshold"],
            "line_tolerance": options["line_angle_tolerance"],
            "correct_pointcloud": not options["no_pointcloud"],
            "correct_mesh": not options["no_mesh"],
            "correct_orthophoto": not options["no_orthophoto"],
            "use_semantic_profiles": not options["disable_semantic_profiles"],
            "generate_confidence_map": not options["disable_confidence_map"],
        }

        self.stdout.write(
            "Running geometry correction synchronously for task {} in project {}.".format(
                options["task_id"],
                options["project_id"],
            )
        )

        result = run_geometry_correction.run(
            str(options["task_id"]),
            int(options["project_id"]),
            opts,
        )

        if result.get("error"):
            raise CommandError("Correction failed: {}".format(result["error"]))

        payload = result.get("output")
        if payload is None:
            try:
                from app.models import Task

                payload = build_status_payload(Task.objects.get(pk=options["task_id"], project=options["project_id"]))
            except Exception as exc:
                raise CommandError("Correction finished without a readable payload: {}".format(exc)) from exc

        self.stdout.write(self.style.SUCCESS(json.dumps(payload, indent=2)))
