import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from app.services.feature_validation import PIPELINE_FEATURE_VALIDATIONS
from app.services.platform_audit import run_platform_audit


STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class ProductionReadinessResult:
    area: str
    name: str
    status: str
    detail: str
    remediation: str = ""

    @property
    def ok(self):
        return self.status == STATUS_OK

    def to_dict(self):
        return {
            "area": self.area,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "remediation": self.remediation,
        }


class ProductionReadinessSummary:
    def __init__(self, results):
        self.results = list(results)

    @property
    def errors(self):
        return [result for result in self.results if result.status == STATUS_ERROR]

    @property
    def warnings(self):
        return [result for result in self.results if result.status == STATUS_WARNING]

    @property
    def ok(self):
        return not self.errors

    @property
    def counts(self):
        counts = {
            STATUS_OK: 0,
            STATUS_WARNING: 0,
            STATUS_ERROR: 0,
        }
        for result in self.results:
            counts[result.status] = counts.get(result.status, 0) + 1
        counts["total"] = len(self.results)
        return counts

    def to_dict(self):
        return {
            "ok": self.ok,
            "counts": self.counts,
            "errors": [result.to_dict() for result in self.errors],
            "warnings": [result.to_dict() for result in self.warnings],
            "results": [result.to_dict() for result in self.results],
        }


def _result(area, name, status, detail, remediation=""):
    return ProductionReadinessResult(area, name, status, detail, remediation)


def _env_enabled(name):
    return os.environ.get(name, "").upper() in ("1", "TRUE", "YES", "ON")


def _writable_directory(path):
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".webodm-readiness-", dir=str(directory), delete=True):
        return True


