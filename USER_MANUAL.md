# User Manual

This manual explains how to use this customized WebODM fork for drone project processing, progress monitoring, field review, issue tracking, client sharing, and operational checks.

It is written for project operators, reviewers, administrators, and pilot customers. For architecture and developer details, use `ARCHITECTURE.md`, `MODULE_BOUNDARIES.md`, `PIPELINE.md`, `PRODUCTION_HARDENING.md`, and `SECURITY_REVIEW.md`. For sales packaging, use `COMMERCIAL_PACKAGES.md`, `COMMERCIAL_DISCLAIMERS.md`, and `ORTHOMOSAIC_COMMERCIAL_FEATURES.md`.

## 1. What This Tool Does

This WebODM fork turns drone captures into reviewable project evidence.

Core capabilities:

- Process drone imagery into orthophotos, DEMs, point clouds, textured models, and standard task assets.
- Review projects on a 2D map and 3D model viewer.
- Compare repeated drone captures to monitor progress and terrain change.
- Track field photos, issues, annotations, design overlays, AI-assisted review items, and reports.
- Share read-only or reviewer links with clients without creating client user accounts.
- Run operational checks for platform health, production readiness, and security review.

## 2. User Roles

### Administrator

Administrators manage users, settings, processing nodes, operational checks, production/security gates, and feature validation.

Typical admin pages:

- `/admin/`
- `/operations/`
- `/feature-validations/`
- `/account/token/`

### Project Operator

Project operators create projects, upload drone datasets, run processing, review outputs, create reports, and share results.

### Reviewer

Reviewers inspect maps, 3D models, issues, reports, and comments. Reviewers may be internal users or external client-share reviewers.

### Client Viewer

Client viewers use tokenized client portal links. They can see shared project deliverables but do not need a WebODM account.

### Client Reviewer

Client reviewers use tokenized client portal links and can add comments when the share role is `reviewer`.

## 3. Basic Concepts

### Project

A project groups related drone captures, issues, reports, design overlays, field photos, and client shares.

### Task

A task is a single drone dataset processing run. A task usually starts with uploaded images or an imported dataset and produces map, elevation, model, and report assets.

### Processing Node

A processing node is the NodeODM engine that performs photogrammetry processing. At least one online processing node is required to process tasks.

### Orthophoto

An orthophoto is the georeferenced map image used for visual review and progress comparison.

### DSM and DTM

DSM and DTM outputs are elevation products. When two compared tasks both have matching DEM assets, terrain delta and volume-style summaries can be generated.

### Issue

An issue is a reviewable project item, such as a defect, change, annotation, or progress note. Issues can be created manually, from AI-assisted review, from object detection, or from monitoring review.

### Client Share

A client share is a tokenized external link for a project. It can be a viewer link or reviewer link.

### Feature Validation

Feature validation is the internal ledger used by staff to track whether the major product features are tested, untested, failing, or blocked.

## 4. First Login

1. Open the WebODM URL.
   - Local development: `http://localhost:8000`
   - Production: use the HTTPS domain supplied by the administrator.
2. Sign in with your WebODM account.
3. Open the dashboard.
4. Confirm that projects are visible and that the left navigation menu is readable.
5. If you are an administrator, open `/operations/` and verify that the platform audit shows no missing or error items.

## 5. Create A Project

1. From the dashboard, create a new project.
2. Give it a clear name, for example `Site A - Monthly Monitoring`.
3. Add users or groups if the project needs shared internal access.
4. Keep one project per real-world site or client deliverable unless the project owner has a different operational convention.

Good project names include:

- Site or client name
- Location or phase
- Date range if useful

Example:

```text
Grand Baie Villas - 2026 Progress Monitoring
```

## 6. Upload And Process A Drone Dataset

1. Open the project.
2. Create a new task.
3. Upload the drone images.
4. Choose processing options if needed.
5. Start processing.
6. Wait for the task to complete.

### Commercial Orthomosaic Presets

Three commercial orthomosaic presets are available for the first customer packages:

