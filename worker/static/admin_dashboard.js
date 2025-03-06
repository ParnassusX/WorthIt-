// Initialize charts
const charts = {};

function initializeCharts() {
    const chartConfig = {
        type: 'line',
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { beginAtZero: true },
                x: { display: false }
            }
        }
    };

    // Queue chart
    charts.queue = new Chart(
        document.getElementById('queue-chart').getContext('2d'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Queue Size',
                    data: [],
                    borderColor: '#2196F3',
                    tension: 0.4
                }]
            }
        }
    );

    // API calls chart
    charts.apiCalls = new Chart(
        document.getElementById('api-calls-chart').getContext('2d'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'API Calls',
                    data: [],
                    borderColor: '#4CAF50',
                    tension: 0.4
                }]
            }
        }
    );

    // Response time chart
    charts.responseTime = new Chart(
        document.getElementById('response-time-chart').getContext('2d'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Response Time',
                    data: [],
                    borderColor: '#FFC107',
                    tension: 0.4
                }]
            }
        }
    );

    // Error rate chart
    charts.errorRate = new Chart(
        document.getElementById('error-rate-chart').getContext('2d'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Error Rate',
                    data: [],
                    borderColor: '#F44336',
                    tension: 0.4
                }]
            }
        }
    );

    // Worker performance chart
    charts.workerPerformance = new Chart(
        document.getElementById('worker-performance-chart').getContext('2d'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Tasks/Minute',
                    data: [],
                    borderColor: '#9C27B0',
                    tension: 0.4
                }]
            }
        }
    );

    // Resource usage chart
    charts.resourceUsage = new Chart(
        document.getElementById('resource-usage-chart').getContext('2d'),
        {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'CPU',
                        data: [],
                        borderColor: '#E91E63',
                        tension: 0.4
                    },
                    {
                        label: 'Memory',
                        data: [],
                        borderColor: '#009688',
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100
                    },
                    x: { display: false }
                }
            }
        }
    );

    // User activity chart
    charts.userActivity = new Chart(
        document.getElementById('user-activity-chart').getContext('2d'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Active Users',
                    data: [],
                    borderColor: '#3F51B5',
                    tension: 0.4
                }]
            }
        }
    );

    // User interactions chart
    charts.interactions = new Chart(
        document.getElementById('interaction-chart').getContext('2d'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Interactions',
                    data: [],
                    borderColor: '#FF5722',
                    tension: 0.4
                }]
            }
        }
    );

    // Feature usage chart
    charts.featureUsage = new Chart(
        document.getElementById('feature-usage-chart').getContext('2d'),
        {
            type: 'bar',
            data: {
                labels: ['Product Analysis', 'Camera Scan', 'Price History'],
                datasets: [{
                    label: 'Usage Count',
                    data: [0, 0, 0],
                    backgroundColor: '#2196F3'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true }
                }
            }
        }
    );
}

// Tab switching functionality
function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.style.display = 'none';
    });
    document.querySelectorAll('.tab-button').forEach(button => {
        button.classList.remove('active');
    });
    document.getElementById(tabId).style.display = 'block';
    document.querySelector(`[onclick="showTab('${tabId}')"]`).classList.add('active');
}

// Real-time updates via Server-Sent Events
const eventSource = new EventSource('/api/metrics/stream');

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateMetrics(data);
};

eventSource.onerror = () => {
    console.error('SSE connection error');
    setTimeout(() => {
        location.reload();
    }, 5000);
};

// Update metrics
function updateMetrics(data) {
    // System metrics
    document.getElementById('uptime').textContent = data.uptime + '%';
    document.getElementById('system-status').textContent = data.system_status;
    document.getElementById('pending-tasks').textContent = data.pending_tasks;
    document.getElementById('redis-health').textContent = data.redis_status;

    // API metrics
    document.getElementById('total-api-calls').textContent = data.total_api_calls;
    document.getElementById('avg-response-time').textContent = data.avg_response_time;
    document.getElementById('error-rate').textContent = data.error_rate + '%';

    // Worker metrics
    document.getElementById('active-workers').textContent = data.active_workers;
    document.getElementById('worker-throughput').textContent = data.worker_throughput;
    document.getElementById('resource-usage').textContent = `CPU: ${data.cpu_usage}% | RAM: ${data.memory_usage}%`;

    // User metrics
    document.getElementById('active-users').textContent = data.active_users;
    document.getElementById('user-interactions').textContent = data.total_interactions;

    // Update charts
    updateCharts(data);
}

// Update chart data
function updateCharts(data) {
    const maxDataPoints = 20;

    Object.keys(charts).forEach(chartKey => {
        const chart = charts[chartKey];
        if (data[chartKey]) {
            chart.data.labels.push(new Date().toLocaleTimeString());
            if (Array.isArray(data[chartKey])) {
                data[chartKey].forEach((value, index) => {
                    chart.data.datasets[index].data.push(value);
                });
            } else {
                chart.data.datasets[0].data.push(data[chartKey]);
            }

            if (chart.data.labels.length > maxDataPoints) {
                chart.data.labels.shift();
                chart.data.datasets.forEach(dataset => {
                    dataset.data.shift();
                });
            }
            chart.update();
        }
    });
}

// Initialize everything when the page loads
document.addEventListener('DOMContentLoaded', () => {
    initializeCharts();
    // Initial data fetch
    fetch('/api/metrics')
        .then(res => res.json())
        .then(data => updateMetrics(data))
        .catch(console.error);
});