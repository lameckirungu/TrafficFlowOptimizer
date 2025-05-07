// Global variables
let intersectionSignals = {};
let signalUpdateInterval = null;

/**
 * Initialize the traffic signal control
 */
function initializeSignalControl() {
    // Set up event listeners
    document.addEventListener('signalsUpdated', function(e) {
        updateSignalDisplay(e.detail);
    });
    
    // Request signal updates every 5 seconds
    signalUpdateInterval = setInterval(function() {
        requestSignalUpdate();
    }, 5000);
}

/**
 * Request signal update from server
 */
function requestSignalUpdate() {
    fetch('/api/signals/update', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
    })
    .then(response => response.json())
    .then(data => {
        console.log('Signal update requested:', data);
    })
    .catch(error => {
        console.error('Error requesting signal update:', error);
    });
}

/**
 * Load signals for all or specific intersection
 * @param {number} intersectionId - Intersection ID (optional)
 */
function loadSignals(intersectionId = null) {
    let url = '/api/signals/state';
    if (intersectionId) {
        url += `?intersection_id=${intersectionId}`;
    }
    
    fetch(url)
        .then(response => response.json())
        .then(data => {
            renderSignals(data, intersectionId);
        })
        .catch(error => {
            console.error('Error loading signals:', error);
        });
}

/**
 * Render traffic signals in the UI
 * @param {Array} signals - Traffic signal data
 * @param {number} filteredIntersectionId - Intersection ID if filtering
 */
function renderSignals(signals, filteredIntersectionId = null) {
    if (!signals || signals.length === 0) {
        document.getElementById('signals-container').innerHTML = 
            '<div class="alert alert-info">No signals available</div>';
        return;
    }
    
    // Group signals by intersection
    const groupedSignals = groupSignalsByIntersection(signals);
    
    // Filter if needed
    let displaySignals = groupedSignals;
    if (filteredIntersectionId) {
        displaySignals = {
            [filteredIntersectionId]: groupedSignals[filteredIntersectionId]
        };
    }
    
    // Render signals
    let html = '';
    
    Object.entries(displaySignals).forEach(([intersectionId, intersectionSignals]) => {
        html += renderIntersectionSignals(intersectionId, intersectionSignals);
    });
    
    document.getElementById('signals-container').innerHTML = html;
    
    // Initialize Feather icons for the dynamically added content
    feather.replace();
    
    // Add event listeners for signal control
    addSignalControlListeners();
}

/**
 * Group signals by intersection ID
 * @param {Array} signals - Traffic signal data
 * @returns {Object} - Signals grouped by intersection
 */
function groupSignalsByIntersection(signals) {
    const grouped = {};
    
    signals.forEach(signal => {
        const intersectionId = signal.intersection_id;
        
        if (!grouped[intersectionId]) {
            grouped[intersectionId] = [];
        }
        
        grouped[intersectionId].push(signal);
    });
    
    return grouped;
}

/**
 * Render signals for a specific intersection
 * @param {number} intersectionId - Intersection ID
 * @param {Array} signals - Traffic signals for this intersection
 * @returns {string} - HTML for the intersection signals
 */
function renderIntersectionSignals(intersectionId, signals) {
    if (!signals || signals.length === 0) return '';
    
    // Sort signals by direction
    signals.sort((a, b) => {
        const dirOrder = { 'N': 0, 'E': 1, 'S': 2, 'W': 3 };
        return (dirOrder[a.direction] || 99) - (dirOrder[b.direction] || 99);
    });
    
    // Create signal cards
    let html = '';
    
    signals.forEach(signal => {
        html += `
        <div class="card signal-card">
            <div class="card-header">
                <div class="d-flex justify-content-between align-items-center">
                    <h6 class="mb-0">Intersection ${intersectionId} - ${getDirectionName(signal.direction)}</h6>
                    <div class="signal-lights">
                        <div class="signal-light ${signal.state === 'red' ? 'signal-red' : 'signal-inactive'}"></div>
                        <div class="signal-light ${signal.state === 'yellow' ? 'signal-yellow' : 'signal-inactive'}"></div>
                        <div class="signal-light ${signal.state === 'green' ? 'signal-green' : 'signal-inactive'}"></div>
                    </div>
                </div>
            </div>
            <div class="card-body">
                <p>Current State: <span class="badge bg-${getSignalStateBadge(signal.state)}">${signal.state.toUpperCase()}</span></p>
                <p>Cycle Time: ${signal.cycle_time}s</p>
                <p>Last Updated: ${formatTimestamp(signal.last_updated)}</p>
                
                <div class="mt-3">
                    <div class="btn-group w-100">
                        <button class="btn btn-sm btn-danger signal-control-btn" 
                                data-intersection="${intersectionId}" 
                                data-direction="${signal.direction}" 
                                data-state="red">Red</button>
                        <button class="btn btn-sm btn-warning signal-control-btn" 
                                data-intersection="${intersectionId}" 
                                data-direction="${signal.direction}" 
                                data-state="yellow">Yellow</button>
                        <button class="btn btn-sm btn-success signal-control-btn" 
                                data-intersection="${intersectionId}" 
                                data-direction="${signal.direction}" 
                                data-state="green">Green</button>
                    </div>
                </div>
            </div>
        </div>`;
    });
    
    return html;
}

