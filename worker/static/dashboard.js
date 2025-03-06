// Real-time dashboard updates via Server-Sent Events
const eventSource = new EventSource('/updates');

// DOM elements
const pendingTasksEl = document.getElementById('pending-tasks');
const activeTasksEl = document.querySelector('#active-tasks .metric-value');
const redisHealthEl = document.querySelector('#redis-health .metric-value');
const taskStreamEl = document.getElementById('task-stream');

// Handle metric updates
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.event === 'metrics') {
    pendingTasksEl.textContent = data.queue_length;
    activeTasksEl.textContent = data.active_tasks;
    redisHealthEl.textContent = data.redis_connected ? '✅ Connected' : '❌ Disconnected';
    redisHealthEl.style.color = data.redis_connected ? '#4CAF50' : '#F44336';
  }

  if (data.event === 'task_update') {
    const div = document.createElement('div');
    div.className = `task-update ${data.status}`;
    div.innerHTML = `
      <span class="timestamp">${new Date().toLocaleTimeString()}</span>
      <span class="task-id">${data.task_id}</span>
      <span class="status">${data.status.toUpperCase()}</span>
    `;
    taskStreamEl.prepend(div);
  }
};

// Handle errors
eventSource.onerror = () => {
  console.error('SSE connection error');
  setTimeout(() => location.reload(), 5000);
};

// Initial data fetch
fetch('/metrics')
  .then(res => res.json())
  .then(data => {
    pendingTasksEl.textContent = data.queue_length;
    activeTasksEl.textContent = data.active_tasks;
    redisHealthEl.textContent = data.redis_connected ? '✅ Connected' : '❌ Disconnected';
    redisHealthEl.style.color = data.redis_connected ? '#4CAF50' : '#F44336';
  });