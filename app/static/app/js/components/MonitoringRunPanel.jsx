import React from 'react';
import PropTypes from 'prop-types';
import $ from 'jquery';

import csrf from '../django/csrf';
import { _ } from '../classes/gettext';

class MonitoringRunPanel extends React.Component {
  static propTypes = {
    projectId: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired
  };

  constructor(props){
    super(props);
    this.pendingLoads = 2;
    this.runContext = 0;
    this.actionInFlight = '';
    this.state = {
      loading: true,
      tasks: [],
      runs: [],
      currentTaskId: '',
      baselineTaskId: '',
      currentRun: null,
      creating: false,
      retrying: false,
      publishing: false,
      previewingAI: false,
      confirmingAI: false,
      aiPreview: null,
      error: ''
    };
  }

  componentDidMount(){
    this.loadTimeline();
    this.loadRuns();
  }

  componentWillUnmount(){
    this.disposed = true;
    this.runContext += 1;
    this.actionInFlight = '';
    [
      this.timelineRequest,
      this.runsRequest,
      this.runRequest,
      this.createRequest,
      this.retryRequest,
      this.publishRequest,
      this.aiPreviewRequest,
      this.aiConfirmRequest
    ].forEach(request => {
      if (request && request.abort) request.abort();
    });
    this.stopPolling();
  }

  responseError = (jqXHR, fallback) => {
    const data = jqXHR && jqXHR.responseJSON;
    if (Array.isArray(data)) return data.join(' ');
    if (data && typeof data === 'object') {
      if (data.detail) return data.detail;
      const key = Object.keys(data)[0];
      if (key) {
        const value = data[key];
        return Array.isArray(value) ? value.join(' ') : String(value);
      }
    }
    return (jqXHR && jqXHR.responseText) || fallback;
  }

  loadTimeline = () => {
    this.timelineRequest = $.getJSON(`/api/projects/${this.props.projectId}/monitoring/timeline`)
      .done(payload => {
        if (this.disposed) return;
        this.setState({
          tasks: Array.isArray(payload.results) ? payload.results : [],
          currentTaskId: payload.default_reference_task_id || '',
          baselineTaskId: payload.default_compare_task_id || ''
        });
      })
      .fail(jqXHR => {
        if (this.disposed) return;
        this.setState({error: this.responseError(jqXHR, _('Cannot load monitoring tasks.'))});
      })
      .always(() => {
        if (!this.disposed) this.finishLoading();
      });
  }

  loadRuns = () => {
    this.runsRequest = $.getJSON(`/api/projects/${this.props.projectId}/monitoring-runs/`)
      .done(payload => {
        if (this.disposed) return;
        const runs = Array.isArray(payload) ? payload : (payload.results || []);
        const currentRun = runs.length ? runs[0] : null;
        this.setState({runs, currentRun});
        if (currentRun && currentRun.status === 'generating') this.startPolling(currentRun.id);
      })
      .fail(jqXHR => {
        if (this.disposed) return;
        this.setState({error: this.responseError(jqXHR, _('Cannot load monitoring runs.'))});
      })
      .always(() => {
        if (!this.disposed) this.finishLoading();
      });
  }

  finishLoading = () => {
    this.pendingLoads = Math.max(0, this.pendingLoads - 1);
    if (this.pendingLoads === 0) this.setState({loading: false});
  }

  request = (url, data) => $.ajax({
    url,
    type: 'POST',
    contentType: 'application/json',
    headers: {
      [csrf.header]: csrf.token
    },
    data: JSON.stringify(data || {})
  });

  isActionBusy = () => Boolean(this.actionInFlight);

  isMutationBusy = () => ['create', 'retry', 'confirm', 'publish'].indexOf(this.actionInFlight) !== -1;

  beginAction = action => {
    if (this.isActionBusy()) return null;
    this.actionInFlight = action;
    return this.runContext;
  };

  finishAction = (action, context, state) => {
    if (this.disposed || context !== this.runContext || this.actionInFlight !== action) return;
    this.actionInFlight = '';
    this.setState(state);
  };

