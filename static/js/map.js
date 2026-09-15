document.addEventListener('DOMContentLoaded', function() {
    const mapContainer = document.getElementById('india-map');
    if (!mapContainer) return;

    // Center map around central India (22.5 N, 79.5 E)
    const map = L.map('india-map').setView([22.5, 79.5], 5);

    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors | ProjectPulse AI',
        maxZoom: 18
    }).addTo(map);

    // Fetch project markers from API
    fetch('/api/map-data')
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                renderMarkers(map, data.markers);
            }
        })
        .catch(err => console.error('Error loading map data:', err));
});

function renderMarkers(map, markers) {
    const colorMap = {
        'LOW': '#10b981',
        'MEDIUM': '#f59e0b',
        'HIGH': '#f97316',
        'CRITICAL': '#ef4444'
    };

    markers.forEach(p => {
        const color = colorMap[p.risk_level] || '#3b82f6';
        
        // Custom circle marker
        const circle = L.circleMarker([p.lat, p.lng], {
            radius: p.risk_level === 'CRITICAL' ? 10 : 8,
            fillColor: color,
            color: '#ffffff',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.85
        }).addTo(map);

        // Rich Popup Card
        const popupContent = `
            <div style="min-width: 240px; font-family: system-ui, sans-serif;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-size: 0.75rem; font-family: monospace; background: #e2e8f0; padding: 2px 6px; border-radius: 4px;">${p.code}</span>
                    <span style="font-size: 0.75rem; font-weight: bold; color: ${color};">${p.risk_level} RISK</span>
                </div>
                <strong style="font-size: 0.95rem; color: #0f172a; display: block; margin-bottom: 4px;">${p.name}</strong>
                <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 8px;">${p.state} &bull; ${p.sector}</div>
                
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; font-size: 0.82rem; margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 3px;">
                        <span>Physical Progress:</span>
                        <strong>${p.physical_progress}%</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 3px;">
                        <span>Delay Risk:</span>
                        <strong style="color: ${p.delay_prob >= 70 ? '#ef4444' : '#0f172a'}">${p.delay_prob}%</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>Cost Overrun Risk:</span>
                        <strong style="color: ${p.cost_prob >= 70 ? '#ef4444' : '#0f172a'}">${p.cost_prob}%</strong>
                    </div>
                </div>

                <a href="/projects/${p.id}" style="display: block; text-align: center; background: #1d3557; color: #ffffff; text-decoration: none; padding: 5px; border-radius: 4px; font-size: 0.82rem; font-weight: 600;">
                    View Project Intelligence
                </a>
            </div>
        `;

        circle.bindPopup(popupContent);
    });
}
