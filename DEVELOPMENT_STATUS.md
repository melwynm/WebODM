# Development Status

Last updated: 2026-05-18

## Purpose

This file tracks the current state of this fork so future work can start from the right baseline without having to reconstruct recent changes from commit history alone.

## Canonical Pipeline

- The single source of truth for the combined processing and roadmap pipeline now lives in `PIPELINE.md`.
- When checking what comes next, use the first stage marked `Next` in `PIPELINE.md`.

## Current Focus

- Stabilize the customized WebODM fork
- Add monitoring and progress workflows for repeated drone captures
- Reduce operational issues in local Docker and NodeODM setups

## Recently Completed

### Feature Validation Dashboard UX

- Reworked the staff feature validation page into a system-health dashboard grouped by P1-P14 pipeline item
- Added top-level health metrics for test coverage, attention items, tested records, and tracked features
- Added per-pipeline coverage cards with status counts, evidence links, maintenance notes, and inline editing
- Added an attention panel so untested, failing, and blocked features are visible without scanning the full list

### Pipeline Reconciliation

- Rechecked P1 through P14 against implementation evidence in APIs, services, models, management commands, UI hooks, and regression tests
- Confirmed P10 through P14 already have working implementation slices and updated the canonical pipeline to match the codebase
- Reframed the next priority as QA and hardening through the feature validation ledger instead of another unimplemented roadmap item

### Monitoring Compare, Timeline, And Terrain Readiness

- Added a monitoring readiness service that reports whether tasks can be compared, which source assets are present, which DSM/DTM terrain delta products are possible, and whether a comparison cache is ready
- Added readiness metadata to monitoring timeline, candidates, and compare API responses
- Extended monitoring regression coverage for readiness metadata, terrain-delta availability, and cache readiness after product generation
- Updated the platform audit to protect the monitoring readiness service
- Updated the canonical pipeline so P7, P8, and P9 are working and P10 is the next priority

### Core Platform Hardening - Platform Audit

- Added a platform audit service that verifies custom fork docs, templates, API modules, service modules, routes, models, and settings still exist after upgrades or refactors
- Added a `platformaudit` management command that reports missing or broken custom surfaces and exits non-zero when required pieces are absent
- Added regression coverage for the audit service, JSON command output, command summary output, and missing-file reporting
- Updated the canonical pipeline so P6 is working and P7 is the next priority

### Textured Model QA And Sharing

- Added a textured-model QA service that reports model, GLB, point cloud, camera-shot, and 3D tile asset readiness
- Added project task QA API at `/api/projects/<project>/tasks/<task>/3d/qa`
- Added tokenized client 3D review pages from client share links without requiring the task or project to be public
- Added client-share asset, safe textured model, scene, and QA API routes for read-only 3D model access
- Added client portal links to open 3D review when model or point-cloud assets are available
- Added regression coverage for QA status, project permissions, tokenized 3D page rendering, and client-share model asset access

### Feature Validation Ledger

- Added a feature validation ledger for tracking whether features are untested, testing, tested, failing, or blocked
- Added admin and staff-only API access for feature validation records with area, evidence URL, test notes, and maintenance notes
- Added a staff browser page at `/feature-validations/` for reviewing and updating feature validation records from the WebODM UI
- Added automatic tester/time stamping when a feature is marked tested
- Added structured `app.logger` entries when feature validation records are created or their status changes
- Added regression coverage for admin-only access, tested stamping, area/status filters, status-change logging, and browser-page updates

### Client Sharing Portal

- Added project-scoped client share links with viewer and reviewer roles
- Added tokenized client portal access without requiring a WebODM user account or making the whole project public
- Added reviewer-only client comments with optional project task, issue, and GeoJSON geometry association
- Added portal JSON and comment APIs for integration with richer client review screens
- Added a lightweight client portal page that summarizes deliverables, open review items, access role, and comments
- Added regression coverage for share management permissions, anonymous portal access, reviewer comments, read-only viewer behavior, expired/disabled links, and portal rendering

### AI-Assisted Issue Detection

- Added server-side OpenAI API key and model settings under the singleton application Settings record
- Added a backend AI issue detection service that prepares safe image previews from field photos or orthophoto previews
- Added a project AI issue detection API that calls OpenAI from the server and creates reviewable `in_review` project issues
- Preserved the human-review loop by storing AI-created issues as normal project issues with AI metadata and confidence
- Added regression coverage for OpenAI request wiring, missing API key handling, issue creation, and project permissions

