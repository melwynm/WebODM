import io
import json
import os
import tempfile
import uuid
from datetime import datetime
from xml.etree import ElementTree

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from app.api.common import get_and_check_project
from app.plugins import GlobalDataStore
from django.utils.translation import gettext_lazy as _


def _get_store():
    return GlobalDataStore('mission-planner')


def _load_project_missions(project_id):
    store = _get_store()
    data = store.get_json('projects', {})
    project_key = str(project_id)
    missions = data.get(project_key, [])
    # Ensure mission IDs exist
    cleaned = []
    for mission in missions:
        if isinstance(mission, dict) and mission.get('id'):
            cleaned.append(mission)
    if len(cleaned) != len(missions):
        data[project_key] = cleaned
        store.set_json('projects', data)
    return data, cleaned


def _save_project_missions(project_id, data, missions):
    data[str(project_id)] = missions
    _get_store().set_json('projects', data)


def _parse_iso_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    try:
        return datetime.strptime(value, '%Y-%m-%d').date().isoformat()
    except ValueError:
        try:
            return datetime.fromisoformat(value).date().isoformat()
        except ValueError:
            raise ValueError(_('Invalid capture date format. Use YYYY-MM-DD.'))


def _safe_float(value):
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _standardize_feature_collection(geometry):
    if not geometry:
        return None
    if isinstance(geometry, (str, bytes)):
        try:
            geometry = json.loads(geometry)
        except json.JSONDecodeError as exc:
            raise ValueError(_('Invalid GeoJSON payload: %(error)s') % {'error': str(exc)})
    if isinstance(geometry, dict) and 'type' in geometry:
        if geometry['type'] == 'FeatureCollection':
            features = geometry.get('features') or []
        elif geometry['type'] == 'Feature':
            features = [geometry]
        else:
            features = [{
                'type': 'Feature',
                'properties': {},
                'geometry': geometry
            }]
    elif isinstance(geometry, list):
        # Assume already a list of features
        features = geometry
    else:
        raise ValueError(_('Unsupported geometry format.'))

    normalized = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        geom = feature.get('geometry')
        if not geom:
            continue
        geom_type = geom.get('type')
        coords = geom.get('coordinates')
        if not geom_type or coords is None:
            continue
        normalized.append({
            'type': 'Feature',
            'properties': feature.get('properties', {}),
            'geometry': {
                'type': geom_type,
                'coordinates': coords
            }
        })

    if not normalized:
        raise ValueError(_('No valid features found in geometry.'))

    return {
        'type': 'FeatureCollection',
        'features': normalized
    }


KML_NS = {
    'kml': 'http://www.opengis.net/kml/2.2',
    'gx': 'http://www.google.com/kml/ext/2.2'
}


def _parse_kml_coordinates(text):
    if not text:
        return []
    coords = []
    for pair in text.replace('\n', ' ').replace('\t', ' ').split():
        parts = [p for p in pair.split(',') if p]
        if len(parts) < 2:
            continue
        lon = _safe_float(parts[0])
        lat = _safe_float(parts[1])
        if lon is None or lat is None:
            continue
        if len(parts) >= 3:
            alt = _safe_float(parts[2])
            if alt is not None:
                coords.append([lon, lat, alt])
                continue
        coords.append([lon, lat])
    return coords


def _parse_kml(data):
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError(_('Invalid KML file: %(error)s') % {'error': str(exc)})

    features = []
    for placemark in root.findall('.//kml:Placemark', KML_NS):
        properties = {}
        name_el = placemark.find('kml:name', KML_NS)
        if name_el is not None and name_el.text:
            properties['name'] = name_el.text

        geometry = None
        line = placemark.find('.//kml:LineString', KML_NS)
        if line is not None:
            coords_el = line.find('kml:coordinates', KML_NS)
            coords = _parse_kml_coordinates(coords_el.text if coords_el is not None else '')
            if len(coords) >= 2:
                geometry = {
                    'type': 'LineString',
                    'coordinates': coords
                }

        if geometry is None:
            track = placemark.find('.//gx:Track', KML_NS)
            if track is not None:
                coords = []
                for coord_el in track.findall('gx:coord', KML_NS):
                    if coord_el.text:
                        parts = coord_el.text.strip().split()
                        if len(parts) >= 2:
                            lon = _safe_float(parts[0])
                            lat = _safe_float(parts[1])
                            alt = _safe_float(parts[2]) if len(parts) >= 3 else None
                            if lon is not None and lat is not None:
                                if alt is not None:
                                    coords.append([lon, lat, alt])
                                else:
                                    coords.append([lon, lat])
                if len(coords) >= 2:
                    geometry = {
                        'type': 'LineString',
                        'coordinates': coords
                    }

        if geometry is None:
            poly = placemark.find('.//kml:Polygon', KML_NS)
            if poly is not None:
                outer_el = poly.find('.//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', KML_NS)
                outer_coords = _parse_kml_coordinates(outer_el.text if outer_el is not None else '')
                if len(outer_coords) >= 4:
                    inner_coords = []
                    for inner in poly.findall('.//kml:innerBoundaryIs/kml:LinearRing/kml:coordinates', KML_NS):
                        inner_coords.append(_parse_kml_coordinates(inner.text or ''))
                    geometry = {
                        'type': 'Polygon',
                        'coordinates': [outer_coords] + inner_coords
                    }

        if geometry is None:
            point = placemark.find('.//kml:Point', KML_NS)
            if point is not None:
                coords_el = point.find('kml:coordinates', KML_NS)
                coords = _parse_kml_coordinates(coords_el.text if coords_el is not None else '')
                if coords:
                    geometry = {
                        'type': 'Point',
                        'coordinates': coords[0]
                    }

        if geometry is not None:
            features.append({
                'type': 'Feature',
                'properties': properties,
                'geometry': geometry
            })

    if not features:
        raise ValueError(_('No supported geometries were found in the KML file.'))

    return {
        'type': 'FeatureCollection',
        'features': features
    }


