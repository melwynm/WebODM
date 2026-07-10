---
name: webodm-pipeline
description: Safe-work contract and repo map for pipeline/roadmap work in this WebODM fork. Use whenever a task mentions "the pipeline", "next item", P1-P14, monitoring, feature validation, commercial readiness, AirTwin, or object detection — before opening code.
---

# WebODM Fork — Pipeline Work Contract

## Document authority (never reorder)

1. `PIPELINE.md` — the ONLY source of truth for the ordered pipeline and the next priority. The next item is the first stage marked `Next`; if none exists, the "Current Next Item" section governs (currently QA hardening via the feature validation ledger, not a new feature).
2. `AGENTS.md` — agent behavior contract; defers to `PIPELINE.md`.
3. `DEVELOPMENT_STATUS.md` — history and status notes only. Never treat it as the ordered pipeline. Its "Known Limits" and "Useful Commands" sections are the practical operations reference.
4. `app/static/app/js/classes/PipelineSteps.js` — UI runtime subset only (the 11 ODM processing steps). Do not add roadmap items here.

## Repo map for pipeline work

- `app/api/` — DRF endpoints, one module per feature (e.g. `monitoring.py`, `feature_validation.py`, `airtwin.py`, `commercial_readiness.py`, `delivery_exports.py`, `issues.py`, `reports.py`). Routes in `app/api/urls.py`.
- `app/api/permissions.py` — `ProjectPermissionPolicy` is the central project-scoped permission entry point. Never duplicate direct `get_perms` checks in new APIs.
- `app/services/` — business logic layer (import direction: api → services → models, see `MODULE_BOUNDARIES.md`). Monitoring is split into `app/services/monitoring/` (alignment, cache, overlays, payloads, products, readiness).
- `app/models/project.py` — Project model; custom object permissions live in its `Meta.permissions` (e.g. `acknowledge_airtwin_import`).
- `app/management/commands/` — operational gates: `platformaudit`, `productionreadiness`, `securityreview`, `reconcilefeaturevalidations`, `onedriveintake`, `createdemoprojects`, `syncdefaultnodes`.
- `app/tests/` — one `test_*` module per feature; run inside Docker with `--keepdb`.
- `coreplugins/objdetect/` — object detection (dog/deer paths); frontend bundles rebuilt via `python manage.py rebuildplugins`.

## Non-negotiable gotchas

1. **Platform audit registration.** Any new root doc, template, API module, service module, route, model, or setting that should survive upgrades MUST be registered in `app/services/platform_audit.py`. `python manage.py platformaudit` exits non-zero on missing surfaces — CI/ops gates depend on it.
2. **Feature validation ledger counts.** `reconcilefeaturevalidations` maintains exactly 20 records (P1–P14 + 6 commercial). `app/tests/test_api_feature_validation.py` asserts that exact count — adding a ledger record requires updating the reconciliation service, the command help text, AND the test.
3. **Project permission count drift.** Adding a permission to `Project.Meta.permissions` requires a migration and breaks any test asserting a fixed `get_perms` length (this bit `test_api_projects.py` when `acknowledge_airtwin_import` was added). Assert on a subset of permission names, never a count.
4. **Plugin builds go stale.** After touching plugin frontend sources, run `python manage.py rebuildplugins`; stale-source detection exists but verify the bundle regenerated.
5. **Tests run in Docker.** `docker exec webapp python manage.py test app.tests.<module> --keepdb`. Do not try to run the Django suite on the Windows host.
6. **Do not touch** the intentional local deletion at `nodeodm/external/NodeODM`.
7. **Docs are contract, not decoration.** Delivered features update `PIPELINE.md` (maintenance note + roadmap row), `DEVELOPMENT_STATUS.md` (Recently Completed section), and often `USER_MANUAL.md` — plus platform audit registration for any new file.

## Definition of done for a pipeline change

- [ ] Feature/service code in `app/services/` (thin API in `app/api/`), permissions via `ProjectPermissionPolicy`
- [ ] Regression tests in `app/tests/test_<feature>.py` pass with `--keepdb`
- [ ] `docker exec webapp python manage.py platformaudit` passes
- [ ] New surfaces registered in `app/services/platform_audit.py`
- [ ] `PIPELINE.md` maintenance note + `DEVELOPMENT_STATUS.md` entry added
- [ ] Feature validation ledger record created/updated (via `/feature-validations/` or `reconcilefeaturevalidations` if it's a P-item or commercial record)
