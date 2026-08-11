import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repositoryRoot = resolve(frontendRoot, '..')
const generatedClient = join(frontendRoot, 'src', 'api', 'client.ts')
const mode = process.argv[2]

if (mode !== 'generate' && mode !== 'check') {
  throw new Error('usage: openapi-client.mjs <generate|check>')
}

function pythonExecutable() {
  if (process.env.QUANTMESH_PYTHON) return process.env.QUANTMESH_PYTHON
  const local = process.platform === 'win32'
    ? join(repositoryRoot, '.venv', 'Scripts', 'python.exe')
    : join(repositoryRoot, '.venv', 'bin', 'python')
  return existsSync(local) ? local : (process.platform === 'win32' ? 'python' : 'python3')
}

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: repositoryRoot,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  if (result.status !== 0) {
    process.stderr.write(result.stdout)
    process.stderr.write(result.stderr)
    process.exit(result.status ?? 1)
  }
}

const temporaryRoot = mkdtempSync(join(tmpdir(), 'quantmesh-openapi-'))
const schemaPath = join(temporaryRoot, 'openapi.json')
const candidatePath = join(temporaryRoot, 'client.ts')

try {
  run(pythonExecutable(), [
    join(repositoryRoot, 'tools', 'export_openapi.py'),
    '--output',
    schemaPath,
  ])
  run(process.execPath, [
    join(frontendRoot, 'node_modules', 'openapi-typescript', 'bin', 'cli.js'),
    schemaPath,
    '--output',
    candidatePath,
  ])

  const candidate = readFileSync(candidatePath)
  if (mode === 'generate') {
    mkdirSync(dirname(generatedClient), { recursive: true })
    writeFileSync(generatedClient, candidate)
    process.stdout.write('generated src/api/client.ts\n')
  } else if (!existsSync(generatedClient) || !readFileSync(generatedClient).equals(candidate)) {
    process.stderr.write('frontend/src/api/client.ts is stale; run npm run generate:api\n')
    process.exitCode = 1
  } else {
    process.stdout.write('frontend/src/api/client.ts is current\n')
  }
} finally {
  rmSync(temporaryRoot, { recursive: true, force: true })
}
