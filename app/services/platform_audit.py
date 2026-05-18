from dataclasses import dataclass
from pathlib import Path

from django.apps import apps
from django.urls import Resolver404, resolve


STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class PlatformAuditResult:
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


class PlatformAuditSummary:
    def __init__(self, results):
        self.results = list(results)

    @property
    def failures(self):
        return [result for result in self.results if result.status in (STATUS_MISSING, STATUS_ERROR)]

    @property
    def ok(self):
        return not self.failures

    @property
    def counts(self):
        counts = {
            STATUS_OK: 0,
            STATUS_MISSING: 0,
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
            "failures": [result.to_dict() for result in self.failures],
            "results": [result.to_dict() for result in self.results],
        }


REQUIRED_FILES = (
    ("docs", "Pipeline source of truth", "PIPELINE.md", "Restore PIPELINE.md and keep the next priority in sync."),
    ("docs", "Architecture guide", "ARCHITECTURE.md", "Restore ARCHITECTURE.md before large fork upgrades."),
    ("docs", "Module boundaries guide", "MODULE_BOUNDARIES.md", "Restore MODULE_BOUNDARIES.md and update boundary tests."),
    ("templates", "Feature validation dashboard", "app/templates/app/feature_validations.html", "Restore the staff validation ledger page."),
    ("templates", "Client portal", "app/templates/app/public/client_portal.html", "Restore the tokenized client portal template."),
    ("templates", "Map workspace", "app/templates/app/map.html", "Restore the project map template."),
    ("templates", "3D model viewer", "app/templates/app/3d_model_display.html", "Restore the 3D viewer template."),
    ("templates", "API token settings page", "app/templates/app/account_token.html", "Restore the account token/settings page."),
    ("api", "AI issue detection API", "app/api/ai_issues.py", "Restore the AI issue detection API module."),
    ("api", "Client portal API", "app/api/client_portal.py", "Restore tokenized client portal API routes."),
    ("api", "Design overlay API", "app/api/design_overlays.py", "Restore design overlay API routes."),
    ("api", "Feature validation API", "app/api/feature_validation.py", "Restore feature validation API routes."),
    ("api", "Field photo API", "app/api/field_photos.py", "Restore field photo API routes."),
    ("api", "Monitoring API", "app/api/monitoring.py", "Restore monitoring timeline and compare API routes."),
    ("api", "Project issue API", "app/api/issues.py", "Restore project issue and annotation API routes."),
    ("api", "Project report API", "app/api/reports.py", "Restore stakeholder report API routes."),
    ("api", "Textured model QA API", "app/api/textured_model_qa.py", "Restore textured model QA API routes."),
    ("services", "AI issue detection service", "app/services/ai_issue_detection.py", "Restore AI issue detection service logic."),
    ("services", "Feature validation service", "app/services/feature_validation.py", "Restore feature validation logging service."),
    ("services", "Project reports service", "app/services/project_reports.py", "Restore report-building service logic."),
    ("services", "Textured model export service", "app/services/textured_model_exports.py", "Restore textured model export helpers."),
    ("services", "Textured model QA service", "app/services/textured_model_qa.py", "Restore textured model QA service logic."),
    ("services", "Monitoring alignment service", "app/services/monitoring/alignment.py", "Restore monitoring alignment service."),
    ("services", "Monitoring cache service", "app/services/monitoring/cache.py", "Restore monitoring cache service."),
    ("services", "Monitoring overlay service", "app/services/monitoring/overlays.py", "Restore monitoring overlay builders."),
    ("services", "Monitoring payload service", "app/services/monitoring/payloads.py", "Restore monitoring API payload helpers."),
    ("services", "Monitoring product service", "app/services/monitoring/products.py", "Restore monitoring product orchestration."),
    ("services", "Monitoring readiness service", "app/services/monitoring/readiness.py", "Restore monitoring readiness checks."),
    ("management", "Default NodeODM repair command", "app/management/commands/syncdefaultnodes.py", "Restore the default-node repair command."),
    ("management", "OneDrive intake command", "app/management/commands/onedriveintake.py", "Restore OneDrive task intake command."),
    ("tests", "Module boundary tests", "app/tests/test_module_boundaries.py", "Restore boundary regression tests."),
)


