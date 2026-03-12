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
    public: false,
    mapType: 'orthophoto',
    comparison: null,
    onApply: () => {},
    onClear: () => {}
  };

  static propTypes = {
    task: PropTypes.object,
    public: PropTypes.bool,
    mapType: PropTypes.string,
    comparison: PropTypes.object,
    onApply: PropTypes.func,
    onClear: PropTypes.func
  };

  constructor(props){
    super(props);

    this.state = {
      open: false,
      loadingCandidates: false,
      running: false,
      candidates: [],
      selectedTaskId: '',
      progress: 0,
      progressStatus: '',
      error: ''
    };
  }

  componentDidUpdate(prevProps, prevState){
    if (this.state.open && !prevState.open && this.props.task){
      this.loadCandidates();
    }

    if (prevProps.task && this.props.task && prevProps.task.id !== this.props.task.id){
      this.setState({
        open: false,
        candidates: [],
        selectedTaskId: '',
        progress: 0,
        progressStatus: '',
        running: false,
        error: ''
      });
    }
  }

  loadCandidates = () => {
    if (!this.props.task) return;

    this.setState({loadingCandidates: true, error: ''});
    $.getJSON(`/api/projects/${this.props.task.project}/tasks/${this.props.task.id}/monitoring/candidates`)
      .done(({results}) => {
        const candidates = Array.isArray(results) ? results : [];
        const selectedTaskId = candidates.length > 0 ? candidates[0].id : '';
        this.setState({candidates, selectedTaskId});
      })
      .fail(() => {
        this.setState({error: _('Cannot load monitoring candidates.')});
      })
      .always(() => {
        this.setState({loadingCandidates: false});
      });
  }

  toggleOpen = () => {
    this.setState({open: !this.state.open, error: ''});
  }

  handleSelectTask = e => {
    this.setState({selectedTaskId: e.target.value});
  }

  handleRun = () => {
    const { task } = this.props;
    const { selectedTaskId } = this.state;
    if (!task || !selectedTaskId){
      this.setState({error: _('Select a task to compare.')});
      return;
    }

    this.setState({running: true, progress: 0, progressStatus: _('Preparing comparison...'), error: ''});
    $.ajax({
      type: 'POST',
      url: `/api/projects/${task.project}/tasks/${task.id}/monitoring/compare`,
      data: { compare_task: selectedTaskId }
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
    }).fail(() => {
      this.setState({running: false, error: _('Cannot start the monitoring comparison.')});
    });
  }

  handleClear = () => {
    this.props.onClear();
    this.setState({progress: 0, progressStatus: '', error: ''});
  }

  renderSummary(){
    const { comparison } = this.props;
    if (!comparison) return '';

    const shift = comparison.alignment && comparison.alignment.shift_meters ? comparison.alignment.shift_meters : {x: 0, y: 0};
    const confidence = comparison.alignment && comparison.alignment.confidence !== undefined ? comparison.alignment.confidence : null;
    const warnings = comparison.alignment && comparison.alignment.warnings ? comparison.alignment.warnings : [];

    return (
      <div className="monitoring-summary">
        <div className="summary-title">{comparison.compare_task.name}</div>
        <div>{_('Correction')}: {shift.x}m / {shift.y}m</div>
        {confidence !== null ? <div>{_('Confidence')}: {confidence}</div> : ''}
        {warnings.length > 0 ? <div className="summary-warning">{warnings[0]}</div> : ''}
      </div>
    );
  }

  render(){
    const { task, public: isPublic, mapType, comparison } = this.props;
    const { open, loadingCandidates, running, candidates, selectedTaskId, progress, progressStatus } = this.state;

    if (!task || isPublic || mapType !== 'orthophoto') return '';

    return (
      <div className={"monitoring-compare " + (open ? 'open' : '')}>
        <button
          type="button"
          className="btn btn-sm btn-secondary monitoring-toggle"
          onClick={this.toggleOpen}>
          <i className="fa fa-arrows-alt fa-fw"></i> {_('Monitor')}
        </button>

        {open ? <div className="monitoring-panel theme-secondary">
          <div className="panel-header">
            <div className="panel-title">{_('Monitoring & Progress')}</div>
            <button type="button" className="close" onClick={this.toggleOpen}>&times;</button>
          </div>

          <div className="panel-section">
            <label>{_('Current task')}</label>
            <div className="panel-value">{task.name || task.id}</div>
          </div>

          <div className="panel-section">
            <label htmlFor="monitoring-task-select">{_('Compare against')}</label>
            {loadingCandidates ? <div className="panel-value">{_('Loading tasks...')}</div> :
              <select id="monitoring-task-select" className="form-control" value={selectedTaskId} onChange={this.handleSelectTask}>
                {candidates.length === 0 ? <option value="">{_('No completed orthophotos found')}</option> : ''}
                {candidates.map(candidate => (
                  <option key={candidate.id} value={candidate.id}>{candidate.name || candidate.id}</option>
                ))}
              </select>}
          </div>

          <div className="panel-help">{_('The system automatically aligns the orthophotos before generating the overlay and change heatmap.')}</div>
          <ErrorMessage bind={[this, 'error']} />

          {running ? <ProgressBar current={progress} total={100} template={progressStatus || ''} /> : ''}

          <div className="panel-actions">
            <button type="button" className="btn btn-primary" disabled={running || !selectedTaskId} onClick={this.handleRun}>{_('Load Comparison')}</button>
            {comparison ? <button type="button" className="btn btn-default" onClick={this.handleClear}>{_('Clear')}</button> : ''}
          </div>
        </div> : ''}

        {comparison ? this.renderSummary() : ''}
      </div>
    );
  }
}

export default MonitoringCompareButton;
