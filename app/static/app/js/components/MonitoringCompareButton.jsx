import React from 'react';
import PropTypes from 'prop-types';
import $ from 'jquery';

import '../css/MonitoringCompareButton.scss';
import ErrorMessage from './ErrorMessage';
import ProgressBar from './ProgressBar';
import Workers from '../classes/Workers';
import { _ } from '../classes/gettext';

class MonitoringCompareButton extends React.Component {
  static defaultProps = {
    task: null,
    project: null,
    public: false,
    mapType: 'orthophoto',
    comparison: null,
    onApply: () => {},
    onClear: () => {}
  };

  static propTypes = {
    task: PropTypes.object,
    project: PropTypes.object,
    public: PropTypes.bool,
    mapType: PropTypes.string,
    comparison: PropTypes.object,
    onApply: PropTypes.func,
    onClear: PropTypes.func
  };

  constructor(props){
    super(props);

    this.state = this.getInitialState();
  }

  getInitialState(){
    return {
      open: false,
      loadingTimeline: false,
      running: false,
      timelineTasks: [],
      referenceTaskId: '',
      compareTaskId: '',
      progress: 0,
      progressStatus: '',
      error: ''
    };
  }

  componentDidUpdate(prevProps, prevState){
    if (this.state.open && !prevState.open && this.getProjectId()){
      this.loadTimeline();
    }

    if (this.getProjectIdFromProps(prevProps) !== this.getProjectId() || this.getContextTaskIdFromProps(prevProps) !== this.getContextTaskId()){
      this.setState(this.getInitialState());
    }
  }

  getProjectIdFromProps = props => {
    if (props.task && props.task.project) return props.task.project;
    if (props.project && props.project.id) return props.project.id;
    return null;
  }

  getProjectId = () => this.getProjectIdFromProps(this.props)

  getContextTaskIdFromProps = props => {
    if (props.task && props.task.id) return props.task.id;
    return null;
  }

  getContextTaskId = () => this.getContextTaskIdFromProps(this.props)

  getTaskById = taskId => {
    if (!taskId) return null;
    return this.state.timelineTasks.find(task => task.id === taskId) || null;
  }

  getPairReadiness = () => {
    const compareTask = this.getTaskById(this.state.compareTaskId);
    if (compareTask && compareTask.pair_readiness) return compareTask.pair_readiness;
    return null;
  }

  getReadinessValue = (ready, readyLabel, missingLabel) => {
    return {
      ready,
      label: ready ? readyLabel : missingLabel
    };
  }

  isKnownTaskId = (tasks, taskId) => {
    if (!taskId) return false;
    return tasks.some(task => task.id === taskId);
  }

  pickAdjacentTaskId = (referenceTaskId, tasks, preferredTaskId = '') => {
    if (!referenceTaskId || tasks.length < 2) return '';
    if (preferredTaskId && preferredTaskId !== referenceTaskId && this.isKnownTaskId(tasks, preferredTaskId)) return preferredTaskId;

    const referenceIndex = tasks.findIndex(task => task.id === referenceTaskId);
    if (referenceIndex === -1) return '';
    if (referenceIndex > 0) return tasks[referenceIndex - 1].id;
    if (referenceIndex + 1 < tasks.length) return tasks[referenceIndex + 1].id;
    return '';
  }

  loadTimeline = () => {
    const projectId = this.getProjectId();
    if (!projectId) return;

    const contextTaskId = this.getContextTaskId();
    const query = contextTaskId ? `?task=${contextTaskId}` : '';

    this.setState({loadingTimeline: true, error: ''});
    $.getJSON(`/api/projects/${projectId}/monitoring/timeline${query}`)
      .done(payload => {
        const timelineTasks = Array.isArray(payload.results) ? payload.results : [];
        const referenceTaskId = this.isKnownTaskId(timelineTasks, payload.default_reference_task_id) ?
          payload.default_reference_task_id :
          (timelineTasks.length > 0 ? timelineTasks[timelineTasks.length - 1].id : '');
        const compareTaskId = this.pickAdjacentTaskId(referenceTaskId, timelineTasks, payload.default_compare_task_id || '');

        this.setState({timelineTasks, referenceTaskId, compareTaskId});
      })
      .fail(jqXHR => {
        const responseError = jqXHR && jqXHR.responseJSON ? (jqXHR.responseJSON.detail || jqXHR.responseJSON.error) : '';
        this.setState({error: responseError || _('Cannot load the monitoring timeline.')});
      })
      .always(() => {
        this.setState({loadingTimeline: false});
      });
  }

