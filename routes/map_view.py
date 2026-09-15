from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from database.models import Project
from services.rbac_service import get_scoped_projects_query

map_bp = Blueprint('map_view', __name__)

@map_bp.route('/map')
@login_required
def index():
    return render_template('map.html')

@map_bp.route('/api/map-data')
@login_required
def api_map_data():
    query = get_scoped_projects_query(current_user)
    projects = query.all()
    
    # State center coordinates for fallback if exact lat/long missing
    STATE_COORDS = {
        'Maharashtra': (19.7515, 75.7139),
        'Telangana': (17.8749, 78.1008),
        'Andhra Pradesh': (15.9129, 79.7400),
        'Karnataka': (15.3173, 75.7139),
        'Tamil Nadu': (11.1271, 78.6569),
        'Kerala': (10.8505, 76.2711),
        'Gujarat': (22.2587, 71.1924),
        'Rajasthan': (27.0238, 74.2179),
        'Uttar Pradesh': (26.8467, 80.9462),
        'Madhya Pradesh': (22.9734, 78.6569),
        'Odisha': (20.9517, 85.0985),
        'West Bengal': (22.9868, 87.8550),
        'Bihar': (25.0961, 85.3131),
        'Delhi': (28.7041, 77.1025),
        'Haryana': (29.0588, 76.0856),
        'Punjab': (31.1471, 75.3412),
        'Assam': (26.2006, 92.9376),
        'Jammu & Kashmir': (33.7782, 76.5762)
    }
    
    # Minimum required marker fields only
    markers = []
    for p in projects:
        lat = p.latitude
        lng = p.longitude
        if lat is None or lng is None:
            coords = STATE_COORDS.get(p.state, (20.5937, 78.9629))
            lat, lng = coords
            
        markers.append({
            'id': p.id,
            'code': p.project_code,
            'name': p.project_name,
            'sector': p.sector,
            'state': p.state,
            'lat': lat,
            'lng': lng,
            'risk_level': p.risk_level,
            'delay_prob': round(p.delay_probability, 1),
            'cost_prob': round(p.cost_overrun_probability, 1),
            'physical_progress': p.physical_progress
        })
        
    return jsonify({
        'status': 'success',
        'count': len(markers),
        'markers': markers
    })
