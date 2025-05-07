// Global variables
let trafficTrendChart = null;
let trafficData = [];
let selectedMetric = 'vehicle_count';
let showPredictions = false;
let lastUpdateTime = Date.now();
let intersectionData = {};

/**
 * Initialize traffic overview metrics
 */
function initializeTrafficOverview() {
    // Set up event listeners for metric selection
    document.querySelectorAll('[data-metric]').forEach(button => {
        button.addEventListener('click', function() {
            // Remove active class from all buttons
            document.querySelectorAll('[data-metric]').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Add active class to clicked button
            this.classList.add('active');
            
            // Update selected metric
            selectedMetric = this.getAttribute('data-metric');
            
            // Update chart
            updateTrafficTrendChart();
        });
    });
    
    // Set up predictions toggle
    const predictionsSwitch = document.getElementById('show-predictions-switch');
    if (predictionsSwitch) {
        predictionsSwitch.addEventListener('change', function() {
            showPredictions = this.checked;
            updateMap();
        });
    }
}

/**
 * Load traffic data from API
 */
function loadTrafficData() {
    fetch('/api/traffic/data')
        .then(response => response.json())
        .then(data => {
            trafficData = data;
            updateTrafficOverview(data);
            updateTrafficTrendChart();
            
            // If we're showing predictions, load them too
            if (showPredictions) {
                loadPredictions();
            }
        })
        .catch(error => {
            console.error('Error loading traffic data:', error);
        });
}

/**
 * Load traffic predictions from API
 */
function loadPredictions() {
    // Get unique intersection IDs
    const intersectionIds = [...new Set(trafficData.map(d => d.intersection_id))];
    
    // Fetch predictions for each intersection
    const promises = intersectionIds.map(id => {
        return fetch(`/api/predictions/traffic?intersection_id=${id}`)
            .then(response => response.json());
    });
    
    Promise.all(promises)
        .then(results => {
            // Process and display predictions
            displayPredictions(results);
        })
        .catch(error => {
            console.error('Error loading predictions:', error);
        });
}

/**
 * Display predictions on the map and in the UI
 */
function displayPredictions(predictions) {
    if (!showPredictions) return;
    
    // Update map with prediction data
    updateMapPredictions(predictions);
    
    // Could also update other UI elements with predictions
}

/**
 * Update traffic overview metrics
 */
function updateTrafficOverview(data) {
    if (!data || data.length === 0) return;
    
    // Calculate metrics across all intersections
    let totalVehicles = 0;
    let totalWaitTime = 0;
    let congestedSegments = 0;
    let emergencyCount = 0;
    
    data.forEach(item => {
        totalVehicles += item.vehicle_count || 0;
        totalWaitTime += item.wait_time || 0;
        
        // Check for congestion (wait time > 45s and queue > 10)
        if ((item.wait_time > 45) && (item.queue_length > 10)) {
            congestedSegments++;
        }
    });
    
    // Calculate averages
    const avgWaitTime = totalWaitTime / data.length;
    
    // Determine congestion level
    let congestionLevel = 'Low';
    const congestionRatio = congestedSegments / data.length;
    
    if (congestionRatio > 0.5) {
        congestionLevel = 'High';
    } else if (congestionRatio > 0.25) {
        congestionLevel = 'Medium';
    }
    
    // Update UI
    document.getElementById('total-vehicles').textContent = totalVehicles;
    document.getElementById('avg-wait-time').textContent = `${avgWaitTime.toFixed(1)}s`;
    document.getElementById('congestion-level').textContent = congestionLevel;
    
    // Set color based on congestion level
    const congestionEl = document.getElementById('congestion-level');
    if (congestionEl) {
        congestionEl.classList.remove('text-success', 'text-warning', 'text-danger');
        
        if (congestionLevel === 'Low') {
            congestionEl.classList.add('text-success');
        } else if (congestionLevel === 'Medium') {
            congestionEl.classList.add('text-warning');
        } else {
            congestionEl.classList.add('text-danger');
        }
    }
    
    // Update intersection data for the map
    organizeIntersectionData(data);
}

/**
 * Initialize traffic trends chart
 */
function initializeTrafficTrends() {
    const ctx = document.getElementById('traffic-trend-chart').getContext('2d');
    
    trafficTrendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 300
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                }
            }
        }
    });
}

/**
 * Update the traffic trend chart with the latest data
 */