  isCurrentRun = (context, runId) => (
    !this.disposed &&
    context === this.runContext &&
    this.state.currentRun &&
    this.state.currentRun.id === runId
  );

  invalidateRunReads = () => {
    this.runContext += 1;
    this.stopPolling();
    [this.runRequest, this.aiPreviewRequest].forEach(request => {
      if (request && request.abort) request.abort();
    });
    if (this.actionInFlight === 'preview') this.actionInFlight = '';
  };

  startPolling = runId => {
    this.stopPolling();
    const context = this.runContext;
    this.pollTimer = setTimeout(() => this.refreshRun(runId, true, context), 1500);
  }

  stopPolling = () => {
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.pollTimer = null;
  }

  refreshRun = (runId, keepPolling = false, context = this.runContext) => {
    this.runRequest = $.getJSON(`/api/projects/${this.props.projectId}/monitoring-runs/${runId}/`)
      .done(run => {
        if (!this.isCurrentRun(context, runId)) return;
        this.setState(prevState => ({
          currentRun: run,
          runs: prevState.runs.map(item => item.id === run.id ? run : item)
        }));
        if (keepPolling && run.status === 'generating') this.startPolling(run.id);
      })
      .fail(jqXHR => {
        if (!this.isCurrentRun(context, runId)) return;
        this.setState({error: this.responseError(jqXHR, _('Cannot refresh monitoring run.'))});
      });
  }

  setCurrentTask = e => {
    const currentTaskId = e.target.value;
    const index = this.state.tasks.findIndex(task => task.id === currentTaskId);
    let baselineTaskId = '';
    if (index > 0) baselineTaskId = this.state.tasks[index - 1].id;
    else if (index !== -1 && index + 1 < this.state.tasks.length) baselineTaskId = this.state.tasks[index + 1].id;
    this.setState({currentTaskId, baselineTaskId, error: ''});
  }

  setBaselineTask = e => this.setState({baselineTaskId: e.target.value, error: ''});

  startRun = e => {
    e.preventDefault();
    const context = this.beginAction('create');
    if (context === null) return;
    if (!this.state.currentTaskId || !this.state.baselineTaskId) {
      this.actionInFlight = '';
      this.setState({error: _('Choose current and baseline surveys.')});
      return;
    }
    if (this.state.currentTaskId === this.state.baselineTaskId) {
      this.actionInFlight = '';
      this.setState({error: _('Current and baseline surveys must be different.')});
      return;
    }

    this.setState({creating: true, error: '', aiPreview: null});
    this.createRequest = this.request(`/api/projects/${this.props.projectId}/monitoring-runs/`, {
      current_task: this.state.currentTaskId,
      baseline_task: this.state.baselineTaskId
    }).done(run => {
      if (this.disposed || context !== this.runContext || this.actionInFlight !== 'create') return;
      this.setState(prevState => ({
        currentRun: run,
        runs: [run].concat(prevState.runs.filter(item => item.id !== run.id))
      }));
      if (run.status === 'generating') this.startPolling(run.id);
    }).fail(jqXHR => {
      if (this.disposed || context !== this.runContext || this.actionInFlight !== 'create') return;
      this.setState({error: this.responseError(jqXHR, _('Cannot start monitoring run.'))});
    }).always(() => this.finishAction('create', context, {creating: false}));
  }

  retryRun = () => {
    const run = this.state.currentRun;
    if (!run) return;
    const context = this.beginAction('retry');
    if (context === null) return;
    this.setState({retrying: true, error: ''});
    this.retryRequest = this.request(
      `/api/projects/${this.props.projectId}/monitoring-runs/${run.id}/retry/`
    ).done(updated => {
      if (!this.isCurrentRun(context, run.id)) return;
      this.setState(prevState => ({
        currentRun: updated,
        runs: prevState.runs.map(item => item.id === updated.id ? updated : item)
      }));
      if (updated.status === 'generating') this.startPolling(updated.id);
    }).fail(jqXHR => {
      if (!this.isCurrentRun(context, run.id)) return;
      this.setState({error: this.responseError(jqXHR, _('Cannot retry monitoring run.'))});
    }).always(() => this.finishAction('retry', context, {retrying: false}));
  }

