import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from app import models
from app.services.monitoring import monitoring_pair_readiness, task_monitoring_readiness
from app.services.project_reports import build_project_progress_report, normalize_report_template
from nodeodm import status_codes


class MonitoringRunError(Exception):
    pass


ACTIVE_RUN_STATUSES = (
    models.ProjectMonitoringRun.STATUS_GENERATING,
    models.ProjectMonitoringRun.STATUS_REVIEW,
)


def ready_monitoring_tasks(project):
    tasks = project.task_set.filter(status=status_codes.COMPLETED).order_by("created_at", "id")
    return [task for task in tasks if task_monitoring_readiness(task)["can_compare"]]


def _project_task(project, task_id, field_name):
    if not task_id:
        return None
    try:
        return project.task_set.get(pk=task_id)
    except (models.Task.DoesNotExist, DjangoValidationError):
        raise MonitoringRunError("{} must belong to this project.".format(field_name))


def select_monitoring_pair(project, current_task_id=None, baseline_task_id=None):
    tasks = ready_monitoring_tasks(project)
    if len(tasks) < 2:
        raise MonitoringRunError("At least two completed orthophoto tasks are required.")

    current_task = _project_task(project, current_task_id, "Current task")
    baseline_task = _project_task(project, baseline_task_id, "Baseline task")

    if current_task is None:
        current_task = tasks[-1]

    ready_ids = {str(task.id) for task in tasks}
    if str(current_task.id) not in ready_ids:
        raise MonitoringRunError("Current task is not ready for monitoring comparison.")

    if baseline_task is None:
        current_index = next(index for index, task in enumerate(tasks) if task.id == current_task.id)
        if current_index > 0:
            baseline_task = tasks[current_index - 1]
        elif current_index + 1 < len(tasks):
            baseline_task = tasks[current_index + 1]

    if baseline_task is None or str(baseline_task.id) not in ready_ids:
        raise MonitoringRunError("Baseline task is not ready for monitoring comparison.")
    if current_task.id == baseline_task.id:
        raise MonitoringRunError("Current and baseline tasks must be different.")

    readiness = monitoring_pair_readiness(current_task, baseline_task)
    if not readiness["can_compare"]:
        raise MonitoringRunError(readiness["issues"][0])
    return current_task, baseline_task, readiness


def monitoring_run_issues(run):
    return models.ProjectIssue.objects.filter(
        project=run.project,
        properties__monitoring_run_id=str(run.id),
    ).select_related("task", "created_by", "assigned_to")


def queue_monitoring_run(run, *, enqueue_comparison):
    # The caller supplies the worker dispatch so this service stays independent
    # of Celery; it receives (current_task_id, baseline_task_id, run_id, attempt_id).
    readiness = monitoring_pair_readiness(run.current_task, run.baseline_task)
    if not readiness["can_compare"]:
        run.status = models.ProjectMonitoringRun.STATUS_FAILED
        run.last_error = readiness["issues"][0]
        run.save(update_fields=("status", "last_error", "updated_at"))
        return run

    if readiness["cache"]["ready"]:
        run.status = models.ProjectMonitoringRun.STATUS_REVIEW
        run.last_error = ""
        if run.comparison_generated_at is None:
            run.comparison_generated_at = timezone.now()
        run.save(update_fields=("status", "last_error", "comparison_generated_at", "updated_at"))
        return run

    run.status = models.ProjectMonitoringRun.STATUS_GENERATING
    run.last_error = ""
    run.celery_task_id = str(uuid.uuid4())
    run.save(update_fields=("status", "last_error", "celery_task_id", "updated_at"))

    # Workers must see both the run and its attempt ID before they can complete it.
    attempt_id = run.celery_task_id

    def dispatch_comparison():
        try:
            enqueue_comparison(
                str(run.current_task_id),
                str(run.baseline_task_id),
                str(run.id),
                attempt_id,
            )
        except Exception as exc:
            models.ProjectMonitoringRun.objects.filter(
                pk=run.pk,
                status=models.ProjectMonitoringRun.STATUS_GENERATING,
                celery_task_id=attempt_id,
            ).update(
                status=models.ProjectMonitoringRun.STATUS_FAILED,
                last_error="Could not queue monitoring comparison: {}".format(exc),
                updated_at=timezone.now(),
            )
        # Eager execution can finish during dispatch; keep the caller's run current.
        run.refresh_from_db()

    transaction.on_commit(dispatch_comparison)
    return run