def _check_static_configuration(
    allow_http=False,
    allow_wildcard_hosts=False,
    allow_open_cors=False,
    allow_generated_secret=False,
):
    results = []

    if settings.DEBUG:
        results.append(_result(
            "security",
            "Debug mode",
            STATUS_ERROR,
            "DEBUG is enabled.",
            "Set WO_DEBUG=NO and verify no settings override re-enables DEBUG.",
        ))
    else:
        results.append(_result("security", "Debug mode", STATUS_OK, "DEBUG is disabled."))

    if os.environ.get("WO_SECRET_KEY") or allow_generated_secret:
        detail = "WO_SECRET_KEY is set." if os.environ.get("WO_SECRET_KEY") else "Generated secret accepted by flag."
        results.append(_result("security", "Secret key", STATUS_OK, detail))
    else:
        results.append(_result(
            "security",
            "Secret key",
            STATUS_ERROR,
            "WO_SECRET_KEY is not set explicitly.",
            "Set a long stable WO_SECRET_KEY before recreating production containers.",
        ))

    ssl_enabled = _env_enabled("WO_SSL") or (settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE)
    if ssl_enabled:
        results.append(_result("security", "HTTPS cookies", STATUS_OK, "HTTPS/cookie secure settings are enabled."))
    elif allow_http:
        results.append(_result("security", "HTTPS cookies", STATUS_WARNING, "HTTP accepted by command flag."))
    else:
        results.append(_result(
            "security",
            "HTTPS cookies",
            STATUS_ERROR,
            "HTTPS/cookie secure settings are not enabled.",
            "Set WO_SSL=YES or run behind a trusted HTTPS proxy with secure cookie settings.",
        ))

    if "*" in getattr(settings, "ALLOWED_HOSTS", []):
        if allow_wildcard_hosts:
            results.append(_result("security", "Allowed hosts", STATUS_WARNING, "Wildcard ALLOWED_HOSTS accepted by command flag."))
        else:
            results.append(_result(
                "security",
                "Allowed hosts",
                STATUS_ERROR,
                "ALLOWED_HOSTS contains '*'.",
                "Use a settings override to restrict ALLOWED_HOSTS to production domains.",
            ))
    else:
        results.append(_result("security", "Allowed hosts", STATUS_OK, ", ".join(settings.ALLOWED_HOSTS)))

    if getattr(settings, "CORS_ORIGIN_ALLOW_ALL", False):
        if allow_open_cors:
            results.append(_result("security", "CORS", STATUS_WARNING, "Open CORS accepted by command flag."))
        else:
            results.append(_result(
                "security",
                "CORS",
                STATUS_ERROR,
                "CORS_ORIGIN_ALLOW_ALL is enabled.",
                "Use a settings override to allow only trusted client origins.",
            ))
    else:
        results.append(_result("security", "CORS", STATUS_OK, "CORS is restricted."))

    backup_dir = os.environ.get("WO_BACKUP_DIR", "")
    if not backup_dir:
        results.append(_result(
            "backup",
            "Backup directory",
            STATUS_ERROR,
            "WO_BACKUP_DIR is not set.",
            "Set WO_BACKUP_DIR to a durable host path and run a restore drill before pilot launch.",
        ))
    else:
        try:
            _writable_directory(backup_dir)
            results.append(_result("backup", "Backup directory", STATUS_OK, "{} is writable.".format(backup_dir)))
        except Exception as exc:
            results.append(_result(
                "backup",
                "Backup directory",
                STATUS_ERROR,
                "{} is not writable ({})".format(backup_dir, exc),
                "Create the backup path and grant write permission to the runtime user.",
            ))

    retention_days = os.environ.get("WO_BACKUP_RETENTION_DAYS", "")
    try:
        retention = int(retention_days)
    except (TypeError, ValueError):
        retention = 0
    if retention >= 7:
        results.append(_result("backup", "Backup retention", STATUS_OK, "{} days.".format(retention)))
    else:
        results.append(_result(
            "backup",
            "Backup retention",
            STATUS_WARNING,
            "WO_BACKUP_RETENTION_DAYS is not set to at least 7.",
            "Keep enough daily backups to recover from delayed data-loss discovery.",
        ))

    for env_name, label in (("WO_MEDIA_DIR", "Media persistence"), ("WO_DB_DIR", "Database persistence")):
        value = os.environ.get(env_name, "")
        if not value:
            results.append(_result(
                "persistence",
                label,
                STATUS_WARNING,
                "{} is not set.".format(env_name),
                "Set {} to a durable host path or named Docker volume.".format(env_name),
            ))
        elif value in ("appmedia", "dbdata"):
            results.append(_result(
                "persistence",
                label,
                STATUS_WARNING,
                "{} uses the default Docker volume {}.".format(env_name, value),
                "Host bind mounts are easier to inspect and back up in production.",
            ))
        else:
            results.append(_result("persistence", label, STATUS_OK, "{}={}".format(env_name, value)))

    airtwin_enabled = getattr(settings, "AIRTWIN_WEBHOOK_ENABLED", False)
    if not airtwin_enabled:
        results.append(_result(
            "integration",
            "AirTwin webhook",
            STATUS_OK,
            "AirTwin completion webhook is disabled.",
        ))
    else:
        missing = []
        if not getattr(settings, "AIRTWIN_WEBHOOK_URL", ""):
            missing.append("AIRTWIN_WEBHOOK_URL")
        if not getattr(settings, "AIRTWIN_WEBHOOK_SECRET", ""):
            missing.append("AIRTWIN_WEBHOOK_SECRET")
        if missing:
            results.append(_result(
                "integration",
                "AirTwin webhook",
                STATUS_ERROR,
                "AirTwin webhook is enabled but configuration is incomplete.",
                "Set {} in the container environment.".format(" and ".join(missing)),
            ))
        else:
            results.append(_result(
                "integration",
                "AirTwin webhook",
                STATUS_OK,
                "AirTwin webhook URL and signing secret are configured.",
            ))

        retention = getattr(settings, "AIRTWIN_OUTPUT_RETENTION_DAYS", 0)
        if retention >= 1:
            results.append(_result(
                "integration",
                "AirTwin output retention",
                STATUS_OK,
                "{} day retention target is configured.".format(retention),
            ))
        else:
            results.append(_result(
                "integration",
                "AirTwin output retention",
                STATUS_WARNING,
                "No positive AirTwin retention target is configured.",
                "Set AIRTWIN_OUTPUT_RETENTION_DAYS and retain outputs until import is confirmed.",
            ))

    return results


