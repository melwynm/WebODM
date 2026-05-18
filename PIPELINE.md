# Priority Pipeline

Last updated: 2026-05-18

This file is the single source of truth for the project pipeline in this fork.
It combines:

- the runtime WebODM processing foundation
- the fork's monitoring and progress workflow roadmap

When someone asks for "the pipeline", "the next item", or "what comes next", use this file.
The next item is the first stage marked `Next` in the priority roadmap.

## Current Next Item

Backlog grooming / next priority selection

P1 through P4 now have working slices. The feature validation ledger is available to record whether each workflow has been tested, is untested, is failing, or is blocked.

## Priority Roadmap

| Priority | Stage | Type | Status | Why it matters |
| --- | --- | --- | --- | --- |
| P1 | Mobile/Field Photo Capture | Workflow | Working | Adds field context by attaching ground photos or 360 photos to map locations. |
| P2 | AI-Assisted Issue Detection | Workflow | Working | Turns imagery and change products into reviewable project issues. |
| P3 | Client Sharing Portal | Workflow | Working | Gives clients polished read-only access, comments, roles, and shareable review links. |
| P4 | Textured Model QA + Sharing | Workflow | Working | Adds textured-model readiness checks and tokenized client 3D review access. |

## Working Product Foundation

These workflow and platform capabilities are already available and should be protected while building the next priorities.

| Priority Role | Stage | Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Foundation | Monitoring Compare MVP | Workflow | Working | Compare orthophotos in single-task view with translational auto-alignment, overlay output, and change heatmap output. |
| Foundation | Project Timeline Monitoring | Workflow | Working | Project-level timeline selection, timeline-driven compare launch, and regenerated comparison cache invalidation. |
| Foundation | DSM/DTM Delta and Cut/Fill | Workflow | Working | Terrain change products beyond orthophoto-only comparison. |
| Foundation | Change Issues and Annotations | Workflow | Working | Promote detected changes into trackable issues and annotations with status. |
| Foundation | Advanced Alignment | Workflow | Working | Conservative rotation and scale correction when translation-only alignment confidence is weak. |
| Foundation | Stakeholder Reports | Workflow | Working | Export project progress as stakeholder-friendly web reports with print-to-PDF support. |
| Foundation | OneDrive Folder Task Intake | Workflow | Working | Create import tasks from a configured OneDrive-synced folder via the `onedriveintake` management command. |
| Foundation | Core Platform Hardening | Platform | Working | Keep core modules thin, modular, testable, and upgrade-friendly. |
| Foundation | Design/BIM/Plan Overlays | Workflow | Working | Store project design overlays and render supported GeoJSON/Shapefile references on 2D maps. |
| Foundation | Feature Validation Ledger | Platform | Working | Track feature test status, evidence, maintenance notes, status-change logs, and staff browser review for future QA. |

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
- Use the feature validation ledger at `/feature-validations/` to mark completed features as `tested`, `untested`, `failing`, or `blocked` after every smoke test or regression pass.
- `Foundation` means the stage is available in the fork today and should remain stable.
- `Working` means the stage is available in the fork today.
- `Next` means this is the immediate next delivery target.
- `Planned` means the stage is queued after the current next item.

## Notes

- `app/static/app/js/classes/PipelineSteps.js` remains the UI-facing runtime subset only.
- `DEVELOPMENT_STATUS.md` remains the change log and implementation-status companion document.
- 2026-05-18 map review feedback pass improved project map control readability, map-type icon visibility, title contrast, and layer panel height behavior.
- 2026-05-18 shell navigation pass modernized the left menu and moved authenticated user actions to a bottom-left sidebar account card.