### Mobile/Field Photo Capture

- Added project-scoped field photo records for ground photos and 360 photos with GeoJSON point locations
- Added upload, list, update, and delete API support with project permission checks and optional task association
- Added map markers and photo popups for field photos in the 2D map
- Added a map camera control so project editors can attach a field photo to a clicked map location
- Added regression coverage for create/list/delete, file validation, location validation, and project permissions

### Design/BIM/Plan Overlays

- Added project-scoped design overlay records with upload, list, and delete API support
- Added permission checks so project viewers can load overlays and project editors can manage them
- Render supported GeoJSON and zipped Shapefile overlays automatically in the 2D map layer control
- Reused the existing map overlay parser path so temporary and persistent overlays stay consistent
- Added regression coverage for overlay create/list/delete, file validation, and project permissions

### Object Detection Stability

- Fixed object detection worker failures caused by serialized worker execution not having access to module-level imports
- Added regression coverage for object detection code paths
- Added ONNX compatibility handling for newer custom models, including the dog model case that required opset down-conversion for the runtime in this stack

### Monitoring And Progress MVP

- Added a first monitoring compare workflow for orthophotos in single-task map view
- Added a `Monitor` UI control to compare the current task with another completed task in the same project
- Implemented automatic alignment correction before overlay generation to compensate for small georeferencing drift from non-RTK flights
- Generated two outputs for review:
  - aligned comparison overlay
  - change heatmap overlay
- Added backend caching for generated monitoring products
- Added regression tests for alignment estimation and monitoring tile/API generation

### Project Timeline Monitoring

- Expanded monitoring from a single-task compare flow into a project-level timeline workspace
- Added a project monitoring timeline API that lists completed orthophoto tasks in timeline order
- Added timeline-driven reference and compare task selection in the map UI
- Added direct comparison launch from timeline-selected tasks instead of only from the current task context
- Added monitoring cache invalidation when orthophoto inputs change and when compared tasks are deleted
- Added regression coverage for timeline ordering and cache invalidation behavior

### DSM/DTM Delta And Cut/Fill

- Added optional DSM and DTM delta products to monitoring comparisons when both selected tasks have matching DEM assets
- Generated terrain delta tile overlays alongside the existing aligned orthophoto and change heatmap layers
- Added cut/fill-style volume summaries, net volume, delta range, and valid-pixel stats to terrain layers
- Extended monitoring cache invalidation to include DSM and DTM input timestamps
- Added regression coverage for terrain layer generation, tile serving, and orthophoto-only fallback behavior

### OneDrive Folder Task Intake

- Added a `onedriveintake` management command for creating WebODM import tasks from a OneDrive-synced local folder
- Supports zipped datasets and immediate child folders containing imagery
- Packages folder datasets into WebODM's existing `media/imports` flow and queues them with `pending_action=IMPORT`
- Tracks processed dataset fingerprints in a cache state file to avoid duplicate task creation on repeated runs
- Supports `WO_ONEDRIVE_INTAKE_DIR`, `--folder`, `--min-age`, `--dry-run`, and `--no-process`

### Change Issues And Annotations

- Added project-level issue and annotation tracking for detected changes, defects, progress notes, and review annotations
- Added nested project issue API endpoints with project-level permission checks and GeoJSON geometry validation
- Added a dashboard issues panel for creating issues, listing current issues, and updating issue status
- Added Django admin management and regression coverage for create/list/update, project permission enforcement, task ownership validation, and geometry validation

### Stakeholder Progress Reports

- Added a project progress report API for dashboard/client reporting
- Added printable stakeholder web reports with a `Print / Save PDF` action
- Reports summarize project metadata, task counts, latest deliverables, exported assets, and open issues/annotations
- Added a dashboard `Report` link for each project
- Added regression coverage for JSON reports, printable HTML, and project-scoped permissions

### Advanced Alignment

- Added similarity alignment metadata for monitoring comparisons, including transform type, rotation, scale, center point, and translation
- Added a conservative rotation/scale search path that runs only when the existing translation alignment has low confidence
- Updated aligned overlay transform and overlap bounds calculations to support similarity transforms instead of translation-only shifts
- Reduced alignment preview size to keep monitoring comparisons responsive while preserving full-resolution output generation
- Added regression coverage for translation stability and similarity-transform application

### Core Platform Hardening

