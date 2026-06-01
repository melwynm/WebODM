# Commercial Packages

This document defines the initial sellable packages for this WebODM fork. It is an internal sales and delivery reference, not a public price list. Add local currency, margins, travel, capture costs, and support terms before sending quotes to clients. Use `COMMERCIAL_DISCLAIMERS.md` for standard caveats and handoff wording.

## Package Summary

| Package | Best For | Core Deliverables | Delivery Gate |
| --- | --- | --- | --- |
| Basic Orthomosaic | Simple site mapping and visual evidence | Orthophoto, standard report, issue notes when needed, expiring client share | `basic_orthomosaic` commercial readiness package |
| Construction Progress | Architects, contractors, project managers | High-resolution orthomosaic, CAD/design overlay review, DSM/DTM when available, progress/issues report, delivery bundle | `architecture_cad` commercial readiness package |
| Agriculture Field Analysis | Farms, agronomists, field managers | Field orthomosaic, plant-health formula review when supported, DSM context, scouting issues, report, delivery bundle | `agriculture_field` commercial readiness package |
| Solar Inspection | Solar farm owners/operators and maintenance teams | High-detail orthomosaic, panel/row issue map, thermal follow-up when available, field evidence, report, delivery bundle | `solar_inspection` commercial readiness package |

## Basic Orthomosaic

### Included

- One completed orthomosaic task.
- Orthophoto review and export.
- Standard stakeholder progress report.
- Expiring viewer or reviewer client share.
- Delivery ZIP bundle when client handoff is required.

### Excluded

- CAD/design comparison.
- Plant-health interpretation.
- Thermal inspection.
- Survey certification.
- Legal, engineering, electrical, or agronomy certification.

### Required Before Delivery

- Completed task with `orthophoto.tif`.
- No queued/running delivery-scope tasks.
- No unresolved delivery-blocking issues.
- Commercial readiness sign-off.
- Expiring client share.

## Construction Progress

### Included

- `Architecture CAD Orthomosaic` processing preset.
- High-resolution orthomosaic review.
- CAD/design overlay comparison using GeoJSON or zipped Shapefile overlays.
- DSM/DTM availability check for terrain/surface deltas.
- Progress/change issues and annotations.
- Construction report template.
- Delivery ZIP bundle.

### Excluded

- Native DWG/RVT ingestion.
- Contract certification or quantity-surveyor sign-off.
- Guaranteed survey-grade accuracy without proper RTK/GCP control.
- Manual drafting or BIM authoring unless quoted separately.

### Required Before Delivery

- Completed orthomosaic task with `orthophoto.tif`, `dsm.tif`, and `dtm.tif`.
- At least one georeferenced design overlay when CAD comparison is sold.
- Human review of overlay alignment.
- Report and legal caveat review.
- Expiring client share.

## Agriculture Field Analysis

### Included

- `Agriculture Field Analysis` processing preset.
- Field orthomosaic review.
- Plant-health formula review when sensor bands support it.
- DSM context when available.
- Field photos and scouting issues.
- Agriculture report template.
- Delivery ZIP bundle.

### Excluded

- Yield guarantees.
- Crop prescription maps unless separately specified.
- Agronomy certification.
- Multispectral claims from RGB-only imagery.
- Field sampling or lab analysis.

### Required Before Delivery

- Completed orthomosaic task with `orthophoto.tif`.
- DSM when sold as part of field context.
- Sensor band and calibration caveats in the report.
- Human review of plant-health outputs.
- Expiring client share.

## Solar Inspection

### Included

- `Solar Panel Inspection` processing preset.
- High-detail orthomosaic review.
- Panel/row issue mapping.
- Thermal orthophoto follow-up when suitable thermal imagery exists.
- Field photos for close-up evidence.
- Solar report template.
- Delivery ZIP bundle.

### Excluded

- Electrical certification.
- Guaranteed fault classification without qualified review.
- Thermal conclusions from unsuitable capture conditions.
- Panel serial-number inventory unless separately specified.
- Repair dispatch or maintenance management.

### Required Before Delivery

- Completed orthomosaic task with `orthophoto.tif`.
- DSM when sold as row/table context.
- Human-confirmed issue review.
- Thermal caveats when thermal imagery is used.
- Expiring client share.

## Pricing Inputs

Use these inputs to build local prices:

- Flight/capture time.
- Travel and site access cost.
- Processing time and compute cost.
- Manual review time.
- Report preparation time.
- Number of repeat visits.
- Delivery bundle/GIS export needs.
- Support and revision allowance.
- Liability and professional review requirements.

## Standard Quote Language

Use plain package names in quotes:

- Basic Orthomosaic
- Construction Progress
- Agriculture Field Analysis
- Solar Inspection

Avoid promising autonomous certification. Phrase outputs as map evidence, decision support, review-ready findings, or human-reviewed inspection evidence.

## Upgrade Paths

- Basic Orthomosaic -> Construction Progress when CAD/design overlay comparison is required.
- Basic Orthomosaic -> Agriculture Field Analysis when field health review or agronomy-facing reporting is required.
- Basic Orthomosaic -> Solar Inspection when panel/row issue mapping or thermal follow-up is required.
- Any package -> recurring monitoring when repeat captures are part of the contract.

## Delivery Checklist

Before invoicing or client handoff:

- Run the project commercial readiness endpoint.
- Generate the customer-specific report.
- Export the delivery bundle.
- Confirm client share expiry.
- Confirm caveats are visible.
- Record feature validation evidence when testing a new package or representative dataset.
