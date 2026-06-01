# Commercial Orthomosaic Feature Package

This file defines the commercial orthomosaic package for this WebODM fork. It is written for sales, delivery, and QA so the product offer is explicit instead of scattered across presets, map tools, reports, and plugins.

Use `COMMERCIAL_PACKAGES.md` for package boundaries, quote inputs, inclusions, exclusions, and upgrade paths. Use `COMMERCIAL_DISCLAIMERS.md` for standard caveats and handoff wording.

The first three target customers are:

- Architects and construction teams comparing CAD/design intent against reality.
- Agriculture teams reviewing field condition and plant-health products.
- Solar operators inspecting panels, rows, and thermal follow-up evidence.

## Commercial Position

The orthomosaic package is the 2D evidence layer for paid work. A task produces the orthophoto, DEMs, exportable GeoTIFFs, tiles, reports, and map layers. Project workflows then add overlays, issues, monitoring comparisons, field photos, AI-assisted review, object detection, client sharing, and operational checks.

Do not sell the orthomosaic as a certification result by itself. Sell it as a decision-support deliverable that must be reviewed by a qualified human.

## Customer Packages

| Customer | System preset | Primary promise | Supporting product features |
| --- | --- | --- | --- |
| Architecture and construction | `Architecture CAD Orthomosaic` | Compare latest site reality against CAD/design overlays and track progress across visits. | Design overlays, monitoring timeline, orthophoto compare, DSM/DTM delta, issues, reports, client portal. |
| Agriculture | `Agriculture Field Analysis` | Produce field-scale orthomosaics and plant-health formula layers for scouting and operational review. | Radiometric calibration, NDVI/VARI formulas, formula export, DSM, field photos, issues, reports, client portal. |
| Solar inspection | `Solar Panel Inspection` | Produce high-detail site orthomosaics for panel/row review and issue mapping, with thermal follow-up when available. | High-resolution orthophoto, thermal orthophoto plugin, object detection path, AI-assisted issues, field photos, reports, client portal. |

## Preset Requirements

### Architecture CAD Orthomosaic

Required preset traits:

- High-quality feature matching for structured sites.
- High-resolution orthophoto output.
- DSM and DTM enabled for terrain/progress deltas.
- COG and overviews enabled for large-file delivery and responsive map review.

Use when the client cares about plan comparison, work progress, elevation deltas, or a stakeholder report.

### Agriculture Field Analysis

Required preset traits:

- Radiometric calibration for supported cameras.
- Planar field processing for broad nadir captures.
- DSM enabled for canopy/surface context.
- COG and overviews enabled for field-scale exports and map responsiveness.

Use with multispectral or RGB field captures. NDVI is available when the orthophoto bands support it; VARI is available for RGB-style plant-health review.

### Solar Panel Inspection

Required preset traits:

- High-detail feature matching for repeated panel rows and structured surfaces.
- High-resolution orthophoto output.
- DSM enabled for table/row context.
- Seam-leveling skip enabled to preserve thermal-friendly review behavior.
- COG and overviews enabled for large-site delivery.

Use this for RGB inspection tasks. For thermal work, process the RGB geometry first, then use the thermal orthophoto workflow when suitable thermal imagery is available.

## Feature Coverage Matrix

