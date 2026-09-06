import React from 'react';
import $ from 'jquery';
import csrf from '../django/csrf';
import { _ } from '../classes/gettext';
import AIIssueDetectionPanel from './AIIssueDetectionPanel';

const DEFAULT_FORM = {
  title: '',
  description: '',
  issue_type: 'annotation',
  priority: 'medium',
  status: 'open'
};

class ProjectIssuesPanel extends React.Component {
  constructor(props){
    super(props);

    this.updateRequests = {};

    this.state = {
      loading: true,
      saving: false,
      updatingIssueIds: [],
      error: '',
      issues: [],
      showAIReview: false,
      form: {...DEFAULT_FORM}
    };
  }

  componentDidMount(){
    this.refresh();
  }

  componentWillUnmount(){
    this.disposed = true;
    if (this.loadRequest) this.loadRequest.abort();
    if (this.saveRequest) this.saveRequest.abort();
    Object.keys(this.updateRequests).forEach(issueId => {
      const request = this.updateRequests[issueId];
      if (request && request.abort) request.abort();
    });
  }

  refresh = () => {
    this.setState({loading: true, error: ''});
    this.loadRequest = $.getJSON(`/api/projects/${this.props.projectId}/issues/`)
      .done(json => {
        this.setState({issues: json.results || json});
      })
      .fail((_, __, error) => {
        this.setState({error: error || _('Cannot load issues')});
      })
      .always(() => {
        this.setState({loading: false});
      });
  }

  setFormValue = field => e => {
    this.setState({
      form: {
        ...this.state.form,
        [field]: e.target.value
      }
    });
  }

  createIssue = e => {
    e.preventDefault();
    if (!this.props.canEdit) return;
    if (!this.state.form.title.trim()) {
      this.setState({error: _('Title is required')});
      return;
    }

    this.setState({saving: true, error: ''});
    this.saveRequest = $.ajax({
      url: `/api/projects/${this.props.projectId}/issues/`,
      type: 'POST',
      contentType: 'application/json',
      headers: {
        [csrf.header]: csrf.token
      },
      data: JSON.stringify(this.state.form)
    }).done(issue => {
      this.setState({
        issues: [issue].concat(this.state.issues),
        form: {...DEFAULT_FORM}
      });
    }).fail((jqXHR) => {
      this.setState({error: jqXHR.responseText || _('Cannot create issue')});
    }).always(() => {
      this.setState({saving: false});
    });
  }

  updateIssueStatus = issue => e => {
    if (!this.props.canEdit) return;
    const issueId = String(issue.id);
    if (this.updateRequests[issueId]) return;
    const status = e.target.value;
    if (status === issue.status) return;

    this.setState(prevState => ({
      updatingIssueIds: prevState.updatingIssueIds.concat(issueId),
      error: ''
    }));
    const request = $.ajax({
      url: `/api/projects/${this.props.projectId}/issues/${issue.id}/`,
      type: 'PATCH',
      contentType: 'application/json',
      headers: {
        [csrf.header]: csrf.token
      },
      data: JSON.stringify({status})
    });
    this.updateRequests[issueId] = request;
    request.done(updated => {
      if (this.disposed || this.updateRequests[issueId] !== request) return;
      this.setState(prevState => ({
        issues: prevState.issues.map(item => item.id === updated.id ? updated : item)
      }));
    }).fail((jqXHR) => {
      if (this.disposed || this.updateRequests[issueId] !== request) return;
      this.setState({error: jqXHR.responseText || _('Cannot update issue')});
    }).always(() => {
      if (this.disposed || this.updateRequests[issueId] !== request) return;
      delete this.updateRequests[issueId];
      this.setState(prevState => ({
        updatingIssueIds: prevState.updatingIssueIds.filter(id => id !== issueId)
      }));
    });
  }

  toggleAIReview = () => {
    if (!this.props.canEdit) return;
    this.setState({showAIReview: !this.state.showAIReview});
  }

