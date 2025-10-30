import React from 'react';
import '../css/MapPreview.scss';
import 'leaflet/dist/leaflet.css';
import Leaflet from 'leaflet';
import PropTypes from 'prop-types';
import $ from 'jquery';
import ErrorMessage from './ErrorMessage';
import Utils from '../classes/Utils';
import '../vendor/leaflet/Leaflet.Autolayers/css/leaflet.auto-layers.css';
import '../vendor/leaflet/Leaflet.Autolayers/leaflet-autolayers';
import Basemaps from '../classes/Basemaps';
import Standby from './Standby';
import exifr from '../vendor/exifr';
import '../vendor/leaflet/leaflet-markers-canvas';
import { _, interpolate } from '../classes/gettext';
import CropButton from './CropButton';
import 'leaflet-fullscreen/dist/Leaflet.fullscreen';
import 'leaflet-fullscreen/dist/leaflet.fullscreen.css';
import proj4 from 'proj4';

class MapPreview extends React.Component {
  static defaultProps = {
    getFiles: null,
    onPolygonChange: () => {},
    onImagesBboxChanged: () => {}
  };
    
  static propTypes = {
    getFiles: PropTypes.func.isRequired,
    onPolygonChange: PropTypes.func,
    onImagesBboxChanged: PropTypes.func
  };

  constructor(props) {
    super(props);
    
    this.state = {
        showLoading: true,
        error: ""
    };

    this.basemaps = {};
    this.mapBounds = null;
    this.exifData = [];
    this.gcpData = [];
    this.geoData = [];
    this.hasTimestamp = true;
    this.MaxImagesPlot = 10000;
    this.gcpLayer = null;
    this.geoLayer = null;
  }

  componentDidMount() {
    this.map = Leaflet.map(this.container, {
      scrollWheelZoom: true,
      positionControl: false,
      zoomControl: false,
      minZoom: 0,
      maxZoom: 24
    });

    this.group = L.layerGroup();
    this.group.addTo(this.map);

    // For some reason, in production this class is not added (but we need it)
    // leaflet bug?
    $(this.container).addClass("leaflet-touch");

    //add zoom control with your options
    Leaflet.control.zoom({
         position:'bottomleft'
    }).addTo(this.map);

    this.basemaps = {};
    
    Basemaps.forEach((src, idx) => {
    const { url, ...props } = src;
    const tileProps = Utils.clone(props);
    tileProps.maxNativeZoom = tileProps.maxZoom;
    tileProps.maxZoom = tileProps.maxZoom + 99;
    const layer = L.tileLayer(url, tileProps);

    if (idx === 2) {
        layer.addTo(this.map);
    }

    this.basemaps[props.label] = layer;
    });

    const customLayer = L.layerGroup();
    customLayer.on("add", a => {
        const defaultCustomBm = window.localStorage.getItem('lastCustomBasemap') || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
      
        let url = window.prompt([_('Enter a tile URL template. Valid coordinates are:'),
_('{z}, {x}, {y} for Z/X/Y tile scheme'),
_('{-y} for flipped TMS-style Y coordinates'),
'',
_('Example:'),
'https://tile.openstreetmap.org/{z}/{x}/{y}.png'].join("\n"), defaultCustomBm);
        
    if (url){
        customLayer.clearLayers();
        const l = L.tileLayer(url, {
        maxNativeZoom: 24,
        maxZoom: 99,
        minZoom: 0
        });
        customLayer.addLayer(l);
        l.bringToBack();
        window.localStorage.setItem('lastCustomBasemap', url);
    }
    });
    this.basemaps[_("Custom")] = customLayer;
    this.basemaps[_("None")] = L.layerGroup();

    this.autolayers = Leaflet.control.autolayers({
      overlays: {},
      selectedOverlays: [],
      baseLayers: this.basemaps
    }).addTo(this.map);

    this.map.addControl(new L.Control.Fullscreen({
        position: 'bottomleft'
    }));

    var fullscreenchange;

    if ('onfullscreenchange' in document) {
        fullscreenchange = 'fullscreenchange';
    } else if ('onmozfullscreenchange' in document) {
        fullscreenchange = 'mozfullscreenchange';
    } else if ('onwebkitfullscreenchange' in document) {
        fullscreenchange = 'webkitfullscreenchange';
    } else if ('onmsfullscreenchange' in document) {
        fullscreenchange = 'MSFullscreenChange';
    }

    if (fullscreenchange) {
        var onFullscreenChange = L.bind(this.map._onFullscreenChange, this.map);

        this.map.whenReady(function () {
            L.DomEvent.on(document, fullscreenchange, onFullscreenChange);
        });

        this.map.on('unload', function () {
            L.DomEvent.off(document, fullscreenchange, onFullscreenChange);
        });
    }

    this.cropButton = new CropButton({
      position:'bottomleft',
      title: _("Set Reconstruction Area (optional)"),
      group: this.group,
      onPolygonCreated: this.onPolygonCreated,
      onPolygonChange: this.props.onPolygonChange
    });
    this.map.addControl(this.cropButton);

    this.map.fitBounds([
     [13.772919746115805,
     45.664640939831735],
     [13.772825784981254,
     45.664591558975154]]);
    this.map.attributionControl.setPrefix("");

    this.loadNewFiles();
  }

