/**
 * geometry_correction/static/geometry_correction/main.js
 *
 * Injects the "Apply Geometry Correction" button into every WebODM task view.
 * Uses WebODM's plugin JS injection mechanism (loaded on every page).
 */

(function () {
  "use strict";

  const API_BASE = "/api/plugins/geometry_correction";
  const POLL_INTERVAL_MS = 3000;

  // ── Helpers ──────────────────────────────────────────────────────────────

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : "";
  }

  async function apiPost(url, body) {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: resp.statusText }));
      throw new Error(err.error || resp.statusText);
    }
    return resp.json();
  }

  async function apiGet(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(resp.statusText);
    return resp.json();
  }

  // ── Modal ─────────────────────────────────────────────────────────────────

  function createModal() {
    const overlay = document.createElement("div");
    overlay.id = "gc-modal-overlay";
    overlay.style.cssText = `
      position:fixed;inset:0;background:rgba(0,0,0,.55);
      display:flex;align-items:center;justify-content:center;z-index:9999;
    `;

    const box = document.createElement("div");
    box.style.cssText = `
      background:#fff;border-radius:8px;padding:28px 32px;min-width:360px;
      max-width:520px;box-shadow:0 8px 32px rgba(0,0,0,.25);font-family:sans-serif;
    `;

    const title = document.createElement("h3");
    title.textContent = "Geometry Correction";
    title.style.cssText = "margin:0 0 16px;font-size:18px;color:#222;";

    const body = document.createElement("div");
    body.id = "gc-modal-body";

    const closeBtn = document.createElement("button");
    closeBtn.textContent = "✕";
    closeBtn.style.cssText = `
      position:absolute;top:10px;right:14px;background:none;border:none;
      font-size:20px;cursor:pointer;color:#888;
    `;
    closeBtn.onclick = () => overlay.remove();
    box.style.position = "relative";

    box.appendChild(closeBtn);
    box.appendChild(title);
    box.appendChild(body);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    return { overlay, body };
  }

  function setModalContent(body, html) {
    body.innerHTML = html;
  }

  // ── Options Form ──────────────────────────────────────────────────────────

  function buildOptionsForm() {
    return `
      <p style="color:#555;font-size:14px;margin-bottom:16px;">
        Adjust thresholds or leave defaults. Originals are never overwritten.
      </p>
      <label style="display:block;margin-bottom:10px;">
        <span style="font-size:13px;color:#444;">Plane snap threshold (m)</span><br>
        <input id="gc-plane-thresh" type="number" step="0.01" value="0.05"
          style="width:100%;padding:6px;border:1px solid #ccc;border-radius:4px;">
      </label>
      <label style="display:block;margin-bottom:10px;">
        <span style="font-size:13px;color:#444;">Line angle tolerance (°)</span><br>
        <input id="gc-line-tol" type="number" step="0.5" value="2.0"
          style="width:100%;padding:6px;border:1px solid #ccc;border-radius:4px;">
      </label>
      <div style="display:flex;gap:10px;margin-top:6px;">
        <label style="font-size:13px;cursor:pointer;">
          <input type="checkbox" id="gc-chk-pc" checked> Point Cloud
        </label>
        <label style="font-size:13px;cursor:pointer;">
          <input type="checkbox" id="gc-chk-mesh" checked> Mesh
        </label>
        <label style="font-size:13px;cursor:pointer;">
          <input type="checkbox" id="gc-chk-ortho" checked> Orthophoto
        </label>
      </div>
      <button id="gc-run-btn" style="
        margin-top:18px;width:100%;padding:10px;background:#27ae60;
        color:#fff;border:none;border-radius:6px;font-size:15px;cursor:pointer;
        font-weight:600;
      ">Run Correction</button>
    `;
  }

  // ── Progress polling ──────────────────────────────────────────────────────

  function statusHtml(job) {
    const icons = { pending: "⏳", running: "⚙️", completed: "✅", failed: "❌" };
    const icon = icons[job.status] || "🔄";
    let details = "";

    if (job.status === "completed" && job.result) {
      const r = job.result;
      if (r.pointcloud) {
        details += `<li>Point cloud: ${r.pointcloud.planes_detected} planes detected, 
          ${r.pointcloud.original_points?.toLocaleString()} pts</li>`;
      }
      if (r.orthophoto) {
        const a = r.orthophoto.correction_angle_deg?.toFixed(3);
        details += `<li>Orthophoto: ${r.orthophoto.axis_aligned_lines} axis lines, 
          rotation corrected by ${a}°</li>`;
      }
      if (r.mesh) {
        details += `<li>Mesh: ${r.mesh.planes_detected} planes, 
          ${r.mesh.triangles?.toLocaleString()} triangles</li>`;
      }
    }

    return `
      <p style="font-size:22px;text-align:center;margin:8px 0;">${icon}</p>
      <p style="text-align:center;font-size:15px;color:#333;font-weight:600;">
        ${job.status.charAt(0).toUpperCase() + job.status.slice(1)}
      </p>
      ${details ? `<ul style="font-size:13px;color:#555;margin-top:12px;">${details}</ul>` : ""}
      ${job.error_message ? `<p style="color:#c0392b;font-size:13px;">${job.error_message}</p>` : ""}
      ${["completed","failed"].includes(job.status)
        ? '<p style="font-size:12px;color:#888;margin-top:10px;">Corrected files saved alongside originals in task assets.</p>'
        : '<p style="font-size:13px;color:#888;">Processing… this may take a few minutes.</p>'
      }
    `;
  }

  async function pollJob(jobId, modalBody) {
    let done = false;
    while (!done) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      try {
        const job = await apiGet(`${API_BASE}/status/${jobId}/`);
        setModalContent(modalBody, statusHtml(job));
        if (["completed", "failed"].includes(job.status)) done = true;
      } catch (e) {
        setModalContent(modalBody, `<p style="color:red;">Poll error: ${e.message}</p>`);
        done = true;
      }
    }
  }

  // ── Inject button into task view ──────────────────────────────────────────

  function injectButton(taskId, projectId) {
    if (document.getElementById("gc-inject-btn")) return; // already injected

    // Find the actions toolbar in the task view
    const toolbar = document.querySelector(".task-action-buttons, .task-options-bar, .btn-toolbar");
    if (!toolbar) return;

    const btn = document.createElement("button");
    btn.id = "gc-inject-btn";
    btn.className = "btn btn-sm btn-default";
    btn.innerHTML = '<i class="fa fa-drafting-compass"></i> Geometry Correction';
    btn.style.marginLeft = "6px";

    btn.onclick = () => {
      const { overlay, body } = createModal();
      setModalContent(body, buildOptionsForm());

      document.getElementById("gc-run-btn").addEventListener("click", async () => {
        const options = {
          plane_threshold: parseFloat(document.getElementById("gc-plane-thresh").value),
          line_tolerance: parseFloat(document.getElementById("gc-line-tol").value),
          correct_pointcloud: document.getElementById("gc-chk-pc").checked,
          correct_mesh: document.getElementById("gc-chk-mesh").checked,
          correct_orthophoto: document.getElementById("gc-chk-ortho").checked,
        };

        setModalContent(body, `<p style="text-align:center;padding:20px;color:#555;">Queuing job…</p>`);

        try {
          const resp = await apiPost(`${API_BASE}/correct/`, {
            task_id: taskId,
            project_id: projectId,
            options,
          });
          setModalContent(body, statusHtml({ status: "pending" }));
          pollJob(resp.job_id, body);
        } catch (e) {
          setModalContent(body, `<p style="color:red;">Error: ${e.message}</p>`);
        }
      });
    };

    toolbar.appendChild(btn);
  }

  // ── Bootstrap: watch for task views ──────────────────────────────────────

  function tryInject() {
    // WebODM embeds task/project IDs in the URL: /projects/<pid>/tasks/<tid>/
    const m = window.location.pathname.match(/\/projects\/(\d+)\/tasks\/([^/]+)/);
    if (m) injectButton(m[2], m[1]);
  }

  // Run on load and on SPA navigation
  tryInject();
  let lastUrl = location.href;
  new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      setTimeout(tryInject, 800);
    }
  }).observe(document.body, { subtree: true, childList: true });
})();