| Capability | Architecture | Agriculture | Solar | Status |
| --- | --- | --- | --- | --- |
| Orthophoto generation | Required | Required | Required | Present in the WebODM runtime pipeline. |
| High-resolution orthophoto preset | Required | Optional by field scale | Required | Present through commercial system presets. |
| COG / web overviews | Required | Required | Required | Present through preset options and task import COG handling. |
| Orthophoto export | Required | Required | Required | Present through map layer export APIs. |
| Plant-health formulas | Not primary | Required | Not primary | Present through NDVI, VARI, and related formula rendering/export. |
| Radiometric calibration | Optional | Required | Thermal-dependent | Present through multispectral/thermal options. |
| Thermal orthophoto | Optional | Optional | Required for thermal inspections | Present through the thermal orthophoto plugin. |
| CAD/design overlay comparison | Required | Optional | Optional | Present through project design overlays. |
| Repeated capture monitoring | Required | Useful | Useful | Present through monitoring timeline and compare. |
| DSM/DTM delta and cut/fill | Required when measuring change | Optional | Optional | Present when compared tasks both have DEM assets. |
| Issues and annotations | Required | Required | Required | Present through project issues and map annotations. |
| Field photos | Useful | Useful | Useful | Present through project field photos. |
| AI-assisted issue review | Optional | Optional | Useful | Present with server-side key configuration and human review. |
| Object detection workflow | Optional | Optional | Useful | Present through the existing object-detection path and issue promotion. |
| Stakeholder reports | Required | Useful | Required | Present through project progress reports. |
| Client portal | Required | Useful | Required | Present through tokenized viewer/reviewer links. |
| OneDrive intake | Useful for repeat visits | Useful for frequent fields | Useful for route-based inspections | Present through the Operations UI and management command. |
| Production readiness gate | Required | Required | Required | Present through `productionreadiness`. |
| Security review gate | Required | Required | Required | Present through `securityreview`. |
| Platform audit | Required | Required | Required | Present through `platformaudit`. |

## Architecture Workflow

1. Create one project per site or contract.
2. Upload the capture as a new task.
3. Select `Architecture CAD Orthomosaic`.
4. Process the task and confirm the orthophoto, DSM, and DTM are present.
5. Upload CAD/design exports as GeoJSON or zipped Shapefile overlays.
6. Review overlay alignment against the orthophoto.
7. For repeat visits, use monitoring compare against the prior task.
8. Convert important differences into issues.
9. Generate a stakeholder progress report.
10. Share a tokenized reviewer link with an expiry date.

Recommended report template: `/api/projects/<project-id>/reports/progress?template=architecture_cad&format=html`.

## Agriculture Workflow

1. Create one project per farm, field block, or customer site.
2. Upload one clean capture date per task.
3. Select `Agriculture Field Analysis`.
4. Process the task and inspect the orthophoto.
5. Use plant-health formulas where bands support the formula.
6. Export formula layers when the customer needs GIS deliverables.
7. Attach field photos where ground truth is available.
8. Create issues for scouting zones, crop stress, or follow-up actions.
9. Generate a report that includes caveats about sensor bands, calibration, and weather.

Recommended report template: `/api/projects/<project-id>/reports/progress?template=agriculture_field&format=html`.

## Solar Workflow

1. Create one project per plant or inspection contract.
2. Upload RGB imagery as the primary geometry task.
3. Select `Solar Panel Inspection`.
4. Process and verify the high-detail orthophoto.
5. Use the thermal workflow when thermal imagery exists and the RGB orthophoto is available.
6. Map panel or row issues as project issues.
7. Use AI-assisted review or object detection only as triage, then confirm manually.
8. Add field photos for close-up evidence.
9. Produce a stakeholder report and share a reviewer link with an expiry date.

Recommended report template: `/api/projects/<project-id>/reports/progress?template=solar_inspection&format=html`.

## Acceptance Checks Before Selling

Run these checks before a commercial pilot:

- `python manage.py platformaudit`
- `python manage.py productionreadiness`
- `python manage.py securityreview`
- `/api/projects/<project-id>/commercial/readiness`
- `/api/projects/<project-id>/delivery/export?template=<template-key>`
- `python manage.py createdemoprojects --owner <username>` when a clean sales or onboarding demo is needed.
- Process one representative dataset for each customer type.
- Confirm each new commercial preset appears in the task preset picker.
- Confirm exports open in the customer's GIS/CAD workflow where relevant.
- Confirm client links expire and do not expose internal admin tooling.
- Confirm reports include measurement and inspection caveats.

## Current Limitations

- CAD/BIM comparison depends on the customer supplying georeferenced overlay exports such as GeoJSON or zipped Shapefile; native DWG/RVT ingestion is not part of this package.
- Agriculture formulas depend on sensor bands and calibration quality. RGB-only captures should be positioned as visual/VARI-style scouting, not full multispectral agronomy.
- Solar thermal inspection depends on suitable thermal imagery, capture discipline, and human confirmation. The tool can organize and visualize evidence, but it is not an autonomous electrical certification system.
- Monitoring compare requires completed orthophotos from the same project and works best when repeat flights use consistent altitude, overlap, and coverage.