  previewAI = () => {
    const run = this.state.currentRun;
    if (!run) return;
    const context = this.beginAction('preview');
    if (context === null) return;
    this.setState({previewingAI: true, aiPreview: null, error: ''});
    this.aiPreviewRequest = this.request(`/api/projects/${this.props.projectId}/ai/issue-detection`, {
      source: 'monitoring_change',
      task: run.current_task,
      compare_task: run.baseline_task,
      monitoring_run: run.id,
      max_images: 1,
      create: false
    }).done(aiPreview => {
      if (!this.isCurrentRun(context, run.id)) return;
      this.setState({aiPreview});
    }).fail(jqXHR => {
      if (!this.isCurrentRun(context, run.id)) return;
      this.setState({error: this.responseError(jqXHR, _('Cannot review monitoring changes with AI.'))});
    }).always(() => this.finishAction('preview', context, {previewingAI: false}));
  }

  confirmAI = () => {
    const token = this.state.aiPreview && this.state.aiPreview.confirmation_token;
    const run = this.state.currentRun;
    if (!token || !run) return;
    const context = this.beginAction('confirm');
    if (context === null) return;
    this.setState({confirmingAI: true, error: ''});
    this.aiConfirmRequest = this.request(`/api/projects/${this.props.projectId}/ai/issue-detection`, {
      confirmation_token: token,
      create: true
    }).done(() => {
      if (!this.isCurrentRun(context, run.id)) return;
      this.setState(prevState => ({
        aiPreview: {...prevState.aiPreview, confirmation_token: null}
      }));
      this.refreshRun(run.id);
    }).fail(jqXHR => {
      if (!this.isCurrentRun(context, run.id)) return;
      this.setState({error: this.responseError(jqXHR, _('Cannot create monitoring issues.'))});
    }).always(() => this.finishAction('confirm', context, {confirmingAI: false}));
  }

  publishRun = () => {
    const run = this.state.currentRun;
    if (!run) return;
    const context = this.beginAction('publish');
    if (context === null) return;
    this.setState({publishing: true, error: ''});
    this.publishRequest = this.request(
      `/api/projects/${this.props.projectId}/monitoring-runs/${run.id}/publish/`
    ).done(published => {
      if (!this.isCurrentRun(context, run.id)) return;
      this.setState(prevState => ({
        currentRun: published,
        runs: prevState.runs.map(item => item.id === published.id ? published : item)
      }));
    }).fail(jqXHR => {
      if (!this.isCurrentRun(context, run.id)) return;
      this.setState({error: this.responseError(jqXHR, _('Cannot publish monitoring run.'))});
    }).always(() => this.finishAction('publish', context, {publishing: false}));
  }

  selectRun = e => {
    if (this.isMutationBusy()) return;
    this.invalidateRunReads();
    const run = this.state.runs.find(item => item.id === e.target.value) || null;
    this.setState({currentRun: run, aiPreview: null, error: '', previewingAI: false});
    if (run && run.status === 'generating') this.startPolling(run.id);
  }

  newRun = () => {
    if (this.isMutationBusy()) return;
    this.invalidateRunReads();
    this.setState({currentRun: null, aiPreview: null, error: '', previewingAI: false});
  }

  openURL = url => {
    if (url) window.open(url, '_blank', 'noopener');
  }