- Added `ARCHITECTURE.md` and `MODULE_BOUNDARIES.md` to define core layer responsibilities, service boundaries, import direction, and upgrade-confidence rules
- Added `app/services/` as the application service layer
- Moved project progress report construction and HTML rendering from the API view into `app/services/project_reports.py`
- Added `ProjectPermissionPolicy` as a central project-scoped API permission entry point
- Updated newer project-scoped APIs to use the permission policy instead of duplicating direct project access checks
- Split monitoring implementation into focused services for alignment, cache, overlays, payloads, and product orchestration
- Removed the legacy `app/monitoring.py` compatibility facade and moved runtime callers to service imports
- Replaced the test-named async result abstraction with `worker/results.py` so runtime APIs and plugins do not import test plumbing

### Default NodeODM Repair

- Added a `syncdefaultnodes` management command to repair legacy default-node aliases such as `nodeodm`
- Reassigns tasks from stale default-node records to the current default node hostname
- Wired the command into startup so the stack can self-heal when default node aliases drift
- Added a regression test covering the legacy `nodeodm` hostname repair path

### Mission Planner Alias Cleanup

- Stopped startup warnings caused by the legacy `mission-planner` alias folder being discovered alongside the canonical `mission_planner` package
- Plugin discovery now prefers canonical underscore-named packages when a hyphenated legacy alias exists next to them
- Added regression coverage so hyphenated legacy aliases are skipped when a valid underscore twin is present

## What Is Working Now

- Standard WebODM task processing
- Default local WebODM UI on port `8000`
- Object detection, including the previously failing dog model path
- Monitoring compare for orthophotos with automatic translational alignment correction
- Monitoring readiness metadata for compare eligibility, cache state, and DSM/DTM terrain-delta availability
- Monitoring alignment can now carry rotation and scale corrections when translation-only confidence is weak
- Monitoring compare from a project timeline view with timeline-based task selection
- DSM/DTM terrain delta overlays and cut/fill-style volume stats when compared tasks include DEM assets
- Project issues and annotations from the dashboard via each project's `Issues` panel
- Project field photos from the 2D map via the camera control and field-photo marker layer
- AI-assisted issue detection via server-side OpenAI configuration and the project issue review workflow
- Client sharing portal links with viewer/reviewer roles and tokenized client comments
- Textured model QA and tokenized client 3D review links
- Feature validation ledger via `/feature-validations/`, `/api/feature-validations/`, and Django admin for tested/untested/failing/blocked tracking
- Platform upgrade audit via `python manage.py platformaudit`
- Stakeholder progress reports from the dashboard via each project's `Report` link
- OneDrive-synced folder task intake via `python manage.py onedriveintake --project <id> --folder <path>`
- NodeODM stale-hostname repair via `python manage.py syncdefaultnodes --count 1`

## Known Limits

### Monitoring

- Monitoring still uses orthophoto-to-orthophoto comparison as the required alignment baseline
- DSM/DTM terrain products are available only when both compared tasks have matching DEM assets
- Advanced alignment is a conservative similarity transform; it is not full local/rubber-sheet warping yet
- No rubber-sheet/local warping or design/BIM comparison workflow yet

### Operations

- There is an unrelated local deletion at `nodeodm/external/NodeODM` that has intentionally been left untouched
- If a stale default processing node ever persists after a restart, you can repair it manually with `docker exec webapp python manage.py syncdefaultnodes --count 1`


## Useful Commands

```bash
docker compose build webapp
docker-compose up -d webapp worker
docker exec webapp python manage.py test app.tests.test_monitoring --keepdb
docker exec webapp python manage.py test app.tests.test_api_project_issues --keepdb
docker exec webapp python manage.py test app.tests.test_api_project_reports --keepdb
docker exec webapp python manage.py test app.tests.test_api_client_portal --keepdb
docker exec webapp python manage.py test app.tests.test_api_textured_model_qa --keepdb
docker exec webapp python manage.py test app.tests.test_api_feature_validation --keepdb
docker exec webapp python manage.py test app.tests.test_platform_audit --keepdb
docker exec webapp python manage.py test app.tests.test_onedrive_intake --keepdb
docker exec webapp python manage.py test app.tests.test_app.TestApp.test_syncdefaultnodes_repairs_legacy_default_node --keepdb
docker exec webapp python manage.py platformaudit
docker exec webapp python manage.py syncdefaultnodes --count 1
docker exec webapp python manage.py onedriveintake --project <project-id> --folder /webodm/app/media/imports/onedrive --dry-run
```