/**
 * Add event listeners for signal control buttons
 */
function addSignalControlListeners() {
    document.querySelectorAll('.signal-control-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const intersectionId = this.getAttribute('data-intersection');
            const direction = this.getAttribute('data-direction');
            const state = this.getAttribute('data-state');
            
            // Call API to change signal state
            overrideSignal(intersectionId, direction, state);
        });
    });
}

/**
 * Override a traffic signal state
 * @param {number} intersectionId - Intersection ID
 * @param {string} direction - Direction (N, S, E, W)
 * @param {string} state - New state (red, yellow, green)
 */
function overrideSignal(intersectionId, direction, state) {
    fetch('/api/signals/override', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            intersection_id: parseInt(intersectionId),
            direction: direction,
            state: state,
            cycle_time: 60  // Default cycle time
        }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            console.error('Error overriding signal:', data.error);
            return;
        }
        
        console.log('Signal override successful:', data);
        
        // Update the signal in the UI
        updateSignalDisplay([data.signal]);
    })
    .catch(error => {
        console.error('Error overriding signal:', error);
    });
}

/**
 * Update signal display with new data
 * @param {Array} signals - Updated signal data
 */
function updateSignalDisplay(signals) {
    if (!signals || signals.length === 0) return;
    
    signals.forEach(signal => {
        // Find the signal card
        const signalCard = document.querySelector(`.signal-card .card-header h6:contains("Intersection ${signal.intersection_id} - ${getDirectionName(signal.direction)}")`).closest('.signal-card');
        
        if (!signalCard) return;
        
        // Update signal lights
        const lightElements = signalCard.querySelectorAll('.signal-light');
        lightElements.forEach(light => light.className = 'signal-light signal-inactive');
        
        if (signal.state === 'red') {
            lightElements[0].className = 'signal-light signal-red';
        } else if (signal.state === 'yellow') {
            lightElements[1].className = 'signal-light signal-yellow';
        } else if (signal.state === 'green') {
            lightElements[2].className = 'signal-light signal-green';
        }
        
        // Update state text
        const stateText = signalCard.querySelector('p:nth-child(1) .badge');
        stateText.className = `badge bg-${getSignalStateBadge(signal.state)}`;
        stateText.textContent = signal.state.toUpperCase();
        
        // Update cycle time
        const cycleText = signalCard.querySelector('p:nth-child(2)');
        cycleText.textContent = `Cycle Time: ${signal.cycle_time}s`;
        
        // Update timestamp
        const timestampText = signalCard.querySelector('p:nth-child(3)');
        timestampText.textContent = `Last Updated: ${formatTimestamp(signal.last_updated)}`;
    });
}

/**
 * Get badge color for signal state
 * @param {string} state - Signal state
 * @returns {string} - Bootstrap color class
 */
function getSignalStateBadge(state) {
    switch (state) {
        case 'red': return 'danger';
        case 'yellow': return 'warning';
        case 'green': return 'success';
        default: return 'secondary';
    }
}

/**
 * Format timestamp for display
 * @param {string} timestamp - ISO timestamp
 * @returns {string} - Formatted time
 */
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
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

// Helper function to allow jQuery-like :contains selector
Element.prototype.querySelector = function(selector) {
    if (selector.includes(':contains(')) {
        const matches = selector.match(/:contains\(["'](.+)["']\)/);
        if (matches) {
            const searchText = matches[1];
            const modifiedSelector = selector.replace(/:contains\(["'].+["']\)/, '');
            
            const elements = Array.from(this.querySelectorAll(modifiedSelector));
            return elements.find(el => el.textContent.includes(searchText)) || null;
        }
    }
    return HTMLElement.prototype.querySelector.call(this, selector);
};