def _lock_project(project_id):
    # Lock a row that always exists, including before the first run is created.
    models.Project.objects.select_for_update().get(pk=project_id)


def _active_pair_runs(run):
    return models.ProjectMonitoringRun.objects.filter(
        project_id=run.project_id,
        current_task_id=run.current_task_id,
        baseline_task_id=run.baseline_task_id,
        status__in=ACTIVE_RUN_STATUSES,
    )


@transaction.atomic
def create_monitoring_run(
    project,
    user,
    current_task_id=None,
    baseline_task_id=None,
    report_template=None,
    *,
    enqueue_comparison,
):
    current_task, baseline_task, readiness = select_monitoring_pair(
        project,
        current_task_id=current_task_id,
        baseline_task_id=baseline_task_id,
    )

    _lock_project(project.pk)
    existing = models.ProjectMonitoringRun.objects.select_for_update().filter(
        project=project,
        current_task=current_task,
        baseline_task=baseline_task,
        status__in=ACTIVE_RUN_STATUSES,
    ).first()
    if existing is not None:
        return existing, False

    run = models.ProjectMonitoringRun.objects.create(
        project=project,
        current_task=current_task,
        baseline_task=baseline_task,
        report_template=normalize_report_template(project, report_template),
        status=(
            models.ProjectMonitoringRun.STATUS_REVIEW
            if readiness["cache"]["ready"]
            else models.ProjectMonitoringRun.STATUS_GENERATING
        ),
        comparison_generated_at=timezone.now() if readiness["cache"]["ready"] else None,
        created_by=user,
    )
    return queue_monitoring_run(run, enqueue_comparison=enqueue_comparison), True


@transaction.atomic
def retry_monitoring_run(run, *, enqueue_comparison):
    _lock_project(run.project_id)
    run = models.ProjectMonitoringRun.objects.select_for_update().select_related(
        "current_task", "baseline_task"
    ).get(pk=run.pk)
    if run.status == models.ProjectMonitoringRun.STATUS_PUBLISHED:
        raise MonitoringRunError("Published monitoring runs cannot be regenerated.")
    if run.status == models.ProjectMonitoringRun.STATUS_GENERATING:
        return run
    if _active_pair_runs(run).exclude(pk=run.pk).exists():
        raise MonitoringRunError("Another monitoring run is already active for these tasks.")
    return queue_monitoring_run(run, enqueue_comparison=enqueue_comparison)


def _active_client_share(project, share_id=None):
    now = timezone.now()
    active_shares = project.client_shares.filter(enabled=True).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )
    if share_id:
        try:
            return active_shares.get(pk=share_id)
        except (models.ProjectClientShare.DoesNotExist, ValueError, TypeError):
            raise MonitoringRunError("Client share must be active and belong to this project.")
    return active_shares.first()


@transaction.atomic
def publish_monitoring_run(run, user, client_share_id=None):
    run = models.ProjectMonitoringRun.objects.select_for_update().select_related(
        "project", "current_task", "baseline_task"
    ).get(pk=run.pk)
    if run.status == models.ProjectMonitoringRun.STATUS_PUBLISHED:
        return run
    if run.status != models.ProjectMonitoringRun.STATUS_REVIEW:
        raise MonitoringRunError("Monitoring comparison must be ready before publication.")

    readiness = monitoring_pair_readiness(run.current_task, run.baseline_task)
    if not readiness["cache"]["ready"]:
        raise MonitoringRunError("Monitoring comparison is no longer ready. Regenerate it before publication.")

    share = _active_client_share(run.project, client_share_id)
    if share is None:
        share = models.ProjectClientShare.objects.create(
            project=run.project,
            name=("{} monitoring review".format(run.current_task.name or "Project"))[:255],
            role=models.ProjectClientShare.ROLE_VIEWER,
            created_by=user,
        )

    run.client_share = share
    run.status = models.ProjectMonitoringRun.STATUS_PUBLISHED
    run.published_at = timezone.now()
    run.report_snapshot = build_project_progress_report(
        run.project,
        template=run.report_template,
        monitoring_run=run,
    )
    run.last_error = ""
    run.save(update_fields=(
        "client_share",
        "report_snapshot",
        "status",
        "published_at",
        "last_error",
        "updated_at",
    ))
    return run