  onPolygonCreated = (polygon) => {
    const popupContainer = L.DomUtil.create('div');
    popupContainer.className = "crop-button-delete";
    const deleteLink = L.DomUtil.create('a');
    deleteLink.href = "javascript:void(0)";
    deleteLink.innerHTML = `<i class="fa fa-trash"></i> ${_("Delete")}`;
    deleteLink.onclick = (e) => {
        L.DomEvent.stop(e);
        this.cropButton.deletePolygon();
    };
    popupContainer.appendChild(deleteLink);

    polygon.bindPopup(popupContainer);
  }

  sampled = (arr, N) => {
    // Return a uniformly sampled array with max N elements
    if (arr.length <= N) return arr;
    else{
      const res = [];
      const step = arr.length / N;
      for (let i = 0; i < N; i++){
        res.push(arr[Math.floor(i * step)]);
      }

      return res;
    }
  };

  loadNewFiles = () => {
    this.setState({showLoading: true});

    if (this.imagesGroup){
      this.map.removeLayer(this.imagesGroup);
      this.imagesGroup = null;
    }

    if (this.gcpLayer){
      this.map.removeLayer(this.gcpLayer);
      this.gcpLayer = null;
    }

    if (this.geoLayer){
      this.map.removeLayer(this.geoLayer);
      this.geoLayer = null;
    }

    this.exifData = [];
    this.gcpData = [];
    this.geoData = [];
    this.hasTimestamp = true;

    this.readExifData().then(() => {
      const images = this.sampled(this.exifData, this.MaxImagesPlot).map(exif => {
        let layer = L.circleMarker([exif.gps.latitude, exif.gps.longitude], {
          radius: 8,
          fillOpacity: 1,
          color: "#fcfcff", //ff9e67
          fillColor: "#4b96f3",
          weight: 1.5,
        }).bindPopup(exif.image.name);
        layer.feature = layer.feature || {};
        layer.feature.type = "Feature";
        layer.feature.properties = layer.feature.properties || {};
        layer.feature.properties["Filename"] = exif.image.name;
        if (this.hasTimestamp) layer.feature.properties["Timestamp"] = exif.timestamp;
        return layer;
      });

      if (this.capturePath){
        this.map.removeLayer(this.capturePath);
        this.capturePath = null;
      }

      // Only show line if we have reliable date/time info
      if (this.hasTimestamp && this.exifData.length > 0){
        let coords = this.exifData.map(exif => [exif.gps.latitude, exif.gps.longitude]);
        this.capturePath = L.polyline(coords, {
          color: "#4b96f3",
          weight: 3
        });
        this.capturePath.addTo(this.map);
      }

      if (images.length > 0){
        this.imagesGroup = L.featureGroup(images).addTo(this.map);
      }

      const gcpMarkers = this.gcpData.map((entry, index) => {
        const marker = L.circleMarker([entry.gps.latitude, entry.gps.longitude], {
          radius: 7,
          fillOpacity: 1,
          color: "#d9480f",
          fillColor: "#ffa94d",
          weight: 1.5,
        }).bindPopup(entry.label);
        marker.feature = marker.feature || {};
        marker.feature.type = "Feature";
        marker.feature.properties = marker.feature.properties || {};
        marker.feature.properties["Type"] = "GCP";
        marker.feature.properties["Label"] = entry.label;
        if (entry.source) marker.feature.properties["Source"] = entry.source;
        if (entry.gps.altitude !== null) marker.feature.properties["Altitude"] = entry.gps.altitude;
        return marker;
      });

      if (gcpMarkers.length > 0){
        this.gcpLayer = L.featureGroup(gcpMarkers).addTo(this.map);
        this.gcpLayer.bringToFront();
      }

      const geoMarkers = this.geoData.map((entry, index) => {
        const marker = L.circleMarker([entry.gps.latitude, entry.gps.longitude], {
          radius: 7,
          fillOpacity: 1,
          color: "#2f9e44",
          fillColor: "#51cf66",
          weight: 1.5,
        }).bindPopup(entry.label);
        marker.feature = marker.feature || {};
        marker.feature.type = "Feature";
        marker.feature.properties = marker.feature.properties || {};
        marker.feature.properties["Type"] = "Geo";
        marker.feature.properties["Label"] = entry.label;
        if (entry.source) marker.feature.properties["Source"] = entry.source;
        if (entry.gps.altitude !== null) marker.feature.properties["Altitude"] = entry.gps.altitude;
        return marker;
      });

      if (geoMarkers.length > 0){
        this.geoLayer = L.featureGroup(geoMarkers).addTo(this.map);
        this.geoLayer.bringToFront();
      }

      const bboxData = this.computeBbox([
        ...this.exifData,
        ...this.gcpData,
        ...this.geoData
      ]);

      if (bboxData){
        const bounds = L.latLngBounds(
          [
            [bboxData[1], bboxData[0]],
            [bboxData[3], bboxData[2]]
          ]
        );
        if (bounds.isValid()){
          this.map.fitBounds(bounds);
        }
      }

      this.props.onImagesBboxChanged(bboxData);

      this.setState({showLoading: false});

    }).catch(e => {
      this.setState({showLoading: false, error: e.message});
    });
  }