- `Architecture CAD Orthomosaic` for high-resolution site reality capture, CAD/design overlay comparison, construction progress monitoring, DSM/DTM deltas, and reports.
- `Agriculture Field Analysis` for field-scale orthomosaics, radiometric calibration, plant-health formula layers, DSM context, and GIS-ready exports.
- `Solar Panel Inspection` for high-detail solar site orthomosaics, panel/row issue mapping, thermal follow-up workflows, and client review.

Use `ORTHOMOSAIC_COMMERCIAL_FEATURES.md` as the product coverage matrix for these commercial packages.

During processing, watch for:

- Queued or running status
- Processing node availability
- Failed status or task errors
- Missing assets after completion

If processing fails, inspect the task console/logs and verify that the dataset has enough overlap, valid images, and a reachable processing node.

## 7. Recommended Drone Capture Practices

For reliable commercial outputs:

- Use consistent flight altitude across repeated captures.
- Keep high forward and side overlap.
- Use RTK/GCPs where precision matters.
- Avoid mixing unrelated flights in the same task.
- Keep image timestamps and camera metadata intact.
- Use one capture date per task when doing progress monitoring.
- Keep DSM/DTM generation enabled when terrain change matters.

For repeated progress monitoring, fly from similar altitude, angle, overlap, and boundary coverage each time. The monitoring tools can align small differences, but they are not a replacement for disciplined capture.

## 8. Review A Task On The Map

1. Open a completed task.
2. Use the 2D map view to inspect the orthophoto.
3. Toggle layers such as orthophoto, DSM, DTM, field photos, design overlays, monitoring products, and annotations when available.
4. Use zoom and pan to inspect specific areas.
5. Add issues or annotations where review is needed.

Common review checks:

- Is the orthophoto complete?
- Are edges clipped or distorted?
- Are there obvious processing artifacts?
- Are expected site areas visible?
- Are DSM/DTM assets present when terrain analysis is needed?

## 9. Field Photos

Field photos add ground context to project maps.

Use field photos for:

- Ground-level evidence
- Safety or defect details
- 360-photo context
- Photos that explain changes not obvious from the drone view

Workflow:

1. Open the project map.
2. Use the camera control or field-photo action.
3. Pick the map location.
4. Upload the photo.
5. Add a useful name and description.
6. Save.

Field photo uploads accept common image formats such as JPG, PNG, WEBP, TIFF, and JPEG.

## 10. Design, BIM, And Plan Overlays

Design overlays let reviewers compare actual drone outputs against plan data.

Supported overlay types:

- GeoJSON
- JSON containing supported map geometry
- Zipped Shapefile packages

Workflow:

1. Open the project.
2. Add a design overlay.
3. Upload the supported overlay file.
4. Open the map.
5. Toggle the overlay in the layer control.
6. Compare the overlay against the latest orthophoto.

Keep design overlay coordinate systems aligned with the project outputs. If an overlay appears far away from the site, confirm the source CRS and export format.

## 11. Issues And Annotations

Use issues for anything that needs review, action, or later reference.

Issue types include:

- Annotation
- Change
- Defect
- Progress

Typical workflow:

1. Open the project or map.
2. Create an issue from the issue panel, map annotation, AI-assisted review, object detection, or monitoring result.
3. Add a clear title.
4. Set priority.
5. Link to a task when relevant.
6. Add geometry when the issue is location-specific.
7. Keep the status updated.

Recommended status discipline:

- `in_review` for new unconfirmed items.
- `open` for confirmed work.
- `resolved` after the project team addresses the item.
- `closed` after final review.

## 12. AI-Assisted Issue Detection

AI-assisted issue detection reviews field photos or orthophoto previews and creates reviewable issue candidates.

Important limits:

- AI output is assistance only.
- A human must review every AI-created issue.
- AI should not be presented as authoritative inspection or certification.
- The OpenAI API key must remain server-side.

Workflow:

1. Confirm the administrator has configured the OpenAI API key and model in Settings or environment.
2. Open the project.
3. Run AI-assisted issue detection from the project workflow.
4. Review each candidate.
5. Keep useful issues and close or delete incorrect items.

If AI review reports no available images, confirm that the project has field photos or a task with a usable orthophoto preview.

## 13. Object Detection

Object detection can identify supported object classes and show results on the map.

Current examples include:

- Cars
- Trees
- Athletic facilities
- Boats
- Planes
- Cattle
- Dogs
- Deer

