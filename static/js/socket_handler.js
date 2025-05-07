// Global socket connection
let socket;

/**
 * Initialize Socket.IO connection
 */
function initializeSocketConnection() {
    // Connect to Socket.IO server
    socket = io.connect(window.location.protocol + '//' + window.location.host);
    
    // Setup event handlers
    socket.on('connect', function() {
        console.log('Connected to server');
        updateConnectionStatus(true);
        
        // Request initial data
        socket.emit('request_data_update', {});
    });
    
    socket.on('disconnect', function() {
        console.log('Disconnected from server');
        updateConnectionStatus(false);
    });
    
    // Traffic data updates
    socket.on('traffic_update', function(data) {
        // Handle traffic data for a specific intersection
        updateTrafficData(data);
    });
    
    socket.on('all_traffic_data', function(data) {
        // Handle consolidated traffic data for all intersections
        updateAllTrafficData(data);
    });
    
    // Signal updates
    socket.on('signals_updated', function(data) {
        updateSignals(data.updated_signals);
    });
    
    // Emergency vehicle alerts
    socket.on('emergency_vehicle', function(data) {
        showEmergencyAlert(data);
    });
    
    // Scenario progress updates
    socket.on('scenario_progress', function(data) {
        updateScenarioProgress(data);
    });
    
    // Simulation state updates
    socket.on('simulation_state', function(data) {
        updateSimulationStatus(data);
    });
    
    // Active scenario updates
    socket.on('active_scenario', function(data) {
        updateActiveScenarioIndicator(data);
    });
}

/**
 * Update the connection status indicator
 */
function updateConnectionStatus(connected) {
    const statusEl = document.getElementById('connection-status');
    if (!statusEl) return;
    
    if (connected) {
        statusEl.innerHTML = '<span class="badge bg-success">Connected</span>';
    } else {
        statusEl.innerHTML = '<span class="badge bg-danger">Disconnected</span>';
    }
}

/**
 * Request updated data from the server
 */
function requestDataUpdate(intersectionId = null) {
    if (!socket || !socket.connected) return;
    
    socket.emit('request_data_update', {
        intersection_id: intersectionId
    });
}

/**
 * Placeholder function to update traffic data for a specific intersection
 * Will be implemented in dashboard.js
 */
function updateTrafficData(data) {
    // This will be implemented in dashboard.js
    console.log('Received traffic update for intersection', data.intersection_id);
    
    // Dispatch custom event for other components to handle
    document.dispatchEvent(new CustomEvent('trafficDataUpdated', {
        detail: data
    }));
}

/**
 * Placeholder function to update all traffic data
 * Will be implemented in dashboard.js
 */
function updateAllTrafficData(data) {
    // This will be implemented in dashboard.js
    console.log('Received update for all traffic data', data.length, 'records');
    
    // Dispatch custom event for other components to handle
    document.dispatchEvent(new CustomEvent('allTrafficDataUpdated', {
        detail: data
    }));
}

/**
 * Placeholder function to update signals
 * Will be implemented in signal_control.js
 */
function updateSignals(signals) {
    // This will be implemented in signal_control.js
    console.log('Received signal updates for', signals.length, 'signals');
    
    // Dispatch custom event for other components to handle
    document.dispatchEvent(new CustomEvent('signalsUpdated', {
        detail: signals
    }));
}

/**
 * Show emergency vehicle alert
 */
function showEmergencyAlert(data) {
    console.log('Emergency vehicle alert:', data);
    
    // Update the emergency counter
    const counterEl = document.getElementById('emergency-count');
    if (counterEl) {
        const currentCount = parseInt(counterEl.textContent || '0');
        counterEl.textContent = currentCount + 1;
        counterEl.parentElement.parentElement.classList.add('emergency-alert');
        
        // Remove the alert effect after 5 seconds
        setTimeout(() => {
            counterEl.parentElement.parentElement.classList.remove('emergency-alert');
        }, 5000);
    }
    
    // Show modal if available
    const modal = document.getElementById('emergencyModal');
    if (modal) {
        const nameEl = document.getElementById('emergency-intersection-name');
        const directionEl = document.getElementById('emergency-direction-text');
        
        if (nameEl) nameEl.textContent = data.intersection_name;
        
        if (directionEl) {
            // Convert direction code to readable text
            const directions = {
                'N': 'North',
                'S': 'South',
                'E': 'East',
                'W': 'West'
            };
            directionEl.textContent = directions[data.direction] || data.direction;
        }
        
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
    
    // Dispatch custom event for other components to handle
    document.dispatchEvent(new CustomEvent('emergencyVehicle', {
        detail: data
    }));
}

/**
 * Update scenario progress
 * This will be replaced by dashboard.js or scenarios.js
 */
function updateScenarioProgress(data) {
    console.log('Scenario progress:', data);
    
    // Dispatch custom event for other components to handle
    document.dispatchEvent(new CustomEvent('scenarioProgress', {
        detail: data
    }));
}

/**
 * Update the simulation status in the UI
 */
function updateSimulationStatus(data) {
    const badge = document.getElementById('simulation-status-badge');
    if (!badge) return;
    
    if (data.running) {
        badge.className = 'badge bg-success';
        badge.textContent = `Running (${data.speed}x)`;
    } else {
        badge.className = 'badge bg-secondary';
        badge.textContent = 'Paused';
    }
    
    // Update speed dropdown
    const speedSelect = document.getElementById('simulation-speed');
    if (speedSelect) {
        speedSelect.value = data.speed;
    }
}

/**
 * Update the active scenario indicator
 */
function updateActiveScenarioIndicator(data) {
    const indicator = document.getElementById('active-scenario-indicator');
    if (!indicator) return;
    
    if (data.active) {
        indicator.innerHTML = `
            <span class="badge bg-info ms-2">
                Scenario: ${data.name} (${data.progress}%)
            </span>`;
    } else {
        indicator.innerHTML = '';
    }
}