  computeBbox = data => {
    // minx, miny, maxx, maxy
    let bbox = [Infinity, Infinity, -Infinity, -Infinity];
    let hasPoints = false;
    data.forEach(ed => {
      if (ed && ed.gps && this.isValidLatLon(ed.gps.latitude, ed.gps.longitude)){
        hasPoints = true;
        bbox[0] = Math.min(bbox[0], ed.gps.longitude);
        bbox[1] = Math.min(bbox[1], ed.gps.latitude);
        bbox[2] = Math.max(bbox[2], ed.gps.longitude);
        bbox[3] = Math.max(bbox[3], ed.gps.latitude);
      }
    });
    return hasPoints ? bbox : null;
  }

  readExifData = () => {
    const files = this.props.getFiles();
    const images = [];
    const gcpFiles = [];
    const geoFiles = [];

    for (let i = 0; i < files.length; i++){
      const f = files[i];
      const mime = f.type || "";
      const name = (f.name || "").toLowerCase();

      if (mime.indexOf("image") === 0) images.push(f);

      if (name){
        if (name === 'gcp_list.txt' || name === 'gcp.txt' || name === 'ground_control_points.txt' || name.endsWith('_gcp.txt')){
          gcpFiles.push(f);
        }else if (name === 'geo.txt' || name.endsWith('_geo.txt') || name === 'coords.txt'){
          geoFiles.push(f);
        }
      }
    }

    const options = {
      ifd0: false,
      exif: [0x9003],
      gps: [0x0001, 0x0002, 0x0003, 0x0004, 0x0005, 0x0006],
      interop: false,
      ifd1: false // thumbnail
    };

    const imagePromise = new Promise((resolve) => {
      const next = (i) => {
        if (i < images.length - 1) parseImage(i + 1);
        else{
          if (this.hasTimestamp){
            this.exifData.sort((a, b) => {
              if (a.timestamp < b.timestamp) return -1;
              else if (a.timestamp > b.timestamp) return 1;
              else return 0;
            });
          }
          resolve();
        }
      };

      const parseImage = i => {
        const img = images[i];
        exifr.parse(img, options).then(exif => {
          if (!exif.latitude || !exif.longitude){
            next(i);
            return;
          }

          let dateTime = exif.DateTimeOriginal;
          let timestamp = null;
          if (dateTime && dateTime.getTime) timestamp = dateTime.getTime();
          if (!timestamp) this.hasTimestamp = false;

          this.exifData.push({
            image: img,
            gps: {
              latitude: exif.latitude,
              longitude: exif.longitude,
              altitude: exif.GPSAltitude !== undefined ? exif.GPSAltitude : null,
            },
            timestamp
          });

          next(i);
        }).catch((e) => {
          console.warn(e);
          next(i);
        });
      };

      if (images.length > 0) parseImage(0);
      else resolve();
    });

    const gcpPromise = Promise.all(gcpFiles.map(this.parseGcpFile)).then(results => {
      this.gcpData = results.reduce((acc, current) => acc.concat(current), []);
    });

    const geoPromise = Promise.all(geoFiles.map(this.parseGeoFile)).then(results => {
      this.geoData = results.reduce((acc, current) => acc.concat(current), []);
    });

    return Promise.all([imagePromise, gcpPromise, geoPromise]);
  }

