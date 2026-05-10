# Module Boundaries

Last updated: 2026-05-10

This file defines practical boundaries for new development.

## Import Direction

Prefer this direction:

```text
api -> services -> models/utilities
worker -> services -> models/utilities
management commands -> services -> models/utilities
frontend -> api
```

Avoid this direction:

```text
models -> api
models -> worker
services -> api views
services -> HTTP request objects
worker -> API views
```

## Permissions

Project-scoped APIs should use `ProjectPermissionPolicy` from `app/api/permissions.py`.

Do not duplicate project access checks inline unless there is a documented exception.

## Services

Services must not depend on Django REST Framework request/response objects. They may use Django models and settings.

Good service input examples:

- a `Project`
- a `Task`
- a plain dictionary of validated options
- a file path

Bad service input examples:

- a DRF `Request`
- a serializer instance
- a viewset instance

## Monitoring

Monitoring implementation lives in focused services:

- `app/services/monitoring/alignment.py`: alignment estimation and preview matching
- `app/services/monitoring/cache.py`: cache paths, input fingerprints, metadata loading, and invalidation
- `app/services/monitoring/overlays.py`: aligned overlays, change heatmaps, and terrain delta rasters
- `app/services/monitoring/payloads.py`: API layer payload and tile URL construction
- `app/services/monitoring/products.py`: orchestration for generating a comparison product set
- `app/services/monitoring/common.py`: shared raster helpers, constants, transforms, and errors

Do not recreate an `app/monitoring.py` facade. Runtime callers should import the service package or the specific owning service module.

## Reports

Report construction belongs in `app/services/project_reports.py`. API views should only select format and return JSON or HTML.

## Tests

Every module should have:

- service tests for business behavior
- API tests for permissions and response contracts
- a small number of end-to-end tests for integration confidence

Heavy raster or worker tests should be targeted and serial. Do not rely on broad suites that hide the slow or flaky case.
