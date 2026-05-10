# Architecture

Last updated: 2026-05-10

This fork should stay easy to upgrade by keeping the WebODM core thin and by placing new workflow behavior behind explicit module boundaries.

## Layer Responsibilities

### Models

Models define data shape, relationships, validation that must always hold, and small object-level helpers.

Models should not:

- call external services
- render responses
- run long image/raster/vector workflows
- know about HTTP request objects
- orchestrate Celery jobs

### API Views

API views should authenticate, authorize, validate request data, call services, and serialize responses.

API views should not:

- contain business workflows
- generate report bodies
- manipulate large files directly unless they are streaming a service output
- duplicate permission rules

### Services

Services live under `app/services/` or a feature-specific service package. They own workflow/business behavior.

Use services for:

- report building
- monitoring product generation
- task import/export workflows
- issue creation rules
- integration orchestration

Services should be callable from API views, management commands, and Celery tasks.

### Worker Tasks

Celery tasks should be thin wrappers:

1. load inputs
2. call one service
3. report progress
4. return a serializable result

Worker tasks should not contain the core business logic they execute.

### Frontend

Frontend modules should call stable API contracts. Repeated UI patterns should become shared components, not copied JSX fragments.

## Current Core Hotspots

These files are powerful but too broad and should be progressively split:

- `app/services/monitoring/`: monitoring is split by responsibility, but the raster-heavy services still need focused tests as new behavior is added
- `app/models/task.py`: task persistence, file paths, image processing helpers, asset management, and processing orchestration
- `app/api/tasks.py`: task serializers, task mutation APIs, imports, downloads, exports, and helper functions
- `worker/tasks.py`: periodic tasks, processing orchestration, monitoring compare, and export jobs

## Target Feature Shape

New workflow features should follow this shape:

```text
app/
  api/<feature>.py
  services/<feature>.py
  tests/test_api_<feature>.py
  tests/test_<feature>_services.py
```

If a feature becomes large, graduate it to:

```text
app/<feature>/
  services.py
  selectors.py
  payloads.py
  tests.py
```

Avoid creating hidden cross-feature dependencies. If two features need the same helper, promote it to a shared service or utility with tests.

## Update Confidence Rules

Before adding a large feature:

- identify the owning module
- define the API contract
- add focused service tests
- add permission tests
- keep the API view thin
- update `PIPELINE.md` only after the implementation status changes

Before upgrading upstream WebODM:

- run the core smoke tests
- run focused tests for changed modules
- inspect conflicts in files listed under Current Core Hotspots
- avoid carrying local workflow code inside upstream-heavy files when a service can own it