  toggleOpen = () => {
    this.setState({open: !this.state.open, error: ''});
  }

  handleReferenceTask = taskId => {
    this.setState(prevState => ({
      referenceTaskId: taskId,
      compareTaskId: this.pickAdjacentTaskId(taskId, prevState.timelineTasks, prevState.compareTaskId)
    }));
  }

  handleCompareTask = taskId => {
    this.setState(prevState => ({
      compareTaskId: this.pickAdjacentTaskId(prevState.referenceTaskId, prevState.timelineTasks, taskId)
    }));
  }

  handleRun = () => {
    const projectId = this.getProjectId();
    const { referenceTaskId, compareTaskId } = this.state;
    if (!projectId || !referenceTaskId || !compareTaskId){
      this.setState({error: _('Choose two timeline tasks to compare.')});
      return;
    }
    if (referenceTaskId === compareTaskId){
      this.setState({error: _('Choose two different timeline tasks to compare.')});
      return;
    }

    this.setState({running: true, progress: 0, progressStatus: _('Preparing comparison...'), error: ''});
    $.ajax({
      type: 'POST',
      url: `/api/projects/${projectId}/tasks/${referenceTaskId}/monitoring/compare`,
      data: { compare_task: compareTaskId }
    }).done(result => {
      if (!result || !result.celery_task_id){
        this.setState({running: false, error: _('Invalid monitoring response.')});
        return;
      }

      Workers.waitForCompletion(result.celery_task_id, error => {
        if (error){
          this.setState({running: false, error: error.toString ? error.toString() : error});
          return;
        }

        Workers.getOutput(result.celery_task_id, (outputError, output) => {
          if (outputError){
            this.setState({running: false, error: outputError.toString ? outputError.toString() : outputError});
            return;
          }

          this.props.onApply(output);
          this.setState({running: false, open: false, progress: 100, progressStatus: _('Comparison ready')});
        });
      }, (status, progress) => {
        this.setState({progressStatus: status, progress: Math.round((progress || 0) * 100)});
      });
    }).fail(jqXHR => {
      const responseError = jqXHR && jqXHR.responseJSON ? (jqXHR.responseJSON.detail || jqXHR.responseJSON.error) : '';
      this.setState({running: false, error: responseError || _('Cannot start the monitoring comparison.')});
    });
  }

  handleClear = () => {
    this.props.onClear();
    this.setState({progress: 0, progressStatus: '', error: ''});
  }

  formatTaskName = task => {
    if (!task) return '-';
    return task.name || task.id;
  }

  formatTaskDate = task => {
    if (!task || !task.created_at) return _('Unknown date');
    return new Date(task.created_at).toLocaleString();
  }

  renderSelectionSummary(){
    const referenceTask = this.getTaskById(this.state.referenceTaskId);
    const compareTask = this.getTaskById(this.state.compareTaskId);

    return (
      <div className="selection-grid">
        <div className="panel-section compact">
          <label>{_('Reference')}</label>
          <div className="panel-value strong">{this.formatTaskName(referenceTask)}</div>
          <div className="panel-muted">{this.formatTaskDate(referenceTask)}</div>
        </div>
        <div className="panel-section compact">
          <label>{_('Compare')}</label>
          <div className="panel-value strong">{this.formatTaskName(compareTask)}</div>
          <div className="panel-muted">{this.formatTaskDate(compareTask)}</div>
        </div>
      </div>
    );
  }

