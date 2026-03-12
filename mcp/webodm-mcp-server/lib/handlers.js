import fs from "fs";
import path from "path";
import {
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

    setAuthToken(payload.token);
    return {
      success: true,
      message: "Authentication succeeded.",
      token_received: Boolean(getAuthToken()),
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


