from django.utils import timezone
from django.utils.html import conditional_escape

from app import models
from nodeodm import status_codes


REPORT_TEMPLATE_GENERAL = "general"
REPORT_TEMPLATE_ARCHITECTURE = "architecture_cad"
REPORT_TEMPLATE_AGRICULTURE = "agriculture_field"
REPORT_TEMPLATE_SOLAR = "solar_inspection"

REPORT_TEMPLATES = {
    REPORT_TEMPLATE_GENERAL: {
        "label": "General Progress Report",
        "title": "Progress Report",
        "description": "General stakeholder report for project deliverables, issues, and task status.",
        "focus": [
            "Latest completed deliverables",
            "Open issues and annotations",
            "Client-share-ready project summary",
        ],
        "caveats": [
            "Measurements and inspection findings should be reviewed by a qualified human before commercial use.",
        ],
    },
    REPORT_TEMPLATE_ARCHITECTURE: {
        "label": "Architecture / Construction Report",
        "title": "Construction Progress Report",
        "description": "Client report for CAD/design overlay comparison and construction progress follow-up.",
        "focus": [
            "Latest orthomosaic and construction progress status",
            "CAD/design overlay comparison",
            "DSM/DTM terrain or surface change readiness",
            "Open defects, changes, and progress issues",
        ],
        "caveats": [
            "CAD/design comparison depends on georeferenced overlay quality and site control.",
            "Progress evidence should be reconciled with contract documents before certification.",
        ],
    },
    REPORT_TEMPLATE_AGRICULTURE: {
        "label": "Agriculture Field Analysis Report",
        "title": "Field Analysis Report",
        "description": "Client report for field-scale orthomosaic, plant-health review, and scouting follow-up.",
        "focus": [
            "Field orthomosaic coverage",
            "Plant-health formula layers when supported by sensor bands",
            "Ground-truth field photos and scouting issues",
            "Operational follow-up zones",
        ],
        "caveats": [
            "Plant-health formulas depend on sensor bands, calibration quality, weather, and capture timing.",
            "RGB-only vegetation layers are scouting aids, not full multispectral agronomy diagnostics.",
        ],
    },
    REPORT_TEMPLATE_SOLAR: {
        "label": "Solar Inspection Report",
        "title": "Solar Inspection Report",
        "description": "Client report for solar panel orthomosaic review, issue mapping, and thermal follow-up.",
        "focus": [
            "High-detail orthomosaic coverage",
            "Panel or row issue map",
            "Thermal orthophoto follow-up when available",
            "Human-confirmed defects and close-up evidence",
        ],
        "caveats": [
            "Thermal findings require suitable capture conditions and qualified human confirmation.",
            "This report is decision-support evidence and is not an electrical certification by itself.",
        ],
    },
}

PACKAGE_REPORT_TEMPLATE_MAP = {
    models.ProjectCommercialReadiness.PACKAGE_ARCHITECTURE_CAD: REPORT_TEMPLATE_ARCHITECTURE,
    models.ProjectCommercialReadiness.PACKAGE_AGRICULTURE_FIELD: REPORT_TEMPLATE_AGRICULTURE,
    models.ProjectCommercialReadiness.PACKAGE_SOLAR_INSPECTION: REPORT_TEMPLATE_SOLAR,
    models.ProjectCommercialReadiness.PACKAGE_BASIC_ORTHOMOSAIC: REPORT_TEMPLATE_GENERAL,
}


def _iso(value):
    return value.isoformat() if value else None


def _task_payload(task):
    return {
        "id": str(task.id),
        "name": task.name or str(task.id),
        "status": task.status,
        "created_at": _iso(task.created_at),
        "processing_time": task.processing_time,
        "available_assets": task.available_assets or [],
    }


def normalize_report_template(project, template=None):
    if template in REPORT_TEMPLATES:
        return template
    try:
        package = project.commercial_readiness.package
    except Exception:
        package = None
    return PACKAGE_REPORT_TEMPLATE_MAP.get(package, REPORT_TEMPLATE_GENERAL)


