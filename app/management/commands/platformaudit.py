import json

from django.core.management.base import BaseCommand, CommandError

from app.services.platform_audit import run_platform_audit


class Command(BaseCommand):
    requires_system_checks = []
    help = "Audit custom fork surfaces that should survive WebODM upgrades."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Output the full audit report as JSON.")

    def handle(self, *args, **options):
        summary = run_platform_audit()

        if options["json"]:
            self.stdout.write(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        else:
            for result in summary.results:
                label = "[{}] {}: {}".format(result.status.upper(), result.area, result.name)
                if result.ok:
                    self.stdout.write(self.style.SUCCESS("{} - {}".format(label, result.detail)))
                else:
                    self.stdout.write(self.style.ERROR("{} - {}".format(label, result.detail)))
                    if result.remediation:
                        self.stdout.write("  {}".format(result.remediation))

            counts = summary.counts
            self.stdout.write(
                "Platform audit complete: {ok} ok, {missing} missing, {error} error, {total} total".format(
                    **counts
                )
            )

        if summary.failures:
            raise CommandError("Platform audit failed with {} issue(s).".format(len(summary.failures)))
