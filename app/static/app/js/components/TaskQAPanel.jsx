import '../css/TaskQAPanel.scss';
import React from 'react';
import PropTypes from 'prop-types';
import { _ } from '../classes/gettext';

class TaskQAPanel extends React.Component {
  static propTypes = {
    data: PropTypes.object.isRequired
  };

  static defaultProps = {
    data: {}
  };

  formatValue(value, units){
    if (value === undefined || value === null || isNaN(value)) return '–';
    const absValue = Math.abs(value);
    const decimals = absValue >= 1 ? 2 : 3;
    return `${absValue.toFixed(decimals)} ${units || 'm'}`;
  }

  computeHorizontalRmse(rmse){
    if (!rmse) return null;
    if (rmse.horizontal !== undefined && rmse.horizontal !== null) return rmse.horizontal;
    if (typeof rmse.x === 'number' && typeof rmse.y === 'number'){
      return Math.sqrt(Math.pow(rmse.x, 2) + Math.pow(rmse.y, 2));
    }
    return null;
  }

  computeTotalRmse(rmse){
    if (!rmse) return null;
    if (rmse.total !== undefined && rmse.total !== null) return rmse.total;
    const horizontal = this.computeHorizontalRmse(rmse);
    const vertical = (rmse.vertical !== undefined && rmse.vertical !== null) ? rmse.vertical : rmse.z;
    if (typeof horizontal === 'number' && typeof vertical === 'number'){
      return Math.sqrt(Math.pow(horizontal, 2) + Math.pow(vertical, 2));
    }
    return null;
  }

  getThreshold(){
    const { data } = this.props;
    const base = (data && typeof data.average_error === 'number') ? data.average_error : 0;
    const candidate = base > 0 ? base * 2 : 0;
    return Math.max(candidate, 0.05);
  }

  renderSummary(){
    const { data } = this.props;
    const units = data.units || 'm';
    const rmse = data.rmse || {};
    const summaryItems = [
      { label: _('Average Error'), value: this.formatValue(data.average_error, units) },
      { label: _('RMSE (Horizontal)'), value: this.formatValue(this.computeHorizontalRmse(rmse), units) },
      { label: _('RMSE (Vertical)'), value: this.formatValue(rmse.vertical !== undefined ? rmse.vertical : rmse.z, units) },
      { label: _('RMSE (Total)'), value: this.formatValue(this.computeTotalRmse(rmse), units) }
    ].filter(item => item.value && item.value !== '–');

    if (!summaryItems.length) return null;

    return (
      <div className="task-qa-summary">
        {summaryItems.map(item => (
          <div key={item.label} className="task-qa-summary-item">
            <div className="task-qa-summary-label">{item.label}</div>
            <div className="task-qa-summary-value">{item.value}</div>
          </div>
        ))}
      </div>
    );
  }

  renderTable(){
    const { data } = this.props;
    const units = data.units || 'm';
    const points = Array.isArray(data.points) ? data.points : [];

    if (!points.length){
      return <div className="task-qa-empty">{_('No residuals available.')}</div>;
    }

    const threshold = this.getThreshold();

    return (
      <table className="task-qa-table">
        <thead>
          <tr>
            <th>{_('Point')}</th>
            <th>{_('Horizontal')}</th>
            <th>{_('Vertical')}</th>
            <th>{_('Total')}</th>
            <th>{_('Status')}</th>
          </tr>
        </thead>
        <tbody>
          {points.map(point => {
            const total = point.error_total;
            const highlight = typeof total === 'number' && total > threshold;
            const rowClass = highlight ? 'task-qa-row task-qa-row--warning' : 'task-qa-row';
            const status = point.checkpoint ? _('Checkpoint') : (point.used === false ? _('Unused') : _('Used'));
            return (
              <tr key={point.id || point.label} className={rowClass}>
                <td>{point.label || point.name || '–'}</td>
                <td>{this.formatValue(point.error_horizontal, units)}</td>
                <td>{this.formatValue(point.error_vertical, units)}</td>
                <td>{this.formatValue(total, units)}</td>
                <td>{status}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  render(){
    return (
      <div className="task-qa-panel">
        <div className="task-qa-header">
          <h5>{_('Ground control accuracy')}</h5>
          <p className="task-qa-description">{_('Review residual errors to validate the quality of your control network.')}</p>
        </div>
        {this.renderSummary()}
        {this.renderTable()}
      </div>
    );
  }
}

export default TaskQAPanel;
