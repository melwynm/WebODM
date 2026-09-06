import React from 'react';
import PropTypes from 'prop-types';
import $ from 'jquery';

import csrf from '../django/csrf';
import StatusCodes from '../classes/StatusCodes';
import { _ } from '../classes/gettext';

class AIIssueDetectionPanel extends React.Component {
  static defaultProps = {
    onIssuesCreated: () => {}
  };

  static propTypes = {
    projectId: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
    onIssuesCreated: PropTypes.func
  };

  constructor(props){
    super(props);

    this.reviewGeneration = 0;
    this.reviewInFlight = false;

    this.state = {
      loadingTasks: true,
      tasks: [],
      source: 'auto',
      taskId: '',
      maxImages: 3,
      previewing: false,
      confirming: false,
      error: '',
      preview: null,
      createdCount: 0
    };
  }

  componentDidMount(){
    this.loadTasks();
  }

  componentWillUnmount(){
    this.disposed = true;
    this.reviewGeneration += 1;
    this.reviewInFlight = false;
    [this.tasksRequest, this.previewRequest, this.confirmRequest].forEach(request => {
      if (request && request.abort) request.abort();
    });
  }

  loadTasks = () => {
    const url = `/api/projects/${this.props.projectId}/tasks/?status=${StatusCodes.COMPLETED}&available_assets=orthophoto.tif&ordering=-created_at`;
    this.tasksRequest = $.getJSON(url)
      .done(tasks => {
        if (this.disposed) return;
        this.setState({tasks: Array.isArray(tasks) ? tasks : []});
      })
      .fail(jqXHR => {
        if (this.disposed) return;
        this.setState({error: this.responseError(jqXHR, _('Cannot load orthophoto tasks.'))});
      })
      .always(() => {
        if (this.disposed) return;
        this.setState({loadingTasks: false});
      });
  }

  responseError = (jqXHR, fallback) => {
    const data = jqXHR && jqXHR.responseJSON;
    if (Array.isArray(data)) return data.join(' ');
    if (data && typeof data === 'object') {
      if (data.detail) return data.detail;
      const firstKey = Object.keys(data)[0];
      if (firstKey) {
        const value = data[firstKey];
        if (Array.isArray(value)) return value.join(' ');
        if (value !== null && value !== undefined) return value.toString();
      }
    }
    return (jqXHR && jqXHR.responseText) || fallback;
  }

  setSource = e => {
    if (this.isBusy()) return;
    this.reviewGeneration += 1;
    const source = e.target.value;
    const nextState = {source, preview: null, createdCount: 0, error: ''};
    if (source === 'task_orthophoto' && !this.state.taskId && this.state.tasks.length) {
      nextState.taskId = this.state.tasks[0].id;
    }
    this.setState(nextState);
  }

  setTask = e => {
    if (this.isBusy()) return;
    this.reviewGeneration += 1;
    this.setState({taskId: e.target.value, preview: null, createdCount: 0, error: ''});
  }

  setMaxImages = e => {
    if (this.isBusy()) return;
    this.reviewGeneration += 1;
    const parsed = parseInt(e.target.value, 10);
    this.setState({
      maxImages: Number.isNaN(parsed) ? 1 : Math.max(1, Math.min(parsed, 8)),
      preview: null,
      createdCount: 0
    });
  }

  requestPayload = () => {
    const payload = {
      source: this.state.source,
      max_images: this.state.maxImages,
      create: false
    };
    if (this.state.taskId) payload.task = this.state.taskId;
    return payload;
  }

  isBusy = () => this.reviewInFlight || this.state.previewing || this.state.confirming;

  previewIssues = e => {
    e.preventDefault();
    if (this.isBusy()) return;
    if (this.state.source === 'task_orthophoto' && !this.state.taskId) {
      this.setState({error: _('Choose an orthophoto task.')});
      return;
    }

    const reviewGeneration = ++this.reviewGeneration;
    this.reviewInFlight = true;
    this.setState({previewing: true, error: '', preview: null, createdCount: 0});
    this.previewRequest = $.ajax({
      url: `/api/projects/${this.props.projectId}/ai/issue-detection`,
      type: 'POST',
      contentType: 'application/json',
      headers: {
        [csrf.header]: csrf.token
      },
      data: JSON.stringify(this.requestPayload())
    }).done(preview => {
      if (this.disposed || reviewGeneration !== this.reviewGeneration) return;
      this.setState({preview});
    }).fail(jqXHR => {
      if (this.disposed || reviewGeneration !== this.reviewGeneration) return;
      this.setState({error: this.responseError(jqXHR, _('Cannot run AI review.'))});
    }).always(() => {
      if (this.disposed || reviewGeneration !== this.reviewGeneration) return;
      this.reviewInFlight = false;
      this.setState({previewing: false});
    });
  }