  renderSetup(){
    const ready = this.state.tasks.length >= 2;
    const busy = this.isActionBusy();
    return (
      <form className="monitoring-run-setup" onSubmit={this.startRun} aria-busy={busy}>
        <div className="monitoring-run-field">
          <label htmlFor={`monitor-current-${this.props.projectId}`}>{_('Current survey')}</label>
          <select id={`monitor-current-${this.props.projectId}`} className="form-control" value={this.state.currentTaskId} onChange={this.setCurrentTask} disabled={!ready || busy}>
            <option value="">{_('Select survey')}</option>
            {this.state.tasks.map(task => <option value={task.id} key={task.id}>{task.name || task.id}</option>)}
          </select>
        </div>
        <div className="monitoring-run-field">
          <label htmlFor={`monitor-baseline-${this.props.projectId}`}>{_('Baseline survey')}</label>
          <select id={`monitor-baseline-${this.props.projectId}`} className="form-control" value={this.state.baselineTaskId} onChange={this.setBaselineTask} disabled={!ready || busy}>
            <option value="">{_('Select baseline')}</option>
            {this.state.tasks.filter(task => task.id !== this.state.currentTaskId).map(task => <option value={task.id} key={task.id}>{task.name || task.id}</option>)}
          </select>
        </div>
        <button type="submit" className="btn btn-primary monitoring-run-start" disabled={!ready || busy}>
          <i aria-hidden="true" className={'fa ' + (this.state.creating ? 'fa-circle-notch fa-spin' : 'fa-play')}></i>
          {_('Start review run')}
        </button>
        {!ready && !this.state.loading ? <div className="monitoring-run-empty">{_('Two completed orthophoto surveys are required.')}</div> : ''}
      </form>
    );
  }

  renderSteps(run){
    const compareReady = run.status === 'review' || run.status === 'published';
    const published = run.status === 'published';
    return (
      <ol className="monitoring-run-steps" aria-label={_('Monitoring progress')}>
        <li className="is-complete"><i aria-hidden="true" className="fa fa-check"></i><span>{_('Surveys')}</span></li>
        <li className={compareReady ? 'is-complete' : (run.status === 'failed' ? 'is-failed' : 'is-active')} aria-current={!compareReady ? 'step' : undefined}>
          <i aria-hidden="true" className={'fa ' + (run.status === 'generating' ? 'fa-circle-notch fa-spin' : run.status === 'failed' ? 'fa-exclamation' : 'fa-check')}></i>
          <span>{_('Compare')}</span>
        </li>
        <li className={run.issue_count ? 'is-complete' : (compareReady && !published ? 'is-active' : '')} aria-current={compareReady && !published && !run.issue_count ? 'step' : undefined}>
          <i aria-hidden="true" className={'fa ' + (run.issue_count ? 'fa-check' : 'fa-search')}></i><span>{_('Review')}</span>
        </li>
        <li className={published ? 'is-complete' : ''}><i aria-hidden="true" className={'fa ' + (published ? 'fa-check' : 'fa-share-alt')}></i><span>{_('Publish')}</span></li>
      </ol>
    );
  }

  renderCandidates(){
    const preview = this.state.aiPreview;
    if (!preview) return '';
    const candidates = Array.isArray(preview.candidates) ? preview.candidates : [];
    return (
      <div className="monitoring-ai-preview">
        {candidates.length ? <ul>
          {candidates.map((candidate, index) => <li key={`${candidate.title}-${index}`}>
            <strong>{candidate.title}</strong>
            {candidate.description ? <p>{candidate.description}</p> : ''}
            <span>{candidate.priority} | {candidate.issue_type}</span>
          </li>)}
        </ul> : <div className="monitoring-run-empty">{_('No review candidates found.')}</div>}
        {preview.confirmation_token ? <button type="button" className="btn btn-primary" onClick={this.confirmAI} disabled={this.state.confirmingAI}>
          <i className={'fa ' + (this.state.confirmingAI ? 'fa-circle-notch fa-spin' : 'fa-check')}></i>
          {_('Create review issues')}
        </button> : ''}
      </div>
    );
  }