REQUIRED_ROUTES = (
    ("routes", "Dashboard", "/dashboard/", "Restore the dashboard URL."),
    ("routes", "Feature validation dashboard", "/feature-validations/", "Restore the feature validation browser page."),
    ("routes", "API token settings page", "/account/token/", "Restore the account token/settings route."),
    ("routes", "Project task map", "/map/project/1/task/2/", "Restore project task map route."),
    ("routes", "Project task 3D viewer", "/3d/project/1/task/2/", "Restore project task 3D route."),
    ("routes", "Client portal", "/client/projects/token/", "Restore tokenized client portal route."),
    ("routes", "Client 3D review", "/client/projects/token/tasks/2/3d/", "Restore tokenized client 3D review route."),
    ("routes", "API status", "/api/status/", "Restore API status route."),
    ("routes", "Feature validation API", "/api/feature-validations/", "Restore feature validation API router."),
    ("routes", "Project issue API", "/api/projects/1/issues/", "Restore project issue API router."),
    ("routes", "Design overlay API", "/api/projects/1/design-overlays/", "Restore design overlay API router."),
    ("routes", "Field photo API", "/api/projects/1/field-photos/", "Restore field photo API router."),
    ("routes", "Client share API", "/api/projects/1/client-shares/", "Restore project client-share API router."),
    ("routes", "Textured model QA API", "/api/projects/1/tasks/2/3d/qa", "Restore textured model QA API route."),
    ("routes", "Monitoring candidates API", "/api/projects/1/tasks/2/monitoring/candidates", "Restore monitoring candidates route."),
    ("routes", "Monitoring compare API", "/api/projects/1/tasks/2/monitoring/compare", "Restore monitoring compare route."),
    ("routes", "Monitoring timeline API", "/api/projects/1/monitoring/timeline", "Restore monitoring timeline route."),
    ("routes", "Project progress report API", "/api/projects/1/reports/progress", "Restore stakeholder report route."),
    ("routes", "AI issue detection API", "/api/projects/1/ai/issue-detection", "Restore AI issue detection route."),
    ("routes", "Client portal API", "/api/client-shares/token/", "Restore tokenized client portal API route."),
    ("routes", "Client textured model QA API", "/api/client-shares/token/tasks/2/3d/qa", "Restore tokenized client 3D QA route."),
    ("routes", "Client textured model asset API", "/api/client-shares/token/tasks/2/textured_model/", "Restore tokenized client model asset route."),
)


REQUIRED_MODELS = (
    ("models", "Feature validation ledger model", "app.FeatureValidation", "Restore the FeatureValidation model and migrations."),
    ("models", "Project issue model", "app.ProjectIssue", "Restore the ProjectIssue model and migrations."),
    ("models", "Project field photo model", "app.ProjectFieldPhoto", "Restore the ProjectFieldPhoto model and migrations."),
    ("models", "Project design overlay model", "app.ProjectDesignOverlay", "Restore the ProjectDesignOverlay model and migrations."),
    ("models", "Project client share model", "app.ProjectClientShare", "Restore the ProjectClientShare model and migrations."),
)


REQUIRED_SETTING_FIELDS = (
    ("settings", "OpenAI API key field", "openai_api_key", "Restore the server-side OpenAI API key setting."),
    ("settings", "OpenAI model field", "openai_model", "Restore the server-side OpenAI model setting."),
)


def repo_root_from_service():
    return Path(__file__).resolve().parents[2]


def check_file(repo_root, area, name, relative_path, remediation):
    path = repo_root / relative_path
    if path.exists():
        return PlatformAuditResult(area, name, STATUS_OK, str(relative_path))
    return PlatformAuditResult(area, name, STATUS_MISSING, str(relative_path), remediation)


def check_route(area, name, route, remediation):
    try:
        match = resolve(route)
    except Resolver404:
        return PlatformAuditResult(area, name, STATUS_MISSING, route, remediation)
    except Exception as exc:
        return PlatformAuditResult(area, name, STATUS_ERROR, "{} ({})".format(route, exc), remediation)

    target = getattr(match.func, "__name__", None) or getattr(match.func, "__class__", type(match.func)).__name__
    return PlatformAuditResult(area, name, STATUS_OK, "{} -> {}".format(route, target))


def check_model(area, name, label, remediation):
    try:
        app_label, model_name = label.split(".", 1)
        model = apps.get_model(app_label, model_name)
    except Exception as exc:
        return PlatformAuditResult(area, name, STATUS_ERROR, "{} ({})".format(label, exc), remediation)

    if model is None:
        return PlatformAuditResult(area, name, STATUS_MISSING, label, remediation)
    return PlatformAuditResult(area, name, STATUS_OK, label)


def check_setting_field(area, name, field_name, remediation):
    try:
        setting_model = apps.get_model("app", "Setting")
        setting_model._meta.get_field(field_name)
    except Exception as exc:
        return PlatformAuditResult(area, name, STATUS_MISSING, "{} ({})".format(field_name, exc), remediation)

    return PlatformAuditResult(area, name, STATUS_OK, "Setting.{}".format(field_name))


def run_platform_audit(repo_root=None):
    repo_root = Path(repo_root) if repo_root is not None else repo_root_from_service()
    results = []

    for file_check in REQUIRED_FILES:
        results.append(check_file(repo_root, *file_check))

    for route_check in REQUIRED_ROUTES:
        results.append(check_route(*route_check))

    for model_check in REQUIRED_MODELS:
        results.append(check_model(*model_check))

    for setting_check in REQUIRED_SETTING_FIELDS:
        results.append(check_setting_field(*setting_check))

    return PlatformAuditSummary(results)
