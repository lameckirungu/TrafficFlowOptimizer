// Global variables
let trafficMap = null;
let intersectionMarkers = {};
let predictionMarkers = {};
let showPredictionsOnMap = false;

/**
 * Initialize the traffic map
 * @param {Array} intersections - List of intersections
 */
function initializeTrafficMap(intersections) {
    // Create map
    trafficMap = L.map('traffic-map').setView([40.7128, -74.0060], 14);
    
    // Add dark-themed tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(trafficMap);
    
    // Add intersections to the map
    addIntersectionsToMap(intersections);
    
    // Set up event listeners
    document.addEventListener('mapDataUpdated', function(e) {
        updateTrafficOnMap(e.detail);
    });
    
    document.addEventListener('mapPredictionsUpdated', function(e) {
        updatePredictionsOnMap(e.detail);
    });
    
    document.addEventListener('mapUpdateRequested', function(e) {
        showPredictionsOnMap = e.detail.showPredictions;
        togglePredictionVisibility(showPredictionsOnMap);
    });
    
    // Fix map display issue when tab becomes visible
    document.addEventListener('visibilitychange', function() {
        if (!document.hidden && trafficMap) {
            trafficMap.invalidateSize();
        }
    });
    
    // Handle tab activation for Bootstrap tabs
    document.querySelectorAll('button[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', function() {
            trafficMap.invalidateSize();
        });
    });
}

/**
 * Add intersections to the map
 * @param {Array} intersections - List of intersections
 */
function addIntersectionsToMap(intersections) {
    if (!trafficMap || !intersections) return;
    
    // Create a bounds object to fit all intersections
    const bounds = L.latLngBounds();
    
    // Add each intersection as a marker
    intersections.forEach(intersection => {
        const latLng = L.latLng(intersection.location_lat, intersection.location_lng);
        
        // Create marker with intersection details
        const marker = L.circle(latLng, {
            color: '#3388ff',
            fillColor: '#3388ff',
            fillOpacity: 0.5,
            radius: 50
        }).addTo(trafficMap);
        
        // Create popup content
        const popupContent = `
            <div class="intersection-popup">
                <h6>${intersection.name}</h6>
                <p>ID: ${intersection.id}</p>
                <p>${intersection.num_roads}-way intersection</p>
                <button class="btn btn-sm btn-primary view-details-btn" 
                        data-id="${intersection.id}">View Details</button>
            </div>
        `;
        
        marker.bindPopup(popupContent);
        
        marker.on('click', function() {
            // When marker is clicked, show signals for this intersection
            const filter = document.getElementById('intersection-filter');
            if (filter) {
                filter.value = intersection.id;
                filter.dispatchEvent(new Event('change'));
            }
        });
        
        // Store marker reference
        intersectionMarkers[intersection.id] = {
            marker: marker,
            directions: {}
        };
        
        // Add to bounds
        bounds.extend(latLng);
    });
    
    // Fit map to bounds with padding
    trafficMap.fitBounds(bounds, { padding: [50, 50] });
}

/**
 * Update traffic data visualization on the map
 * @param {Object} intersectionData - Traffic data organized by intersection
 */