function updateTrafficTrendChart() {
    if (!trafficTrendChart || !trafficData || trafficData.length === 0) return;
    
    // Organize data by intersection and timestamp
    const organizedData = organizeChartData(trafficData, selectedMetric);
    
    // Update chart data
    trafficTrendChart.data.labels = organizedData.labels;
    trafficTrendChart.data.datasets = organizedData.datasets;
    
    // Update chart
    trafficTrendChart.update();
}

/**
 * Organize chart data by intersection and timestamp
 */
function organizeChartData(data, metric) {
    // Group data by intersection
    const intersectionGroups = {};
    
    data.forEach(item => {
        const intersectionId = item.intersection_id;
        
        if (!intersectionGroups[intersectionId]) {
            intersectionGroups[intersectionId] = {
                name: `Intersection ${intersectionId}`,
                data: []
            };
        }
        
        intersectionGroups[intersectionId].data.push({
            timestamp: new Date(item.timestamp),
            value: item[metric] || 0
        });
    });
    
    // Sort each intersection's data by timestamp
    Object.values(intersectionGroups).forEach(intersection => {
        intersection.data.sort((a, b) => a.timestamp - b.timestamp);
    });
    
    // Get unique timestamps across all intersections
    const allTimestamps = [...new Set(data.map(item => item.timestamp))].sort();
    
    // Format timestamps for labels
    const labels = allTimestamps.map(ts => {
        const date = new Date(ts);
        return date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    });
    
    // Create datasets for chart
    const datasets = Object.values(intersectionGroups).map((intersection, index) => {
        // Generate a color based on index
        const hue = (index * 137.5) % 360;
        const color = `hsl(${hue}, 70%, 60%)`;
        
        return {
            label: intersection.name,
            data: intersection.data.map(d => d.value),
            fill: false,
            borderColor: color,
            backgroundColor: color,
            tension: 0.4
        };
    });
    
    return {
        labels,
        datasets
    };
}

/**
 * Organize traffic data by intersection
 */
function organizeIntersectionData(data) {
    // Group data by intersection
    data.forEach(item => {
        const intersectionId = item.intersection_id;
        
        if (!intersectionData[intersectionId]) {
            intersectionData[intersectionId] = {
                id: intersectionId,
                directions: {}
            };
        }
        
        // Group by direction
        const direction = item.direction;
        intersectionData[intersectionId].directions[direction] = item;
    });
    
    // Update map with organized data
    updateMapData(intersectionData);
}

/**
 * Update map data - this function will be implemented in map.js
 */
function updateMapData(data) {
    // This will be implemented in map.js
    console.log('Map data updated with', Object.keys(data).length, 'intersections');
    
    // Dispatch custom event for map component to handle
    document.dispatchEvent(new CustomEvent('mapDataUpdated', {
        detail: data
    }));
}

/**
 * Update map predictions - this function will be implemented in map.js
 */
function updateMapPredictions(predictions) {
    // This will be implemented in map.js
    console.log('Map predictions updated with', predictions.length, 'predictions');
    
    // Dispatch custom event for map component to handle
    document.dispatchEvent(new CustomEvent('mapPredictionsUpdated', {
        detail: predictions
    }));
}

/**
 * Update map - this function will be implemented in map.js
 */
function updateMap() {
    // This will be implemented in map.js
    console.log('Map update requested, showing predictions:', showPredictions);
    
    // Dispatch custom event for map component to handle
    document.dispatchEvent(new CustomEvent('mapUpdateRequested', {
        detail: { showPredictions }
    }));
}

// Initialize when the document is ready
document.addEventListener('DOMContentLoaded', function() {
    initializeTrafficOverview();
    initializeTrafficTrends();
    
    // Handle socket events
    document.addEventListener('trafficDataUpdated', function(e) {
        // This is triggered by socket_handler.js
        const data = e.detail;
        
        // Update the intersection data
        if (data.traffic_data && data.traffic_data.length > 0) {
            data.traffic_data.forEach(item => {
                if (!intersectionData[data.intersection_id]) {
                    intersectionData[data.intersection_id] = {
                        id: data.intersection_id,
                        directions: {}
                    };
                }
                
                // Update direction data
                intersectionData[data.intersection_id].directions[item.direction] = item;
            });
            
            // Update map if it's been more than 1 second since last update
            if (Date.now() - lastUpdateTime > 1000) {
                updateMapData(intersectionData);
                lastUpdateTime = Date.now();
            }
        }
    });
    
    document.addEventListener('allTrafficDataUpdated', function(e) {
        // This is triggered by socket_handler.js
        trafficData = e.detail;
        updateTrafficOverview(trafficData);
        updateTrafficTrendChart();
    });
});
