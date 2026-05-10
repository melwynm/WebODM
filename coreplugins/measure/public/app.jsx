import L from 'leaflet';
import 'leaflet-measure-ex/dist/leaflet-measure';
import 'leaflet-measure-ex/dist/leaflet-measure.css';
import './app.scss';
import MeasurePopup from './MeasurePopup';
import Utils from 'webodm/classes/Utils';
import ReactDOM from 'ReactDOM';
import React from 'React';
import $ from 'jquery';
import { _, get_format } from 'webodm/classes/gettext';
import { unitSystem } from 'webodm/classes/Units';

export default class App{
    constructor(map){
        this.map = map;

        const measure = L.control.measure({
          position: 'topright',
          labels:{
            measureDistancesAndAreas: _('Measure volume, area and length'),
            areaMeasurement: _('Measurement'),
            measure: _("Measure"),
            createNewMeasurement: _("Create a new measurement"),
            startCreating: _("Start creating a measurement by adding points to the map"),
            finishMeasurement: _("Finish measurement"),
            lastPoint: _("Last point"),
            area: _("Area"),
            perimeter: _("Perimeter"),
            pointLocation: _("Point location"),
            linearMeasurement: _("Linear measurement"),
            pathDistance: _("Path distance"),
            centerOnArea: _("Center on this area"),
            centerOnLine: _("Center on this line"),
            centerOnLocation: _("Center on this location"),
            cancel: _("Cancel"),
            delete: _("Delete"),
            acres: _("Acres"),
            feet: _("Feet"),
            kilometers: _("Kilometers"),
            hectares: _("Hectares"),
            meters: _("Meters"),
            miles: _("Miles"),
            sqfeet: _("Sq Feet"),
            sqmeters: _("Sq Meters"),
            sqmiles: _("Sq Miles"),
            decPoint: get_format("DECIMAL_SEPARATOR"),
            thousandsSep: get_format("THOUSAND_SEPARATOR")
          },
          popupOptions: Object.assign({}, L.Control.Measure.prototype.options.popupOptions, {
            // Prevent Leaflet from auto-panning the map when showing measurement
            // popups. Auto-pan causes the basemap to move just after clicking,
            // which makes the marker appear in a different on-screen position than
            // the original click.
            autoPan: false
          }),
          primaryLengthUnit: 'meters',
          secondaryLengthUnit: 'feet',
          primaryAreaUnit: 'sqmeters',
          secondaryAreaUnit: 'acres'
        }).addTo(map);
        const measureTitle = _('Measure volume, area and length');
        const measureToggle = measure.$toggle;
        const configureCaptureMarker = marker => {
          if (!marker) return;

          marker.options.keyboard = false;
          marker.options.autoPanOnFocus = false;
          marker.options.bubblingMouseEvents = false;

          if (marker._icon){
            L.DomEvent.off(marker._icon, 'focus', marker._panOnFocus, marker);
            marker._icon.setAttribute('tabindex', '-1');
            marker._icon.setAttribute('aria-hidden', 'true');
          }
        };
        const wrapCaptureMarkerIcon = handler => {
          if (typeof handler !== 'function') return handler;

          return function(){
            configureCaptureMarker(this._captureMarker);
            const result = handler.apply(this, arguments);
            configureCaptureMarker(this._captureMarker);
            return result;
          };
        };
        const wrapMeasureHandler = handler => {
          if (typeof handler !== 'function') return handler;

          return function(e){
            if (e && e.originalEvent){
              e.originalEvent._webodmSuppressMapClick = true;
            }
            if (e){
              L.DomEvent.stop(e);
            }
            return handler.call(this, e);
          };
        };
        const wrapMeasureStart = handler => {
          if (typeof handler !== 'function') return handler;

          return function(){
            const result = handler.apply(this, arguments);
            configureCaptureMarker(this._captureMarker);
            return result;
          };
        };

        if (measureToggle){
          measureToggle.classList.add('map-control-button', 'leaflet-bar-part', 'theme-secondary', 'webodm-measure-toggle');
          measureToggle.setAttribute('title', measureTitle);
          measureToggle.setAttribute('aria-label', measureTitle);
          measureToggle.innerHTML = '<i class="fas fa-ruler-combined" aria-hidden="true"></i>';
        }

        measure._setCaptureMarkerIcon = wrapCaptureMarkerIcon(measure._setCaptureMarkerIcon);
        measure._startMeasure = wrapMeasureStart(measure._startMeasure);
        measure._handleMeasureClick = wrapMeasureHandler(measure._handleMeasureClick);
        measure._handleMeasureDoubleClick = wrapMeasureHandler(measure._handleMeasureDoubleClick);

        measure._getMeasurementDisplayStrings = measurement => {
          const us = unitSystem();

          return {
            lengthDisplay: us.length(measurement.length).toString(),
            areaDisplay: us.area(measurement.area).toString()
          };
        };

        const $btnExport = $(`<br/><a href='#' class='js-start start'>${_("Export Measurements")}</a>`);
        $btnExport.appendTo($(measure.$startPrompt).children("ul.tasks"));
        $btnExport.on('click', () => {
          const features = [];
          map.eachLayer(layer => {
            const mp = layer._measurePopup;
            if (mp){
              features.push(mp.getGeoJSON());
            }
          });

          const geoJSON = {
            type: "FeatureCollection",
            features: features
          };

          Utils.saveAs(JSON.stringify(geoJSON, null, 4), "measurements.geojson")
        });

        map.on('measurepopupshown', ({popupContainer, model, resultFeature}) => {
            // Only modify area popup, length popup is fine as default
            const $container = $("<div/>"),
                  $popup = $(popupContainer);
            
            if (model.area !== 0){
              // Erase measurements for area
              $popup.children("p").empty();
            }
            $popup.children("ul.tasks").before($container);

            ReactDOM.render(<MeasurePopup 
                                model={model}
                                resultFeature={resultFeature} 
                                map={map} />, $container.get(0));
        });
    }
}
