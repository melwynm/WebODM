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

  function trainingPercentFromMessage(message) {
    const match = String(message || "").match(/\[\s*(\d+(?:\.\d+)?)\s*%\s*\]/);
    if (!match) return null;
    return Math.max(0, Math.min(100, Math.floor(parseFloat(match[1]))));
  }

  class GaussianSplatButton extends React.Component {
    constructor(props) {
      super(props);
      this.state = {
        status: null,
        loading: false,
        error: "",
        showTrainOptions: false,
        iterations: "7000",
        trainingPercent: null,
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
        const parsedTrainingPercent = trainingPercentFromMessage(status.message);
        let trainingPercent = this.state.trainingPercent;
        if (status.status === "pending") trainingPercent = null;
        if (status.status === "running" && parsedTrainingPercent !== null) {
          trainingPercent = trainingPercent === null
            ? parsedTrainingPercent
            : Math.max(trainingPercent, parsedTrainingPercent);
        }
        this.setState({ status, error: "", trainingPercent });
        if (["pending", "running"].indexOf(status.status) !== -1) {
          this.pollTimer = window.setTimeout(this.refreshStatus, POLL_INTERVAL_MS);
        }
      } catch (_error) {
        this.setState({ status: null });
      }
    };

    train = async () => {
      const iterations = parseInt(this.state.iterations, 10);
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
        this.setState({ showTrainOptions: false });
        await this.refreshStatus();
      } catch (error) {
        this.setState({ error: error.message });
      } finally {
        this.setState({ loading: false });
      }
    };

    openTrainOptions = () => {
      this.setState({ showTrainOptions: true, error: "" });
    };

    closeTrainOptions = () => {
      this.setState({ showTrainOptions: false, error: "" });
    };

    renderTrainOptions() {
      if (!this.state.showTrainOptions) return null;

      return React.createElement("div", { className: "gaussian-splat-train-options" },
        React.createElement("label", {
          className: "gaussian-splat-train-label",
          htmlFor: `gaussian-splat-iterations-${this.props.task.id}`,
        }, "Training iterations"),
        React.createElement("input", {
          id: `gaussian-splat-iterations-${this.props.task.id}`,
          className: "form-control input-sm gaussian-splat-iterations",
          type: "number",
          min: 100,
          step: 100,
          value: this.state.iterations,
          disabled: this.state.loading,
          onChange: event => this.setState({ iterations: event.target.value, error: "" }),
        }),
        React.createElement("div", { className: "gaussian-splat-train-actions" },
          React.createElement("button", {
            type: "button",
            className: "btn btn-sm btn-primary",
            disabled: this.state.loading,
            onClick: this.train,
          },
            React.createElement("i", { className: this.state.loading ? "fa fa-circle-notch fa-spin" : "fa fa-play" }),
            " ",
            this.state.loading ? "Starting..." : "Start Training"
          ),
          React.createElement("button", {
            type: "button",
            className: "btn btn-sm btn-default",
            disabled: this.state.loading,
            onClick: this.closeTrainOptions,
          }, "Cancel")
        ),
        hasSplat(this.props.task)
          ? React.createElement("small", { className: "gaussian-splat-train-warning" }, "Starting will replace the current splat when training completes.")
          : null
      );
    }

    renderStatus() {
      const status = this.state.status;
      if (!status || status.status === "pending") return null;

      if (status.status === "completed") {
        const result = status.result || {};
        const downloadUrl = result.download_url ||
          `/api/projects/${this.props.task.project}/tasks/${this.props.task.id}/download/gaussian_splat.ply`;
        const returnUrl = `${window.location.pathname}${window.location.search}`;
        const viewerUrl = "/plugins/gaussian_splat/viewer/index.html" +
          `?content=${encodeURIComponent(downloadUrl)}` +
          `&return=${encodeURIComponent(returnUrl)}`;

        return React.createElement("span", {
          style: {
            display: "inline-flex",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "8px",
            marginLeft: "8px",
          },
        },
          React.createElement("span", {
            style: {
              color: "var(--odm-text-secondary, #64748b)",
              fontSize: "12px",
              fontWeight: 600,
            },
            title: status.message || "Gaussian Splat training complete.",
          }, "Splat ready"),
          React.createElement("a", {
            className: "btn btn-sm btn-primary gaussian-splat-view",
            href: viewerUrl,
            title: "Open the trained Gaussian Splat in the interactive viewer",
          },
            React.createElement("i", { className: "fa fa-eye" }),
            " View Splat"
          ),
          React.createElement("a", {
            className: "btn btn-sm btn-primary gaussian-splat-download",
            href: downloadUrl,
            download: "gaussian_splat.ply",
            title: "Download the trained Gaussian Splat PLY",
          },
            React.createElement("i", { className: "fa fa-download" }),
            " Download Splat"
          )
        );
      }

      const text = status.status === "running"
        ? `Splat ${this.state.trainingPercent === null ? (status.progress || 0) : this.state.trainingPercent}%`
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
          onClick: this.openTrainOptions,
          title: "Train a Gaussian Splat PLY with OpenSplat",
        },
          React.createElement("i", { className: inProgress ? "fa fa-circle-notch fa-spin" : "fa fa-braille" }),
          " ",
          label
        ),
        this.renderStatus(),
        this.renderTrainOptions(),
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
