# Security Review

This is the commercial security gate for this WebODM fork. Run it before paid pilots, after upgrades, and before exposing a new public hostname.

## Command

```powershell
docker exec webapp python manage.py securityreview
```

For automation:

```powershell
docker exec webapp python manage.py securityreview --json
```

The command checks:

- HTTPS cookie posture, `DEBUG`, `ALLOWED_HOSTS`, and CORS
- DRF anonymous and authenticated API throttling
- client-share token shape and API token entropy
- accidental OpenAI key references in frontend/template source
- OneDrive intake root policy
- active client shares without expiry
- expired shares still enabled
- stored API token shape
- default test accounts in non-test databases

Warnings can be accepted only when they are documented for the deployment. Errors block commercial launch.

## Production Settings

Use `WO_SETTINGS` to keep deployment-specific security settings outside the repository:

```python
ALLOWED_HOSTS = ["webodm.example.com"]
CORS_ORIGIN_ALLOW_ALL = False
CORS_ALLOWED_ORIGINS = ["https://webodm.example.com"]
CSRF_TRUSTED_ORIGINS = ["https://webodm.example.com"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

The base settings include generous API throttles. Tune these per deployment:

```text
WO_API_ANON_THROTTLE_RATE=120/min
WO_API_USER_THROTTLE_RATE=1200/min
```

## Client Shares

Client share URLs are bearer tokens. Treat them like credentials:

- Set `expires_at` on commercial review links.
- Disable shares after client sign-off.
- Use reviewer links only when comments are needed.
- Do not send share URLs through public channels.

## OneDrive Intake

Set `WO_ONEDRIVE_INTAKE_DIR` to a single mounted intake folder. When this variable is set, the intake service rejects folders outside that root.

```text
WO_ONEDRIVE_INTAKE_DIR=/srv/webodm/onedrive-intake
```

Keep the mounted folder dedicated to drone intake. Do not point it at a user home directory or broad company sync root.

## OpenAI Key

The OpenAI key must remain server-side. Configure it in the WebODM Settings record or via `OPENAI_API_KEY`; never put it in templates, frontend bundles, screenshots, client portals, or exported reports.

AI-assisted issue detection should be sold as review assistance, not authoritative inspection.

## Launch Gate

Before a client-facing deployment:

```powershell
docker exec webapp python manage.py securityreview
docker exec webapp python manage.py productionreadiness
docker exec webapp python manage.py platformaudit
```

All three commands should complete with zero errors.
