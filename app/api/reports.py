from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import conditional_escape
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app import models
from app.api.common import get_and_check_project
from nodeodm import status_codes


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


def build_project_progress_report(project):
    tasks = list(project.task_set.all().order_by("-created_at", "-id"))
    issues = list(project.issues.select_related("task", "created_by", "assigned_to").order_by("-created_at", "-id"))

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
    for asset in ("orthophoto.tif", "dsm.tif", "dtm.tif", "georeferenced_model.laz", "textured_model.zip"):
        if asset in assets:
            labels.append(asset)
    return ", ".join(labels or assets[:4])


def render_progress_report_html(report):
    project = report["project"]
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

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{esc(project['name'])} Progress Report</title>
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
      <p>{esc(project['description'] or 'Stakeholder progress report')}</p>
      <p>Generated {esc(report['generated_at'])}</p>
    </header>
    <main>
      <section class="summary">
        <div class="metric"><strong>{summary['tasks']['total']}</strong><span>Total tasks</span></div>
        <div class="metric"><strong>{summary['tasks']['completed']}</strong><span>Completed</span></div>
        <div class="metric"><strong>{summary['tasks']['processing']}</strong><span>Processing</span></div>
        <div class="metric"><strong>{summary['issues'].get('open', 0)}</strong><span>Open issues</span></div>
      </section>
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
    </main>
    <footer>Share this page with logged-in stakeholders, or use Print / Save PDF for an offline report.</footer>
  </article>
</body>
</html>"""


class ProjectProgressReport(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, project_pk=None):
        project = get_and_check_project(request, project_pk)
        report = build_project_progress_report(project)
        fmt = (request.query_params.get("format") or "").lower()

        if fmt == "html":
            return HttpResponse(render_progress_report_html(report), content_type="text/html; charset=utf-8")

        return Response(report)