def _extract_geojson_from_upload(uploaded_file):
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith('.kml'):
        return _parse_kml(data)
    else:
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = data.decode('utf-8', errors='ignore')
        return _standardize_feature_collection(text)


def _format_mission_payload(request):
    name = request.data.get('name')
    notes = request.data.get('notes')
    capture_date = request.data.get('capture_date') or request.data.get('captureDate')
    source = 'manual'
    geometry = None

    if request.data.get('geometry'):
        geometry = _standardize_feature_collection(request.data.get('geometry'))

    upload = request.FILES.get('plan_file') or request.FILES.get('file')
    if upload is not None:
        geometry = _extract_geojson_from_upload(upload)
        source = 'upload'
        upload_name = upload.name
    else:
        upload_name = None

    if geometry is None:
        raise ValueError(_('A mission plan requires a geometry or a GeoJSON/KML file.'))

    capture_iso = _parse_iso_date(capture_date) if capture_date else None

    return {
        'id': str(uuid.uuid4()),
        'name': name or _('Untitled mission'),
        'notes': notes or '',
        'capture_date': capture_iso,
        'geometry': geometry,
        'source': source,
        'file_name': upload_name,
        'created_at': timezone.now().isoformat(),
        'updated_at': timezone.now().isoformat()
    }


def _update_mission(existing, request):
    updated = existing.copy()
    if 'name' in request.data:
        updated['name'] = request.data.get('name') or existing.get('name') or _('Untitled mission')
    if 'notes' in request.data:
        updated['notes'] = request.data.get('notes') or ''
    capture_date = request.data.get('capture_date') or request.data.get('captureDate')
    if capture_date is not None:
        updated['capture_date'] = _parse_iso_date(capture_date) if capture_date else None
    upload = request.FILES.get('plan_file') or request.FILES.get('file')
    geometry_payload = request.data.get('geometry')
    if upload is not None:
        updated['geometry'] = _extract_geojson_from_upload(upload)
        updated['source'] = 'upload'
        updated['file_name'] = upload.name
    elif geometry_payload is not None:
        if isinstance(geometry_payload, (str, bytes)) and len(str(geometry_payload).strip()) == 0:
            pass
        else:
            updated['geometry'] = _standardize_feature_collection(geometry_payload)
            updated['source'] = 'manual'
            updated['file_name'] = existing.get('file_name')
    updated['updated_at'] = timezone.now().isoformat()
    return updated


@method_decorator(csrf_exempt, name='dispatch')
class ProjectMissionListView(APIView):
    def get(self, request, project_pk=None):
        project = get_and_check_project(request, project_pk)
        _, missions = _load_project_missions(project.id)
        return Response({'project': project.id, 'missions': missions})

    def post(self, request, project_pk=None):
        project = get_and_check_project(request, project_pk, ('change_project', ))
        data, missions = _load_project_missions(project.id)
        try:
            mission = _format_mission_payload(request)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        missions.append(mission)
        _save_project_missions(project.id, data, missions)
        return Response({'mission': mission}, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name='dispatch')
class ProjectMissionDetailView(APIView):
    def get_mission(self, project_id, mission_id):
        data, missions = _load_project_missions(project_id)
        for mission in missions:
            if mission.get('id') == mission_id:
                return data, missions, mission
        return data, missions, None

    def patch(self, request, project_pk=None, mission_id=None):
        project = get_and_check_project(request, project_pk, ('change_project', ))
        data, missions, mission = self.get_mission(project.id, mission_id)
        if mission is None:
            return Response({'error': _('Mission not found.')}, status=status.HTTP_404_NOT_FOUND)
        try:
            updated = _update_mission(mission, request)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        missions = [updated if m.get('id') == mission_id else m for m in missions]
        _save_project_missions(project.id, data, missions)
        return Response({'mission': updated})

    def delete(self, request, project_pk=None, mission_id=None):
        project = get_and_check_project(request, project_pk, ('change_project', ))
        data, missions, mission = self.get_mission(project.id, mission_id)
        if mission is None:
            return Response({'error': _('Mission not found.')}, status=status.HTTP_404_NOT_FOUND)
        missions = [m for m in missions if m.get('id') != mission_id]
        _save_project_missions(project.id, data, missions)
        return Response(status=status.HTTP_204_NO_CONTENT)
