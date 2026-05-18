# Priority Pipeline

Last updated: 2026-05-18

This file is the single source of truth for the project pipeline in this fork.
It combines:

- the runtime WebODM processing foundation
- the fork's monitoring and progress workflow roadmap

When someone asks for "the pipeline", "the next item", or "what comes next", use this file.
The next item is the first stage marked `Next` in the priority roadmap.

## Current Next Item

P6 - Core Platform Hardening

P1 through P5 now have working slices. The next priority is core platform hardening so the custom fork features stay modular, testable, and easier to maintain across WebODM upgrades.

## Priority Roadmap

| Priority | Stage | Type | Status | Why it matters |
| --- | --- | --- | --- | --- |
| P1 | Mobile/Field Photo Capture | Workflow | Working | Adds field context by attaching ground photos or 360 photos to map locations. |
| P2 | AI-Assisted Issue Detection | Workflow | Working | Turns imagery and change products into reviewable project issues. |
| P3 | Client Sharing Portal | Workflow | Working | Gives clients polished read-only access, comments, roles, and shareable review links. |
| P4 | Textured Model QA + Sharing | Workflow | Working | Adds textured-model readiness checks and tokenized client 3D review access. |
| P5 | Feature Validation Ledger | Platform | Working | Creates the system memory for what has been tested, what is failing, and what evidence supports maintenance decisions. |
| P6 | Core Platform Hardening | Platform | Next | Keeps custom fork features modular, testable, and easier to maintain across WebODM upgrades. |
| P7 | Monitoring Compare MVP | Workflow | Planned | Protects the core progress-monitoring experience: compare orthophotos, auto-align, and generate change outputs. |
| P8 | Project Timeline Monitoring | Workflow | Planned | Makes multi-date project review easier through timeline selection, compare launch, and cache invalidation. |
| P9 | DSM/DTM Delta and Cut/Fill | Workflow | Planned | Extends progress review from imagery into measurable terrain and volume change products. |
| P10 | Change Issues and Annotations | Workflow | Planned | Turns detected differences into traceable issues, annotations, assignments, and review outcomes. |
| P11 | Advanced Alignment | Workflow | Planned | Improves comparison reliability when translation-only alignment is not enough. |
| P12 | Stakeholder Reports | Workflow | Planned | Packages progress, QA, and change evidence into reports that non-technical stakeholders can review. |
| P13 | Design/BIM/Plan Overlays | Workflow | Planned | Lets project teams compare reality against design, BIM, or plan references directly on the 2D map. |
| P14 | OneDrive Folder Task Intake | Workflow | Planned | Streamlines repeated task creation from a configured OneDrive-synced folder. |

## Working Product Foundation

These workflow and platform capabilities are already available and should be protected while building the next priorities.

| Priority | Stage | Type | Status | Notes |
| --- | --- | --- | --- | --- |
| P5 | Feature Validation Ledger | Platform | Working | Track feature test status, evidence, maintenance notes, status-change logs, and staff browser review for future QA. |
| P6 | Core Platform Hardening | Platform | Working | Keep core modules thin, modular, testable, and upgrade-friendly. |
| P7 | Monitoring Compare MVP | Workflow | Working | Compare orthophotos in single-task view with translational auto-alignment, overlay output, and change heatmap output. |
| P8 | Project Timeline Monitoring | Workflow | Working | Project-level timeline selection, timeline-driven compare launch, and regenerated comparison cache invalidation. |
| P9 | DSM/DTM Delta and Cut/Fill | Workflow | Working | Terrain change products beyond orthophoto-only comparison. |
| P10 | Change Issues and Annotations | Workflow | Working | Promote detected changes into trackable issues and annotations with status. |
| P11 | Advanced Alignment | Workflow | Working | Conservative rotation and scale correction when translation-only alignment confidence is weak. |
| P12 | Stakeholder Reports | Workflow | Working | Export project progress as stakeholder-friendly web reports with print-to-PDF support. |
| P13 | Design/BIM/Plan Overlays | Workflow | Working | Store project design overlays and render supported GeoJSON/Shapefile references on 2D maps. |
| P14 | OneDrive Folder Task Intake | Workflow | Working | Create import tasks from a configured OneDrive-synced folder via the `onedriveintake` management command. |

## Runtime Processing Foundation

These are the standard WebODM processing stages. They remain the working runtime baseline, not the priority roadmap.

| Runtime Order | Stage | Type | Status | Notes |
| --- | --- | --- | --- | --- |
| 1 | Load Dataset | Runtime | Working | Ingest imagery and validate the input set. |
| 2 | Structure From Motion | Runtime | Working | Solve camera poses and sparse reconstruction. |
| 3 | Multi View Stereo | Runtime | Working | Build dense depth information. |
| 4 | Point Filtering | Runtime | Working | Clean and refine the point cloud. |
| 5 | Meshing | Runtime | Working | Generate the surface mesh. |
| 6 | Texturing | Runtime | Working | Apply imagery to 3D geometry. |
| 7 | Georeferencing | Runtime | Working | Align outputs to spatial coordinates. |
| 8 | DEM | Runtime | Working | Produce elevation products. |
| 9 | Orthophoto | Runtime | Working | Produce the orthomosaic. |
| 10 | Report | Runtime | Working | Generate the standard processing report. |
| 11 | Postprocess | Runtime | Working | Finalize assets and derived outputs. |

## Interpretation Rules

- `P1` is delivered and should remain stable.
- `P2` is delivered and should remain stable.
- `P3` is delivered as a first working portal slice and should remain stable.
- `P4` is delivered as a first textured-model QA and tokenized sharing slice and should remain stable.
- `P5` is delivered and should remain stable as the feature validation and maintenance evidence ledger.
- `P6` is the immediate next priority and should focus on modularity, testability, upgrade safety, and reducing fragile custom code.
- `P7` through `P14` are ordered follow-up priorities; each already has a working foundation, but should be revisited in this order for hardening, QA, and product polish.
- Use the feature validation ledger at `/feature-validations/` to mark completed features as `tested`, `untested`, `failing`, or `blocked` after every smoke test or regression pass.
- `Working` means the stage is available in the fork today.
- `Next` means this is the immediate next delivery target.
- `Planned` means the stage is queued after the current next item.

## Notes

- `app/static/app/js/classes/PipelineSteps.js` remains the UI-facing runtime subset only.
- `DEVELOPMENT_STATUS.md` remains the change log and implementation-status companion document.
- 2026-05-18 map review feedback pass improved project map control readability, map-type icon visibility, title contrast, and layer panel height behavior.
- 2026-05-18 shell navigation pass modernized the left menu and moved authenticated user actions to a bottom-left sidebar account card.
- 2026-05-18 backlog grooming assigned explicit P1-P14 priority order to all product and platform pipeline items.
- 2026-05-18 P5 delivered feature validation coverage metrics, attention filters, API attention fields, and staff dashboard signals for untested, failing, and blocked workflows.