def _commercial_evidence(project, tasks, issues):
    completed_orthomosaic_tasks = [
        task for task in tasks
        if task.status == status_codes.COMPLETED and "orthophoto.tif" in (task.available_assets or [])
    ]
    latest_task = completed_orthomosaic_tasks[0] if completed_orthomosaic_tasks else None
    latest_assets = (latest_task.available_assets if latest_task else []) or []
    return {
        "completed_orthomosaic_tasks": len(completed_orthomosaic_tasks),
        "latest_deliverable_task": _task_payload(latest_task) if latest_task else None,
        "has_dsm": "dsm.tif" in latest_assets,
        "has_dtm": "dtm.tif" in latest_assets,
        "has_thermal": "thermal_orthophoto.tif" in latest_assets,
        "design_overlay_count": project.design_overlays.count(),
        "field_photo_count": project.field_photos.count(),
        "client_share_count": project.client_shares.count(),
        "open_issue_count": len([
            issue for issue in issues
            if issue.status in (models.ProjectIssue.STATUS_OPEN, models.ProjectIssue.STATUS_IN_REVIEW)
        ]),
    }


def build_project_progress_report(project, template=None):
    tasks = list(project.task_set.all().order_by("-created_at", "-id"))
    issues = list(project.issues.select_related("task", "created_by", "assigned_to").order_by("-created_at", "-id"))
    template_key = normalize_report_template(project, template)
    report_template = REPORT_TEMPLATES[template_key]

    task_counts = {
        "total": len(tasks),
        "completed": len([task for task in tasks if task.status == status_codes.COMPLETED]),
        "processing": len([task for task in tasks if task.status in (status_codes.QUEUED, status_codes.RUNNING)]),
        "failed": len([task for task in tasks if task.status == status_codes.FAILED]),
    }

    issue_counts = {}
    for status_key, _label in models.ProjectIssue.STATUS_CHOICES:
        issue_counts[status_key] = len([issue for issue in issues if issue.status == status_key])

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "created_at": _iso(project.created_at),
            "owner": project.owner.username if project.owner else None,
        },
        "generated_at": timezone.now().isoformat(),
        "report_template": {
            "key": template_key,
            "label": report_template["label"],
            "title": report_template["title"],
            "description": report_template["description"],
            "focus": report_template["focus"],
            "caveats": report_template["caveats"],
        },
        "commercial_evidence": _commercial_evidence(project, tasks, issues),
        "summary": {
            "tasks": task_counts,
            "issues": issue_counts,
        },
        "latest_tasks": [_task_payload(task) for task in tasks[:8]],
        "open_issues": [
            {
                "id": issue.id,
                "title": issue.title,
                "description": issue.description,
                "issue_type": issue.issue_type,
                "status": issue.status,
                "priority": issue.priority,
                "task": issue.task.name if issue.task else None,
                "created_by": issue.created_by.username if issue.created_by else None,
                "assigned_to": issue.assigned_to.username if issue.assigned_to else None,
                "created_at": _iso(issue.created_at),
            }
            for issue in issues
            if issue.status not in (models.ProjectIssue.STATUS_CLOSED, models.ProjectIssue.STATUS_RESOLVED)
        ][:12],
    }


def _asset_labels(assets):
    if not assets:
        return "No exported assets yet"
    labels = []
    for asset in ("orthophoto.tif", "dsm.tif", "dtm.tif", "georeferenced_model.laz", "textured_model.zip", "gaussian_splat.ply"):
        if asset in assets:
            labels.append(asset)
    return ", ".join(labels or assets[:4])


