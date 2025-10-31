import React from 'react';
import PropTypes from 'prop-types';
import Storage from 'webodm/classes/Storage';
import L from 'leaflet';
import './ObjDetectPanel.scss';
import ErrorMessage from 'webodm/components/ErrorMessage';
import Workers from 'webodm/classes/Workers';
import Utils from 'webodm/classes/Utils';
import { _ } from 'webodm/classes/gettext';

export default class ObjDetectPanel extends React.Component {
  static defaultProps = {
  };
  static propTypes = {
    onClose: PropTypes.func.isRequired,
    tasks: PropTypes.object.isRequired,
    isShowed: PropTypes.bool.isRequired,
    map: PropTypes.object.isRequired
  }

  constructor(props){
    super(props);

    this.state = {
        error: "",
        permanentError: "",
        model: Storage.getItem("last_objdetect_model") || "cars",
        loading: true,
        task: props.tasks[0] || null,
        detecting: false,
        progress: null,
        objLayer: null,
        classSummary: [],
    };
  }

  componentDidMount(){
  }

  componentDidUpdate(){
    if (this.props.isShowed && this.state.loading){
      const {id, project} = this.state.task;
      
      this.loadingReq = $.getJSON(`/api/projects/${project}/tasks/${id}/`)
          .done(res => {
              const { available_assets } = res;
              if (available_assets.indexOf("orthophoto.tif") === -1){
                this.setState({permanentError: _("No orthophoto is available. To use object detection you need an orthophoto.")});
              }
          })
          .fail(() => {
            this.setState({permanentError: _("Cannot retrieve information for task. Are you are connected to the internet?")})
          })
          .always(() => {
            this.setState({loading: false});
            this.loadingReq = null;
          });
    }
  }

  componentWillUnmount(){
    if (this.loadingReq){
      this.loadingReq.abort();
      this.loadingReq = null;
    }
    if (this.detectReq){
      this.detectReq.abort();
      this.detectReq = null;
    }
  }

  handleSelectModel = e => {
    this.setState({model: e.target.value});
  }

  getFormValues = () => {
    const { model } = this.state;

    return {
      model
    };
  }

  buildClassSummary = geojson => {
    const summary = {};
    const unknownLabel = _("Unknown");

    if (geojson && Array.isArray(geojson.features)){
      geojson.features.forEach(feature => {
        const props = feature && feature.properties ? feature.properties : {};
        const label = props['class'] !== undefined && props['class'] !== null && `${props['class']}`.trim() !== ""
          ? props['class']
          : unknownLabel;

        if (!summary[label]) summary[label] = 0;
        summary[label] += 1;
      });
    }

    return Object.keys(summary)
      .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
      .map(label => ({ label, count: summary[label] }));
  }

  addGeoJSON = (geojson, cb) => {
    const { map } = this.props;

    try{
      this.handleRemoveObjLayer();

      const objLayer = L.geoJSON(geojson, {
        onEachFeature: (feature, layer) => {
            if (feature.properties && feature.properties['class'] !== undefined) {
                layer.bindPopup(`<div style="margin-right: 32px;">
                    <b>${_("Label:")}</b> ${feature.properties['class']}<br/>
                    <b>${_("Confidence:")}</b> ${feature.properties.score.toFixed(3)}<br/>
                  </div>
                  `);
            }
        },
        style: feature => {
            // TODO: different colors for different elevations?
            return {color: "red"};
        }
      });

      objLayer.addTo(map);
      objLayer.label = this.state.model;

      this.setState({
        objLayer,
        classSummary: this.buildClassSummary(geojson)
      });

      cb();
    }catch(e){
      cb(e.message);
    }
  }

  handleRemoveObjLayer = () => {
    const { map } = this.props;

    if (this.state.objLayer){
      map.removeLayer(this.state.objLayer);
      this.setState({objLayer: null, classSummary: []});
    }
  }

  saveInputValues = () => {
    // Save settings
    Storage.setItem("last_objdetect_model", this.state.model);
  }

