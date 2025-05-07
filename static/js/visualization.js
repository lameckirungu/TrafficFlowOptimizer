/**
 * Traffic Visualization Module
 * Handles visualization of traffic data using D3.js
 */

// Global variables
let visualizationData = {};
let visualizationMode = 'vehicle_count';

/**
 * Initialize traffic visualizations
 */
function initializeVisualizations() {
    // Set up event listeners for visualization mode changes
    document.querySelectorAll('[data-metric]').forEach(button => {
        button.addEventListener('click', function() {
            visualizationMode = this.getAttribute('data-metric');
            updateVisualizations();
        });
    });
    
    // Handle data updates
    document.addEventListener('allTrafficDataUpdated', function(e) {
        const data = e.detail;
        processVisualizationData(data);
        updateVisualizations();
    });
}

/**
 * Process raw traffic data for visualizations
 * @param {Array} data - Raw traffic data
 */
function processVisualizationData(data) {
    if (!data || data.length === 0) return;
    
    // Group data by intersection and direction
    const grouped = {};
    
    data.forEach(item => {
        const intersectionId = item.intersection_id;
        const direction = item.direction;
        const key = `${intersectionId}-${direction}`;
        
        if (!grouped[key]) {
            grouped[key] = [];
        }
        
        grouped[key].push(item);
    });
    
    // Sort each group by timestamp
    Object.keys(grouped).forEach(key => {
        grouped[key].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    });
    
    visualizationData = grouped;
}

/**
 * Update all visualizations based on current data and mode
 */
function updateVisualizations() {
    updateHeatmap();
    updateTrendCharts();
    updateComparisons();
}

/**
 * Update heatmap visualization
 */
function updateHeatmap() {
    const container = document.getElementById('traffic-heatmap');
    if (!container) return;
    
    // Extract data for heatmap
    const heatmapData = [];
    
    Object.entries(visualizationData).forEach(([key, items]) => {
        if (items.length === 0) return;
        
        // Use the most recent data point
        const latest = items[items.length - 1];
        
        const [intersectionId, direction] = key.split('-');
        
        heatmapData.push({
            id: intersectionId,
            direction: direction,
            value: latest[visualizationMode] || 0
        });
    });
    
    // Sort by intersection ID and direction
    heatmapData.sort((a, b) => {
        if (a.id !== b.id) return a.id - b.id;
        
        // Direction order: N, E, S, W
        const dirOrder = { 'N': 0, 'E': 1, 'S': 2, 'W': 3 };
        return (dirOrder[a.direction] || 99) - (dirOrder[b.direction] || 99);
    });
    
    // Clear container
    container.innerHTML = '';
    
    // Set up D3 heatmap
    const width = container.clientWidth;
    const height = 300;
    const cellSize = 50;
    
    // Create SVG
    const svg = d3.select('#traffic-heatmap')
        .append('svg')
        .attr('width', width)
        .attr('height', height);
    
    // Find min/max values for color scale
    const values = heatmapData.map(d => d.value);
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    
    // Color scale based on visualization mode
    let colorScale;
    
    switch (visualizationMode) {
        case 'wait_time':
            // Red scale for wait times (higher is worse)
            colorScale = d3.scaleSequential()
                .domain([0, Math.max(60, maxValue)])
                .interpolator(d3.interpolateReds);
            break;
        case 'queue_length':
            // Purple scale for queue length (higher is worse)
            colorScale = d3.scaleSequential()
                .domain([0, Math.max(20, maxValue)])
                .interpolator(d3.interpolatePurples);
            break;
        case 'vehicle_count':
        default:
            // Blue scale for vehicle count (neutral)
            colorScale = d3.scaleSequential()
                .domain([0, Math.max(30, maxValue)])
                .interpolator(d3.interpolateBlues);
            break;
    }
    
    // Create unique intersection and direction lists
    const intersections = [...new Set(heatmapData.map(d => d.id))];
    const directions = ['N', 'E', 'S', 'W'];
    
    // Calculate grid layout
    const cellsPerRow = Math.floor(width / cellSize);
    
    // Create cells
    svg.selectAll('rect')
        .data(heatmapData)
        .enter()
        .append('rect')
        .attr('x', (d, i) => (i % cellsPerRow) * cellSize)
        .attr('y', (d, i) => Math.floor(i / cellsPerRow) * cellSize)
        .attr('width', cellSize - 2)
        .attr('height', cellSize - 2)
        .attr('fill', d => colorScale(d.value))
        .attr('stroke', '#333')
        .attr('stroke-width', 1)
        .append('title')
        .text(d => `Intersection ${d.id}, ${getDirectionName(d.direction)}: ${d.value}`);
    
    // Add labels
    svg.selectAll('text')
        .data(heatmapData)
        .enter()
        .append('text')
        .attr('x', (d, i) => (i % cellsPerRow) * cellSize + cellSize / 2)
        .attr('y', (d, i) => Math.floor(i / cellsPerRow) * cellSize + cellSize / 2)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('fill', d => d.value > (maxValue * 0.7) ? '#fff' : '#000')
        .text(d => d.value.toFixed(0));
}

/**
 * Update trend charts for each intersection
 */
