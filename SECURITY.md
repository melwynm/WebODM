# Security Policy

## Commercial Security Gate

Before exposing a client-facing deployment, run:

```bash
python manage.py securityreview
python manage.py productionreadiness
python manage.py platformaudit
```

See `SECURITY_REVIEW.md` for the commercial review checklist and required deployment posture.

## Reporting a Vulnerability

If you've found a vulnerability AND you have a proof of exploitation (either theoretical or practical) you can contact https://uav4geo.com/contact to report it.

Please DO NOT contact us if one of our dependencies has a newly reported CVE! Having a CVE does not always mean a vulnerability is exploitable. Only contact us if you have a proof of exploitation in WebODM!
 
