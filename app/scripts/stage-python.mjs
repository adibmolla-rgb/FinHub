// Stage what the desktop app ships besides its own binary:
//   src-tauri/pybundle/     backend + engine sources (copied into the app's resources as python/)
//   src-tauri/binaries/finhub-uv-<target-triple>[.exe]   uv, renamed so it never clobbers a user's own uv
//
// uv is copied from FINHUB_UV_BIN, or else from the `uv` found on PATH.
import { execFileSync } from 'node:child_process'
import { chmodSync, copyFileSync, cpSync, existsSync, mkdirSync, rmSync, statSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repo = resolve(appDir, '..')
const tauriDir = join(appDir, 'src-tauri')
const bundle = join(tauriDir, 'pybundle')

const SKIP = new Set(['.venv', '__pycache__', '.pytest_cache', 'tests', 'node_modules'])
const filter = (src) => !SKIP.has(basename(src)) && !src.endsWith('.pyc')

rmSync(bundle, { recursive: true, force: true })
mkdirSync(bundle, { recursive: true })

// Backend: project files + source tree.
const backendOut = join(bundle, 'backend')
mkdirSync(backendOut, { recursive: true })
for (const f of ['pyproject.toml', 'uv.lock', '.python-version']) copyFileSync(join(repo, 'backend', f), join(backendOut, f))
cpSync(join(repo, 'backend', 'src'), join(backendOut, 'src'), { recursive: true, filter })

// Engines: each engine's project files and worker sources.
cpSync(join(repo, 'engines'), join(bundle, 'engines'), { recursive: true, filter })

for (const f of ['LICENSE', 'NOTICE']) copyFileSync(join(repo, f), join(bundle, f))

// uv sidecar, named the way Tauri's externalBin expects: binaries/finhub-uv-<target-triple>[.exe].
const triple = execFileSync('rustc', ['-vV'], { encoding: 'utf8' }).match(/^host: (.+)$/m)[1].trim()
const isWin = process.platform === 'win32'
let uvSource = process.env.FINHUB_UV_BIN
if (!uvSource) {
  const finder = isWin ? 'where' : 'which'
  uvSource = execFileSync(finder, ['uv'], { encoding: 'utf8' }).split(/\r?\n/)[0].trim()
}
if (!uvSource || !existsSync(uvSource)) throw new Error('uv not found: install uv or set FINHUB_UV_BIN')
const binDir = join(tauriDir, 'binaries')
mkdirSync(binDir, { recursive: true })
const uvTarget = join(binDir, `finhub-uv-${triple}${isWin ? '.exe' : ''}`)
copyFileSync(uvSource, uvTarget)
if (!isWin) chmodSync(uvTarget, 0o755)

const mb = (statSync(uvTarget).size / 1e6).toFixed(1)
console.log(`staged python sources -> ${bundle}`)
console.log(`staged uv (${mb} MB) -> ${uvTarget}`)