Dog and deer detection use the generic model path with class-specific GSD-aware size filtering unless specialized models are configured. Treat detections as review candidates, not confirmed counts. Before selling deer counts as a wildlife deliverable, complete the validation gate in `DEER_DETECTION_VALIDATION.md`.

Workflow:

1. Open the task map.
2. Open the object detection panel.
3. Select the model/class.
4. Run detection.
5. Review the displayed detections.
6. Download GeoJSON if needed.
7. Use `Create Issues` only after confirming the detections are useful for review.

## 14. Monitoring Compare

Monitoring compare is used to compare two completed drone captures from the same project.

Workflow:

1. Open a completed task.
2. Open monitoring or timeline controls.
3. Select a reference task.
4. Select a comparison task.
5. Confirm readiness indicators.
6. Generate or load the comparison.
7. Review aligned overlay and change heatmap.
8. If DEM assets are available for both tasks, review DSM/DTM delta products.

Readiness indicators help answer:

- Do both tasks have orthophotos?
- Are DSM and DTM products available?
- Is a cached comparison already available?
- Can terrain delta products be generated?

## 15. Timeline Monitoring

Timeline monitoring helps review repeated captures in date order.

Use it for:

- Monthly progress reviews
- Before/after comparisons
- Selecting a baseline and current task
- Quickly checking which dates are ready for comparison

Recommended workflow:

1. Open the project map.
2. Open timeline monitoring.
3. Review available completed tasks.
4. Pick the baseline capture.
5. Pick the latest capture.
6. Launch compare.
7. Record useful findings as issues or include them in a report.

## 16. DSM/DTM Delta And Volume Review

Terrain delta products are available when both compared tasks include matching DEM assets.

Use terrain delta for:

- Cut/fill-style review
- Earthworks monitoring
- Stockpile or terrain movement indication
- Elevation change screening

Important limits:

- Results depend on input quality and alignment.
- Use RTK/GCP-backed captures for serious measurement workflows.
- Treat volume outputs as review evidence unless validated against survey-grade methods.

## 17. 3D Model Review

Completed tasks can include a 3D model, point cloud, textured model, or related assets.

Workflow:

1. Open the task.
2. Open the 3D view.
3. Inspect model completeness and texture quality.
4. Use textured model QA to confirm whether key assets are present.
5. If sharing with a client, use a client share link rather than exposing internal project access.

If the model is missing, confirm that processing options generated the required model assets.

## 18. Stakeholder Reports

Reports summarize project progress and review evidence for non-technical stakeholders.

Workflow:

1. Open the project dashboard.
2. Click the project `Report` link.
3. Review task counts, latest deliverables, issues, and project metadata.
4. Use print/save PDF from the browser when a PDF handoff is needed.
5. Include caveats where AI, object detection, or monitoring deltas need human interpretation.

Commercial report templates are available through the project progress report API:

- `/api/projects/<project-id>/reports/progress?template=architecture_cad`
- `/api/projects/<project-id>/reports/progress?template=agriculture_field`
- `/api/projects/<project-id>/reports/progress?template=solar_inspection`

If no template is supplied, the report uses the project's commercial readiness package when one has been selected. Each commercial template adds client review focus, evidence counters, and package-specific caveats.

Client delivery bundles are available as ZIP exports:

```text
/api/projects/<project-id>/delivery/export?template=<template-key>
```

The bundle includes a manifest, progress report JSON, commercial readiness JSON, issue export, and available deliverable assets such as orthophoto, DSM, DTM, thermal orthophoto, design overlays, and field photos.

Delivery bundles also include `commercial_disclaimers.md` so client handoffs carry the standard caveats.

Reports are intended to be readable by clients and project managers without direct map tooling.

## 19. Client Sharing Portal

Client sharing gives external users tokenized access without creating WebODM user accounts.

Share roles:

- `viewer`: read-only access.
- `reviewer`: read-only access plus comments.

Recommended workflow:

1. Open the project.
2. Create a client share.
3. Choose a clear name, for example `Client Review - May 2026`.
4. Choose viewer or reviewer role.
5. Set an expiry date for commercial links.
6. Send the portal link through a trusted channel.
7. Disable the share after sign-off.

