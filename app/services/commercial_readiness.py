from dataclasses import dataclass

from django.utils import timezone

from app import models
from nodeodm import status_codes


STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_BLOCKED = "blocked"
STATUS_MANUAL = "manual"

MANUAL_FIELDS = (
    "deliverables_reviewed",
    "human_reviewed",
    "report_reviewed",
    "client_share_reviewed",
    "legal_disclaimer_reviewed",
)

PACKAGE_DEFINITIONS = {
    models.ProjectCommercialReadiness.PACKAGE_BASIC_ORTHOMOSAIC: {
        "label": "Basic Orthomosaic",
        "description": "Client-ready orthomosaic delivery with report, expiring share link, and human review.",
        "requires_dsm": False,
        "requires_dtm": False,
        "requires_design_overlay": False,
    },
    models.ProjectCommercialReadiness.PACKAGE_ARCHITECTURE_CAD: {
        "label": "Architecture CAD Orthomosaic",
        "description": "Construction progress package with CAD/design overlays, DSM/DTM deltas, issues, and reporting.",
        "requires_dsm": True,
        "requires_dtm": True,
        "requires_design_overlay": True,
    },
    models.ProjectCommercialReadiness.PACKAGE_AGRICULTURE_FIELD: {
        "label": "Agriculture Field Analysis",
        "description": "Field analysis package with plant-health review, DSM context, issues, and reporting.",
        "requires_dsm": True,
        "requires_dtm": False,
        "requires_design_overlay": False,
    },
    models.ProjectCommercialReadiness.PACKAGE_SOLAR_INSPECTION: {
        "label": "Solar Panel Inspection",
        "description": "Solar inspection package with high-detail orthomosaic, issue mapping, thermal follow-up, and reporting.",
        "requires_dsm": True,
        "requires_dtm": False,
        "requires_design_overlay": False,
    },
}


@dataclass(frozen=True)
class CommercialReadinessItem:
    key: str
    title: str
    status: str
    detail: str
    remediation: str = ""
    required: bool = True

    @property
    def ok(self):
        return self.status in (STATUS_OK, STATUS_WARNING)

    def to_dict(self):
        return {
            "key": self.key,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "remediation": self.remediation,
            "required": self.required,
        }


def _item(key, title, status, detail, remediation="", required=True):
    return CommercialReadinessItem(key, title, status, detail, remediation, required)


def get_or_create_project_commercial_readiness(project):
    readiness, _created = models.ProjectCommercialReadiness.objects.get_or_create(project=project)
    return readiness


def normalize_package(package):
    if package in PACKAGE_DEFINITIONS:
        return package
    return models.ProjectCommercialReadiness.PACKAGE_BASIC_ORTHOMOSAIC


def _task_payload(task):
    if task is None:
        return None
    return {
        "id": str(task.id),
        "name": task.name,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "available_assets": task.available_assets or [],
    }


def _latest_completed_orthomosaic_task(project):
    for task in project.task_set.filter(status=status_codes.COMPLETED).order_by("-created_at", "-id"):
        if "orthophoto.tif" in (task.available_assets or []):
            return task
    return None


def _completed_orthomosaic_tasks(project):
    return [
        task
        for task in project.task_set.filter(status=status_codes.COMPLETED).order_by("-created_at", "-id")
        if "orthophoto.tif" in (task.available_assets or [])
    ]


def _active_expiring_client_shares(project):
    now = timezone.now()
    return [
        share
        for share in project.client_shares.filter(enabled=True, expires_at__isnull=False, expires_at__gt=now)
        if share.is_active()
    ]


def _open_review_issue_count(project):
    return project.issues.filter(
        status__in=(models.ProjectIssue.STATUS_OPEN, models.ProjectIssue.STATUS_IN_REVIEW)
    ).count()