def render_progress_report_html(report):
    project = report["project"]
    report_template = report["report_template"]
    evidence = report["commercial_evidence"]
    summary = report["summary"]
    esc = conditional_escape

    task_rows = "".join(
        f"""
        <tr>
          <td>{esc(task['name'])}</td>
          <td>{esc(task['status'])}</td>
          <td>{esc(task['created_at'] or '')}</td>
          <td>{esc(_asset_labels(task['available_assets']))}</td>
        </tr>
        """
        for task in report["latest_tasks"]
    ) or "<tr><td colspan=\"4\">No tasks yet.</td></tr>"

    issue_rows = "".join(
        f"""
        <tr>
          <td>{esc(issue['title'])}</td>
          <td>{esc(issue['issue_type'])}</td>
          <td>{esc(issue['priority'])}</td>
          <td>{esc(issue['status'])}</td>
          <td>{esc(issue['task'] or '')}</td>
        </tr>
        """
        for issue in report["open_issues"]
    ) or "<tr><td colspan=\"5\">No open issues.</td></tr>"

    focus_rows = "".join(
        f"<li>{esc(item)}</li>"
        for item in report_template["focus"]
    )

    caveat_rows = "".join(
        f"<li>{esc(item)}</li>"
        for item in report_template["caveats"]
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{esc(project['name'])} {esc(report_template['title'])}</title>
  <style>
    :root {{
      color: #172033;
      background: #f6f8fb;
      font-family: Arial, Helvetica, sans-serif;
    }}
    body {{ margin: 0; padding: 32px; }}
    .report {{ max-width: 1040px; margin: 0 auto; background: #fff; border: 1px solid #d8dee9; }}
    header {{ padding: 28px 32px; border-bottom: 1px solid #d8dee9; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    h2 {{ margin: 28px 0 12px; font-size: 18px; }}
    p {{ margin: 0; color: #526076; line-height: 1.45; }}
    main {{ padding: 0 32px 32px; }}
    .actions {{ display: flex; justify-content: flex-end; gap: 8px; margin-bottom: 18px; }}
    button {{ background: #0b63ce; color: #fff; border: 0; padding: 10px 14px; border-radius: 4px; font-weight: 700; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 24px; }}
    .metric {{ border: 1px solid #d8dee9; padding: 16px; }}
    .metric strong {{ display: block; font-size: 28px; }}
    .metric span {{ color: #526076; font-size: 12px; text-transform: uppercase; }}
    .note-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 16px; }}
    .note {{ border: 1px solid #d8dee9; padding: 12px; }}
    .note strong {{ display: block; font-size: 20px; }}
    ul {{ margin: 8px 0 0; padding-left: 20px; line-height: 1.5; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; border-bottom: 1px solid #d8dee9; padding: 10px 8px; vertical-align: top; }}
    th {{ background: #eef2f7; font-size: 12px; text-transform: uppercase; }}
    footer {{ padding: 18px 32px; border-top: 1px solid #d8dee9; color: #526076; font-size: 12px; }}
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .report {{ border: 0; }}
      .actions {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class="actions">
    <button onclick="window.print()">Print / Save PDF</button>
  </div>
  <article class="report">
    <header>
      <h1>{esc(project['name'])}</h1>
      <p>{esc(report_template['label'])}</p>
      <p>{esc(project['description'] or report_template['description'])}</p>
      <p>Generated {esc(report['generated_at'])}</p>
    </header>
    <main>
      <section class="summary">
        <div class="metric"><strong>{summary['tasks']['total']}</strong><span>Total tasks</span></div>
        <div class="metric"><strong>{summary['tasks']['completed']}</strong><span>Completed</span></div>
        <div class="metric"><strong>{summary['tasks']['processing']}</strong><span>Processing</span></div>
        <div class="metric"><strong>{summary['issues'].get('open', 0)}</strong><span>Open issues</span></div>
      </section>
      <h2>Client Review Focus</h2>
      <p>{esc(report_template['description'])}</p>
      <ul>{focus_rows}</ul>
      <div class="note-grid">
        <div class="note"><strong>{evidence['completed_orthomosaic_tasks']}</strong><span>Completed orthomosaics</span></div>
        <div class="note"><strong>{evidence['design_overlay_count']}</strong><span>Design overlays</span></div>
        <div class="note"><strong>{evidence['field_photo_count']}</strong><span>Field photos</span></div>
      </div>
      <h2>Latest Deliverables</h2>
      <table>
        <thead><tr><th>Task</th><th>Status</th><th>Created</th><th>Assets</th></tr></thead>
        <tbody>{task_rows}</tbody>
      </table>
      <h2>Open Issues And Annotations</h2>
      <table>
        <thead><tr><th>Title</th><th>Type</th><th>Priority</th><th>Status</th><th>Task</th></tr></thead>
        <tbody>{issue_rows}</tbody>
      </table>
      <h2>Commercial Caveats</h2>
      <ul>{caveat_rows}</ul>
    </main>
    <footer>Share this page with logged-in stakeholders, or use Print / Save PDF for an offline report.</footer>
  </article>
</body>
</html>"""
