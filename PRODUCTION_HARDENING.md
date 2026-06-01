# Production Hardening

This runbook is the minimum operating baseline before selling hosted access or running a paid client pilot.

## Readiness Gate

Run this before launch and after every upgrade:

```powershell
docker exec webapp python manage.py productionreadiness
docker exec webapp python manage.py securityreview
docker exec webapp python manage.py platformaudit
```

For CI or scripts:

```powershell
docker exec webapp python manage.py productionreadiness --json
```

Do not launch commercially while `productionreadiness` reports errors. Warnings can be accepted only when they are deliberate and documented for that deployment.

## Compose Baseline

Use the production overlay with the normal WebODM compose files:

```powershell
docker compose -f docker-compose.yml -f docker-compose.nodeodm.yml -f docker-compose.ssl.yml -f docker-compose.production.yml up -d
```

For manually supplied certificates, use `docker-compose.ssl-manual.yml` instead of `docker-compose.ssl.yml`.

The production overlay adds container health checks and log rotation. It does not replace host monitoring; keep external uptime checks for `https://<host>/api/status/`.

## Environment

Start from [.env.production.example](.env.production.example). The production `.env` must set:

- `WO_DEBUG=NO`
- `WO_SSL=YES` or equivalent secure-cookie settings behind a trusted HTTPS proxy
- `WO_SECRET_KEY` with a stable long random value
- `WO_MEDIA_DIR`, `WO_DB_DIR`, and `WO_BACKUP_DIR` pointing to durable storage
- `WO_BACKUP_RETENTION_DAYS` of at least `7`
- `WO_API_ANON_THROTTLE_RATE` and `WO_API_USER_THROTTLE_RATE` tuned for expected client traffic
- `WO_ONEDRIVE_INTAKE_DIR` pointing to a dedicated mounted intake folder if OneDrive intake is used

Use `WO_SETTINGS` for production-only Django settings. At minimum, restrict:

```python
ALLOWED_HOSTS = ["webodm.example.com"]
CORS_ORIGIN_ALLOW_ALL = False
CORS_ALLOWED_ORIGINS = ["https://webodm.example.com"]
CSRF_TRUSTED_ORIGINS = ["https://webodm.example.com"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

## Backup

Create a database and media backup before upgrades and at least daily:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = "C:\webodm-backups"
New-Item -ItemType Directory -Force -Path $backupDir

docker exec db pg_dump -U postgres -d webodm_dev -Fc -f /tmp/webodm-$stamp.dump
docker cp db:/tmp/webodm-$stamp.dump "$backupDir\webodm-$stamp.dump"
docker exec db rm -f /tmp/webodm-$stamp.dump

docker exec webapp tar -C /webodm/app -czf /tmp/webodm-media-$stamp.tgz media
docker cp webapp:/tmp/webodm-media-$stamp.tgz "$backupDir\webodm-media-$stamp.tgz"
docker exec webapp rm -f /tmp/webodm-media-$stamp.tgz
```

Keep backups off the application disk as soon as practical.

## Restore Drill

Run a restore drill on a non-production host before the first paid client:

```powershell
docker compose down
docker compose up -d db

docker cp C:\webodm-backups\webodm-YYYYMMDD-HHMMSS.dump db:/tmp/restore.dump
docker exec db pg_restore -U postgres -d webodm_dev --clean --if-exists /tmp/restore.dump
docker exec db rm -f /tmp/restore.dump

docker compose up -d webapp worker yamlnodeodm
docker cp C:\webodm-backups\webodm-media-YYYYMMDD-HHMMSS.tgz webapp:/tmp/restore-media.tgz
docker exec webapp tar -C /webodm/app -xzf /tmp/restore-media.tgz
docker exec webapp rm -f /tmp/restore-media.tgz

docker exec webapp python manage.py productionreadiness
```

Confirm that login, project listing, map tiles, 3D assets, reports, OneDrive intake dry-run, and one small processing task work after restore.

## Monitoring

Minimum commercial monitoring:

- HTTPS uptime check against `/api/status/`
- Docker health status for `webapp`, `worker`, `db`, `broker`, and `nodeodm`
- Disk free alerts for media, database, and backup paths
- Backup age alert if the last successful backup is older than 24 hours
- Error log review after each upgrade and after failed tasks

Useful commands:

```powershell
docker compose ps
docker stats --no-stream
docker logs --tail 200 webapp
docker logs --tail 200 worker
docker logs --tail 200 nodeodm
```

## Launch Checklist

- `productionreadiness` passes with zero errors
- `securityreview` passes with zero errors
- `platformaudit` passes
- A backup has been created and restored on a non-production host
- HTTPS certificate renewals are confirmed
- At least one processing node is online
- Feature validation ledger shows P1-P14 tested after smoke/regression checks
- Client terms, privacy policy, AGPL source-offer process, and support path are ready