def _system_items(project, package_key):
    package = PACKAGE_DEFINITIONS[package_key]
    items = []
    latest_task = _latest_completed_orthomosaic_task(project)
    completed_orthomosaic_tasks = _completed_orthomosaic_tasks(project)
    active_processing_count = project.task_set.filter(
        status__in=(status_codes.QUEUED, status_codes.RUNNING)
    ).count()
    failed_task_count = project.task_set.filter(status=status_codes.FAILED).count()
    open_review_issues = _open_review_issue_count(project)
    active_expiring_shares = _active_expiring_client_shares(project)
    has_design_overlay = project.design_overlays.exists()

    if latest_task:
        items.append(_item(
            "completed_orthomosaic",
            "Completed orthomosaic",
            STATUS_OK,
            "{} completed orthomosaic task(s). Latest: {}.".format(len(completed_orthomosaic_tasks), latest_task.name),
        ))
    else:
        items.append(_item(
            "completed_orthomosaic",
            "Completed orthomosaic",
            STATUS_BLOCKED,
            "No completed task with orthophoto.tif is available.",
            "Process a task successfully with an orthophoto before client delivery.",
        ))

    if active_processing_count:
        items.append(_item(
            "processing_complete",
            "Processing complete",
            STATUS_BLOCKED,
            "{} task(s) are still queued or running.".format(active_processing_count),
            "Wait for processing to complete or remove unfinished tasks from the delivery scope.",
        ))
    else:
        items.append(_item(
            "processing_complete",
            "Processing complete",
            STATUS_OK,
            "No queued or running tasks are blocking delivery.",
        ))

    if failed_task_count:
        items.append(_item(
            "failed_tasks_reviewed",
            "Failed tasks reviewed",
            STATUS_WARNING,
            "{} failed task(s) are present in the project.".format(failed_task_count),
            "Confirm failed tasks are unrelated to the client delivery or reprocess them.",
            required=False,
        ))
    else:
        items.append(_item(
            "failed_tasks_reviewed",
            "Failed tasks reviewed",
            STATUS_OK,
            "No failed tasks are present.",
            required=False,
        ))

    assets = (latest_task.available_assets if latest_task else []) or []
    missing_elevation_assets = []
    if package["requires_dsm"] and "dsm.tif" not in assets:
        missing_elevation_assets.append("dsm.tif")
    if package["requires_dtm"] and "dtm.tif" not in assets:
        missing_elevation_assets.append("dtm.tif")

    if missing_elevation_assets:
        items.append(_item(
            "elevation_assets",
            "Elevation assets",
            STATUS_BLOCKED,
            "Missing required asset(s): {}.".format(", ".join(missing_elevation_assets)),
            "Reprocess with the matching commercial preset or enable the required DSM/DTM outputs.",
        ))
    elif package["requires_dsm"] or package["requires_dtm"]:
        required_assets = ["dsm.tif"] if package["requires_dsm"] else []
        if package["requires_dtm"]:
            required_assets.append("dtm.tif")
        items.append(_item(
            "elevation_assets",
            "Elevation assets",
            STATUS_OK,
            "Required elevation asset(s) are available: {}.".format(", ".join(required_assets)),
        ))
    elif "dsm.tif" in assets or "dtm.tif" in assets:
        items.append(_item(
            "elevation_assets",
            "Elevation assets",
            STATUS_OK,
            "Optional DSM/DTM assets are available.",
            required=False,
        ))
    else:
        items.append(_item(
            "elevation_assets",
            "Elevation assets",
            STATUS_WARNING,
            "No DSM/DTM assets are available for optional elevation context.",
            "Enable DSM/DTM if terrain or surface change is part of the sale.",
            required=False,
        ))

    if package["requires_design_overlay"] and not has_design_overlay:
        items.append(_item(
            "design_overlay",
            "Design/CAD overlay",
            STATUS_BLOCKED,
            "No project design overlay is available.",
            "Upload a georeferenced GeoJSON or zipped Shapefile design overlay before CAD comparison delivery.",
        ))
    elif has_design_overlay:
        items.append(_item(
            "design_overlay",
            "Design/CAD overlay",
            STATUS_OK,
            "{} design overlay record(s) are available.".format(project.design_overlays.count()),
            required=package["requires_design_overlay"],
        ))
    else:
        items.append(_item(
            "design_overlay",
            "Design/CAD overlay",
            STATUS_OK,
            "No design overlay is required for this package.",
            required=False,
        ))

    if active_expiring_shares:
        items.append(_item(
            "client_share",
            "Expiring client share",
            STATUS_OK,
            "{} active client share(s) have expiry dates.".format(len(active_expiring_shares)),
        ))
    else:
        items.append(_item(
            "client_share",
            "Expiring client share",
            STATUS_BLOCKED,
            "No active client share with a future expiry date is available.",
            "Create an expiring viewer or reviewer client share before delivery.",
        ))

    if latest_task:
        items.append(_item(
            "stakeholder_report",
            "Stakeholder report",
            STATUS_OK,
            "Progress report can be generated for the latest deliverables.",
        ))
    else:
        items.append(_item(
            "stakeholder_report",
            "Stakeholder report",
            STATUS_BLOCKED,
            "No completed orthomosaic exists for the report.",
            "Process a successful orthomosaic task, then generate the project progress report.",
        ))

    if open_review_issues:
        items.append(_item(
            "open_issue_review",
            "Open issue review",
            STATUS_BLOCKED,
            "{} open or in-review issue(s) remain.".format(open_review_issues),
            "Resolve, close, or explicitly remove remaining issues from the client delivery scope.",
        ))
    else:
        items.append(_item(
            "open_issue_review",
            "Open issue review",
            STATUS_OK,
            "No open or in-review issues remain.",
        ))

    return items, latest_task