Security notes:

- Client share URLs are bearer tokens.
- Anyone with the URL can access that shared project view until the share is disabled or expired.
- Do not send share URLs through public channels.
- Prefer expiring shares for every commercial client handoff.

## 20. OneDrive Folder Intake

OneDrive intake creates import tasks from a synced folder.

Supported dataset layouts:

- A `.zip` file containing imagery.
- A folder containing at least two supported image files.

Browser workflow:

1. Open `/operations/`.
2. Select a project.
3. Enter the intake folder path.
4. Keep `Dry run only` enabled first.
5. Run intake.
6. Review ready datasets.
7. Disable dry run only when ready to create tasks.
8. Choose whether to start processing automatically.

Command workflow:

```bash
python manage.py onedriveintake --project <project-id> --folder <folder-path> --dry-run
python manage.py onedriveintake --project <project-id> --folder <folder-path>
```

Operational notes:

- Set `WO_ONEDRIVE_INTAKE_DIR` in production so intake paths are constrained to one mounted folder.
- The intake state file prevents duplicate task creation for the same dataset fingerprint.
- Use `--min-age` to avoid importing files that are still syncing.
- Use `--no-process` when you want to create tasks without starting workers.

## 21. Operations Page

Administrators can use `/operations/` for operational checks and intake workflows.

The Operations page includes:

- Platform audit summary.
- Protected file/route/service/model checks.
- OneDrive folder intake form.
- Dry-run support for intake.

If platform audit reports missing or error items, stop upgrades or client operations until the cause is understood.

## 22. Demo Projects

Administrators can create synthetic commercial demo projects for sales, onboarding, and internal training:

```bash
python manage.py createdemoprojects --owner <username>
```

The command creates or updates three projects:

- `Demo - Architecture CAD Orthomosaic`
- `Demo - Agriculture Field Analysis`
- `Demo - Solar Panel Inspection`

Each demo project includes synthetic task assets, a package-specific commercial readiness sign-off, a reviewer client share with an expiry date, and sample review evidence. Demo projects are not customer data and should be kept separate from paid client work.

## 23. Feature Validation Ledger

The feature validation ledger is available at `/feature-validations/`.

Use it to track whether the main workflows and commercial packages are:

- Untested
- Testing
- Tested
- Failing
- Blocked

Recommended use:

1. Run focused tests or smoke checks.
2. Mark the corresponding feature as tested.
3. Add evidence or maintenance notes.
4. Mark failing or blocked features immediately when regressions are found.

`reconcilefeaturevalidations` creates the P1-P14 pipeline records and the commercial records for architecture/CAD orthomosaic, agriculture field analysis, solar panel inspection, readiness checks, report templates, and demo project mode.

Administrators can reconcile the pipeline records:

```bash
python manage.py reconcilefeaturevalidations --tested --overwrite-notes --user <username>
```

Only use `--tested` after a real validation pass.

## 24. Production Readiness

Before paid pilots or production launch, administrators should run:

```bash
python manage.py productionreadiness
python manage.py securityreview
python manage.py platformaudit
```

The expected launch posture is:

- Zero production-readiness errors.
- Zero security-review errors.
- Zero platform-audit missing/error items.
- Backups configured and restore tested.
- HTTPS enabled.
- Stable `WO_SECRET_KEY` configured.
- `ALLOWED_HOSTS` and CORS restricted in production settings.
- Processing node online.
- Client shares reviewed for expiry.

See `PRODUCTION_HARDENING.md` and `SECURITY_REVIEW.md` for details.

## 25. API Token

Users can manage their API token at `/account/token/`.

Use API tokens for integrations that need authenticated API access.

Security guidance:

- Treat API tokens like passwords.
- Regenerate tokens if they are exposed.
- Do not paste tokens into screenshots, public tickets, or client reports.
- Use HTTPS for all token-based API calls.

Example header:

```text
Authorization: Token <your_api_key>
```

### AirTwin Integration

For an AirTwin service account, edit the project and select the **AirTwin
integration** permission role. Process surveys with the **AirTwin Export** preset.
The task list then shows whether AirTwin is pending, importing, imported, or failed.
Do not delete a task before it shows **AirTwin imported** unless the import is being
intentionally abandoned. See `AIRTWIN_INTEGRATION.md` for API, webhook, retry,
networking, geospatial, and retention setup.

