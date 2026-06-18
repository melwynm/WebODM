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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Task UUID."),
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
        task_id: stringField("Current task UUID."),
        compare_task: stringField("Comparison task ID."),
      },
      ["project_id", "task_id", "compare_task"]
    ),
  },
  {
    name: "webodm_get_monitoring_timeline",
    description: "Fetch the ordered monitoring timeline and default comparison pair for a project.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: stringField("Optional task UUID used as the timeline context."),
      },
      ["project_id"]
    ),
  },
  {
    name: "webodm_get_textured_model_qa",
    description: "Fetch the commercial QA summary for a task's textured 3D model.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: stringField("Task UUID."),
      },
      ["project_id", "task_id"]
    ),
  },
  {
    name: "webodm_get_progress_report",
    description: "Fetch a project progress report as JSON or rendered HTML using an optional commercial template.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        template: {
          type: "string",
          enum: ["general", "architecture_cad", "agriculture_field", "solar_inspection"],
          description: "Optional commercial report template.",
        },
        format: {
          type: "string",
          enum: ["json", "html"],
          description: "Response format. Omit or use json for structured data.",
        },
      },
      ["project_id"]
    ),
  },
  {
    name: "webodm_get_commercial_readiness",
    description: "Fetch package-specific system checks and manual sign-off state for commercial delivery.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        package: {
          type: "string",
          enum: ["basic_orthomosaic", "architecture_cad", "agriculture_field", "solar_inspection"],
          description: "Optional package override used for readiness checks.",
        },
      },
      ["project_id"]
    ),
  },
  {
    name: "webodm_update_commercial_readiness",
    description: "Update commercial package selection, reviewer notes, and manual delivery sign-off fields.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        patch: openObjectSchema,
      },
      ["project_id", "patch"]
    ),
  },
  {
    name: "webodm_get_delivery_export_url",
    description: "Build the authenticated project delivery ZIP URL, optionally selecting a commercial report template.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        template: {
          type: "string",
          enum: ["general", "architecture_cad", "agriculture_field", "solar_inspection"],
          description: "Optional report template included in the delivery bundle.",
        },
        include_jwt_query: booleanField("Include the active JWT in authenticated_url. This is unavailable for permanent Token auth."),
      },
      ["project_id"]
    ),
  },
  {
    name: "webodm_detect_ai_issues",
    description: "Run server-side AI issue detection against project field photos or an orthophoto preview and optionally create review issues.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        task_id: stringField("Optional task UUID."),
        source: {
          type: "string",
          enum: ["auto", "field_photos", "orthophoto"],
          description: "Image source selection.",
        },
        create: booleanField("Whether detected candidates should be created as in-review project issues."),
        max_images: numberField("Maximum source images to inspect, from 1 to 8."),
      },
      ["project_id"]
    ),
  },
  {
    name: "webodm_start_object_detection",
    description: "Start orthophoto object detection. Poll the returned celery_task_id with worker tools; deer results use the GSD-aware deer filter.",
    inputSchema: schema(
      {
        task_id: stringField("Task UUID."),
        model: {
          type: "string",
          enum: ["cars", "trees", "athletic", "boats", "planes", "cattle", "dogs", "deer"],
          description: "Detection model or class family.",
        },
      },
      ["task_id", "model"]
    ),
  },
  {
    name: "webodm_list_feature_validations",
    description: "List the staff-only feature validation ledger with optional status, area, attention, and pagination filters.",
    inputSchema: schema({ query: openObjectSchema }),
  },
  {
    name: "webodm_get_feature_validation",
    description: "Fetch one staff-only feature validation record by stable key.",
    inputSchema: schema({ key: stringField("Feature validation key.") }, ["key"]),
  },
  {
    name: "webodm_create_feature_validation",
    description: "Create a staff-only feature validation ledger record.",
    inputSchema: schema({ payload: openObjectSchema }, ["payload"]),
  },
  {
    name: "webodm_update_feature_validation",
    description: "Patch a staff-only feature validation record and update test attribution when status changes.",
    inputSchema: schema(
      { key: stringField("Feature validation key."), patch: openObjectSchema },
      ["key", "patch"]
    ),
  },
  {
    name: "webodm_delete_feature_validation",
    description: "Delete a staff-only feature validation record by key.",
    inputSchema: schema({ key: stringField("Feature validation key.") }, ["key"]),
  },
  {
    name: "webodm_list_project_issues",
    description: "List project issues and annotations with optional task, status, issue_type, ordering, and pagination filters.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), query: openObjectSchema },
      ["project_id"]
    ),
  },
  {
    name: "webodm_get_project_issue",
    description: "Fetch one project issue or annotation.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), issue_id: numberField("Issue ID.") },
      ["project_id", "issue_id"]
    ),
  },
  {
    name: "webodm_create_project_issue",
    description: "Create a project issue or annotation, optionally linked to a task and GeoJSON geometry.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), payload: openObjectSchema },
      ["project_id", "payload"]
    ),
  },
  {
    name: "webodm_update_project_issue",
    description: "Patch a project issue, including review status, assignment, properties, or geometry.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), issue_id: numberField("Issue ID."), patch: openObjectSchema },
      ["project_id", "issue_id", "patch"]
    ),
  },
  {
    name: "webodm_delete_project_issue",
    description: "Delete a project issue or annotation.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), issue_id: numberField("Issue ID.") },
      ["project_id", "issue_id"]
    ),
  },
  {
    name: "webodm_list_design_overlays",
    description: "List CAD, GeoJSON, or zipped Shapefile design overlays attached to a project.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), query: openObjectSchema },
      ["project_id"]
    ),
  },
  {
    name: "webodm_create_design_overlay",
    description: "Upload a local design overlay file to a project.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        file_path: stringField("Absolute or workspace-relative overlay file path."),
        name: stringField("Optional overlay name."),
        description: stringField("Optional overlay description."),
      },
      ["project_id", "file_path"]
    ),
  },
  {
    name: "webodm_update_design_overlay",
    description: "Patch design overlay metadata.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), overlay_id: numberField("Overlay ID."), patch: openObjectSchema },
      ["project_id", "overlay_id", "patch"]
    ),
  },
  {
    name: "webodm_delete_design_overlay",
    description: "Delete a project design overlay and its uploaded file.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), overlay_id: numberField("Overlay ID.") },
      ["project_id", "overlay_id"]
    ),
  },
  {
    name: "webodm_list_field_photos",
    description: "List project field photos with optional task and pagination filters.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), query: openObjectSchema },
      ["project_id"]
    ),
  },
  {
    name: "webodm_create_field_photo",
    description: "Upload a local field photo with optional task, location, capture, and metadata fields.",
    inputSchema: schema(
      {
        project_id: numberField("Project ID."),
        image_path: stringField("Absolute or workspace-relative image path."),
        payload: openObjectSchema,
      },
      ["project_id", "image_path"]
    ),
  },
  {
    name: "webodm_update_field_photo",
    description: "Patch field photo metadata.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), photo_id: numberField("Field photo ID."), patch: openObjectSchema },
      ["project_id", "photo_id", "patch"]
    ),
  },
  {
    name: "webodm_delete_field_photo",
    description: "Delete a project field photo and its uploaded image.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), photo_id: numberField("Field photo ID.") },
      ["project_id", "photo_id"]
    ),
  },
  {
    name: "webodm_list_client_shares",
    description: "List tokenized client portal shares for a project.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), query: openObjectSchema },
      ["project_id"]
    ),
  },
  {
    name: "webodm_get_client_share",
    description: "Fetch one project client share, including role, expiry, enabled state, and portal URL.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), share_id: numberField("Client share ID.") },
      ["project_id", "share_id"]
    ),
  },
  {
    name: "webodm_create_client_share",
    description: "Create a tokenized client viewer or reviewer share.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), payload: openObjectSchema },
      ["project_id", "payload"]
    ),
  },
  {
    name: "webodm_update_client_share",
    description: "Patch a client share's name, role, enabled state, or expiry.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), share_id: numberField("Client share ID."), patch: openObjectSchema },
      ["project_id", "share_id", "patch"]
    ),
  },
  {
    name: "webodm_delete_client_share",
    description: "Delete and invalidate a project client share.",
    inputSchema: schema(
      { project_id: numberField("Project ID."), share_id: numberField("Client share ID.") },
      ["project_id", "share_id"]
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