  handleDetect = () => {
    this.handleRemoveObjLayer();
    this.setState({detecting: true, error: "", progress: null});
    const taskId = this.state.task.id;
    this.saveInputValues();

    this.detectReq = $.ajax({
        type: 'POST',
        url: `/api/plugins/objdetect/task/${taskId}/detect`,
        data: this.getFormValues()
    }).done(result => {
        if (result.celery_task_id){
          Workers.waitForCompletion(result.celery_task_id, error => {
            if (error) this.setState({detecting: false, error});
            else{
              Workers.getOutput(result.celery_task_id, (error, geojson) => {
                try{
                  geojson = JSON.parse(geojson);
                }catch(e){
                  error = "Invalid GeoJSON";
                }

                if (error) this.setState({detecting: false, error});
                else{
                  this.addGeoJSON(geojson, e => {
                    if (e) this.setState({error: JSON.stringify(e)});
                    this.setState({detecting: false});
                  });
                }
              });
            }
          }, (_, progress) => {
            this.setState({progress});
          });
        }else if (result.error){
            this.setState({detecting: false, error: result.error});
        }else{
            this.setState({detecting: false, error: "Invalid response: " + result});
        }
    }).fail(error => {
        this.setState({detecting: false, error: JSON.stringify(error)});
    });
  }

  handleDownload = () => {
    Utils.saveAs(JSON.stringify(this.state.objLayer.toGeoJSON(14), null, 4), `${this.state.objLayer.label || "objects"}.geojson`);
  }

  render(){
    const { loading, permanentError, objLayer, detecting, model, progress, classSummary } = this.state;
    const models = [
      {label: _('Cars'), value: 'cars'},
      {label: _('Trees'), value: 'trees'},
      {label: _('Athletic Facilities'), value: 'athletic'},
      {label: _('Boats'), value: 'boats'},
      {label: _('Planes'), value: 'planes'},
      {label: _('Cattle'), value: 'cattle'}
    ]
    
    let content = "";
    if (loading) content = (<span><i className="fa fa-circle-notch fa-spin"></i> {_("Loading…")}</span>);
    else if (permanentError) content = (<div className="alert alert-warning">{permanentError}</div>);
    else{
      const featCount = objLayer ? objLayer.getLayers().length : 0;

      content = (<div>
        <ErrorMessage bind={[this, "error"]} />
        <div className="row model-selector">
            <select className="form-control" value={model} onChange={this.handleSelectModel}>
              {models.map(m => <option value={m.value} key={m.value}>{m.label}</option>)}
            </select>
            <button onClick={this.handleDetect}
                    disabled={detecting} type="button" className="btn btn-sm btn-primary btn-detect">
              {detecting ? <i className="fa fa-spin fa-circle-notch"/> : <i className="fa fa-search fa-fw"/>} {_("Detect")} {detecting && progress !== null ? ` (${progress.toFixed(0)}%)` : ""}
            </button>
        </div>
        
        {objLayer ? <div className="detect-action-buttons">
            <span><strong>{_("Count:")}</strong> {featCount}</span>
            <div>
              {featCount > 0 ? <button onClick={this.handleDownload}
                    type="button" className="btn btn-sm btn-primary btn-download">
                <i className="fa fa-download fa-fw"/> {_("Download")}
              </button> : ""}
              <button onClick={this.handleRemoveObjLayer}
                      type="button" className="btn btn-sm btn-default">
                <i className="fa fa-trash fa-fw"/>
              </button>
            </div>
        </div> : ""}

        {classSummary.length > 0 ? <div className="class-summary">
            <strong>{_("Detected classes:")}</strong>
            <ul>
              {classSummary.map(item => <li key={item.label}>{item.label} ({item.count})</li>)}
            </ul>
        </div> : ""}
      </div>);
    }

    return (<div className="objdetect-panel">
      <span className="close-button" onClick={this.props.onClose}/>
      <div className="title">{_("Object Detection")}</div>
      <hr/>
      {content}
    </div>);
  }
}