  renderReadiness(){
    const referenceTask = this.getTaskById(this.state.referenceTaskId);
    const compareTask = this.getTaskById(this.state.compareTaskId);
    const pairReadiness = this.getPairReadiness();
    const referenceReady = referenceTask && referenceTask.readiness ? referenceTask.readiness.can_compare : false;
    const compareReady = compareTask && compareTask.readiness ? compareTask.readiness.can_compare : false;
    const terrain = pairReadiness && pairReadiness.terrain_products ? pairReadiness.terrain_products : {};
    const cache = pairReadiness && pairReadiness.cache ? pairReadiness.cache : {};
    const issues = pairReadiness && Array.isArray(pairReadiness.issues) ? pairReadiness.issues : [];

    const items = [
      this.getReadinessValue(referenceReady, _('Reference ready'), _('Reference missing')),
      this.getReadinessValue(compareReady, _('Compare ready'), _('Compare missing')),
      this.getReadinessValue(!!terrain.dsm_delta, _('DSM delta'), _('No DSM delta')),
      this.getReadinessValue(!!terrain.dtm_delta, _('DTM delta'), _('No DTM delta')),
      this.getReadinessValue(!!cache.ready, _('Cached'), _('Not cached'))
    ];

    return (
      <div className="panel-section readiness-section">
        <label>{_('Readiness')}</label>
        <div className="readiness-grid">
          {items.map(item => (
            <div key={item.label} className={'readiness-chip ' + (item.ready ? 'is-ready' : 'is-muted')}>
              <i className={'fa ' + (item.ready ? 'fa-check-circle' : 'fa-circle')}></i>
              <span>{item.label}</span>
            </div>
          ))}
        </div>
        {cache.ready && cache.generated_at ? <div className="panel-muted readiness-cache">{_('Cached result')}: {new Date(cache.generated_at).toLocaleString()}</div> : ''}
        {issues.length > 0 ? <div className="readiness-warning"><i className="fa fa-exclamation-triangle"></i> {issues[0]}</div> : ''}
      </div>
    );
  }

