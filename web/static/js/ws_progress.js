/** WebSocket 进度推送客户端 */

/**
 * 连接 WebSocket 获取实时进度
 * @param {string} url - WebSocket URL (默认 /ws)
 * @returns {{ disconnect: Function, onMessage: Function }}
 */
function connectProgressWS(url = '/ws') {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}${url}`;
    let ws = null;
    const listeners = [];
    let reconnectTimer = null;

    function connect() {
        ws = new WebSocket(wsUrl);

        ws.onopen = function() {
            console.log('[WS] Connected');
            sendMsg('list');
        };

        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                listeners.forEach(fn => fn(data));
            } catch (e) {
                console.warn('[WS] Parse error:', e);
            }
        };

        ws.onclose = function() {
            console.log('[WS] Disconnected');
            // 3秒后重连
            reconnectTimer = setTimeout(connect, 3000);
        };

        ws.onerror = function(error) {
            console.error('[WS] Error:', error);
        };
    }

    function sendMsg(type, extra = {}) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type, ...extra }));
        }
    }

    function onMessage(fn) {
        listeners.push(fn);
    }

    function disconnect() {
        if (reconnectTimer) clearTimeout(reconnectTimer);
        if (ws) ws.close();
        listeners.length = 0;
    }

    connect();

    return { disconnect, onMessage, send: sendMsg };
}

/**
 * 更新进度条UI
 * @param {Object} task - 任务数据
 * @param {string} containerId - 容器ID
 */
function updateProgressBar(task, containerId = 'progress-container') {
    const container = document.getElementById(containerId);
    if (!container) return;

    const statusColors = {
        'pending': 'text-gray-500',
        'running': 'text-blue-500',
        'completed': 'text-green-500',
        'failed': 'text-red-500',
        'cancelled': 'text-yellow-500',
    };

    const statusLabels = {
        'pending': '等待中',
        'running': '运行中',
        'completed': '已完成',
        'failed': '失败',
        'cancelled': '已取消',
    };

    const color = statusColors[task.status] || 'text-gray-500';
    const label = statusLabels[task.status] || task.status;

    container.innerHTML = `
        <div class="p-4 bg-gray-50 rounded border">
            <div class="flex justify-between items-center mb-2">
                <span class="font-medium text-sm">
                    <span class="inline-block w-2 h-2 rounded-full ${task.status === 'running' ? 'bg-blue-500 animate-pulse' : 'bg-gray-400'} mr-2"></span>
                    ${task.step || task.type || ''}
                </span>
                <span class="text-sm ${color}">${label}</span>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-2 mb-2">
                <div class="bg-blue-600 h-2 rounded-full transition-all duration-300" style="width: ${task.progress || 0}%"></div>
            </div>
            <div class="text-xs text-gray-500">${task.message || ''}</div>
        </div>
    `;
}

/**
 * 启动监控并显示进度
 * @param {string} domain - 领域名
 */
function startMonitor(domain) {
    fetch(`/domains/${domain}/monitor`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            console.log('Monitor started:', data);
            document.getElementById('progress-panel').classList.remove('hidden');
            document.getElementById('progress-container').innerHTML = `
                <div class="p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-700">
                    监控任务已启动 (task: ${data.task_id})
                </div>`;
        })
        .catch(err => console.error('Start monitor failed:', err));
}

/**
 * 启动发现并显示进度
 * @param {string} domain - 领域名
 */
function startDiscover(domain) {
    fetch(`/domains/${domain}/discover`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            console.log('Discover started:', data);
            document.getElementById('progress-panel').classList.remove('hidden');
            document.getElementById('progress-container').innerHTML = `
                <div class="p-3 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-700">
                    发现任务已启动 (task: ${data.task_id})
                </div>`;
        })
        .catch(err => console.error('Start discover failed:', err));
}

/**
 * 启动复盘并显示进度
 * @param {string} domain - 领域名
 */
function startReview(domain) {
    fetch(`/domains/${domain}/review`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            console.log('Review started:', data);
            document.getElementById('progress-panel').classList.remove('hidden');
            document.getElementById('progress-container').innerHTML = `
                <div class="p-3 bg-purple-50 border border-purple-200 rounded text-sm text-purple-700">
                    复盘任务已启动 (task: ${data.task_id})
                </div>`;
        })
        .catch(err => console.error('Start review failed:', err));
}

/**
 * 取消任务
 * @param {string} taskId - 任务ID
 */
function cancelTask(taskId) {
    fetch(`/ws/cancel/${taskId}`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            console.log('Cancelled:', data);
        })
        .catch(err => console.error('Cancel failed:', err));
}
