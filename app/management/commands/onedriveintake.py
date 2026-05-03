import os

from django.core.management.base import BaseCommand, CommandError

from app.models import Project
from app.onedrive_intake import OneDriveIntakeError, intake_onedrive_folder


class Command(BaseCommand):
    help = "Create import tasks from a OneDrive-synced intake folder."

    def add_arguments(self, parser):
        parser.add_argument("--project", required=True, type=int, help="Project ID that will receive imported tasks.")
        parser.add_argument(
            "--folder",
            default=os.environ.get("WO_ONEDRIVE_INTAKE_DIR", ""),
            help="OneDrive-synced intake folder. Defaults to WO_ONEDRIVE_INTAKE_DIR.",
        )
        parser.add_argument(
            "--min-age",
            default=int(os.environ.get("WO_ONEDRIVE_INTAKE_MIN_AGE", "60") or 60),
            type=int,
            help="Minimum age in seconds before a dataset is considered stable.",
        )
        parser.add_argument("--dry-run", action="store_true", help="List datasets without creating tasks.")
        parser.add_argument("--no-process", action="store_true", help="Create import tasks without dispatching workers.")

    def handle(self, *args, **options):
        folder = options["folder"]
        if not folder:
            raise CommandError("Set --folder or WO_ONEDRIVE_INTAKE_DIR.")

        try:
            project = Project.objects.get(pk=options["project"])
        except Project.DoesNotExist:
            raise CommandError("Project does not exist: {}".format(options["project"]))

        try:
            results = intake_onedrive_folder(
                project,
                folder,
                min_age_seconds=options["min_age"],
                dry_run=options["dry_run"],
                auto_process=not options["no_process"],
            )
        except OneDriveIntakeError as e:
            raise CommandError(str(e))

        created = 0
        skipped = 0
        ready = 0
        for result in results:
            dataset = result["dataset"]
            status = result["status"]
            if status == "created":
                created += 1
                self.stdout.write(
                    self.style.SUCCESS("created task {} from {}".format(result["task"].id, dataset["name"]))
                )
            elif status == "ready":
                ready += 1
                self.stdout.write("ready {}".format(dataset["name"]))
            else:
                skipped += 1
                self.stdout.write("skipped {}".format(dataset["name"]))

        self.stdout.write(
            "OneDrive intake complete: {} created, {} ready, {} skipped".format(created, ready, skipped)
        )