## 26. Troubleshooting

### The Site Does Not Load

Check:

- Is the webapp container running?
- Is the configured port reachable?
- Is HTTPS configured correctly in production?
- Does `/api/status/` return a response?

Useful command:

```bash
docker compose ps
```

### Login Fails

Check:

- Username and password.
- Whether the account is active.
- Whether the browser is using the correct domain.
- HTTPS and cookie settings in production.

### Upload Fails

Check:

- File size and disk space.
- Dataset image format.
- Browser/network interruptions.
- Media volume write permissions.

### Processing Stays Queued

Check:

- At least one processing node is online.
- NodeODM container is running.
- Worker container is running.
- The task has not exceeded quota or failed before dispatch.

Useful commands:

```bash
docker logs --tail 200 worker
docker logs --tail 200 nodeodm
```

### Processing Fails

Check:

- Task console output.
- Image overlap and image count.
- Camera metadata.
- Available disk and memory.
- NodeODM logs.

Try a small known-good dataset to distinguish system problems from capture problems.

### Monitoring Compare Is Not Available

Check:

- Both tasks are completed.
- Both tasks belong to the same project.
- Both tasks have orthophotos.
- DSM/DTM delta needs DEM assets on both tasks.
- The timeline readiness panel explains missing assets.

### Client Link Does Not Work

Check:

- The share is enabled.
- The share has not expired.
- The token URL was copied correctly.
- The task or asset belongs to the shared project.

### OneDrive Intake Finds No Datasets

Check:

- The folder path is visible inside the webapp container.
- The folder contains zip files or child folders with at least two images.
- Files are older than the configured minimum age.
- `WO_ONEDRIVE_INTAKE_DIR` allows the selected path.
- The files are not still syncing.

## 27. Commercial Use Checklist

Before using the tool with a paying client:

- Confirm the selected offer matches `COMMERCIAL_PACKAGES.md`.
- Confirm the caveats in `COMMERCIAL_DISCLAIMERS.md` are acceptable for the client and contract.
- Open the project commercial readiness endpoint at `/api/projects/<project-id>/commercial/readiness`.
- Select the correct commercial package: `basic_orthomosaic`, `architecture_cad`, `agriculture_field`, or `solar_inspection`.
- Confirm the checklist has no `blocked` or `manual` items before client delivery.
- Run `productionreadiness`.
- Run `securityreview`.
- Run `platformaudit`.
- Confirm backup and restore.
- Confirm HTTPS.
- Confirm processing node capacity.
- Confirm project permissions.
- Confirm client shares have expiry dates.
- Confirm AI/object detection outputs are reviewed by a human.
- Confirm reports include appropriate measurement caveats.
- Confirm AGPL/source-code obligations are understood.

The commercial readiness checklist combines system checks and manual sign-off. System checks confirm required deliverables such as orthophotos, DSM/DTM assets, design overlays, expiring client shares, reports, and open issue status. Manual sign-off confirms deliverables, human review, report wording, client-share scope, and legal/commercial caveats.

## 28. Glossary

### AI-Assisted Issue Detection

Server-side workflow that uses configured OpenAI credentials to create reviewable issue candidates from project imagery.

### Client Portal

Tokenized external page for client review.

### Design Overlay

Project reference layer such as GeoJSON or zipped Shapefile plan data.

### Feature Validation Ledger

Staff-maintained record of feature status, evidence, and maintenance notes.

### Monitoring Compare

Workflow that compares two completed tasks and generates change review layers.

### NodeODM

Processing engine used by WebODM to run photogrammetry jobs.

### OneDrive Intake

Workflow that imports zipped datasets or folder datasets from a OneDrive-synced path.

### Platform Audit

Internal command/page that verifies protected custom fork surfaces still exist.

### Production Readiness

Deployment check for commercial operations, including HTTPS, backups, persistence, runtime state, and processing nodes.

### Security Review

Deployment and runtime security check covering settings, throttling, tokens, secrets, intake root policy, and client shares.

### Task

A single processing run within a project.
