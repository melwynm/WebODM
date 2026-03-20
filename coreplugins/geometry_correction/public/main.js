(function () {
  "use strict";

  const API_BASE = "/api/plugins/geometry_correction";
  const POLL_INTERVAL_MS = 3000;

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : "";
  }

  async function apiPost(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || response.statusText);
    }

    return response.json();
  }

  async function apiGet(url) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(response.statusText);
    }
    return response.json();
  }

  function createModal() {
    const overlay = document.createElement("div");
    overlay.id = "gc-modal-overlay";
    overlay.style.cssText = [
      "position:fixed",
      "inset:0",
      "background:rgba(12, 20, 36, 0.55)",
      "display:flex",
      "align-items:center",
      "justify-content:center",
      "z-index:9999",
    ].join(";");

    const box = document.createElement("div");
    box.style.cssText = [
      "position:relative",
      "background:#fff",
      "border-radius:12px",
      "padding:28px 32px",
      "min-width:360px",
      "max-width:560px",
      "box-shadow:0 20px 60px rgba(0,0,0,.20)",
      "font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    ].join(";");

    const title = document.createElement("h3");
    title.textContent = "Geometry Correction";
    title.style.cssText = "margin:0 0 16px;font-size:20px;color:#1b2733;";

    const body = document.createElement("div");
    body.id = "gc-modal-body";

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.textContent = "x";
    closeButton.style.cssText = [
      "position:absolute",
      "top:8px",
      "right:12px",
      "border:none",
      "background:none",
      "font-size:24px",
      "color:#8091a7",
      "cursor:pointer",
    ].join(";");
    closeButton.onclick = () => overlay.remove();

    box.appendChild(closeButton);
    box.appendChild(title);
    box.appendChild(body);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    return { overlay, body };
  }

  function setModalContent(body, html) {
    body.innerHTML = html;
  }

  function buildOptionsForm() {
    return `
      <p style="color:#506173;font-size:14px;margin-bottom:16px;">
        Run post-processing corrections without overwriting the original assets.
      </p>
      <label style="display:block;margin-bottom:12px;">
        <span style="display:block;font-size:13px;color:#314356;margin-bottom:4px;">Plane snap threshold (m)</span>
        <input id="gc-plane-thresh" type="number" step="0.01" value="0.05"
          style="width:100%;padding:8px 10px;border:1px solid #cfd7e3;border-radius:8px;">
      </label>
      <label style="display:block;margin-bottom:12px;">
        <span style="display:block;font-size:13px;color:#314356;margin-bottom:4px;">Line angle tolerance (deg)</span>
        <input id="gc-line-tol" type="number" step="0.5" value="2.0"
          style="width:100%;padding:8px 10px;border:1px solid #cfd7e3;border-radius:8px;">
      </label>
      <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;">
        <label style="font-size:13px;color:#314356;cursor:pointer;"><input type="checkbox" id="gc-chk-pc" checked> Point Cloud</label>
        <label style="font-size:13px;color:#314356;cursor:pointer;"><input type="checkbox" id="gc-chk-mesh" checked> Mesh</label>
        <label style="font-size:13px;color:#314356;cursor:pointer;"><input type="checkbox" id="gc-chk-ortho" checked> Orthophoto</label>
      </div>
      <button id="gc-run-btn" type="button" style="
        margin-top:18px;width:100%;padding:11px 14px;border:none;border-radius:9px;
        background:#1f7a4f;color:#fff;font-size:15px;font-weight:600;cursor:pointer;
      ">Run Correction</button>
    `;
  }

  function renderProgressBar(progress) {
    const width = Math.max(0, Math.min(100, Number(progress) || 0));
    return `
      <div style="margin:14px 0 10px;">
        <div style="height:10px;background:#e7edf5;border-radius:999px;overflow:hidden;">
          <div style="height:100%;width:${width}%;background:linear-gradient(90deg,#1f7a4f,#4caf7d);transition:width .25s ease;"></div>
        </div>
        <div style="margin-top:6px;font-size:12px;color:#617384;text-align:right;">${width}%</div>
      </div>
    `;
  }

  function statusHtml(job) {
    const icons = { pending: "[...]", running: "[~]", completed: "[OK]", failed: "[!]" };
    const status = job.status || "pending";
    const progress = status === "completed" ? 100 : job.progress || 0;
    const icon = icons[status] || "[...]";
    let details = "";

    if (status === "completed" && job.result) {
      const result = job.result;
      if (result.pointcloud) {
        details += `<li>Point cloud: ${result.pointcloud.planes_detected} planes, ${Number(result.pointcloud.original_points || 0).toLocaleString()} points</li>`;
      }
      if (result.orthophoto) {
        const angle = Number(result.orthophoto.correction_angle_deg || 0).toFixed(3);
        details += `<li>Orthophoto: ${result.orthophoto.axis_aligned_lines} aligned lines, ${angle} deg correction</li>`;
      }
      if (result.mesh) {
        details += `<li>Mesh: ${result.mesh.planes_detected} planes, ${Number(result.mesh.triangles || 0).toLocaleString()} triangles</li>`;
      }
    }

    return `
      <p style="font-size:24px;text-align:center;margin:8px 0 0;">${icon}</p>
      <p style="text-align:center;font-size:15px;font-weight:600;color:#1b2733;margin:6px 0 0;">
        ${status.charAt(0).toUpperCase() + status.slice(1)}
      </p>
      ${renderProgressBar(progress)}
      <p style="text-align:center;font-size:13px;color:#607286;margin:8px 0 0;">${job.message || (status === "running" ? "Processing geometry correction." : "")}</p>
      ${details ? `<ul style="margin-top:14px;color:#445567;font-size:13px;padding-left:18px;">${details}</ul>` : ""}
      ${job.error_message ? `<p style="margin-top:12px;color:#c0392b;font-size:13px;">${job.error_message}</p>` : ""}
      ${status === "completed"
        ? '<p style="font-size:12px;color:#7a8b9c;margin-top:12px;">Corrected outputs were written to the task assets under geometry_correction.</p>'
        : ""}
    `;
  }

  async function pollJob(jobId, modalBody) {
    let finished = false;

    while (!finished) {
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      try {
        const job = await apiGet(`${API_BASE}/status/${jobId}/`);
        setModalContent(modalBody, statusHtml(job));
        finished = ["completed", "failed"].includes(job.status);
      } catch (error) {
        setModalContent(modalBody, `<p style="color:#c0392b;">Polling failed: ${error.message}</p>`);
        finished = true;
      }
    }
  }

  function injectButton(taskId, projectId) {
    if (document.getElementById("gc-inject-btn")) {
      return;
    }

    const toolbar = document.querySelector(".task-action-buttons, .task-options-bar, .btn-toolbar");
    if (!toolbar) {
      return;
    }

    const button = document.createElement("button");
    button.id = "gc-inject-btn";
    button.className = "btn btn-sm btn-default";
    button.innerHTML = '<i class="fa fa-drafting-compass"></i> Geometry Correction';
    button.style.marginLeft = "6px";

    button.onclick = () => {
      const { body } = createModal();
      setModalContent(body, buildOptionsForm());

      document.getElementById("gc-run-btn").addEventListener("click", async () => {
        const options = {
          plane_threshold: parseFloat(document.getElementById("gc-plane-thresh").value),
          line_tolerance: parseFloat(document.getElementById("gc-line-tol").value),
          correct_pointcloud: document.getElementById("gc-chk-pc").checked,
          correct_mesh: document.getElementById("gc-chk-mesh").checked,
          correct_orthophoto: document.getElementById("gc-chk-ortho").checked,
        };

        setModalContent(body, "<p style='text-align:center;padding:18px 0;color:#506173;'>Queuing geometry correction...</p>");

        try {
          const response = await apiPost(`${API_BASE}/correct/`, {
            task_id: taskId,
            project_id: projectId,
            options,
          });
          setModalContent(body, statusHtml({ status: "pending", progress: 0, message: response.message }));
          pollJob(response.job_id, body);
        } catch (error) {
          setModalContent(body, `<p style="color:#c0392b;">Error: ${error.message}</p>`);
        }
      });
    };

    toolbar.appendChild(button);
  }

  function tryInject() {
    const match = window.location.pathname.match(/\/projects\/(\d+)\/tasks\/([^/]+)/);
    if (match) {
      injectButton(match[2], match[1]);
    }
  }

  tryInject();
  let lastUrl = window.location.href;
  new MutationObserver(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      window.setTimeout(tryInject, 800);
    }
  }).observe(document.body, { subtree: true, childList: true });
})();
