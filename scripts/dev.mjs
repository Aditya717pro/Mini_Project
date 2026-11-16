import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const frontend = join(root, 'frontend');
const backend = join(root, 'backend');
const isWindows = process.platform === 'win32';
const npmCommand = isWindows ? 'npm.cmd' : 'npm';
const venvPython = join(
  backend,
  '.venv',
  isWindows ? 'Scripts' : 'bin',
  isWindows ? 'python.exe' : 'python',
);

if (!existsSync(venvPython)) {
  console.error('Backend environment not found. Run "npm install" first.');
  process.exit(1);
}

const children = [];
let shuttingDown = false;

function spawnNpm(args, cwd) {
  if (process.env.npm_execpath) {
    return spawn(process.execPath, [process.env.npm_execpath, ...args], {
      cwd,
      stdio: 'inherit',
    });
  }
  return spawn(npmCommand, args, {
    cwd,
    stdio: 'inherit',
    shell: isWindows,
  });
}

function terminate(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  if (isWindows) {
    spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
      stdio: 'ignore',
    });
    return;
  }
  child.kill('SIGTERM');
}

function shutdown(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) terminate(child);
  setTimeout(() => process.exit(code), 400);
}

function start(name, child) {
  children.push(child);
  child.on('error', (error) => {
    console.error(`[${name}] failed to start: ${error.message}`);
    shutdown(1);
  });
  child.on('exit', (code, signal) => {
    if (shuttingDown) return;
    console.error(`[${name}] stopped (code ${code ?? 'null'}, signal ${signal ?? 'none'})`);
    shutdown(code ?? 1);
  });
}

const frontendProcess = spawnNpm(['--prefix', 'frontend', 'run', 'dev'], root);
start('frontend', frontendProcess);

const backendProcess = spawn(
  venvPython,
  ['-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000'],
  { cwd: backend, stdio: 'inherit' },
);
start('backend', backendProcess);

console.log('MedDataHub development servers starting');
console.log('  Frontend: http://localhost:5173');
console.log('  API docs: http://127.0.0.1:8000/docs');
console.log('Press Ctrl+C to stop both.');

process.on('SIGINT', () => {
  console.log('\nStopping MedDataHub development servers...');
  shutdown(0);
});
process.on('SIGTERM', () => {
  shutdown(0);
});
