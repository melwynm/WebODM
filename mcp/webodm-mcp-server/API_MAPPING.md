# API Mapping

This file maps the current WebODM API in this repository to the MCP tools in this package.

## Authentication

| WebODM Endpoint | MCP Tool |
| --- | --- |
| POST /api/token-auth/ | webodm_authenticate |
| GET /api/token/ | webodm_get_api_token |
| POST /api/token/regenerate/ | webodm_regenerate_api_token |

## Projects

| WebODM Endpoint | MCP Tool |
| --- | --- |
| GET /api/projects/ | webodm_list_projects |
| GET /api/projects/{id}/ | webodm_get_project |
| POST /api/projects/ | webodm_create_project |
| PATCH /api/projects/{id}/ | webodm_update_project |
| POST /api/projects/{id}/edit/ | webodm_edit_project |
| DELETE /api/projects/{id}/ | webodm_delete_project |
| POST /api/projects/{id}/duplicate/ | webodm_duplicate_project |
| GET /api/projects/{id}/permissions/ | webodm_get_project_permissions |

## Tasks

| WebODM Endpoint | MCP Tool |
| --- | --- |
| GET /api/projects/{project_id}/tasks/ | webodm_list_tasks |
| GET /api/projects/{project_id}/tasks/{task_id}/ | webodm_get_task |
| POST /api/projects/{project_id}/tasks/ | webodm_create_task |
| POST /api/projects/{project_id}/tasks/ with partial=true | webodm_create_partial_task |
| POST /api/projects/{project_id}/tasks/{task_id}/upload/ | webodm_upload_task_files |
| POST /api/projects/{project_id}/tasks/{task_id}/commit/ | webodm_commit_task_upload |
| PATCH /api/projects/{project_id}/tasks/{task_id}/ | webodm_update_task |
| POST /api/projects/{project_id}/tasks/import with url | webodm_import_task_from_url |
| POST /api/projects/{project_id}/tasks/import with file | webodm_import_task_from_archive |
| GET /api/projects/{project_id}/tasks/{task_id}/output/ | webodm_get_task_output |
| POST /api/projects/{project_id}/tasks/{task_id}/cancel/ | webodm_cancel_task |
| POST /api/projects/{project_id}/tasks/{task_id}/restart/ | webodm_restart_task |
| POST /api/projects/{project_id}/tasks/{task_id}/remove/ | webodm_remove_task |
| POST /api/projects/{project_id}/tasks/{task_id}/compact/ | webodm_compact_task |
| POST /api/projects/{project_id}/tasks/{task_id}/duplicate/ | webodm_duplicate_task |

## Task Asset and Visualization Endpoints

| WebODM Endpoint | MCP Tool |
| --- | --- |
| GET /api/projects/{project_id}/tasks/{task_id}/download/{asset} | webodm_get_task_download_url |
| GET /api/projects/{project_id}/tasks/{task_id}/assets/{path} | webodm_get_task_asset_url |
| GET /api/projects/{project_id}/tasks/{task_id}/{orthophoto|dsm|dtm}/tiles.json | webodm_get_task_raster_info |
| GET /api/projects/{project_id}/tasks/{task_id}/{orthophoto|dsm|dtm}/bounds | webodm_get_task_raster_info |
| GET /api/projects/{project_id}/tasks/{task_id}/{orthophoto|dsm|dtm}/metadata | webodm_get_task_raster_info |
| POST /api/projects/{project_id}/tasks/{task_id}/{asset_type}/export | webodm_export_task_asset |
| GET /api/projects/{project_id}/tasks/{task_id}/3d/scene | webodm_get_task_scene |
| POST /api/projects/{project_id}/tasks/{task_id}/3d/scene | webodm_save_task_scene |
| POST /api/projects/{project_id}/tasks/{task_id}/3d/cameraview | webodm_save_task_camera_view |
| GET /api/projects/{project_id}/tasks/{task_id}/monitoring/candidates | webodm_get_monitoring_candidates |
| POST /api/projects/{project_id}/tasks/{task_id}/monitoring/compare | webodm_create_monitoring_compare |

## Processing Nodes

| WebODM Endpoint | MCP Tool |
| --- | --- |
| GET /api/processingnodes/ | webodm_list_processing_nodes |
| GET /api/processingnodes/{id}/ | webodm_get_processing_node |
| POST /api/processingnodes/ | webodm_add_processing_node |
| PATCH /api/processingnodes/{id}/ | webodm_update_processing_node |
| DELETE /api/processingnodes/{id}/ | webodm_delete_processing_node |
| GET /api/processingnodes/options/ | webodm_get_processing_options |

## Presets

| WebODM Endpoint | MCP Tool |
| --- | --- |
| GET /api/presets/ | webodm_list_presets |
| GET /api/presets/{id}/ | webodm_get_preset |
| POST /api/presets/ | webodm_create_preset |
| PATCH /api/presets/{id}/ | webodm_update_preset |
| DELETE /api/presets/{id}/ | webodm_delete_preset |

## Worker Utilities

| WebODM Endpoint | MCP Tool |
| --- | --- |
| GET /api/workers/check/{celery_task_id} | webodm_check_worker_task |
| GET /api/workers/get/{celery_task_id} | webodm_get_worker_result_url |

## Pure MCP Utilities

These tools do not hit WebODM directly:

- `webodm_get_task_status_info`
- `webodm_get_pending_action_info`

## Notes

- This fork accepts both `Authorization: Bearer <jwt>` and `Authorization: Token <api_key>`.
- The MCP package can bootstrap with `webodm_authenticate` and then switch the live session to permanent auth with `webodm_get_api_token`.
- `webodm_regenerate_api_token` uses `POST /api/token/regenerate/` on purpose, even though `POST /api/token/` also rotates the token in WebODM.
- `?jwt=` URL helpers only work when the current MCP session is using a JWT/Bearer token.
- `/api/projects/` may return a plain array when `page` is not provided.
- The worker result endpoint is mapped as a URL helper because the response may be a binary file.
