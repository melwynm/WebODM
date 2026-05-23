import logging

from django.utils import timezone


logger = logging.getLogger('app.logger')

PIPELINE_FEATURE_VALIDATIONS = (
    {
        'key': 'mobile-field-photo-capture',
        'name': 'Mobile/Field Photo Capture',
        'area': 'P1',
        'test_notes': 'API regression tests cover create/list/delete, file validation, location validation, permissions, and map marker integration.',
        'maintenance_notes': 'Keep project permission checks, location GeoJSON validation, and file validation covered.',
    },
    {
        'key': 'ai-assisted-issue-detection',
        'name': 'AI-Assisted Issue Detection',
        'area': 'P2',
        'test_notes': 'API regression tests cover server-side OpenAI request wiring, missing API key handling, issue creation, and project permissions.',
        'maintenance_notes': 'Keep API key handling server-side and preserve human review before closing AI-created issues.',
    },
    {
        'key': 'client-sharing-portal',
        'name': 'Client Sharing Portal',
        'area': 'P3',
        'test_notes': 'Regression tests cover share management permissions, anonymous portal access, reviewer comments, read-only viewer behavior, expired/disabled links, and portal rendering.',
        'maintenance_notes': 'Expand future testing to richer map/review UI once tokenized map access changes.',
    },
    {
        'key': 'textured-model-qa-sharing',
        'name': 'Textured Model QA + Sharing',
        'area': 'P4',
        'test_notes': 'Regression tests cover textured-model QA status, project permissions, tokenized 3D page rendering, client-share model asset access, and safe GLB serving. Browser smoke confirmed the project 3D model renders.',
        'maintenance_notes': 'Keep token asset proxy read-only. Rebuild ModelView and run collectstatic after frontend changes so 3D routes serve current bundles.',
    },
    {
        'key': 'feature-validation-ledger',
        'name': 'Feature Validation Ledger',
        'area': 'P5',
        'test_notes': 'Regression tests cover admin-only API access, tested stamping, area/status/attention filters, status-change logging, and browser-page updates.',
        'maintenance_notes': 'Use this ledger after smoke tests and regressions so working, untested, failing, and blocked states stay visible.',
    },
    {
        'key': 'core-platform-hardening',
        'name': 'Core Platform Hardening',
        'area': 'P6',
        'test_notes': 'Platform audit regression tests, the platformaudit management command, and the staff Operations UI protect custom docs, routes, templates, APIs, services, models, and settings.',
        'maintenance_notes': 'Use Administration > Operations or run platformaudit after upgrades, dependency changes, and broad refactors.',
    },
    {
        'key': 'monitoring-compare-mvp',
        'name': 'Monitoring Compare MVP',
        'area': 'P7',
        'test_notes': 'Monitoring regressions cover comparison generation, alignment estimation, readiness metadata, generated tile serving, and cache state.',
        'maintenance_notes': 'Protect orthophoto-to-orthophoto comparison as the baseline for timeline and terrain workflows.',
    },
    {
        'key': 'project-timeline-monitoring',
        'name': 'Project Timeline Monitoring',
        'area': 'P8',
        'test_notes': 'Monitoring regressions cover timeline ordering, timeline readiness metadata, compare launch metadata, and cache invalidation behavior.',
        'maintenance_notes': 'Keep multi-date task selection tied to completed orthophoto task readiness.',
    },
    {
        'key': 'dsm-dtm-delta-cut-fill',
        'name': 'DSM/DTM Delta and Cut/Fill',
        'area': 'P9',
        'test_notes': 'Monitoring regressions cover DSM/DTM terrain delta readiness, terrain layer generation, tile serving, volume summaries, and orthophoto-only fallback behavior.',
        'maintenance_notes': 'Keep terrain products optional and clearly gated by matching DEM asset availability.',
    },
    {
        'key': 'change-issues-annotations',
        'name': 'Change Issues and Annotations',
        'area': 'P10',
        'test_notes': 'Project issue API regressions cover create/list/update, project permission enforcement, task ownership validation, and GeoJSON geometry validation.',
        'maintenance_notes': 'Keep change detections traceable through normal issue statuses and review outcomes.',
    },
    {
        'key': 'advanced-alignment',
        'name': 'Advanced Alignment',
        'area': 'P11',
        'test_notes': 'Monitoring alignment regressions cover translation stability and conservative similarity-transform application for low-confidence comparisons.',
        'maintenance_notes': 'Keep rotation/scale correction conservative; local rubber-sheet warping remains future work.',
    },
    {
        'key': 'stakeholder-reports',
        'name': 'Stakeholder Reports',
        'area': 'P12',
        'test_notes': 'Project report regressions cover JSON reports, printable HTML, dashboard report links, and project-scoped permissions.',
        'maintenance_notes': 'Keep reports stakeholder-readable and printable without requiring direct map tooling.',
    },
    {
        'key': 'design-bim-plan-overlays',
        'name': 'Design/BIM/Plan Overlays',
        'area': 'P13',
        'test_notes': 'Design overlay regressions cover overlay create/list/delete, supported file validation, permissions, and persistent map overlay rendering paths.',
        'maintenance_notes': 'Keep persistent overlay parsing aligned with temporary map overlay parsing.',
    },
    {
        'key': 'onedrive-folder-task-intake',
        'name': 'OneDrive Folder Task Intake',
        'area': 'P14',
        'test_notes': 'OneDrive intake regressions and the staff Operations UI cover dry-run discovery, folder dataset packaging, duplicate fingerprint protection, import task creation, and no-process behavior.',
        'maintenance_notes': 'Use Administration > Operations for browser intake runs. Keep duplicate protection and minimum-age handling in place for synced folders.',
    },
)


def log_feature_validation_change(feature, user=None, previous_status=None):
    username = getattr(user, 'username', None) or 'system'
    if previous_status and previous_status != feature.status:
        logger.info(
            "Feature validation changed: key=%s status=%s previous_status=%s user=%s",
            feature.key,
            feature.status,
            previous_status,
            username,
        )
    else:
        logger.info(
            "Feature validation recorded: key=%s status=%s user=%s",
            feature.key,
            feature.status,
            username,
        )


def reconcile_pipeline_feature_validations(status=None, overwrite=False, user=None):
    from app.models import FeatureValidation

    results = []
    for item in PIPELINE_FEATURE_VALIDATIONS:
        defaults = {
            'name': item['name'],
            'area': item['area'],
            'test_notes': item['test_notes'],
            'maintenance_notes': item['maintenance_notes'],
        }
        if status:
            defaults['status'] = status
            if user and status == FeatureValidation.STATUS_TESTED:
                defaults['last_tested_by'] = user

        feature, created = FeatureValidation.objects.get_or_create(
            key=item['key'],
            defaults=defaults,
        )

        changed = created
        if not created:
            for field in ('name', 'area'):
                if getattr(feature, field) != item[field]:
                    setattr(feature, field, item[field])
                    changed = True

            if overwrite:
                for field in ('test_notes', 'maintenance_notes'):
                    if getattr(feature, field) != item[field]:
                        setattr(feature, field, item[field])
                        changed = True

            if status and feature.status != status:
                feature.status = status
                changed = True
            if user and status == FeatureValidation.STATUS_TESTED and feature.last_tested_by_id != user.id:
                feature.last_tested_by = user
                changed = True
            if status == FeatureValidation.STATUS_TESTED and feature.last_tested_at is None:
                feature.last_tested_at = timezone.now()
                changed = True

            if changed:
                feature.save()

        if created or changed:
            log_feature_validation_change(feature, user)

        results.append((feature, created, changed))

    return results
