from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from app.services.demo_projects import create_demo_projects


class Command(BaseCommand):
    help = "Create synthetic commercial demo projects for architecture, agriculture, and solar workflows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner",
            default="",
            help="Username that should own the demo projects. Defaults to the first superuser, then the first user.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        owner = None
        if options["owner"]:
            try:
                owner = User.objects.get(username=options["owner"])
            except User.DoesNotExist:
                raise CommandError("User does not exist: {}".format(options["owner"]))
        else:
            owner = User.objects.filter(is_superuser=True).order_by("id").first() or User.objects.order_by("id").first()

        if owner is None:
            raise CommandError("No user exists. Create a user before generating demo projects.")

        results = create_demo_projects(owner)
        for result in results:
            status = "created" if result["created"] else "updated"
            self.stdout.write(
                "{status} {name} (ready={ready}, report={report_url}, readiness={readiness_url})".format(
                    status=status,
                    name=result["project"].name,
                    ready=result["ready"],
                    report_url=result["report_url"],
                    readiness_url=result["readiness_url"],
                )
            )

        self.stdout.write(self.style.SUCCESS("Prepared {} commercial demo project(s).".format(len(results))))