function updateTrendCharts() {
    const container = document.getElementById('trend-charts-container');
    if (!container) return;
    
    // Group data by intersection
    const intersectionData = {};
    
    Object.entries(visualizationData).forEach(([key, items]) => {
        const [intersectionId, direction] = key.split('-');
        
        if (!intersectionData[intersectionId]) {
            intersectionData[intersectionId] = {};
        }
        
        intersectionData[intersectionId][direction] = items;
    });
    
    // Clear container
    container.innerHTML = '';
    
    // Create charts for each intersection
    Object.entries(intersectionData).forEach(([intersectionId, directions]) => {
        const chartContainer = document.createElement('div');
        chartContainer.className = 'col-md-6 mb-4';
        chartContainer.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <h6 class="mb-0">Intersection ${intersectionId} - ${visualizationMode}</h6>
                </div>
                <div class="card-body">
                    <canvas id="trend-chart-${intersectionId}" height="200"></canvas>
                </div>
            </div>
        `;
        container.appendChild(chartContainer);
        
        // Prepare chart data
        const chartData = {
            labels: [],
            datasets: []
        };
        
        // Get unique timestamps across all directions
        const allTimestamps = new Set();
        Object.values(directions).forEach(items => {
            items.forEach(item => allTimestamps.add(item.timestamp));
        });
        
        // Sort timestamps
        chartData.labels = [...allTimestamps].sort().map(ts => {
            const date = new Date(ts);
            return date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        });
        
        // Create datasets for each direction
        Object.entries(directions).forEach(([direction, items], index) => {
            // Generate color based on direction
            const colors = {
                'N': 'rgba(54, 162, 235, 1)',  // Blue
                'E': 'rgba(75, 192, 192, 1)',  // Teal
                'S': 'rgba(255, 159, 64, 1)',  // Orange
                'W': 'rgba(153, 102, 255, 1)'  // Purple
            };
            
            const color = colors[direction] || `hsl(${index * 90}, 70%, 60%)`;
            
            // Map data to timestamps
            const dataMap = {};
            items.forEach(item => {
                dataMap[item.timestamp] = item[visualizationMode] || 0;
            });
            
            // Create dataset
            chartData.datasets.push({
                label: getDirectionName(direction),
                data: chartData.labels.map(label => {
                    const timestamp = [...allTimestamps].sort()[chartData.labels.indexOf(label)];
                    return dataMap[timestamp] || 0;
                }),
                borderColor: color,
                backgroundColor: color.replace('1)', '0.2)'),
                tension: 0.3,
                fill: false
            });
        });
        
        // Create chart
        const ctx = document.getElementById(`trend-chart-${intersectionId}`).getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: chartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: getMetricLabel(visualizationMode)
                        }
                    }
                }
            }
        });
    });
}

/**
 * Update comparison visualizations
 */
function updateComparisons() {
    const container = document.getElementById('comparisons-container');
    if (!container) return;
    
    // Calculate averages by intersection
    const intersectionAverages = {};
    
    Object.entries(visualizationData).forEach(([key, items]) => {
        if (items.length === 0) return;
        
        const [intersectionId, direction] = key.split('-');
        
        if (!intersectionAverages[intersectionId]) {
            intersectionAverages[intersectionId] = {
                sum: 0,
                count: 0,
                max: 0
            };
        }
        
        // Calculate average and max for this direction
        const values = items.map(item => item[visualizationMode] || 0);
        const sum = values.reduce((a, b) => a + b, 0);
        const avg = sum / values.length;
        const max = Math.max(...values);
        
        intersectionAverages[intersectionId].sum += sum;
        intersectionAverages[intersectionId].count += values.length;
        intersectionAverages[intersectionId].max = Math.max(intersectionAverages[intersectionId].max, max);
    });
    
    // Calculate final averages
    Object.keys(intersectionAverages).forEach(id => {
        const data = intersectionAverages[id];
        data.average = data.sum / data.count;
    });
    
    // Sort intersections by average value
    const sortedIntersections = Object.keys(intersectionAverages).sort((a, b) => 
        intersectionAverages[b].average - intersectionAverages[a].average);
    
    // Create bar chart
    const chartContainer = document.createElement('div');
    chartContainer.className = 'chart-container';
    chartContainer.style.height = '300px';
    container.innerHTML = '';
    container.appendChild(chartContainer);
    
    // Create canvas for chart
    const canvas = document.createElement('canvas');
    canvas.id = 'comparison-chart';
    chartContainer.appendChild(canvas);
    
    // Prepare chart data
    const chartData = {
        labels: sortedIntersections.map(id => `Intersection ${id}`),
        datasets: [
            {
                label: `Average ${getMetricLabel(visualizationMode)}`,
                data: sortedIntersections.map(id => intersectionAverages[id].average.toFixed(2)),
                backgroundColor: 'rgba(54, 162, 235, 0.6)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            },
            {
                label: `Maximum ${getMetricLabel(visualizationMode)}`,
                data: sortedIntersections.map(id => intersectionAverages[id].max.toFixed(2)),
                backgroundColor: 'rgba(255, 99, 132, 0.6)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1
            }
        ]
    };
    
    // Create chart
    const ctx = document.getElementById('comparison-chart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: getMetricLabel(visualizationMode)
                    }
                }
            }
        }
    });
}

/**
 * Get human-readable metric label
 * @param {string} metric - Metric code
 * @returns {string} - Metric label
 */
function getMetricLabel(metric) {
    switch (metric) {
        case 'vehicle_count': return 'Vehicle Count';
        case 'average_speed': return 'Average Speed (km/h)';
        case 'queue_length': return 'Queue Length (vehicles)';
        case 'wait_time': return 'Wait Time (seconds)';
        default: return metric;
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

// Initialize visualizations when document is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if we're on a page with visualizations
    if (document.getElementById('traffic-trend-chart')) {
        initializeVisualizations();
    }
});
