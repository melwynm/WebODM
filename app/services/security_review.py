import os
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone


STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

FRONTEND_SECRET_PATTERNS = (
    "openai_api_key",
    "OPENAI_API_KEY",
)
FRONTEND_SCAN_PATHS = (
    "app/templates",
    "app/static/app/js",
    "coreplugins",
)
FRONTEND_SCAN_SUFFIXES = {
    ".html",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
}
FRONTEND_SCAN_EXCLUDED_PARTS = {
    "bundles",
    "vendor",
    "node_modules",
    "__pycache__",
}


@dataclass(frozen=True)
class SecurityReviewResult:
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


class SecurityReviewSummary:
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
    return SecurityReviewResult(area, name, status, detail, remediation)


def _env_enabled(name):
    return os.environ.get(name, "").upper() in ("1", "TRUE", "YES", "ON")


def _rest_framework_settings():
    return getattr(settings, "REST_FRAMEWORK", {}) or {}


def _setting_strings(values):
    return {str(value) for value in values or ()}


def _check_static_settings(allow_http=False, allow_wildcard_hosts=False, allow_open_cors=False):
    results = []

    if settings.DEBUG:
        results.append(_result(
            "configuration",
            "Debug mode",
            STATUS_ERROR,
            "DEBUG is enabled.",
            "Set WO_DEBUG=NO for every commercial environment.",
        ))
    else:
        results.append(_result("configuration", "Debug mode", STATUS_OK, "DEBUG is disabled."))

    secure_cookies = settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
    if secure_cookies or _env_enabled("WO_SSL"):
        results.append(_result("configuration", "Secure cookies", STATUS_OK, "Secure cookie posture is enabled."))
    elif allow_http:
        results.append(_result("configuration", "Secure cookies", STATUS_WARNING, "HTTP accepted by command flag."))
    else:
        results.append(_result(
            "configuration",
            "Secure cookies",
            STATUS_ERROR,
            "Session/CSRF cookies are not forced secure.",
            "Use HTTPS and set secure cookie settings before client access.",
        ))

    if "*" in getattr(settings, "ALLOWED_HOSTS", []):
        if allow_wildcard_hosts:
            results.append(_result("configuration", "Allowed hosts", STATUS_WARNING, "Wildcard ALLOWED_HOSTS accepted by command flag."))
        else:
            results.append(_result(
                "configuration",
                "Allowed hosts",
                STATUS_ERROR,
                "ALLOWED_HOSTS contains '*'.",
                "Restrict ALLOWED_HOSTS to the commercial domain names.",
            ))
    else:
        results.append(_result("configuration", "Allowed hosts", STATUS_OK, ", ".join(settings.ALLOWED_HOSTS)))

    if getattr(settings, "CORS_ORIGIN_ALLOW_ALL", False):
        if allow_open_cors:
            results.append(_result("configuration", "CORS", STATUS_WARNING, "Open CORS accepted by command flag."))
        else:
            results.append(_result(
                "configuration",
                "CORS",
                STATUS_ERROR,
                "CORS_ORIGIN_ALLOW_ALL is enabled.",
                "Restrict CORS to trusted origins before exposing APIs.",
            ))
    else:
        results.append(_result("configuration", "CORS", STATUS_OK, "CORS is restricted."))

    rest_framework = _rest_framework_settings()
    throttle_classes = _setting_strings(rest_framework.get("DEFAULT_THROTTLE_CLASSES"))
    throttle_rates = rest_framework.get("DEFAULT_THROTTLE_RATES", {}) or {}
    has_anon = any(value.endswith("AnonRateThrottle") for value in throttle_classes)
    has_user = any(value.endswith("UserRateThrottle") for value in throttle_classes)
    if has_anon and has_user and throttle_rates.get("anon") and throttle_rates.get("user"):
        results.append(_result(
            "api",
            "Rate limiting",
            STATUS_OK,
            "Anonymous and authenticated API throttles are configured.",
        ))
    else:
        results.append(_result(
            "api",
            "Rate limiting",
            STATUS_ERROR,
            "DRF anonymous/authenticated throttles are not fully configured.",
            "Set DEFAULT_THROTTLE_CLASSES and DEFAULT_THROTTLE_RATES for anon and user traffic.",
        ))

    return results


def _check_token_models():
    results = []
    from app.models import ProjectClientShare
    from app.models.profile import generate_api_key

    token_field = ProjectClientShare._meta.get_field("token")
    if token_field.unique and token_field.db_index and token_field.get_internal_type() == "UUIDField":
        results.append(_result("tokens", "Client share tokens", STATUS_OK, "Client shares use unique indexed UUID tokens."))
    else:
        results.append(_result(
            "tokens",
            "Client share tokens",
            STATUS_ERROR,
            "Client share token field is not unique indexed UUID.",
            "Keep share tokens unguessable, unique, and indexed.",
        ))

    generated_key = generate_api_key()
    if len(generated_key) >= 64:
        results.append(_result("tokens", "API token entropy", STATUS_OK, "Generated API tokens are at least 64 hex characters."))
    else:
        results.append(_result(
            "tokens",
            "API token entropy",
            STATUS_ERROR,
            "Generated API tokens are shorter than expected.",
            "Keep API tokens generated from secrets.token_hex(32) or stronger.",
        ))

    return results


