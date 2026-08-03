/**
 * 从 mapped_root + workspace 解析编译组件 / markets 可选值
 * 优先 harness build status；回退读 pack.json / .pipe/info.json
 */
import { execFile } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { logger } from '../../logger'

function execFileCapture(
  file: string,
  args: string[],
  options: { timeout?: number; windowsHide?: boolean; encoding?: BufferEncoding; maxBuffer?: number },
): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    execFile(file, args, options, (err, stdout, stderr) => {
      if (err) {
        reject(err)
        return
      }
      resolve({
        stdout: typeof stdout === 'string' ? stdout : String(stdout ?? ''),
        stderr: typeof stderr === 'string' ? stderr : String(stderr ?? ''),
      })
    })
  })
}

/** harness / 传音常见 market 码（CLI 用小写） */
export const HARNESS_MARKET_PRESETS = [
  'op', 'eu', 'tr', 'in', 'ru', 'pk', 'eg', 'ng', 'ke', 'za', 'ph', 'id', 'my', 'th', 'vn', 'bd',
] as const

const TR_COMPONENTS = ['trprd', 'trreg', 'trcar', 'trcom'] as const

export interface WorkspaceBuildOptions {
  mapped_root: string
  workspace: string
  components: string[]
  markets: string[]
  /** 建议默认勾选的组件（含 tr* 以便 package） */
  recommended_components: string[]
  /** 建议默认 markets */
  recommended_markets: string[]
  platform?: string
  project_name?: string
  source: 'harness_status' | 'pack_json' | 'fallback'
  warning?: string
}

function normMarket(m: string): string {
  return m.trim().toLowerCase()
}

function uniqSorted(items: string[]): string[] {
  return [...new Set(items.map(s => s.trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b))
}

function mergeTrComponents(base: string[], extraKeys: string[]): string[] {
  const set = new Set(base.map(c => c.trim()).filter(Boolean))
  for (const k of extraKeys) {
    const c = k.trim()
    if (!c) continue
    if (TR_COMPONENTS.includes(c as typeof TR_COMPONENTS[number]) || c.startsWith('tr')) {
      set.add(c)
    }
  }
  return uniqSorted([...set])
}

function recommendedComponents(components: string[]): string[] {
  // 有 package 需求时默认全选（用户可减）；保证有组件就不全空
  return components.length ? [...components] : []
}

function recommendedMarkets(markets: string[]): string[] {
  if (!markets.length) return ['op']
  // 若含 op 优先默认勾选全部 workspace markets（出包常要齐）
  return [...markets]
}

function readJsonFile(path: string): Record<string, unknown> | null {
  if (!existsSync(path)) return null
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as Record<string, unknown>
  } catch {
    return null
  }
}

function fromPackAndInfo(mappedRoot: string, workspace: string): WorkspaceBuildOptions | null {
  const root = join(mappedRoot, workspace)
  const pack =
    readJsonFile(join(root, 'pack.json'))
    ?? readJsonFile(join(root, '.pipe', 'pack.json'))
  const info = readJsonFile(join(root, '.pipe', 'info.json'))

  if (!pack && !info) return null

  const partConf = Array.isArray(pack?.part_conf) ? pack!.part_conf as Array<{ component?: string }> : []
  let components = partConf.map(p => String(p.component ?? '').trim()).filter(Boolean)

  const marketsRaw = Array.isArray(pack?.markets) ? (pack!.markets as unknown[]).map(String) : []
  let markets = uniqSorted(marketsRaw.map(normMarket))

  const compDict = (info?.comp_dict ?? pack?.comp_dict) as Record<string, string> | undefined
  if (compDict && typeof compDict === 'object') {
    components = mergeTrComponents(components, Object.keys(compDict))
  } else {
    // pack 常不含 tr*；MTK/QCOM 出包仍常需
    components = mergeTrComponents(components, [...TR_COMPONENTS])
  }

  if (!components.length && compDict) {
    components = uniqSorted(Object.keys(compDict))
  }

  return {
    mapped_root: mappedRoot,
    workspace,
    components: uniqSorted(components),
    markets: markets.length ? markets : [...HARNESS_MARKET_PRESETS].slice(0, 4),
    recommended_components: recommendedComponents(uniqSorted(components)),
    recommended_markets: recommendedMarkets(markets.length ? markets : ['op']),
    platform: pack?.platform ? String(pack.platform) : undefined,
    project_name: pack?.project_name ? String(pack.project_name) : undefined,
    source: 'pack_json',
  }
}