  handleAIIssuesCreated = issues => {
    if (!issues.length) return;
    this.setState(prevState => {
      const existingIds = new Set(prevState.issues.map(issue => issue.id));
      return {issues: issues.filter(issue => !existingIds.has(issue.id)).concat(prevState.issues)};
    });
  }

  renderIssue(issue){
    const updating = this.state.updatingIssueIds.indexOf(String(issue.id)) !== -1;
    return (
      <li className="project-issue-item" key={issue.id}>
        <div className="project-issue-item__main">
          <div className="project-issue-item__title">{issue.title}</div>
          {issue.description ? <div className="project-issue-item__description">{issue.description}</div> : ''}
          <div className="project-issue-item__meta">
            <span>{issue.issue_type}</span>
            <span>{issue.priority}</span>
            {issue.task_name ? <span>{issue.task_name}</span> : ''}
            {issue.created_by ? <span>{issue.created_by}</span> : ''}
          </div>
        </div>
        <select
          value={issue.status}
          onChange={this.updateIssueStatus(issue)}
          className="form-control project-issue-item__status"
          disabled={!this.props.canEdit || updating}
          aria-busy={updating}
          aria-label={`${_('Status')}: ${issue.title}`}
        >
          <option value="open">{_('Open')}</option>
          <option value="in_review">{_('In Review')}</option>
          <option value="resolved">{_('Resolved')}</option>
          <option value="closed">{_('Closed')}</option>
        </select>
      </li>
    );
  }

  render(){
    const canEdit = this.props.canEdit;

    return (
      <div className="project-issues-panel">
        <div className="project-issues-panel__header">
          <h4>{_('Issues and Annotations')}</h4>
          <div className="project-issues-panel__actions">
            {canEdit ?
              <button type="button" className={'btn btn-xs ai-review-toggle ' + (this.state.showAIReview ? 'btn-primary' : 'btn-default')} onClick={this.toggleAIReview}>
                <i className="fa fa-search"></i> {_('AI Review')}
              </button>
            : ''}
            <button type="button" className="btn btn-default btn-xs" onClick={this.refresh} disabled={this.state.loading} title={_('Refresh')}>
              <i className="fa fa-refresh"></i> {_('Refresh')}
            </button>
          </div>
        </div>

        {this.state.error ? <div className="alert alert-warning">{this.state.error}</div> : ''}

        {canEdit && this.state.showAIReview ?
          <AIIssueDetectionPanel
            projectId={this.props.projectId}
            onIssuesCreated={this.handleAIIssuesCreated}
          />
        : ''}

        {canEdit ?
          <form className="project-issue-form" onSubmit={this.createIssue}>
            <input className="form-control" value={this.state.form.title} onChange={this.setFormValue('title')} placeholder={_('Issue title')} />
            <textarea className="form-control" value={this.state.form.description} onChange={this.setFormValue('description')} placeholder={_('Notes')} />
            <div className="project-issue-form__row">
              <select className="form-control" value={this.state.form.issue_type} onChange={this.setFormValue('issue_type')}>
                <option value="annotation">{_('Annotation')}</option>
                <option value="change">{_('Change')}</option>
                <option value="defect">{_('Defect')}</option>
                <option value="progress">{_('Progress')}</option>
              </select>
              <select className="form-control" value={this.state.form.priority} onChange={this.setFormValue('priority')}>
                <option value="low">{_('Low')}</option>
                <option value="medium">{_('Medium')}</option>
                <option value="high">{_('High')}</option>
                <option value="critical">{_('Critical')}</option>
              </select>
              <button className="btn btn-primary" type="submit" disabled={this.state.saving}>
                <i className="fa fa-plus"></i> {_('Add')}
              </button>
            </div>
          </form>
        : ''}

        {this.state.loading ?
          <div className="text-center"><i className="fa fa-circle-notch fa-spin"></i></div>
        :
          <ul className="project-issue-list">
            {this.state.issues.length ? this.state.issues.map(issue => this.renderIssue(issue)) : <li className="project-issue-empty">{_('No issues yet')}</li>}
          </ul>}
      </div>
    );
  }
}

export default ProjectIssuesPanel;
