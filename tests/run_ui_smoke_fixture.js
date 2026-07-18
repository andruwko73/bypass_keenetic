const { spawn } = require('child_process');
const http = require('http');
const net = require('net');
const path = require('path');

const root = path.resolve(__dirname, '..');
const python = process.platform === 'win32' ? 'py' : 'python3';

function selectPort() {
  const requested = Number(process.env.BYPASS_UI_FIXTURE_PORT || 0);
  if (requested > 0) return Promise.resolve(requested);
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

function waitForFixture(port, deadline) {
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const request = http.get(`http://127.0.0.1:${port}/`, (response) => {
        response.resume();
        if (response.statusCode === 200 && response.headers['x-bypass-ui-fixture'] === '1') {
          resolve();
          return;
        }
        retry();
      });
      request.on('error', retry);
      request.setTimeout(1000, () => request.destroy());
    };
    const retry = () => {
      if (Date.now() >= deadline) {
        reject(new Error('UI fixture did not start.'));
        return;
      }
      setTimeout(attempt, 250);
    };
    attempt();
  });
}

function runSmoke(port) {
  const environment = {
    ...process.env,
    BYPASS_UI_URL: `http://127.0.0.1:${port}/`,
  };
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['tests/ui_smoke.js'], {
      cwd: root,
      env: environment,
      stdio: 'inherit',
    });
    child.once('error', reject);
    child.once('exit', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`UI smoke exited with code ${code}.`));
      }
    });
  });
}

function fixtureRequest(port, route) {
  return new Promise((resolve, reject) => {
    const request = http.get(`http://127.0.0.1:${port}${route}`, (response) => {
      let size = 0;
      response.on('data', (chunk) => { size += chunk.length; });
      response.once('error', reject);
      response.once('end', () => {
        if (response.statusCode === 200 && size > 0) {
          resolve();
        } else {
          reject(new Error(`Fixture request failed: ${route} (${response.statusCode}, ${size}).`));
        }
      });
    });
    request.once('error', reject);
    request.setTimeout(5000, () => request.destroy(new Error(`Fixture request timed out: ${route}`)));
  });
}

async function runConcurrencySmoke(port) {
  const protocols = ['vless', 'vless2', 'vmess', 'trojan', 'shadowsocks'];
  const routes = [
    '/', '/static/app.css', '/static/app.js', '/api/ui_background', '/api/status', '/api/status?compact=1', '/api/status?lite=1',
    '/api/pools', '/api/pool_probe', '/api/command_state', '/api/router_metrics', '/api/event_history', '/api/service_routes',
    ...protocols.flatMap((proto) => [`/api/protocol_panel?proto=${proto}`, `/api/protocol_check_panel?proto=${proto}`]),
  ];
  await Promise.all(Array.from({ length: 100 }, (_, index) => fixtureRequest(port, routes[index % routes.length])));
}

async function main() {
  const port = await selectPort();
  const pythonArgs = process.platform === 'win32'
    ? ['-3.11', 'tests/ui_fixture_server.py', '--port', String(port)]
    : ['tests/ui_fixture_server.py', '--port', String(port)];
  const fixture = spawn(python, pythonArgs, { cwd: root, stdio: 'ignore' });
  try {
    await waitForFixture(port, Date.now() + 15000);
    await runConcurrencySmoke(port);
    await runSmoke(port);
  } finally {
    fixture.kill('SIGTERM');
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
