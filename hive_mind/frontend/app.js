const executeBtn = document.getElementById('execute-btn');
const goalInput = document.getElementById('goal-input');
const logFeed = document.getElementById('log-feed');
const statusText = document.getElementById('global-status');
const shatterTree = document.getElementById('shatter-tree');

let pollingInterval = null;

function addLog(message, type = 'normal') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    logFeed.prepend(entry);
}

function updateVisuals(task) {
    statusText.textContent = task.status;

    if (task.status === 'WORKING' && !shatterTree.querySelector('svg')) {
        // Inject a placeholder fractal animation
        shatterTree.innerHTML = `
            <svg width="100%" height="400" viewBox="0 0 400 400">
                <circle cx="200" cy="200" r="5" fill="#00f2ff">
                    <animate attributeName="r" values="5;20;5" dur="3s" repeatCount="indefinite" />
                </circle>
                <!-- Recursive branches would be drawn here -->
                <path d="M 200 200 L 100 100 M 200 200 L 300 100 M 200 200 L 200 350" stroke="#00f2ff" stroke-width="2" opacity="0.5">
                    <animate attributeName="stroke-dasharray" from="0,1000" to="1000,0" dur="2s" fill="freeze" />
                </path>
            </svg>
        `;
        addLog("DECOMPOSITION DETECTED: Goal shattered into 5 atomic tasks.", "consensus");
    }

    if (task.status === 'COMPLETED') {
        clearInterval(pollingInterval);
        addLog("TRUTH SYNTHESIZED: Collective consensus reached.", "consensus");
        const finalResult = document.createElement('div');
        finalResult.className = 'log-entry';
        finalResult.style.color = '#00f2ff';
        finalResult.innerHTML = `<strong>Final Outcome:</strong><br>${task.result}`;
        logFeed.prepend(finalResult);
    }
}

async function startSwarm() {
    const goal = goalInput.value;
    if (!goal) return;

    addLog(`INITIATING OVERMIND: ${goal}`);
    statusText.textContent = "SHATTERING...";

    try {
        const response = await fetch('http://localhost:8000/swarm/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ goal: goal })
        });

        const data = await response.json();
        const taskId = data.task_id;

        // Start polling for results
        pollingInterval = setInterval(async () => {
            const statusRes = await fetch(`http://localhost:8000/swarm/status/${taskId}`);
            const taskData = await statusRes.json();
            updateVisuals(taskData);
        }, 1000);

    } catch (error) {
        addLog(`ERROR: Connection failed. Is the API server running?`);
    }
}

executeBtn.addEventListener('click', startSwarm);
goalInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') startSwarm();
});
