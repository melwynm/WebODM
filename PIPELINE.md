# Consolidated Pipeline

Last updated: 2026-03-19

This file is the single source of truth for the project pipeline in this fork.
It combines:

- the runtime WebODM processing pipeline
- the fork's monitoring and progress workflow roadmap

When someone asks for "the pipeline" or "the next item in the pipeline", use this file.
The next item is the first stage marked `Next`.

## Current Next Item

`15. Change Issues and Annotations`

Promote detected changes into trackable issues and annotations with status.

## Pipeline Stages

| Order | Stage | Type | Status | Notes |
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
| 12 | Monitoring Compare MVP | Workflow | Working | Compare orthophotos in single-task view with translational auto-alignment, overlay output, and change heatmap output. |
| 13 | Project Timeline Monitoring | Workflow | Working | Monitoring now supports project-level timeline selection, timeline-driven compare launch, and cache invalidation for regenerated timeline comparisons. |
| 14 | DSM/DTM Delta and Cut/Fill | Workflow | Working | Add terrain change products beyond orthophoto-only comparison. |
| 15 | Change Issues and Annotations | Workflow | Next | Promote detected changes into trackable issues and annotations with status. |
| 16 | Advanced Alignment | Workflow | Planned | Improve alignment from translation-only correction to affine or local feature-based warping. |
| 17 | Stakeholder Reports | Workflow | Planned | Export monitoring and progress reports for external review and communication. |
| 18 | OneDrive Folder Task Intake | Workflow | Working | Create import tasks from a configured OneDrive-synced folder via the `onedriveintake` management command. |

## Interpretation Rules

- `Working` means the stage is available in the fork today.
- `Next` means this is the immediate next delivery target.
- `Planned` means the stage is queued after the current next item.

## Notes

- `app/static/app/js/classes/PipelineSteps.js` remains the UI-facing runtime subset only.
- `DEVELOPMENT_STATUS.md` remains the change log and implementation-status companion document.
