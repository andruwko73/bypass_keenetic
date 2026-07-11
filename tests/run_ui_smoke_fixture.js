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

async function main() {
  const port = await selectPort();
  const pythonArgs = process.platform === 'win32'
    ? ['-3.11', 'tests/ui_fixture_server.py', '--port', String(port)]
    : ['tests/ui_fixture_server.py', '--port', String(port)];
  const fixture = spawn(python, pythonArgs, { cwd: root, stdio: 'ignore' });
  try {
    await waitForFixture(port, Date.now() + 15000);
    await runSmoke(port);
  } finally {
    fixture.kill('SIGTERM');
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
