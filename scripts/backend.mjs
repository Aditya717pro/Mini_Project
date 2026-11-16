import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const backend = join(root, 'backend');
const isWindows = process.platform === 'win32';
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

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error('Usage: node scripts/backend.mjs <python arguments>');
  process.exit(1);
}

const result = spawnSync(venvPython, args, {
  cwd: backend,
  stdio: 'inherit',
});

if (result.error) {
  console.error(`Failed to run backend command: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
