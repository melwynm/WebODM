import json

from django.core.management.base import BaseCommand, CommandError

from app.services.production_readiness import (
    STATUS_ERROR,
    STATUS_OK,
    STATUS_WARNING,
    run_production_readiness,
)


class Command(BaseCommand):
    requires_system_checks = []
    help = "Check production deployment hardening before commercial/pilot use."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Output readiness results as JSON.")
        parser.add_argument("--skip-runtime", action="store_true", help="Only check static settings and environment.")
        parser.add_argument("--allow-http", action="store_true", help="Allow non-HTTPS deployments for local staging.")
        parser.add_argument("--allow-wildcard-hosts", action="store_true", help="Allow ALLOWED_HOSTS=['*'].")
        parser.add_argument("--allow-open-cors", action="store_true", help="Allow CORS_ORIGIN_ALLOW_ALL=True.")
        parser.add_argument("--allow-generated-secret", action="store_true", help="Allow missing WO_SECRET_KEY.")

    def handle(self, *args, **options):
        summary = run_production_readiness(
            include_runtime=not options["skip_runtime"],
            allow_http=options["allow_http"],
            allow_wildcard_hosts=options["allow_wildcard_hosts"],
            allow_open_cors=options["allow_open_cors"],
            allow_generated_secret=options["allow_generated_secret"],
        )

        if options["json"]:
            self.stdout.write(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        else:
            for result in summary.results:
                label = "[{}] {}: {}".format(result.status.upper(), result.area, result.name)
                if result.status == STATUS_OK:
                    self.stdout.write(self.style.SUCCESS("{} - {}".format(label, result.detail)))
                elif result.status == STATUS_WARNING:
                    self.stdout.write(self.style.WARNING("{} - {}".format(label, result.detail)))
                    if result.remediation:
                        self.stdout.write("  {}".format(result.remediation))
                elif result.status == STATUS_ERROR:
                    self.stdout.write(self.style.ERROR("{} - {}".format(label, result.detail)))
                    if result.remediation:
                        self.stdout.write("  {}".format(result.remediation))

            counts = summary.counts
            self.stdout.write(
                "Production readiness complete: {ok} ok, {warning} warning, {error} error, {total} total".format(
                    **counts
                )
            )

        if summary.errors:
            raise CommandError("Production readiness failed with {} error(s).".format(len(summary.errors)))