  renderTimeline(){
    const { loadingTimeline, timelineTasks, referenceTaskId, compareTaskId } = this.state;

    if (loadingTimeline){
      return <div className="panel-value">{_('Loading timeline...')}</div>;
    }

    if (timelineTasks.length === 0){
      return <div className="panel-value">{_('No completed orthophotos are available in this project yet.')}</div>;
    }

    return (
      <div className="timeline-list">
        {timelineTasks.map(task => {
          const isReference = task.id === referenceTaskId;
          const isCompare = task.id === compareTaskId;
          const classes = [
            'timeline-task',
            isReference ? 'is-reference' : '',
            isCompare ? 'is-compare' : '',
            task.is_context ? 'is-context' : ''
          ].filter(Boolean).join(' ');

          return (
            <div key={task.id} className={classes}>
              <div className="timeline-marker">{task.position}</div>
              <div className="timeline-card" onClick={() => this.handleReferenceTask(task.id)}>
                <div className="timeline-card__meta">{this.formatTaskDate(task)}</div>
                <div className="timeline-card__title">{this.formatTaskName(task)}</div>
                <div className="timeline-badges">
                  {task.is_context ? <span className="timeline-badge muted">{_('Current')}</span> : ''}
                  {isReference ? <span className="timeline-badge primary">{_('Reference')}</span> : ''}
                  {isCompare ? <span className="timeline-badge accent">{_('Compare')}</span> : ''}
                  {task.readiness && task.readiness.can_compare ? <span className="timeline-badge ready">{_('Ready')}</span> : ''}
                </div>
                {task.readiness ? <div className="timeline-readiness">
                  <span><i className="fa fa-image"></i> {_('Ortho')}</span>
                  {task.readiness.assets && task.readiness.assets.dsm ? <span><i className="fa fa-mountain"></i> {_('DSM')}</span> : ''}
                  {task.readiness.assets && task.readiness.assets.dtm ? <span><i className="fa fa-mountain"></i> {_('DTM')}</span> : ''}
                </div> : ''}
                <div className="timeline-actions">
                  <button type="button" className="btn btn-default btn-sm" onClick={e => { e.stopPropagation(); this.handleReferenceTask(task.id); }}>{_('Set Reference')}</button>
                  <button type="button" className="btn btn-default btn-sm" onClick={e => { e.stopPropagation(); this.handleCompareTask(task.id); }} disabled={timelineTasks.length < 2}>{_('Set Compare')}</button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  renderSummary(){
    const { comparison } = this.props;
    if (!comparison) return '';

    const referenceTask = comparison.reference_task || {};
    const compareTask = comparison.compare_task || {};
    const shift = comparison.alignment && comparison.alignment.shift_meters ? comparison.alignment.shift_meters : {x: 0, y: 0};
    const confidence = comparison.alignment && comparison.alignment.confidence !== undefined ? comparison.alignment.confidence : null;
    const warnings = comparison.alignment && comparison.alignment.warnings ? comparison.alignment.warnings : [];
    const terrainLayers = Object.keys(comparison.layers || {}).filter(key => (comparison.layers[key] || {}).stats);

    return (
      <div className="monitoring-summary">
        <div className="summary-title">{referenceTask.name || referenceTask.id || '-'} {_('vs')} {compareTask.name || compareTask.id || '-'}</div>
        <div>{_('Correction')}: {shift.x}m / {shift.y}m</div>
        {confidence !== null ? <div>{_('Confidence')}: {confidence}</div> : ''}
        {terrainLayers.length > 0 ? <div>{_('Terrain products')}: {terrainLayers.length}</div> : ''}
        {warnings.length > 0 ? <div className="summary-warning">{warnings[0]}</div> : ''}
      </div>
    );
  }

  render(){
    const { task, project, public: isPublic, mapType, comparison } = this.props;
    const { open, running, referenceTaskId, compareTaskId, progress, progressStatus } = this.state;
    const projectId = this.getProjectId();

    if (!projectId || isPublic || mapType !== 'orthophoto') return '';

    return (
      <div className={'monitoring-compare ' + (open ? 'open' : '')}>
        <button
          type="button"
          className="btn btn-sm btn-secondary monitoring-toggle"
          onClick={this.toggleOpen}>
          <i className="fa fa-arrows-alt fa-fw"></i> {_('Monitor')}
        </button>

        {open ? <div className="monitoring-panel theme-secondary">
          <div className="panel-header">
            <div className="panel-title">{_('Monitoring & Progress Timeline')}</div>
            <button type="button" className="close" onClick={this.toggleOpen}>&times;</button>
          </div>

          <div className="panel-section compact panel-context">
            <label>{task ? _('Current task') : _('Project')}</label>
            <div className="panel-value strong">{task ? this.formatTaskName(task) : ((project && project.name) || projectId)}</div>
          </div>

          {this.renderSelectionSummary()}
          {this.renderReadiness()}

          <div className="panel-section timeline-section">
            <label>{_('Timeline')}</label>
            <div className="panel-help">{_('Pick a reference task and a comparison task from the completed orthophoto timeline. The comparison task defaults to the nearest earlier capture when available.')}</div>
            {this.renderTimeline()}
          </div>

          <ErrorMessage bind={[this, 'error']} />
          {running ? <ProgressBar current={progress} total={100} template={progressStatus || ''} /> : ''}

          <div className="panel-actions">
            <button type="button" className="btn btn-primary" disabled={running || !referenceTaskId || !compareTaskId} onClick={this.handleRun}>{_('Load Comparison')}</button>
            {comparison ? <button type="button" className="btn btn-default" onClick={this.handleClear}>{_('Clear')}</button> : ''}
          </div>
        </div> : ''}

        {comparison ? this.renderSummary() : ''}
      </div>
    );
  }
}

export default MonitoringCompareButton;