def _manual_items(readiness):
    labels = {
        "deliverables_reviewed": "Deliverables reviewed",
        "human_reviewed": "Human review completed",
        "report_reviewed": "Report reviewed",
        "client_share_reviewed": "Client share reviewed",
        "legal_disclaimer_reviewed": "Commercial caveats accepted",
    }
    remediations = {
        "deliverables_reviewed": "Review orthophoto, exports, overlays, and DEM assets before checking this item.",
        "human_reviewed": "A qualified human reviewer must confirm AI/object-detection and inspection findings.",
        "report_reviewed": "Open the stakeholder report and confirm wording, evidence, and caveats.",
        "client_share_reviewed": "Confirm client share role, expiry date, and project scope before delivery.",
        "legal_disclaimer_reviewed": "Confirm the client-facing caveats match the package and use case.",
    }
    items = []
    for field in MANUAL_FIELDS:
        value = getattr(readiness, field)
        items.append(_item(
            field,
            labels[field],
            STATUS_OK if value else STATUS_MANUAL,
            "Signed off." if value else "Manual sign-off is still required.",
            "" if value else remediations[field],
        ))
    return items


def build_project_commercial_readiness(project, package=None):
    readiness = get_or_create_project_commercial_readiness(project)
    package_key = normalize_package(package or readiness.package)
    package_definition = PACKAGE_DEFINITIONS[package_key]
    system_items, latest_task = _system_items(project, package_key)
    manual_items = _manual_items(readiness)
    items = system_items + manual_items
    counts = {
        STATUS_OK: 0,
        STATUS_WARNING: 0,
        STATUS_BLOCKED: 0,
        STATUS_MANUAL: 0,
    }
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    counts["total"] = len(items)
    ready = counts[STATUS_BLOCKED] == 0 and counts[STATUS_MANUAL] == 0

    return {
        "ready": ready,
        "package": {
            "key": package_key,
            "label": package_definition["label"],
            "description": package_definition["description"],
        },
        "counts": counts,
        "project": {
            "id": project.id,
            "name": project.name,
        },
        "latest_deliverable_task": _task_payload(latest_task),
        "checklist": [item.to_dict() for item in items],
        "manual_signoff": {
            "package": readiness.package,
            "deliverables_reviewed": readiness.deliverables_reviewed,
            "human_reviewed": readiness.human_reviewed,
            "report_reviewed": readiness.report_reviewed,
            "client_share_reviewed": readiness.client_share_reviewed,
            "legal_disclaimer_reviewed": readiness.legal_disclaimer_reviewed,
            "notes": readiness.notes,
            "updated_by": readiness.updated_by.username if readiness.updated_by else None,
            "updated_at": readiness.updated_at.isoformat() if readiness.updated_at else None,
        },
        "actions": {
            "progress_report_url": "/api/projects/{}/reports/progress?format=html".format(project.id),
            "client_shares_url": "/api/projects/{}/client-shares/".format(project.id),
            "feature_validation_url": "/feature-validations/",
        },
    }