  looksLikeSrsLine = (line) => {
    if (!line) return false;
    const upper = line.trim().toUpperCase();
    return upper.startsWith('EPSG:') || upper.startsWith('+PROJ=') || upper === 'WGS84' || upper.includes('LONG/LAT') || upper.includes('LAT/LONG') || upper.includes('LATLONG');
  };

  splitSrsAndData = (text) => {
    const lines = text.split(/\r?\n/).map(line => line.trim());
    let srs = '';
    const data = [];

    for (let i = 0; i < lines.length; i++){
      const line = lines[i];
      if (line === '' || line[0] === '#') continue;
      if (!srs && this.looksLikeSrsLine(line)){
        srs = line;
        continue;
      }
      data.push(line);
    }

    return { srs, data };
  };

  toNumber = (value) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  parseAltitude = (value) => {
    const parsed = this.toNumber(value);
    return parsed !== null ? parsed : null;
  };

  isValidLatLon = (lat, lon) => Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;

  guessLonLat = (x, y) => {
    if (this.isValidLatLon(y, x)) return [x, y];
    if (this.isValidLatLon(x, y)) return [y, x];
    return null;
  };

  convertToLatLng = (srs, x, y) => {
    const coordX = this.toNumber(x);
    const coordY = this.toNumber(y);
    if (coordX === null || coordY === null) return null;

    if (srs){
      let fromSrs = srs.trim();
      if (fromSrs.toUpperCase() === 'WGS84'){
        fromSrs = 'EPSG:4326';
      }
      try{
        const [lon, lat] = proj4(fromSrs, 'EPSG:4326', [coordX, coordY]);
        if (this.isValidLatLon(lat, lon)){
          return [lon, lat];
        }
      }catch (error){
        console.warn(`Unable to convert coordinates using ${fromSrs}: ${error.message}`);
      }
    }

    return this.guessLonLat(coordX, coordY);
  };

  extractGcpsFromText = (text, sourceName) => {
    const { srs, data } = this.splitSrsAndData(text);
    const points = [];

    data.forEach((line, index) => {
      const parts = line.split(/\s+/);
      if (parts.length < 3) return;

      let coordStart = 0;
      let label = `GCP ${index + 1}`;
      const firstNumber = this.toNumber(parts[0]);
      const secondNumber = parts.length > 1 ? this.toNumber(parts[1]) : null;

      if (firstNumber === null || secondNumber === null){
        if (parts.length < 4) return;
        coordStart = 1;
        label = parts[0];
      }else if (parts.length >= 6){
        label = parts[5];
      }

      if (parts.length <= coordStart + 2) return;

      const coords = this.convertToLatLng(srs, parts[coordStart], parts[coordStart + 1]);
      if (!coords) return;

      const altitude = this.parseAltitude(parts[coordStart + 2]);

      points.push({
        gps: {
          latitude: coords[1],
          longitude: coords[0],
          altitude
        },
        label,
        source: sourceName,
        type: 'gcp'
      });
    });

    return points;
  };

  parseGcpFile = async (file) => {
    try{
      const text = await file.text();
      return this.extractGcpsFromText(text, file.name);
    }catch (error){
      console.warn(`Unable to parse ${file.name}: ${error.message}`);
      return [];
    }
  };

  extractGeoPointsFromText = (text, sourceName) => {
    const { srs, data } = this.splitSrsAndData(text);
    const points = [];

    data.forEach((line, index) => {
      const parts = line.split(/\s+/);
      if (parts.length < 2) return;

      let coordStart = 0;
      let label = `${sourceName || 'Geo'} ${index + 1}`;
      const firstNumber = this.toNumber(parts[0]);
      const secondNumber = this.toNumber(parts[1]);

      if (firstNumber === null || secondNumber === null){
        if (parts.length < 4) return;
        coordStart = 1;
        label = parts[0];
      }

      if (parts.length <= coordStart + 1) return;

      const coords = this.convertToLatLng(srs, parts[coordStart], parts[coordStart + 1]);
      if (!coords) return;

      const altitude = parts.length > coordStart + 2 ? this.parseAltitude(parts[coordStart + 2]) : null;

      points.push({
        gps: {
          latitude: coords[1],
          longitude: coords[0],
          altitude
        },
        label,
        source: sourceName,
        type: 'geo'
      });
    });

    return points;
  };

