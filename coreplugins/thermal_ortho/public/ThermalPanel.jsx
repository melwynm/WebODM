import React from 'react';
import PropTypes from 'prop-types';
import './ThermalPanel.scss';
import $ from 'jquery';
import { _ } from 'webodm/classes/gettext';

const COMPLETED = 40;

export default class ThermalPanel extends React.Component {
  static propTypes = {
    task: PropTypes.object.isRequired,
  };

  constructor(props){
    super(props);

    this.state = {
      loading: true,
      error: '',
      data: null,
      working: false,
    };
  }

  componentDidMount(){
    if (this.shouldRequestStatus()){
      this.loadStatus();
    }else{
      this.setState({loading: false});
    }
  }

  componentWillUnmount(){
    if (this.statusRequest){
      this.statusRequest.abort();
      this.statusRequest = null;
    }
    if (this.pollTimer){
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
  }

  shouldRequestStatus = () => {
    const { task } = this.props;
    const assets = task.available_assets || [];
    return task.status === COMPLETED || assets.indexOf('thermal_orthophoto.tif') !== -1;
  }

  schedulePoll = (data) => {
    if (this.pollTimer){
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }

    if (data && ['queued', 'running', 'waiting_for_odm'].indexOf(data.state) !== -1){
      this.pollTimer = setTimeout(() => this.loadStatus(), data.state === 'waiting_for_odm' ? 8000 : 2500);
    }
  }

  loadStatus = () => {
    const { task } = this.props;

    if (this.statusRequest){
      this.statusRequest.abort();
    }

    this.statusRequest = $.getJSON(`/api/plugins/thermal_ortho/task/${task.id}/status`)
      .done(data => {
        this.setState({data, error: '', loading: false, working: ['queued', 'running'].indexOf(data.state) !== -1});
        this.schedulePoll(data);
      })
      .fail(xhr => {
        if (xhr.statusText === 'abort') return;
        this.setState({error: _('Cannot retrieve thermal status.'), loading: false, working: false});
      })
      .always(() => {
        this.statusRequest = null;
      });
  }

  handleGenerate = () => {
    const { task } = this.props;

    this.setState({working: true, error: ''});
    $.ajax({
      url: `/api/plugins/thermal_ortho/task/${task.id}/process`,
      type: 'POST',
      dataType: 'json',
      data: {camera_type: 'auto'}
    }).done(data => {
      if (data.error){
        this.setState({error: data.error, working: false});
      }else{
        this.setState({data, working: ['queued', 'running'].indexOf(data.state) !== -1, error: ''});
        this.schedulePoll(data);
      }
    }).fail(() => {
      this.setState({error: _('Cannot start thermal generation.'), working: false});
    });
  }

  renderStats(){
    const stats = (this.state.data || {}).stats;
    if (!stats) return '';

    return (
      <div className="thermal-ortho-panel__stats">
        <span>{_('Min')}: {stats.min} C</span>
        <span>{_('Max')}: {stats.max} C</span>
        <span>{_('Mean')}: {stats.mean} C</span>
      </div>
    );
  }

  renderActions(){
    const data = this.state.data || {};
    const canGenerate = data.can_process && !this.state.working;

    if (data.output_available){
      return (
        <div className="thermal-ortho-panel__actions">
          <a className="btn btn-sm btn-primary" href={data.map_url || '#'}>
            <i className="fa fa-globe fa-fw"></i> {_('Open Map')}
          </a>
          <a className="btn btn-sm btn-default" href={data.output_url || '#'}>
            <i className="fa fa-download fa-fw"></i> {_('Download')}
          </a>
          {canGenerate ?
            <button type="button" className="btn btn-sm btn-default" onClick={this.handleGenerate}>
              <i className="fa fa-refresh fa-fw"></i> {_('Regenerate')}
            </button>
          : ''}
        </div>
      );
    }

    if (canGenerate){
      return (
        <div className="thermal-ortho-panel__actions">
          <button type="button" className="btn btn-sm btn-primary" onClick={this.handleGenerate}>
            <i className="fa fa-fire fa-fw"></i> {_('Generate Thermal')}
          </button>
        </div>
      );
    }

    return '';
  }

  render(){
    const { loading, error, data, working } = this.state;

    if (!loading && (!data || !data.supported)){
      return null;
    }

    const progress = data && data.progress ? data.progress : 0;
    const state = data && data.state ? data.state : 'idle';
    const message = data && data.message ? data.message : _('Loading thermal status...');

    return (
      <div className="thermal-ortho-panel">
        <div className="thermal-ortho-panel__header">
          <div className="thermal-ortho-panel__title"><i className="fa fa-fire fa-fw"></i> {_('Thermal')}</div>
          <div className="thermal-ortho-panel__state">{state}</div>
        </div>

        <div className="thermal-ortho-panel__body">
          {data && data.preview_url ?
            <a className="thermal-ortho-panel__preview" href={data.map_url || data.preview_url}>
              <img src={data.preview_url} alt={_('Thermal preview')} />
            </a>
          : ''}

          <div className="thermal-ortho-panel__content">
            {error ? <div className="thermal-ortho-panel__error">{error}</div> : ''}
            <div className="thermal-ortho-panel__message">{message}</div>
            {working || state === 'running' || state === 'queued' ?
              <div className="thermal-ortho-panel__progress">
                <div className="thermal-ortho-panel__progress-bar" style={{width: `${progress}%`}} />
              </div>
            : ''}
            {this.renderStats()}
            {data ? this.renderActions() : ''}
          </div>
        </div>
      </div>
    );
  }
}
