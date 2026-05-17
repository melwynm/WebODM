from django.core.management.base import BaseCommand, CommandError

from app.models import Task

from ...tasks import train_gaussian_splat


class Command(BaseCommand):
    help = "Train a Gaussian Splat PLY for a completed WebODM task."

    def add_arguments(self, parser):
        parser.add_argument("--task-id", required=True)
        parser.add_argument("--iterations", type=int, default=None)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        try:
            task = Task.objects.get(pk=options["task_id"])
        except Task.DoesNotExist:
            raise CommandError("Task not found")

        train_options = {"force": options["force"]}
        if options["iterations"] is not None:
            train_options["iterations"] = options["iterations"]

        def progress(message, value):
            self.stdout.write("[{}%] {}".format(value, message))

        try:
            result = train_gaussian_splat(task, train_options, progress_callback=progress)
        except Exception as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS("Gaussian Splat written to {}".format(result["output"])))
