const http = require('node:http');

// An absolute deadline also bounds servers that connect but never finish a body.
function probeReadiness(url, timeoutMs = 1000) {
  return new Promise((resolve) => {
    let request;
    let settled = false;
    const finish = (ready) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (request) request.destroy();
      resolve(ready);
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    try {
      request = http.get(url, (response) => {
        if (response.statusCode !== 200) return finish(false);
        let body = '';
        response.setEncoding('utf8');
        response.on('data', (chunk) => {
          body += chunk;
          if (body.length > 65536) finish(false);
        });
        response.on('error', () => finish(false));
        response.on('aborted', () => finish(false));
        response.on('end', () => {
          try {
            const health = JSON.parse(body);
            finish(health !== null && health.ready_for_ui === true);
          } catch {
            finish(false);
          }
        });
      });
      request.on('error', () => finish(false));
    } catch {
      finish(false);
    }
  });
}

async function findRunningBackend() {
  const ports = Array.from({ length: 10 }, (_, index) => 8050 + index);
  const ready = await Promise.all(ports.map(port =>
    probeReadiness(`http://127.0.0.1:${port}/api/health`, 200)));
  return ports.find((port, index) => ready[index]) || null;
}

async function waitForReadiness(url, timeoutMs = 30000, intervalMs = 200) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await probeReadiness(url, Math.min(1000, deadline - Date.now()))) return;
    const remaining = deadline - Date.now();
    if (remaining > 0) {
      await new Promise(resolve => setTimeout(resolve, Math.min(intervalMs, remaining)));
    }
  }
  throw new Error('Backend readiness timed out');
}

module.exports = { probeReadiness, findRunningBackend, waitForReadiness };
