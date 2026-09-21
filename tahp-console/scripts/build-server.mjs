import * as esbuild from 'esbuild'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { chmodSync, cpSync, existsSync, mkdirSync, readFileSync, rmSync } from 'fs'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const pkg = JSON.parse(readFileSync(resolve(rootDir, 'package.json'), 'utf-8'))
const version = pkg.version
const serverOutDir = resolve(rootDir, 'dist/server')
const distDataDir = resolve(rootDir, 'dist/data')

rmSync(serverOutDir, { recursive: true, force: true })
mkdirSync(serverOutDir, { recursive: true })
rmSync(distDataDir, { recursive: true, force: true })

await esbuild.build({
  entryPoints: [resolve(rootDir, 'packages/server/src/index.ts')],
  bundle: true,
  platform: 'node',
  target: 'node23',
  format: 'cjs',
  outfile: resolve(serverOutDir, 'index.js'),
  external: ['node-pty', 'node:sqlite', 'socket.io'],
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  sourcemap: true,
  minify: true,
  treeShaking: true,
  logLevel: 'info',
})

const bridgeOutDir = resolve(serverOutDir, 'agent-bridge')
mkdirSync(bridgeOutDir, { recursive: true })
cpSync(
  resolve(rootDir, 'packages/server/src/services/hermes/agent-bridge/hermes_bridge.py'),
  resolve(bridgeOutDir, 'hermes_bridge.py'),
)
chmodSync(resolve(bridgeOutDir, 'hermes_bridge.py'), 0o755)

const ezBuildSrc = resolve(
  rootDir,
  'packages/server/src/services/tahp/adapt-pipeline/assets/ez-build.sh',
)
const ezBuildOutDir = resolve(serverOutDir, 'adapt-pipeline/assets')
mkdirSync(ezBuildOutDir, { recursive: true })
if (existsSync(ezBuildSrc)) {
  cpSync(ezBuildSrc, resolve(ezBuildOutDir, 'ez-build.sh'))
}

const selfCheckOutDir = resolve(serverOutDir, 'self-check')
mkdirSync(selfCheckOutDir, { recursive: true })
cpSync(
  resolve(rootDir, 'packages/server/src/services/tahp/self-check'),
  selfCheckOutDir,
  { recursive: true },
)

const checklistScmpSrc = resolve(
  rootDir,
  'packages/server/src/services/tahp/checklist-scmp-sync/cli',
)
const checklistScmpOut = resolve(serverOutDir, 'checklist-scmp-sync/cli')
if (existsSync(checklistScmpSrc)) {
  mkdirSync(checklistScmpOut, { recursive: true })
  cpSync(checklistScmpSrc, checklistScmpOut, { recursive: true })
}
const checklistScmpReqSrc = resolve(
  rootDir,
  'packages/server/src/services/tahp/checklist-scmp-sync/requirements.txt',
)
if (existsSync(checklistScmpReqSrc)) {
  mkdirSync(resolve(serverOutDir, 'checklist-scmp-sync'), { recursive: true })
  cpSync(checklistScmpReqSrc, resolve(serverOutDir, 'checklist-scmp-sync', 'requirements.txt'))
}

// packages/server/data 在 .gitignore 中（本机运行时 DB），clone 后可能不存在；
// 生产模式实际读写 ~/.tahp-console，此处仅兼容旧产物布局。
const serverDataDir = resolve(rootDir, 'packages/server/data')
if (existsSync(serverDataDir)) {
  cpSync(serverDataDir, distDataDir, { recursive: true })
} else {
  mkdirSync(distDataDir, { recursive: true })
}

const skillsOutDir = resolve(rootDir, 'dist/skills')
rmSync(skillsOutDir, { recursive: true, force: true })
const skillsSrcDir = resolve(rootDir, 'packages/skills')
if (existsSync(skillsSrcDir)) {
  cpSync(
    skillsSrcDir,
    skillsOutDir,
    { recursive: true },
  )
}
