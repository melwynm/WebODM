import {
  booleanField,
  numberField,
  openObjectSchema,
  optionsSchema,
  projectPermissionSchema,
  schema,
  stringField,
} from "./common.js";

export const TOOL_DEFINITIONS = [
  {
    name: "webodm_authenticate",
    description: "Authenticate against WebODM with username/password and store the returned JWT in memory for later tools.",
    inputSchema: schema(
      {
        username: {
          type: "string",
          description: "WebODM username.",
        },
        password: {
          type: "string",
          description: "WebODM password.",
        },
      },
      ["username", "password"]
    ),
  },
  {
    name: "webodm_get_api_token",
    description: "Fetch the current user's permanent WebODM API token. Optionally store it in memory so later tools use Token auth instead of the current JWT.",
    inputSchema: schema({
      store_for_session: booleanField("Whether to replace the current in-memory auth session with the returned permanent API token."),
    }),
  },
  {
    name: "webodm_regenerate_api_token",
    description: "Regenerate the current user's permanent API token. This immediately invalidates the old token, and by default the new token becomes the MCP session credential.",
    inputSchema: schema(
      {
        confirm_invalidate: booleanField("Must be true to confirm that the old permanent token will be invalidated."),
        store_for_session: booleanField("Set false to avoid replacing the current in-memory auth session with the new API token."),
      },
      ["confirm_invalidate"]
    ),
  },
  {
    name: "webodm_list_projects",
    description: "List projects visible to the current WebODM user. Pass query parameters to filter or paginate.",
    inputSchema: schema({ query: openObjectSchema }),
  },
  {
    name: "webodm_get_project",
    description: "Fetch a single project by ID.",
    inputSchema: schema({ project_id: numberField("Project ID.") }, ["project_id"]),
  },
  {
    name: "webodm_create_project",
    description: "Create a project.",
    inputSchema: schema(
      {
        name: stringField("Project name."),
        description: stringField("Optional project description."),
        tags: {
          type: "array",
          description: "Optional project tags.",
          items: { type: "string" },
        },
      },
      ["name"]
    ),
  },
  {
    name: "webodm_update_project",
    description: "Patch a project using the standard REST endpoint.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        patch: openObjectSchema,
      },
      ["project_id", "patch"]
    ),
  },
  {
    name: "webodm_edit_project",
    description: "Use WebODM's special project edit endpoint to update metadata and per-user permissions in one call.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        name: stringField("Project name."),
        description: stringField("Project description."),
        tags: {
          type: "array",
          description: "Project tags.",
          items: { type: "string" },
        },
        permissions: projectPermissionSchema,
      },
      ["project_id"]
    ),
  },
  {
    name: "webodm_delete_project",
    description: "Delete a project. If the current user only has shared access, WebODM removes that access instead of deleting the project.",
    inputSchema: schema({ project_id: numberField("Project ID.") }, ["project_id"]),
  },
  {
    name: "webodm_duplicate_project",
    description: "Duplicate a project.",
    inputSchema: schema({ project_id: numberField("Project ID.") }, ["project_id"]),
  },
  {
    name: "webodm_get_project_permissions",
    description: "Fetch the permission entries for a project.",
    inputSchema: schema({ project_id: numberField("Project ID.") }, ["project_id"]),
  },
  {
    name: "webodm_list_tasks",
    description: "List tasks for a project. Pass query parameters for ordering, status, bbox, and available asset filters.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        query: openObjectSchema,
      },
      ["project_id"]
    ),
  },
  {
    name: "webodm_get_task",
    description: "Fetch a task by project ID and task ID.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_create_task",
    description: "Create a task by uploading at least two local image files.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        image_paths: {
          type: "array",
          description: "Absolute or workspace-relative image paths.",
          items: { type: "string" },
        },
        name: stringField("Optional task name."),
        processing_node: numberField("Optional processing node ID."),
        auto_processing_node: booleanField("Whether WebODM should auto-assign a processing node."),
        align_to: stringField("Optional alignment task ID or 'auto'."),
        resize_to: numberField("Optional maximum image size used for resize-before-process workflows."),
        tags: {
          type: "array",
          description: "Optional task tags.",
          items: { type: "string" },
        },
        options: optionsSchema,
      },
      ["project_id", "image_paths"]
    ),
  },
  {
    name: "webodm_create_partial_task",
    description: "Create a placeholder task with partial=true so images can be uploaded later.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        payload: openObjectSchema,
      },
      ["project_id"]
    ),
  },
  {
    name: "webodm_upload_task_files",
    description: "Upload one or more local files to an existing partial task.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
        image_paths: {
          type: "array",
          description: "Absolute or workspace-relative file paths.",
          items: { type: "string" },
        },
        payload: openObjectSchema,
      },
      ["project_id", "task_id", "image_paths"]
    ),
  },
  {
    name: "webodm_commit_task_upload",
    description: "Commit a partial task after uploads finish so processing can start.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_update_task",
    description: "Patch a task. Use this for moving a task between projects, changing options, crop, tags, and other task serializer fields.",
    inputSchema: schema(
      {
        project_id: numberField("Current project ID."),
        task_id: numberField("Task ID."),
        patch: openObjectSchema,
      },
      ["project_id", "task_id", "patch"]
    ),
  },
  {
    name: "webodm_import_task_from_url",
    description: "Import a processed task archive by URL.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        url: stringField("HTTP or HTTPS URL pointing to a zip archive."),
        name: stringField("Optional imported task name."),
      },
      ["project_id", "url"]
    ),
  },
  {
    name: "webodm_import_task_from_archive",
    description: "Import a processed task archive from a local zip file.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        archive_path: stringField("Local zip file path."),
        name: stringField("Optional imported task name."),
      },
      ["project_id", "archive_path"]
    ),
  },
  {
    name: "webodm_get_task_output",
    description: "Fetch task console output. Pass line, limit, and f via query. f may be text, json, or raw.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
        query: openObjectSchema,
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_cancel_task",
    description: "Cancel a task.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_restart_task",
    description: "Restart a task.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_remove_task",
    description: "Remove a task and its assets.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_compact_task",
    description: "Compact a task's stored assets.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_duplicate_task",
    description: "Duplicate a task.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_get_task_download_url",
    description: "Build a direct download URL for a task asset such as all.zip or orthophoto.tif.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
        asset: stringField("Asset filename, for example all.zip or textured_model.zip."),
        filename: stringField("Optional download filename override."),
        include_jwt_query: booleanField("Whether to include the current JWT as a jwt query parameter in the returned authenticated_url. This only works when the current session is using JWT/Bearer auth."),
      },
      ["project_id", "task_id", "asset"]
    ),
  },
  {
    name: "webodm_get_task_asset_url",
    description: "Build a direct URL to a raw asset path under a task's asset directory.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
        asset_path: stringField("Unsafe asset path segment accepted by WebODM, for example potree/metadata.json."),
        include_jwt_query: booleanField("Whether to include the current JWT as a jwt query parameter in the returned authenticated_url. This only works when the current session is using JWT/Bearer auth."),
      },
      ["project_id", "task_id", "asset_path"]
    ),
  },
  {
    name: "webodm_get_task_raster_info",
    description: "Fetch tiles.json, bounds, or metadata for orthophoto, dsm, or dtm outputs. Extra query params are forwarded as-is.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
        tile_type: {
          type: "string",
          enum: ["orthophoto", "dsm", "dtm"],
          description: "Raster product to inspect.",
        },
        info_type: {
          type: "string",
          enum: ["tiles_json", "bounds", "metadata"],
          description: "Metadata endpoint to call.",
        },
        query: openObjectSchema,
      },
      ["project_id", "task_id", "tile_type", "info_type"]
    ),
  },
  {
    name: "webodm_export_task_asset",
    description: "Request an export for orthophoto, dsm, dtm, or georeferenced_model. The response may contain a ready URL or a celery task ID to poll.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
        asset_type: {
          type: "string",
          enum: ["orthophoto", "dsm", "dtm", "georeferenced_model"],
          description: "Asset family to export.",
        },
        payload: openObjectSchema,
      },
      ["project_id", "task_id", "asset_type"]
    ),
  },
  {
    name: "webodm_get_task_scene",
    description: "Fetch the stored Potree scene for a task.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_save_task_scene",
    description: "Store Potree scene data for a task. The payload must include type='Potree'.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
        scene: openObjectSchema,
      },
      ["project_id", "task_id", "scene"]
    ),
  },
  {
    name: "webodm_save_task_camera_view",
    description: "Store only the Potree camera view for a task.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
        view: openObjectSchema,
      },
      ["project_id", "task_id", "view"]
    ),
  },
  {
    name: "webodm_get_monitoring_candidates",
    description: "List completed tasks in the same project that can be used as monitoring comparison references.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Task ID."),
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_create_monitoring_compare",
    description: "Start a monitoring comparison job between the current task and another task in the same project.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: numberField("Current task ID."),
        compare_task: stringField("Comparison task ID."),
      },
      ["project_id", "task_id", "compare_task"]
    ),
  },
  {
    name: "webodm_list_processing_nodes",
    description: "List processing nodes. Pass query parameters for filters such as ordering or has_available_options.",
    inputSchema: schema({ query: openObjectSchema }),
  },
  {
    name: "webodm_get_processing_node",
    description: "Fetch a processing node by ID.",
    inputSchema: schema({ processing_node_id: numberField("Processing node ID.") }, ["processing_node_id"]),
  },
  {
    name: "webodm_add_processing_node",
    description: "Add a processing node.",
    inputSchema: schema(
      {
        hostname: stringField("Hostname or IP."),
        port: numberField("Port."),
      },
      ["hostname", "port"]
    ),
  },
  {
    name: "webodm_update_processing_node",
    description: "Patch a processing node.",
    inputSchema: schema(
      {
        processing_node_id: numberField("Processing node ID."),
        patch: openObjectSchema,
      },
      ["processing_node_id", "patch"]
    ),
  },
  {
    name: "webodm_delete_processing_node",
    description: "Delete a processing node.",
    inputSchema: schema({ processing_node_id: numberField("Processing node ID.") }, ["processing_node_id"]),
  },
  {
    name: "webodm_get_processing_options",
    description: "Fetch the common processing options across online visible processing nodes.",
    inputSchema: schema({}),
  },
  {
    name: "webodm_list_presets",
    description: "List presets visible to the current user.",
    inputSchema: schema({ query: openObjectSchema }),
  },
  {
    name: "webodm_get_preset",
    description: "Fetch a preset by ID.",
    inputSchema: schema({ preset_id: numberField("Preset ID.") }, ["preset_id"]),
  },
  {
    name: "webodm_create_preset",
    description: "Create a preset.",
    inputSchema: schema(
      {
        name: stringField("Preset name."),
        options: optionsSchema,
      },
      ["name"]
    ),
  },
  {
    name: "webodm_update_preset",
    description: "Patch a preset.",
    inputSchema: schema(
      {
        preset_id: numberField("Preset ID."),
        patch: openObjectSchema,
      },
      ["preset_id", "patch"]
    ),
  },
  {
    name: "webodm_delete_preset",
    description: "Delete a preset owned by the current user.",
    inputSchema: schema({ preset_id: numberField("Preset ID.") }, ["preset_id"]),
  },
  {
    name: "webodm_check_worker_task",
    description: "Check whether a background WebODM worker task is ready.",
    inputSchema: schema({ celery_task_id: stringField("Celery task ID.") }, ["celery_task_id"]),
  },
  {
    name: "webodm_get_worker_result_url",
    description: "Build a direct URL for a worker result download once check_worker_task reports ready=true.",
    inputSchema: schema(
      {
        celery_task_id: stringField("Celery task ID."),
        filename: stringField("Optional filename query parameter."),
        include_jwt_query: booleanField("Whether to include the current JWT as a jwt query parameter in the returned authenticated_url. This only works when the current session is using JWT/Bearer auth."),
      },
      ["celery_task_id"]
    ),
  },
  {
    name: "webodm_get_task_status_info",
    description: "Translate a WebODM task status code into a human-readable description.",
    inputSchema: schema(
      {
        status_code: {
          type: "number",
          enum: [10, 20, 30, 40, 50],
          description: "Task status code.",
        },
      },
      ["status_code"]
    ),
  },
  {
    name: "webodm_get_pending_action_info",
    description: "Translate a WebODM pending action code into a human-readable description.",
    inputSchema: schema(
      {
        pending_action_code: {
          type: "number",
          enum: [1, 2, 3, 4, 5, 6],
          description: "Pending action code.",
        },
      },
      ["pending_action_code"]
    ),
  },
];