def _iter_frontend_source_files(repo_root):
    repo_root = Path(repo_root)
    for relative in FRONTEND_SCAN_PATHS:
        root = repo_root / relative
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in FRONTEND_SCAN_SUFFIXES:
                continue
            if FRONTEND_SCAN_EXCLUDED_PARTS.intersection(path.parts):
                continue
            yield path


def _check_frontend_secret_exposure(repo_root):
    matches = []
    for path in _iter_frontend_source_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in FRONTEND_SECRET_PATTERNS:
            if pattern in text:
                matches.append(str(path.relative_to(repo_root)))

    if matches:
        return [_result(
            "secrets",
            "OpenAI key exposure",
            STATUS_ERROR,
            "OpenAI key identifiers found in frontend/template files: {}".format(", ".join(sorted(matches)[:5])),
            "Keep OpenAI credentials server-side only.",
        )]

    return [_result("secrets", "OpenAI key exposure", STATUS_OK, "No OpenAI key identifiers found in frontend/template files.")]


def _check_onedrive_policy():
    root = os.environ.get("WO_ONEDRIVE_INTAKE_DIR", "").strip()
    if not root:
        return [_result(
            "operations",
            "OneDrive intake root",
            STATUS_WARNING,
            "WO_ONEDRIVE_INTAKE_DIR is not set.",
            "Set WO_ONEDRIVE_INTAKE_DIR so browser/command intake paths are constrained to one mounted folder.",
        )]

    if not os.path.isabs(root):
        return [_result(
            "operations",
            "OneDrive intake root",
            STATUS_ERROR,
            "WO_ONEDRIVE_INTAKE_DIR is not absolute.",
            "Use an absolute mounted path for OneDrive intake.",
        )]

    return [_result("operations", "OneDrive intake root", STATUS_OK, "Configured root: {}".format(root))]


def _check_runtime_state():
    results = []
    from app.models import ProjectClientShare
    from app.models.profile import Profile

    now = timezone.now()
    indefinite_shares = ProjectClientShare.objects.filter(enabled=True, expires_at__isnull=True).count()
    if indefinite_shares:
        results.append(_result(
            "runtime",
            "Client share expiry",
            STATUS_WARNING,
            "{} enabled client share(s) have no expiry.".format(indefinite_shares),
            "Set expiry dates on commercial client review links unless there is a documented reason.",
        ))
    else:
        results.append(_result("runtime", "Client share expiry", STATUS_OK, "All enabled client shares have expiry dates."))

    stale_enabled_shares = ProjectClientShare.objects.filter(enabled=True, expires_at__lte=now).count()
    if stale_enabled_shares:
        results.append(_result(
            "runtime",
            "Expired share cleanup",
            STATUS_WARNING,
            "{} expired share(s) are still enabled.".format(stale_enabled_shares),
            "Disable expired shares during client handoff cleanup.",
        ))
    else:
        results.append(_result("runtime", "Expired share cleanup", STATUS_OK, "No expired enabled shares."))

    weak_api_keys = sum(
        1
        for api_key in Profile.objects.exclude(api_key="").filter(api_key__isnull=False).values_list("api_key", flat=True)
        if not re.match(r"^[0-9a-f]{64,}$", api_key or "")
    )
    if weak_api_keys:
        results.append(_result(
            "runtime",
            "Stored API token shape",
            STATUS_ERROR,
            "{} stored API token(s) do not match the expected format.".format(weak_api_keys),
            "Regenerate short or malformed API tokens before launch.",
        ))
    else:
        results.append(_result("runtime", "Stored API token shape", STATUS_OK, "Stored API tokens match expected shape."))

    if not getattr(settings, "TESTING", False):
        test_users = Profile.objects.filter(user__username__in=("testsuperuser", "testuser", "testuser2")).count()
        if test_users:
            results.append(_result(
                "runtime",
                "Test accounts",
                STATUS_ERROR,
                "Default test accounts exist in this database.",
                "Remove test accounts before exposing the service.",
            ))
        else:
            results.append(_result("runtime", "Test accounts", STATUS_OK, "No default test accounts found."))

    return results


def repo_root_from_settings():
    return Path(settings.BASE_DIR)


def run_security_review(
    include_runtime=True,
    repo_root=None,
    allow_http=False,
    allow_wildcard_hosts=False,
    allow_open_cors=False,
):
    repo_root = Path(repo_root) if repo_root is not None else repo_root_from_settings()
    results = []
    results.extend(_check_static_settings(
        allow_http=allow_http,
        allow_wildcard_hosts=allow_wildcard_hosts,
        allow_open_cors=allow_open_cors,
    ))
    results.extend(_check_token_models())
    results.extend(_check_frontend_secret_exposure(repo_root))
    results.extend(_check_onedrive_policy())
    if include_runtime:
        results.extend(_check_runtime_state())
    return SecurityReviewSummary(results)
