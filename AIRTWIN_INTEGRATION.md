# AirTwin Integration Guide

This integration lets AirTwin pull completed WebODM survey assets with a dedicated,
least-privilege API account. WebODM can also emit an optional signed completion
webhook after a task finishes successfully.

## Integration Account

1. As a WebODM administrator, create a normal user dedicated to AirTwin. Do not
   make it staff or a superuser and do not make it the project owner.
2. Open each project AirTwin may import and grant that user only the project view
   permission. Do not grant add, change, or delete permissions.
3. Sign in as the integration user and open **Account > API Token**, or visit
   `/account/token/`. Reveal the persistent API key once and store it in AirTwin's
   secret manager.
4. Authenticate every AirTwin request with:

   ```http
   Authorization: Token <api-key>
   ```

Do not store the API key, username, password, JWT, or webhook secret in this
repository. JWT access tokens expire and are not suitable for the long-running
integration. Regenerating the API key immediately invalidates the previous key.

## Container Networking

The base `docker-compose.yml` remains a standalone configuration. For a shared
production network, create the external network once and add the optional overlay:

```bash
docker network create airtwin
docker compose -f docker-compose.yml -f docker-compose.nodeodm.yml \
  -f docker-compose.airtwin.yml up -d
```

Attach the AirTwin service to the same external `airtwin` network. AirTwin can then
reach WebODM at `http://webodm:8000`; no production dependency on
`host.docker.internal` is required. Set `AIRTWIN_DOCKER_NETWORK` when the external
network has another name.

## Processing Preset

Select the system preset **AirTwin Export** when creating a task. With the installed
ODM 3.5.6 node it enables these supported options:

- `gltf=true` for `textured_model.glb`
- `dsm=true` for `dsm.tif`
- `dtm=true` for `dtm.tif`
- `3d-tiles=true` for native model and point-cloud OGC 3D Tiles archives

ODM normally also produces `orthophoto.tif`, `shots.geojson`, `report.pdf`, and
`georeferenced_model.laz`; the preset does not enable the corresponding `skip-*`
options. If a future processing node does not advertise `3d-tiles`, use the GLB as
the portable 3D fallback and remove that unsupported option from a copied preset.

Use the recommended task name `<site name> - <survey date>`, for example
`Port Louis Warehouse - 2026-06-22`. Other task names remain valid but receive a
manifest warning.

## Manifest And Assets

AirTwin can retrieve a normalized versioned manifest:

```bash
curl -H "Authorization: Token $WEBODM_API_KEY" \
  http://webodm:8000/api/projects/7/tasks/TASK_UUID/airtwin/manifest
```

The manifest includes project and task identifiers, status, EPSG, timestamps,
supported assets and download URLs, optional site/survey metadata, retention dates,
and readiness warnings. Existing API routes remain authoritative and compatible:

```bash
curl -H "Authorization: Token $WEBODM_API_KEY" \
  http://webodm:8000/api/projects/7/tasks/TASK_UUID/

curl -OJ -H "Authorization: Token $WEBODM_API_KEY" \
  http://webodm:8000/api/projects/7/tasks/TASK_UUID/download/textured_model.glb
```

## Geospatial Requirements

The manifest marks a task ready only when it has a valid EPSG code, successful GPS
or GCP georeferencing evidence, valid WGS84 longitude/latitude coordinates in
`shots.geojson`, and all required AirTwin assets. It warns when camera GPS is the
only georeferencing source. For survey-grade work, use surveyed GCPs in the correct
source CRS and verify the processing report before import.

WebODM does not reproject or rewrite exports for AirTwin. GeoTIFF, DSM, DTM, LAZ,
GLB, and 3D Tiles files are delivered unchanged, preserving the CRS metadata emitted
by ODM. Camera and GCP GeoJSON coordinates are validated as WGS84 longitude/latitude.

## Completion Webhook

Configure these variables in the deployment environment, never in a committed file:

```dotenv
AIRTWIN_WEBHOOK_ENABLED=YES
AIRTWIN_WEBHOOK_URL=http://airtwin:8080/api/integrations/webodm/events
AIRTWIN_WEBHOOK_SECRET=<generated-secret>
AIRTWIN_WEBHOOK_TIMEOUT_SECONDS=10
AIRTWIN_WEBHOOK_MAX_RETRIES=5
AIRTWIN_WEBHOOK_RETRY_BASE_SECONDS=5
AIRTWIN_OUTPUT_RETENTION_DAYS=30
```

The webhook is emitted only after successful completion. Requests contain JSON and:

```text
X-AirTwin-Timestamp: <unix-seconds>
X-AirTwin-Event-Id: <stable-uuid>
X-AirTwin-Signature: sha256=<hex-digest>
```

Verify the signature over the exact request body bytes using:

```text
HMAC-SHA256(secret, timestamp + "." + event_id + "." + body)
```

Store processed event IDs in AirTwin and treat duplicates as successful no-ops.
WebODM retries network errors, HTTP 408, HTTP 429, and 5xx responses with bounded
exponential backoff. Other 4xx responses are permanent failures. Delivery attempts,
HTTP status, and sanitized errors are recorded in Django admin; credentials are
never included in webhook payloads or error records. Webhook failure cannot change
the completed WebODM task status.

## Output Retention

`AIRTWIN_OUTPUT_RETENTION_DAYS` defaults to 30 and is published in the manifest as
an operational retention target. This integration never deletes outputs. Keep task
owners off restrictive quota cleanup, retain completed task media until AirTwin has
confirmed import, and include WebODM media in normal backups. Any later automated
deletion policy must independently check AirTwin import confirmation.

## Troubleshooting

- **401/403 or 404:** confirm the `Token` authentication scheme, current API key,
  and that the integration user has `view_project` on that specific project. WebODM
  intentionally returns 404 for inaccessible project objects.
- **Missing asset:** confirm the task used **AirTwin Export**, completed successfully,
  and lists the asset in the normal task-detail API. Reprocess old tasks when needed.
- **Invalid coordinates or missing CRS:** inspect `shots.geojson`, the task EPSG, the
  report, camera EXIF GPS, and uploaded GCP file. Coordinates must be longitude then
  latitude in WGS84.
- **No webhook:** confirm both web and worker containers received the variables, the
  Celery worker is online, the shared network resolves the AirTwin hostname, and the
  delivery record in Django admin shows the latest sanitized error.
- **Signature mismatch:** verify against the raw body bytes before JSON parsing and
  use the timestamp and event ID header values exactly as received.
