import fs from "fs";
import path from "path";
import {
  AUTH_SCHEMES,
  PENDING_ACTIONS,
  TASK_STATUS,
  appendMultipartField,
  appendTaskFields,
  assertFileExists,
  buildUrlResult,
  compactObject,
  createMultipartForm,
  encodePathPreservingSlashes,
  ensureTokenAvailable,
  getAuthScheme,
  getAuthToken,
  requestJson,
  setAuthToken,
  uploadMultipart,
  WEBODM_BASE_URL,
} from "./common.js";

export const TOOL_HANDLERS = {
  async webodm_authenticate(args) {
    const payload = await requestJson("/api/token-auth/", {
      method: "POST",
      form: {
        username: args.username,
        password: args.password,
      },
      skipAuth: true,
    });

    setAuthToken(payload.token, AUTH_SCHEMES.BEARER);
    return {
      success: true,
      message: "JWT authentication succeeded.",
      token_received: Boolean(getAuthToken()),
      auth_scheme_in_session: getAuthScheme(),
      base_url: WEBODM_BASE_URL,
    };
  },

  async webodm_get_api_token(args) {
    ensureTokenAvailable();
    const payload = await requestJson("/api/token/");
    const storeForSession = Boolean(args.store_for_session);

    if (storeForSession) {
      setAuthToken(payload.api_key, AUTH_SCHEMES.TOKEN);
    }

    return {
      success: true,
      api_key: payload.api_key,
      stored_for_session: storeForSession,
      auth_scheme_in_session: storeForSession ? AUTH_SCHEMES.TOKEN : getAuthScheme(),
      base_url: WEBODM_BASE_URL,
    };
  },

  async webodm_regenerate_api_token(args) {
    ensureTokenAvailable();

    if (!args.confirm_invalidate) {
      throw new Error("Set confirm_invalidate=true to regenerate the permanent API token.");
    }

    const payload = await requestJson("/api/token/regenerate/", {
      method: "POST",
    });
    const storeForSession = args.store_for_session !== false;

    if (storeForSession) {
      setAuthToken(payload.api_key, AUTH_SCHEMES.TOKEN);
    }

    return {
      success: true,
      api_key: payload.api_key,
      stored_for_session: storeForSession,
      auth_scheme_in_session: storeForSession ? AUTH_SCHEMES.TOKEN : getAuthScheme(),
      message: "API token regenerated. Any integrations using the old token will stop working.",
      base_url: WEBODM_BASE_URL,
    };
  },

  async webodm_list_projects(args) {
    ensureTokenAvailable();
    return requestJson("/api/projects/", { query: args.query });
  },

  async webodm_get_project(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/`);
  },

  async webodm_create_project(args) {
    ensureTokenAvailable();
    return requestJson("/api/projects/", {
      method: "POST",
      json: compactObject({
        name: args.name,
        description: args.description,
        tags: args.tags,
      }),
    });
  },

  async webodm_update_project(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/`, {
      method: "PATCH",
      json: args.patch,
    });
  },

  async webodm_edit_project(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/edit/`, {
      method: "POST",
      json: compactObject({
        name: args.name,
        description: args.description,
        tags: args.tags,
        permissions: args.permissions,
      }),
    });
  },

  async webodm_delete_project(args) {
    ensureTokenAvailable();
    const result = await requestJson(`/api/projects/${args.project_id}/`, {
      method: "DELETE",
      responseType: "empty",
    });
    return {
      ...result,
      note: "Owners/admins delete the project. Shared viewers lose access instead.",
    };
  },

  async webodm_duplicate_project(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/duplicate/`, { method: "POST" });
  },

  async webodm_get_project_permissions(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/permissions/`);
  },

  async webodm_list_tasks(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/`, { query: args.query });
  },

  async webodm_get_task(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/`);
  },

  async webodm_create_task(args) {
    ensureTokenAvailable();
    if (!Array.isArray(args.image_paths) || args.image_paths.length < 2) {
      throw new Error("webodm_create_task requires at least 2 image_paths.");
    }

    const form = createMultipartForm();
    for (const imagePath of args.image_paths) {
      const absolutePath = assertFileExists(imagePath, "Image");
      form.append("images", fs.createReadStream(absolutePath), path.basename(absolutePath));
    }

    appendTaskFields(form, {
      name: args.name,
      processing_node: args.processing_node,
      auto_processing_node: args.auto_processing_node,
      align_to: args.align_to,
      resize_to: args.resize_to,
      tags: args.tags,
      options: args.options,
    });

    return uploadMultipart(`/api/projects/${args.project_id}/tasks/`, form);
  },

  async webodm_create_partial_task(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/`, {
      method: "POST",
      json: {
        partial: true,
        ...(args.payload || {}),
      },
    });
  },

  async webodm_upload_task_files(args) {
    ensureTokenAvailable();
    if (!Array.isArray(args.image_paths) || args.image_paths.length === 0) {
      throw new Error("webodm_upload_task_files requires at least 1 file path.");
    }

    const form = createMultipartForm();
    for (const imagePath of args.image_paths) {
      const absolutePath = assertFileExists(imagePath, "Upload file");
      form.append("images", fs.createReadStream(absolutePath), path.basename(absolutePath));
    }

    for (const [key, value] of Object.entries(args.payload || {})) {
      appendMultipartField(form, key, value);
    }

    return uploadMultipart(`/api/projects/${args.project_id}/tasks/${args.task_id}/upload/`, form);
  },

  async webodm_commit_task_upload(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/commit/`, { method: "POST" });
  },

  async webodm_update_task(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/`, {
      method: "PATCH",
      json: args.patch,
    });
  },

  async webodm_import_task_from_url(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/import`, {
      method: "POST",
      form: compactObject({
        url: args.url,
        name: args.name,
      }),
    });
  },

  async webodm_import_task_from_archive(args) {
    ensureTokenAvailable();
    const archivePath = assertFileExists(args.archive_path, "Archive");
    const form = createMultipartForm();
    form.append("filename", fs.createReadStream(archivePath), path.basename(archivePath));
    if (args.name) {
      form.append("name", args.name);
    }
    return uploadMultipart(`/api/projects/${args.project_id}/tasks/import`, form);
  },

  async webodm_get_task_output(args) {
    ensureTokenAvailable();
    const query = args.query || {};
    const responseType = query.f === "text" || query.f === "raw" ? "text" : "json";
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/output/`, {
      query,
      responseType,
    });
  },

  async webodm_cancel_task(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/cancel/`, { method: "POST" });
  },

  async webodm_restart_task(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/restart/`, { method: "POST" });
  },

  async webodm_remove_task(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/remove/`, { method: "POST" });
  },

  async webodm_compact_task(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/compact/`, { method: "POST" });
  },

  async webodm_duplicate_task(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/duplicate/`, { method: "POST" });
  },

  async webodm_get_task_download_url(args) {
    return buildUrlResult(
      `/api/projects/${args.project_id}/tasks/${args.task_id}/download/${encodeURIComponent(args.asset)}`,
      compactObject({ filename: args.filename }),
      Boolean(args.include_jwt_query),
      true
    );
  },

  async webodm_get_task_asset_url(args) {
    return buildUrlResult(
      `/api/projects/${args.project_id}/tasks/${args.task_id}/assets/${encodePathPreservingSlashes(args.asset_path)}`,
      undefined,
      Boolean(args.include_jwt_query),
      true
    );
  },

  async webodm_get_task_raster_info(args) {
    ensureTokenAvailable();
    const suffixMap = {
      tiles_json: "tiles.json",
      bounds: "bounds",
      metadata: "metadata",
    };
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/${args.tile_type}/${suffixMap[args.info_type]}`, {
      query: args.query,
    });
  },

  async webodm_export_task_asset(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/${args.asset_type}/export`, {
      method: "POST",
      json: args.payload || {},
    });
  },

  async webodm_get_task_scene(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/3d/scene`);
  },

  async webodm_save_task_scene(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/3d/scene`, {
      method: "POST",
      json: args.scene,
    });
  },

  async webodm_save_task_camera_view(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/3d/cameraview`, {
      method: "POST",
      json: args.view,
    });
  },

  async webodm_get_monitoring_candidates(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/monitoring/candidates`);
  },

  async webodm_create_monitoring_compare(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/monitoring/compare`, {
      method: "POST",
      json: { compare_task: args.compare_task },
    });
  },

  async webodm_get_monitoring_timeline(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/monitoring/timeline`, {
      query: compactObject({ task: args.task_id }),
    });
  },

  async webodm_get_textured_model_qa(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/tasks/${args.task_id}/3d/qa`);
  },

  async webodm_get_progress_report(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/reports/progress`, {
      query: compactObject({ template: args.template, format: args.format }),
      responseType: "auto",
    });
  },

  async webodm_get_commercial_readiness(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/commercial/readiness`, {
      query: compactObject({ package: args.package }),
    });
  },

  async webodm_update_commercial_readiness(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/commercial/readiness`, {
      method: "PATCH",
      json: args.patch,
    });
  },

  async webodm_get_delivery_export_url(args) {
    return buildUrlResult(
      `/api/projects/${args.project_id}/delivery/export`,
      compactObject({ template: args.template }),
      Boolean(args.include_jwt_query),
      true
    );
  },

  async webodm_detect_ai_issues(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/ai/issue-detection`, {
      method: "POST",
      json: compactObject({
        task: args.task_id,
        source: args.source,
        create: args.create,
        max_images: args.max_images,
      }),
    });
  },

  async webodm_start_object_detection(args) {
    ensureTokenAvailable();
    return requestJson(`/api/plugins/objdetect/task/${args.task_id}/detect`, {
      method: "POST",
      json: { model: args.model },
    });
  },

  async webodm_list_feature_validations(args) {
    ensureTokenAvailable();
    return requestJson("/api/feature-validations/", { query: args.query });
  },

  async webodm_get_feature_validation(args) {
    ensureTokenAvailable();
    return requestJson(`/api/feature-validations/${encodeURIComponent(args.key)}/`);
  },

  async webodm_create_feature_validation(args) {
    ensureTokenAvailable();
    return requestJson("/api/feature-validations/", {
      method: "POST",
      json: args.payload,
    });
  },

  async webodm_update_feature_validation(args) {
    ensureTokenAvailable();
    return requestJson(`/api/feature-validations/${encodeURIComponent(args.key)}/`, {
      method: "PATCH",
      json: args.patch,
    });
  },

  async webodm_delete_feature_validation(args) {
    ensureTokenAvailable();
    return requestJson(`/api/feature-validations/${encodeURIComponent(args.key)}/`, {
      method: "DELETE",
      responseType: "empty",
    });
  },

  async webodm_list_project_issues(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/issues/`, { query: args.query });
  },

  async webodm_get_project_issue(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/issues/${args.issue_id}/`);
  },

  async webodm_create_project_issue(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/issues/`, {
      method: "POST",
      json: args.payload,
    });
  },

  async webodm_update_project_issue(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/issues/${args.issue_id}/`, {
      method: "PATCH",
      json: args.patch,
    });
  },

  async webodm_delete_project_issue(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/issues/${args.issue_id}/`, {
      method: "DELETE",
      responseType: "empty",
    });
  },

  async webodm_list_design_overlays(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/design-overlays/`, { query: args.query });
  },

  async webodm_create_design_overlay(args) {
    ensureTokenAvailable();
    const filePath = assertFileExists(args.file_path, "Design overlay");
    const form = createMultipartForm();
    form.append("file", fs.createReadStream(filePath), path.basename(filePath));
    appendMultipartField(form, "name", args.name);
    appendMultipartField(form, "description", args.description);
    return uploadMultipart(`/api/projects/${args.project_id}/design-overlays/`, form);
  },

  async webodm_update_design_overlay(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/design-overlays/${args.overlay_id}/`, {
      method: "PATCH",
      json: args.patch,
    });
  },

  async webodm_delete_design_overlay(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/design-overlays/${args.overlay_id}/`, {
      method: "DELETE",
      responseType: "empty",
    });
  },

  async webodm_list_field_photos(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/field-photos/`, { query: args.query });
  },

  async webodm_create_field_photo(args) {
    ensureTokenAvailable();
    const imagePath = assertFileExists(args.image_path, "Field photo");
    const form = createMultipartForm();
    form.append("image", fs.createReadStream(imagePath), path.basename(imagePath));
    for (const [key, value] of Object.entries(args.payload || {})) {
      appendMultipartField(form, key, value);
    }
    return uploadMultipart(`/api/projects/${args.project_id}/field-photos/`, form);
  },

  async webodm_update_field_photo(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/field-photos/${args.photo_id}/`, {
      method: "PATCH",
      json: args.patch,
    });
  },

  async webodm_delete_field_photo(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/field-photos/${args.photo_id}/`, {
      method: "DELETE",
      responseType: "empty",
    });
  },

  async webodm_list_client_shares(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/client-shares/`, { query: args.query });
  },

  async webodm_get_client_share(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/client-shares/${args.share_id}/`);
  },

  async webodm_create_client_share(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/client-shares/`, {
      method: "POST",
      json: args.payload,
    });
  },

  async webodm_update_client_share(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/client-shares/${args.share_id}/`, {
      method: "PATCH",
      json: args.patch,
    });
  },

  async webodm_delete_client_share(args) {
    ensureTokenAvailable();
    return requestJson(`/api/projects/${args.project_id}/client-shares/${args.share_id}/`, {
      method: "DELETE",
      responseType: "empty",
    });
  },

  async webodm_list_processing_nodes(args) {
    ensureTokenAvailable();
    return requestJson("/api/processingnodes/", { query: args.query });
  },

  async webodm_get_processing_node(args) {
    ensureTokenAvailable();
    return requestJson(`/api/processingnodes/${args.processing_node_id}/`);
  },

  async webodm_add_processing_node(args) {
    ensureTokenAvailable();
    return requestJson("/api/processingnodes/", {
      method: "POST",
      json: {
        hostname: args.hostname,
        port: args.port,
      },
    });
  },

  async webodm_update_processing_node(args) {
    ensureTokenAvailable();
    return requestJson(`/api/processingnodes/${args.processing_node_id}/`, {
      method: "PATCH",
      json: args.patch,
    });
  },

  async webodm_delete_processing_node(args) {
    ensureTokenAvailable();
    return requestJson(`/api/processingnodes/${args.processing_node_id}/`, {
      method: "DELETE",
      responseType: "empty",
    });
  },

  async webodm_get_processing_options() {
    ensureTokenAvailable();
    return requestJson("/api/processingnodes/options/");
  },

  async webodm_list_presets(args) {
    ensureTokenAvailable();
    return requestJson("/api/presets/", { query: args.query });
  },

  async webodm_get_preset(args) {
    ensureTokenAvailable();
    return requestJson(`/api/presets/${args.preset_id}/`);
  },

  async webodm_create_preset(args) {
    ensureTokenAvailable();
    return requestJson("/api/presets/", {
      method: "POST",
      json: compactObject({
        name: args.name,
        options: args.options,
      }),
    });
  },

  async webodm_update_preset(args) {
    ensureTokenAvailable();
    return requestJson(`/api/presets/${args.preset_id}/`, {
      method: "PATCH",
      json: args.patch,
    });
  },

  async webodm_delete_preset(args) {
    ensureTokenAvailable();
    return requestJson(`/api/presets/${args.preset_id}/`, {
      method: "DELETE",
      responseType: "empty",
    });
  },

  async webodm_check_worker_task(args) {
    return requestJson(`/api/workers/check/${args.celery_task_id}`);
  },

  async webodm_get_worker_result_url(args) {
    return buildUrlResult(
      `/api/workers/get/${encodeURIComponent(args.celery_task_id)}`,
      compactObject({ filename: args.filename }),
      Boolean(args.include_jwt_query),
      false
    );
  },

  async webodm_get_task_status_info(args) {
    const entry = TASK_STATUS[args.status_code];
    if (!entry) {
      throw new Error(`Unknown task status code: ${args.status_code}`);
    }
    return {
      code: args.status_code,
      ...entry,
    };
  },

  async webodm_get_pending_action_info(args) {
    const entry = PENDING_ACTIONS[args.pending_action_code];
    if (!entry) {
      throw new Error(`Unknown pending action code: ${args.pending_action_code}`);
    }
    return {
      code: args.pending_action_code,
      ...entry,
    };
  },
};