function updateTrafficOnMap(intersectionData) {
    if (!trafficMap || !intersectionData) return;
    
    // Update each intersection marker
    Object.values(intersectionData).forEach(intersection => {
        const id = intersection.id;
        const markerInfo = intersectionMarkers[id];
        
        if (!markerInfo) return;
        
        const marker = markerInfo.marker;
        
        // Calculate intersection metrics
        let totalVehicles = 0;
        let avgWaitTime = 0;
        let maxQueueLength = 0;
        let directionCount = 0;
        let hasEmergency = false;
        
        // Process each direction
        Object.entries(intersection.directions).forEach(([direction, data]) => {
            totalVehicles += data.vehicle_count || 0;
            avgWaitTime += data.wait_time || 0;
            maxQueueLength = Math.max(maxQueueLength, data.queue_length || 0);
            directionCount++;
            
            // Check if this is an emergency direction (this would need to be included in the data)
            if (data.has_emergency) {
                hasEmergency = true;
            }
            
            // Update or create direction indicators
            updateDirectionIndicator(id, direction, data);
        });
        
        // Calculate average wait time
        if (directionCount > 0) {
            avgWaitTime /= directionCount;
        }
        
        // Update marker appearance based on traffic
        const congestionLevel = getCongestionLevel(avgWaitTime, maxQueueLength);
        
        // Update marker color based on congestion
        let color = '#3388ff';  // Default blue
        let radius = 50;        // Default radius
        
        switch (congestionLevel) {
            case 'high':
                color = '#dc3545';  // Red for high congestion
                radius = 80;
                break;
            case 'medium':
                color = '#ffc107';  // Yellow for medium congestion
                radius = 65;
                break;
            case 'low':
                color = '#28a745';  // Green for low congestion
                break;
        }
        
        // Emergency vehicles get a special indicator
        if (hasEmergency) {
            color = '#9c27b0';  // Purple for emergency
            radius = 90;
        }
        
        // Update marker
        marker.setStyle({
            color: color,
            fillColor: color,
            radius: radius
        });
        
        // Update popup content
        const popupContent = `
            <div class="intersection-popup">
                <h6>Intersection ${id}</h6>
                <p>Vehicles: ${totalVehicles}</p>
                <p>Avg Wait: ${avgWaitTime.toFixed(1)}s</p>
                <p>Max Queue: ${maxQueueLength}</p>
                <p>Congestion: <span class="badge bg-${getBadgeColor(congestionLevel)}">${congestionLevel.toUpperCase()}</span></p>
                ${hasEmergency ? '<p class="text-danger fw-bold">⚠️ EMERGENCY VEHICLE</p>' : ''}
                <button class="btn btn-sm btn-primary view-details-btn" 
                        data-id="${id}">View Details</button>
            </div>
        `;
        
        // Update popup if it's open
        const popup = marker.getPopup();
        if (popup && popup.isOpen()) {
            popup.setContent(popupContent);
        } else {
            marker.bindPopup(popupContent);
        }
    });
}

/**
 * Update direction indicators for an intersection
 * @param {number} intersectionId - Intersection ID
 * @param {string} direction - Direction (N, S, E, W)
 * @param {Object} data - Traffic data for this direction
 */
function updateDirectionIndicator(intersectionId, direction, data) {
    const markerInfo = intersectionMarkers[intersectionId];
    if (!markerInfo || !markerInfo.marker) return;
    
    // Get base position
    const baseLatLng = markerInfo.marker.getLatLng();
    
    // Define offset based on direction
    const offsets = {
        'N': [0, 0.0003],
        'S': [0, -0.0003],
        'E': [0.0003, 0],
        'W': [-0.0003, 0]
    };
    
    const offset = offsets[direction] || [0, 0];
    const latLng = L.latLng(baseLatLng.lat + offset[1], baseLatLng.lng + offset[0]);
    
    // Create or update direction indicator
    if (!markerInfo.directions[direction]) {
        // Create new direction indicator
        const dirMarker = L.circle(latLng, {
            color: '#ffffff',
            fillColor: '#ffffff',
            fillOpacity: 0.8,
            radius: 10,
            weight: 1
        }).addTo(trafficMap);
        
        // Store reference
        markerInfo.directions[direction] = dirMarker;
    } else {
        // Update existing marker
        const dirMarker = markerInfo.directions[direction];
        dirMarker.setLatLng(latLng);
        
        // Update color based on congestion
        let color = '#ffffff';  // Default white
        
        if (data.wait_time > 45 && data.queue_length > 10) {
            color = '#dc3545';  // Red for congestion
        } else if (data.wait_time > 20 || data.queue_length > 5) {
            color = '#ffc107';  // Yellow for moderate traffic
        } else {
            color = '#28a745';  // Green for light traffic
        }
        
        dirMarker.setStyle({
            color: color,
            fillColor: color
        });
        
        // Create popup content
        const popupContent = `
            <div class="direction-popup">
                <h6>Direction: ${getDirectionName(direction)}</h6>
                <p>Vehicles: ${data.vehicle_count}</p>
                <p>Wait Time: ${data.wait_time.toFixed(1)}s</p>
                <p>Queue: ${data.queue_length} vehicles</p>
                <p>Speed: ${data.average_speed.toFixed(1)} km/h</p>
            </div>
        `;
        
        dirMarker.bindPopup(popupContent);
    }
}

/**
 * Update predictions on the map
 * @param {Array} predictions - Traffic predictions
 */
