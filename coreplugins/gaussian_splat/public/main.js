(function () {
  "use strict";

  const COMPLETED = 40;
  const API_BASE = "/api/plugins/gaussian_splat";
  const POLL_INTERVAL_MS = 4000;

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : "";
  }

  async function apiGet(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(response.statusText);
    return response.json();
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

  function hasSplat(task) {
    return (task.available_assets || []).indexOf("gaussian_splat.ply") !== -1;
  }

  class GaussianSplatButton extends React.Component {
    constructor(props) {
      super(props);
      this.state = {
        status: null,
        loading: false,
        error: "",
      };
      this.pollTimer = null;
    }

    componentDidMount() {
      this.refreshStatus();
    }

    componentWillUnmount() {
      if (this.pollTimer) window.clearTimeout(this.pollTimer);
    }

    refreshStatus = async () => {
      try {
        const status = await apiGet(`${API_BASE}/task/${this.props.task.id}/status`);
        this.setState({ status, error: "" });
        if (["pending", "running"].indexOf(status.status) !== -1) {
          this.pollTimer = window.setTimeout(this.refreshStatus, POLL_INTERVAL_MS);
        }
      } catch (_error) {
        this.setState({ status: null });
      }
    };

    train = async () => {
      const defaultIterations = hasSplat(this.props.task) ? "7000" : "7000";
      const rawIterations = window.prompt("Gaussian Splat iterations", defaultIterations);
      if (rawIterations === null) return;

      const iterations = parseInt(rawIterations, 10);
      if (!Number.isFinite(iterations) || iterations < 100) {
        this.setState({ error: "Iterations must be at least 100." });
        return;
      }

      this.setState({ loading: true, error: "" });
      try {
        await apiPost(`${API_BASE}/task/${this.props.task.id}/train`, {
          options: {
            iterations,
            force: hasSplat(this.props.task),
          },
        });
        await this.refreshStatus();
      } catch (error) {
        this.setState({ error: error.message });
      } finally {
        this.setState({ loading: false });
      }
    };

    renderStatus() {
      const status = this.state.status;
      if (!status || status.status === "pending") return null;

      const text = status.status === "running"
        ? `Splat ${status.progress || 0}%`
        : status.status === "completed"
          ? "Splat ready"
          : status.status === "failed"
            ? "Splat failed"
            : "";

      if (!text) return null;
      return React.createElement("span", {
        style: {
          display: "inline-flex",
          alignItems: "center",
          marginLeft: "8px",
          color: status.status === "failed" ? "#ef4444" : "var(--odm-text-secondary, #64748b)",
          fontSize: "12px",
          fontWeight: 600,
        },
        title: status.error_message || status.message || "",
      }, text);
    }

    render() {
      const task = this.props.task;
      if (task.status !== COMPLETED) return null;

      const inProgress = this.state.status && ["pending", "running"].indexOf(this.state.status.status) !== -1;
      const disabled = this.state.loading || inProgress;
      const label = inProgress ? "Training Splat" : hasSplat(task) ? "Retrain Splat" : "Train Splat";

      return React.createElement("div", { className: "gaussian-splat-action" },
        React.createElement("button", {
          type: "button",
          className: "btn btn-sm btn-default",
          disabled,
          onClick: this.train,
          title: "Train a Gaussian Splat PLY with OpenSplat",
        },
          React.createElement("i", { className: inProgress ? "fa fa-circle-notch fa-spin" : "fa fa-braille" }),
          " ",
          label
        ),
        this.renderStatus(),
        this.state.error ? React.createElement("span", {
          style: { marginLeft: "8px", color: "#ef4444", fontSize: "12px", fontWeight: 600 },
        }, this.state.error) : null
      );
    }
  }

  if (window.PluginsAPI && window.PluginsAPI.Dashboard) {
    window.PluginsAPI.Dashboard.addTaskActionButton(function (args) {
      return React.createElement(GaussianSplatButton, { task: args.task });
    });
  }
})();