async function fromHarnessStatus(mappedRoot: string, workspace: string): Promise<WorkspaceBuildOptions | null> {
  try {
    const { stdout } = await execFileCapture(
      'harness',
      ['--json', 'build', 'status', '--mapped-root', mappedRoot, '--workspace', workspace],
      { timeout: 60_000, windowsHide: true, encoding: 'utf-8', maxBuffer: 4 * 1024 * 1024 },
    )
    const parsed = JSON.parse(stdout) as {
      status?: string
      data?: {
        components?: string[]
        markets?: string[]
        platform?: string
        project_name?: string
        comp_dict?: Record<string, string>
        pack_json_exists?: boolean
      }
      error?: string
    }
    if (parsed.status && parsed.status !== 'ok') return null
    const data = parsed.data
    if (!data) return null

    let components = Array.isArray(data.components) ? data.components.map(String) : []
    if (data.comp_dict && typeof data.comp_dict === 'object') {
      components = mergeTrComponents(components, Object.keys(data.comp_dict))
    } else {
      components = mergeTrComponents(components, [...TR_COMPONENTS])
    }

    const markets = uniqSorted((data.markets ?? []).map(m => normMarket(String(m))))

    return {
      mapped_root: mappedRoot,
      workspace,
      components: uniqSorted(components),
      markets: markets.length ? markets : [...HARNESS_MARKET_PRESETS].slice(0, 4),
      recommended_components: recommendedComponents(uniqSorted(components)),
      recommended_markets: recommendedMarkets(markets.length ? markets : ['op']),
      platform: data.platform,
      project_name: data.project_name,
      source: 'harness_status',
      warning: data.pack_json_exists === false
        ? 'workspace 无 pack.json，组件列表可能不完整'
        : undefined,
    }
  } catch (err) {
    logger.warn({ err: (err as Error).message, mappedRoot, workspace }, '[workspace-build-options] harness status failed')
    return null
  }
}

export async function resolveWorkspaceBuildOptions(
  mappedRoot: string,
  workspace: string,
): Promise<WorkspaceBuildOptions> {
  const root = mappedRoot.trim()
  const ws = workspace.trim().replace(/\\/g, '/')
  if (!root || !ws) {
    return {
      mapped_root: root,
      workspace: ws,
      components: [],
      markets: [...HARNESS_MARKET_PRESETS],
      recommended_components: [],
      recommended_markets: ['op'],
      source: 'fallback',
      warning: '请先填写 mapped_root 与 workspace',
    }
  }

  const fromCli = await fromHarnessStatus(root, ws)
  if (fromCli?.components.length) return fromCli

  const fromFiles = fromPackAndInfo(root, ws)
  if (fromFiles?.components.length) {
    return {
      ...fromFiles,
      warning: fromCli
        ? undefined
        : 'harness build status 不可用，已从本地 pack.json / .pipe 解析',
    }
  }

  // 最终兜底：常见组件 + 全量 market 预设
  const fallbackComponents = ['sys', 'hal', 'krn', 'vext', 'odm', 'trprd', 'trreg']
  return {
    mapped_root: root,
    workspace: ws,
    components: fallbackComponents,
    markets: [...HARNESS_MARKET_PRESETS],
    recommended_components: fallbackComponents,
    recommended_markets: ['op'],
    source: 'fallback',
    warning: '未能从 workspace 解析组件，已提供常见默认列表，请核对后勾选',
  }
}

export function listHarnessMarketPresets(): string[] {
  return [...HARNESS_MARKET_PRESETS]
}