def _check_runtime():
    results = []

    try:
        _writable_directory(settings.MEDIA_ROOT)
        results.append(_result("runtime", "Media root", STATUS_OK, "{} is writable.".format(settings.MEDIA_ROOT)))
    except Exception as exc:
        results.append(_result(
            "runtime",
            "Media root",
            STATUS_ERROR,
            "{} is not writable ({})".format(settings.MEDIA_ROOT, exc),
            "Fix the media volume mount before accepting uploads.",
        ))

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        results.append(_result("runtime", "Database connectivity", STATUS_OK, "Database query succeeded."))
    except Exception as exc:
        results.append(_result(
            "runtime",
            "Database connectivity",
            STATUS_ERROR,
            "Database query failed ({})".format(exc),
            "Check the database container, credentials, and network before launch.",
        ))
        return results

    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            results.append(_result(
                "runtime",
                "Migrations",
                STATUS_ERROR,
                "{} pending migration step(s).".format(len(plan)),
                "Run python manage.py migrate before launch.",
            ))
        else:
            results.append(_result("runtime", "Migrations", STATUS_OK, "No pending migrations."))
    except Exception as exc:
        results.append(_result(
            "runtime",
            "Migrations",
            STATUS_ERROR,
            "Migration check failed ({})".format(exc),
            "Run manage.py migrate and inspect migration state.",
        ))

    try:
        platform_summary = run_platform_audit()
        if platform_summary.ok:
            results.append(_result("runtime", "Platform audit", STATUS_OK, "Platform audit passed."))
        else:
            results.append(_result(
                "runtime",
                "Platform audit",
                STATUS_ERROR,
                "{} platform audit failure(s).".format(len(platform_summary.failures)),
                "Run python manage.py platformaudit and fix missing protected surfaces.",
            ))
    except Exception as exc:
        results.append(_result(
            "runtime",
            "Platform audit",
            STATUS_ERROR,
            "Platform audit failed ({})".format(exc),
            "Run python manage.py platformaudit and inspect the error.",
        ))

    try:
        from app.models import FeatureValidation

        expected_keys = {item["key"] for item in PIPELINE_FEATURE_VALIDATIONS}
        tested_keys = set(FeatureValidation.objects.filter(
            key__in=expected_keys,
            status=FeatureValidation.STATUS_TESTED,
        ).values_list("key", flat=True))
        missing = expected_keys - tested_keys
        if missing:
            results.append(_result(
                "runtime",
                "Feature validation ledger",
                STATUS_WARNING,
                "{} pipeline validation(s) are not marked tested.".format(len(missing)),
                "Run reconcilefeaturevalidations after focused regression/smoke checks.",
            ))
        else:
            results.append(_result("runtime", "Feature validation ledger", STATUS_OK, "All pipeline validations are tested."))
    except Exception as exc:
        results.append(_result(
            "runtime",
            "Feature validation ledger",
            STATUS_WARNING,
            "Could not inspect feature validation ledger ({})".format(exc),
            "Run migrations and reconcilefeaturevalidations after deployment.",
        ))

    try:
        from nodeodm.models import ProcessingNode

        nodes = list(ProcessingNode.objects.all())
        if not nodes:
            results.append(_result(
                "runtime",
                "Processing nodes",
                STATUS_ERROR,
                "No processing nodes are registered.",
                "Start NodeODM and run syncdefaultnodes or add a processing node.",
            ))
        elif any(node.is_online() for node in nodes):
            results.append(_result("runtime", "Processing nodes", STATUS_OK, "{} node(s), at least one online.".format(len(nodes))))
        else:
            results.append(_result(
                "runtime",
                "Processing nodes",
                STATUS_WARNING,
                "{} node(s) registered, none recently refreshed.".format(len(nodes)),
                "Open Processing Nodes or run a task smoke test to refresh node status.",
            ))
    except Exception as exc:
        results.append(_result(
            "runtime",
            "Processing nodes",
            STATUS_WARNING,
            "Could not inspect processing nodes ({})".format(exc),
            "Verify at least one NodeODM worker before accepting client projects.",
        ))

    return results


def run_production_readiness(
    include_runtime=True,
    allow_http=False,
    allow_wildcard_hosts=False,
    allow_open_cors=False,
    allow_generated_secret=False,
):
    results = []
    results.extend(_check_static_configuration(
        allow_http=allow_http,
        allow_wildcard_hosts=allow_wildcard_hosts,
        allow_open_cors=allow_open_cors,
        allow_generated_secret=allow_generated_secret,
    ))

    if include_runtime:
        results.extend(_check_runtime())

    return ProductionReadinessSummary(results)