  confirmIssues = () => {
    if (this.isBusy()) return;
    const token = this.state.preview && this.state.preview.confirmation_token;
    if (!token) return;

    const reviewGeneration = ++this.reviewGeneration;
    this.reviewInFlight = true;
    this.setState({confirming: true, error: ''});
    this.confirmRequest = $.ajax({
      url: `/api/projects/${this.props.projectId}/ai/issue-detection`,
      type: 'POST',
      contentType: 'application/json',
      headers: {
        [csrf.header]: csrf.token
      },
      data: JSON.stringify({
        confirmation_token: token,
        create: true
      })
    }).done(result => {
      if (this.disposed || reviewGeneration !== this.reviewGeneration) return;
      const issues = Array.isArray(result.issues) ? result.issues : [];
      this.setState(prevState => ({
        preview: {
          ...prevState.preview,
          confirmation_token: null
        },
        createdCount: issues.length
      }));
      this.props.onIssuesCreated(issues);
    }).fail(jqXHR => {
      if (this.disposed || reviewGeneration !== this.reviewGeneration) return;
      this.setState({error: this.responseError(jqXHR, _('Cannot create review issues.'))});
    }).always(() => {
      if (this.disposed || reviewGeneration !== this.reviewGeneration) return;
      this.reviewInFlight = false;
      this.setState({confirming: false});
    });
  }

  renderCandidate(candidate, index){
    const confidence = candidate.confidence === null || candidate.confidence === undefined ?
      null : Math.round(candidate.confidence * 100);

    return (
      <li className="ai-issue-candidate" key={`${candidate.title}-${index}`}>
        <div className="ai-issue-candidate__title">{candidate.title}</div>
        {candidate.description ? <div className="ai-issue-candidate__description">{candidate.description}</div> : ''}
        <div className="ai-issue-candidate__meta">
          <span>{candidate.issue_type}</span>
          <span>{candidate.priority}</span>
          {confidence !== null ? <span>{confidence}%</span> : ''}
          {candidate.location_hint ? <span>{candidate.location_hint}</span> : ''}
        </div>
      </li>
    );
  }

  renderPreview(){
    const preview = this.state.preview;
    if (!preview) return '';

    const candidates = Array.isArray(preview.candidates) ? preview.candidates : [];
    return (
      <div className="ai-issue-preview" aria-live="polite">
        <div className="ai-issue-preview__summary">
          <span><i className="fa fa-image fa-fw"></i> {preview.source_count || 0}</span>
          <span><i className="fa fa-flag fa-fw"></i> {candidates.length}</span>
          <span>{preview.model}</span>
        </div>

        {candidates.length ?
          <ul className="ai-issue-candidates">
            {candidates.map((candidate, index) => this.renderCandidate(candidate, index))}
          </ul>
        : <div className="ai-issue-empty">{_('No review candidates found.')}</div>}

        <div className="ai-issue-actions">
          {preview.confirmation_token ?
            <button type="button" className="btn btn-primary" onClick={this.confirmIssues} disabled={this.isBusy()}>
              <i className={'fa ' + (this.state.confirming ? 'fa-circle-notch fa-spin' : 'fa-check')}></i> {_('Create review issues')}
            </button>
          : ''}
          {this.state.createdCount ?
            <span className="ai-issue-created" role="status"><i aria-hidden="true" className="fa fa-check-circle"></i> {_('Created')}: {this.state.createdCount}</span>
          : ''}
        </div>
      </div>
    );
  }

  render(){
    const orthophotoOnly = this.state.source === 'task_orthophoto';
    const busy = this.isBusy();

    return (
      <section id={`ai-issue-review-${this.props.projectId}`} className="ai-issue-detection" aria-label={_('AI issue review')} aria-busy={busy || this.state.loadingTasks}>
        <form className="ai-issue-controls" onSubmit={this.previewIssues} aria-busy={busy}>
          <div className="ai-issue-control">
            <label htmlFor={`ai-source-${this.props.projectId}`}>{_('Source')}</label>
            <select id={`ai-source-${this.props.projectId}`} className="form-control" value={this.state.source} onChange={this.setSource} disabled={busy}>
              <option value="auto">{_('Best available')}</option>
              <option value="field_photos">{_('Field photos')}</option>
              <option value="task_orthophoto">{_('Orthophoto')}</option>
            </select>
          </div>

          <div className="ai-issue-control ai-issue-control--task">
            <label htmlFor={`ai-task-${this.props.projectId}`}>{_('Task')}</label>
            <select id={`ai-task-${this.props.projectId}`} className="form-control" value={this.state.taskId} onChange={this.setTask} disabled={this.state.loadingTasks || busy}>
              <option value="">{_('Project-wide photos')}</option>
              {this.state.tasks.map(task => <option value={task.id} key={task.id}>{task.name || task.id}</option>)}
            </select>
          </div>

          <div className="ai-issue-control ai-issue-control--count">
            <label htmlFor={`ai-count-${this.props.projectId}`}>{_('Images')}</label>
            <input id={`ai-count-${this.props.projectId}`} className="form-control" type="number" min="1" max="8" value={this.state.maxImages} onChange={this.setMaxImages} disabled={orthophotoOnly || busy} />
          </div>

          <button type="submit" className="btn btn-primary ai-issue-preview-button" disabled={busy || (orthophotoOnly && !this.state.taskId)}>
            <i className={'fa ' + (this.state.previewing ? 'fa-circle-notch fa-spin' : 'fa-search')}></i> {_('Preview')}
          </button>
        </form>

        {this.state.loadingTasks ? <div className="ai-issue-empty" role="status">{_('Loading surveys...')}</div> : ''}
        {this.state.error ? <div className="alert alert-warning ai-issue-error" role="alert">{this.state.error}</div> : ''}
        {this.renderPreview()}
      </section>
    );
  }
}

export default AIIssueDetectionPanel;