function updatePredictionsOnMap(predictions) {
    if (!trafficMap || !predictions || !showPredictionsOnMap) return;
    
    // Clear existing prediction markers
    clearPredictionMarkers();
    
    // Add new prediction markers
    predictions.forEach(prediction => {
        const intersectionId = prediction.intersection_id;
        const markerInfo = intersectionMarkers[intersectionId];
        
        if (!markerInfo || !markerInfo.marker) return;
        
        // Get base position
        const baseLatLng = markerInfo.marker.getLatLng();
        
        // Add prediction markers for each direction
        if (prediction.predictions && prediction.predictions.length > 0) {
            prediction.predictions.forEach(dirPrediction => {
                const direction = dirPrediction.direction;
                
                // Define offset based on direction, but slightly further than traffic indicators
                const offsets = {
                    'N': [0, 0.0006],
                    'S': [0, -0.0006],
                    'E': [0.0006, 0],
                    'W': [-0.0006, 0]
                };
                
                const offset = offsets[direction] || [0, 0];
                const latLng = L.latLng(baseLatLng.lat + offset[1], baseLatLng.lng + offset[0]);
                
                // Determine color based on predicted congestion
                const color = dirPrediction.predicted_congestion ? '#dc3545' : '#28a745';
                
                // Create prediction marker
                const predMarker = L.circle(latLng, {
                    color: color,
                    fillColor: color,
                    fillOpacity: 0.6,
                    radius: 15,
                    weight: 2,
                    dashArray: '5, 5'  // Dashed line to distinguish predictions
                }).addTo(trafficMap);
                
                // Create popup content
                const popupContent = `
                    <div class="prediction-popup">
                        <h6>Prediction: ${getDirectionName(direction)}</h6>
                        <p>In ${dirPrediction.prediction_window} minutes:</p>
                        <p>Expected Vehicles: ${dirPrediction.predicted_vehicle_count}</p>
                        <p>Congestion: <span class="badge bg-${dirPrediction.predicted_congestion ? 'danger' : 'success'}">
                            ${dirPrediction.predicted_congestion ? 'Yes' : 'No'}</span></p>
                        <p>Confidence: ${(dirPrediction.confidence * 100).toFixed(0)}%</p>
                    </div>
                `;
                
                predMarker.bindPopup(popupContent);
                
                // Store reference
                if (!predictionMarkers[intersectionId]) {
                    predictionMarkers[intersectionId] = {};
                }
                predictionMarkers[intersectionId][direction] = predMarker;
            });
        }
    });
}

/**
 * Clear all prediction markers from the map
 */
function clearPredictionMarkers() {
    Object.values(predictionMarkers).forEach(directions => {
        Object.values(directions).forEach(marker => {
            trafficMap.removeLayer(marker);
        });
    });
    
    // Reset prediction markers object
    predictionMarkers = {};
}

/**
 * Toggle prediction visibility
 * @param {boolean} show - Whether to show predictions
 */
function togglePredictionVisibility(show) {
    showPredictionsOnMap = show;
    
    if (show) {
        // Load fresh predictions
        const intersectionIds = Object.keys(intersectionMarkers);
        
        if (intersectionIds.length > 0) {
            // Fetch predictions for each intersection
            const promises = intersectionIds.map(id => {
                return fetch(`/api/predictions/traffic?intersection_id=${id}`)
                    .then(response => response.json());
            });
            
            Promise.all(promises)
                .then(results => {
                    updatePredictionsOnMap(results);
                })
                .catch(error => {
                    console.error('Error loading predictions:', error);
                });
        }
    } else {
        // Clear predictions
        clearPredictionMarkers();
    }
}

/**
 * Get congestion level based on wait time and queue length
 * @param {number} waitTime - Average wait time
 * @param {number} queueLength - Maximum queue length
 * @returns {string} - Congestion level (low, medium, high)
 */
function getCongestionLevel(waitTime, queueLength) {
    if (waitTime > 45 && queueLength > 10) {
        return 'high';
    } else if (waitTime > 20 || queueLength > 5) {
        return 'medium';
    } else {
        return 'low';
    }
}

/**
 * Get badge color based on congestion level
 * @param {string} level - Congestion level
 * @returns {string} - Bootstrap color class
 */
function getBadgeColor(level) {
    switch (level) {
        case 'high': return 'danger';
        case 'medium': return 'warning';
        case 'low': return 'success';
        default: return 'secondary';
    }
}

/**
 * Get human-readable direction name
 * @param {string} dir - Direction code (N, S, E, W)
 * @returns {string} - Direction name
 */
function getDirectionName(dir) {
    const directions = {
        'N': 'North',
        'S': 'South',
        'E': 'East',
        'W': 'West'
    };
    return directions[dir] || dir;
}