  parseGeoFile = async (file) => {
    try{
      const text = await file.text();
      return this.extractGeoPointsFromText(text, file.name);
    }catch (error){
      console.warn(`Unable to parse ${file.name}: ${error.message}`);
      return [];
    }
  };

  componentWillUnmount() {
    this.map.remove();
  }

  getCropPolygon = () => {
    return this.cropButton.getCropPolygon();
  }

  setAlignmentPolygon = (task) => {
    if (this.alignPoly){
      this.map.removeLayer(this.alignPoly);
      this.alignPoly = null;
    }

    if (!task || !task.extent){
      if (this.imagesGroup) this.map.fitBounds(this.imagesGroup.getBounds());
      return;
    }

    const [xmin, ymin, xmax, ymax] = task.extent;
    
    this.alignPoly = L.polygon([
      [ymin, xmin],
      [ymax, xmin],
      [ymax, xmax],
      [ymin, xmax],
      [ymin, xmin]
    ], {
      clickable: true,
      weight: 3,
      opacity: 0.9,
      color: "#808f9b",
      fillColor: "#808f9b",
      fillOpacity: 0.2
    }).bindPopup(task.name).addTo(this.map);

    this.alignPoly.bringToBack();
    this.map.fitBounds(this.alignPoly.getBounds());
  }

  download = format => {
    let output = "";
    let filename = `images.${format}`;
    if (format === "geo"){
      filename = "geo.txt";
    }

    const feats = {
      type: "FeatureCollection",
      features: this.exifData.map(ed => {
        return {
          type: "Feature",
          properties: {
            Filename: ed.image.name,
            Timestamp: ed.timestamp
          },
          geometry:{
            type: "Point",
            coordinates: [
              ed.gps.longitude,
              ed.gps.latitude,
              ed.gps.altitude !== null ? ed.gps.altitude : 0
            ]
          }
        }
      })
    };

    if (format === 'geojson'){
      output = JSON.stringify(feats, null, 4);
    }else if (format === 'csv'){
      output = `Filename,Timestamp,Latitude,Longitude,Altitude\r\n${feats.features.map(feat => {
        return `${feat.properties.Filename},${feat.properties.Timestamp},${feat.geometry.coordinates[1]},${feat.geometry.coordinates[0]},${feat.geometry.coordinates[2]}`
      }).join("\r\n")}`;
    }else if (format === 'geo'){
      output = `EPSG:4326\r\n${feats.features.map(feat => {
        return `${feat.properties.Filename} ${feat.geometry.coordinates[0]} ${feat.geometry.coordinates[1]} ${feat.geometry.coordinates[2]}`
      }).join("\r\n")}`;
    }else{
      console.error("Invalid format");
    }

    Utils.saveAs(output, filename);
  }

  render() {
    return (
      <div style={{height: "280px"}} className="map-preview">
        <ErrorMessage bind={[this, 'error']} />

        <Standby 
            message={_("Plotting GPS locations...")}
            show={this.state.showLoading}
            />

        {this.state.error === "" && this.exifData.length > this.MaxImagesPlot ? 
        <div className="plot-warning btn-warning" title={interpolate(_("For performance reasons, only %(num)s images are plotted"), {num: this.MaxImagesPlot})}>
          <i className="fa fa-exclamation-triangle"></i>
        </div>
        : ""}

        {this.state.error === "" ? <div className="download-control">
          <button title={_("Download")} type="button" className="btn btn-sm btn-secondary dropdown-toggle" data-toggle="dropdown">
            <i className="fa fa-download"></i>
          </button>
          <ul className="dropdown-menu">
            <li>
              <a href="javascript:void(0);" onClick={() => this.download('geojson')}><i className="fas fa-map fa-fw"></i> {_("GeoJSON")}</a>
              <a href="javascript:void(0);" onClick={() => this.download('csv')}><i className="fas fa-file-alt fa-fw"></i> {_("CSV")}</a>
              <a href="javascript:void(0);" onClick={() => this.download('geo')}><i className="fas fa-file-alt fa-fw"></i> {_("Geolocation File")}</a>
            </li>
          </ul>
        </div> : ""}

        <div 
          style={{height: "100%"}}
          ref={(domNode) => (this.container = domNode)}
        >
          
        </div>


      </div>
    );
  }
}

export default MapPreview;