  renderRun(run){
    const current = run.current_task_detail || {};
    const baseline = run.baseline_task_detail || {};
    const published = run.status === 'published';
    const busy = this.isActionBusy();
    return (
      <div className="monitoring-run-review" aria-busy={busy}>
        <div className="monitoring-run-pair">
          <div><span>{_('Current')}</span><strong>{current.name}</strong></div>
          <i className="fa fa-long-arrow-alt-left"></i>
          <div><span>{_('Baseline')}</span><strong>{baseline.name}</strong></div>
        </div>
        {this.renderSteps(run)}
        {run.last_error ? <div className="alert alert-warning" role="alert">{run.last_error}</div> : ''}

        <div className="monitoring-run-actions">
          {run.status === 'failed' ? <button type="button" className="btn btn-warning" onClick={this.retryRun} disabled={busy}>
            <i className={'fa ' + (this.state.retrying ? 'fa-circle-notch fa-spin' : 'fa-redo')}></i> {_('Retry')}
          </button> : ''}
          {(run.status === 'review' || published) ? <button type="button" className="btn btn-default" onClick={() => this.openURL(`/map/project/${this.props.projectId}/task/${run.current_task}/`)}>
            <i className="fa fa-map"></i> {_('Open map')}
          </button> : ''}
          {(run.status === 'review' || published) ? <button type="button" className="btn btn-default" onClick={() => this.openURL(run.report_url)}>
            <i className="fa fa-file-pdf"></i> {_('Report')}
          </button> : ''}
          {run.status === 'review' ? <button type="button" className="btn btn-default" onClick={this.previewAI} disabled={busy}>
            <i className={'fa ' + (this.state.previewingAI ? 'fa-circle-notch fa-spin' : 'fa-search')}></i> {_('AI review')}
          </button> : ''}
          {run.can_publish ? <button type="button" className="btn btn-primary" onClick={this.publishRun} disabled={busy}>
            <i className={'fa ' + (this.state.publishing ? 'fa-circle-notch fa-spin' : 'fa-share-alt')}></i> {_('Publish')}
          </button> : ''}
          {published && run.portal_url ? <button type="button" className="btn btn-primary" onClick={() => this.openURL(run.portal_url)}>
            <i className="fa fa-external-link-alt"></i> {_('Open client portal')}
          </button> : ''}
        </div>
        {run.status === 'generating' ? <div className="monitoring-run-progress" role="status" aria-label={_('Generating comparison')}><span></span></div> : ''}
        {run.issue_count ? <div className="monitoring-run-count"><i className="fa fa-flag"></i> {run.issue_count} {_('review issues')}</div> : ''}
        {this.renderCandidates()}
      </div>
    );
  }

  render(){
    const run = this.state.currentRun;
    const mutationBusy = this.isMutationBusy();
    return (
      <section className="monitoring-run-panel" aria-labelledby={`monitoring-runs-${this.props.projectId}`} aria-busy={this.state.loading || mutationBusy}>
        <header className="monitoring-run-header">
          <div>
            <i aria-hidden="true" className="fa fa-route"></i>
            <strong id={`monitoring-runs-${this.props.projectId}`}>{_('Monitoring runs')}</strong>
          </div>
          <div className="monitoring-run-header-actions">
            {this.state.runs.length ? <select className="form-control" aria-label={_('Monitoring run')} value={run ? run.id : ''} onChange={this.selectRun} disabled={mutationBusy}>
              <option value="">{_('New run')}</option>
              {this.state.runs.map(item => <option value={item.id} key={item.id}>{(item.current_task_detail || {}).name} | {item.status_label}</option>)}
            </select> : ''}
            {run ? <button type="button" className="btn btn-default" title={_('New run')} aria-label={_('New monitoring run')} onClick={this.newRun} disabled={mutationBusy}><i aria-hidden="true" className="fa fa-plus"></i></button> : ''}
          </div>
        </header>
        {this.state.error ? <div className="alert alert-warning monitoring-run-error" role="alert">{this.state.error}</div> : ''}
        {this.state.loading ? <div className="monitoring-run-loading" role="status"><i aria-hidden="true" className="fa fa-circle-notch fa-spin"></i> {_('Loading monitoring runs...')}</div> : (run ? this.renderRun(run) : this.renderSetup())}
      </section>
    );
  }
}

export default MonitoringRunPanel;
