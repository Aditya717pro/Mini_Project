import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const frontend = join(root, 'frontend');
const backend = join(root, 'backend');
const isWindows = process.platform === 'win32';
const npmCommand = isWindows ? 'npm.cmd' : 'npm';
const basePython = process.env.PYTHON || (isWindows ? 'python' : 'python3');
const venvPython = join(
  backend,
  '.venv',
  isWindows ? 'Scripts' : 'bin',
  isWindows ? 'python.exe' : 'python',
);

function run(command, args, cwd) {
  const label = [command, ...args].join(' ');
  console.log(`\n> ${label}`);
  const result = spawnSync(command, args, {
    cwd,
    stdio: 'inherit',
    shell: isWindows && command.endsWith('.cmd'),
  });
  if (result.error) {
    console.error(`Failed to run "${label}": ${result.error.message}`);
    process.exit(1);
  }
  if (result.status !== 0) {
    console.error(`Command failed with exit code ${result.status}: ${label}`);
    process.exit(result.status ?? 1);
  }
}

function runNpm(args, cwd) {
  if (process.env.npm_execpath) {
    run(process.execPath, [process.env.npm_execpath, ...args], cwd);
    return;
  }
  run(npmCommand, args, cwd);
}

function copyEnvExample(directory, label) {
  const example = join(directory, '.env.example');
  const target = join(directory, '.env');
  if (!existsSync(example)) return;
  if (existsSync(target)) {
    console.log(`Keeping existing ${label}/.env`);
    return;
  }
  copyFileSync(example, target);
  console.log(`Created ${label}/.env from ${label}/.env.example`);
}

console.log('Setting up MedDataHub development dependencies');

runNpm(['--prefix', 'frontend', 'install'], root);

if (!existsSync(venvPython)) {
  console.log(`\nCreating backend virtual environment with ${basePython}`);
  run(basePython, ['-m', 'venv', '.venv'], backend);
}

run(venvPython, ['-m', 'pip', 'install', '-e', '.[dev]'], backend);

copyEnvExample(frontend, 'frontend');
copyEnvExample(backend, 'backend');

console.log('\nSetup complete. Run "npm run dev" to start the frontend and API.');
