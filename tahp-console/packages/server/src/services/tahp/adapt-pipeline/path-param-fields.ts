/**
 * 适配路径参数字段注册表（选项目「解析」的唯一扩展点）。
 *
 * ---------------------------------------------------------------------------
 * 给后续 Agent / 开发者：增删改字段只改本文件的 PATH_PARAM_FIELDS，不要改 Vue。
 * 前端 PipelineCreateWizard 按 POST /parse-path-params 返回的 fields[] 动态渲染。
 * ---------------------------------------------------------------------------
 *
 * 【新增】在 PATH_PARAM_FIELDS 数组末尾（或按展示顺序插入）追加一项：
 *   {
 *     key: 'MY_FIELD',          // 界面标签 + 落盘 key + 注入适配 formData 的名字
 *     label: 'MY_FIELD',
 *     kind: 'text',             // 'text' 输入框；'select' 下拉（须返回 options）
 *     dependsOn: ['PROJECT_FULL'], // 无依赖则 []；缺依赖时本字段自动失败
 *     parse(ctx) {
 *       // ctx.inputs: OLD_VENDOR_ROOT / NEW_VENDOR_ROOT / project_code / PROJECT_FULL?
 *       // ctx.values: 已解析成功的其它字段（如 PROJECT_FULL、SOC_PLATFORM）
 *       return requireExisting(winJoin(ctx.inputs.NEW_VENDOR_ROOT, 'a', 'b'), 'file')
 *       // 或 { ok: true, value: '...' } / { ok: false, error: '原因', options?: [] }
 *     },
 *   }
 *
 * 【修改名称或解析逻辑】只改对应项的 key / label / dependsOn / parse。
 *   改 key 等于换字段名；旧 run JSON 里仍是旧 key，互不迁移。
 *
 * 【删除】从 PATH_PARAM_FIELDS 去掉该项即可。旧 run 已保存的字段不会被改写。
 *
 * 【路径约定】
 *   - 按用户输入的 VENDOR_ROOT 原文拼接，不要剥掉末尾的 vendor。
 *     例：Z:\\project\\CM8\\vendor + vendor\\transsion\\projects\\X
 *       = Z:\\project\\CM8\\vendor\\vendor\\transsion\\projects\\X
 *   - 用 winJoin / winDir，同时接受 / 与 \\；不要 realpath（映射盘易失败）。
 *   - 路径类字段必须磁盘存在才 ok 并填充；否则 ok=false、value 留空。
 *   - 用户可在 UI 手填覆盖；落盘与适配注入一律用 fields[].value，不要只用 ok。
 *
 * 【验证】改完后：
 *   cd tahp-console
 *   npx vitest run tests/server/adapt-pipeline-path-params.test.ts
 *   npm run build
 *   并重启 BFF。
 */
import fs from 'node:fs'
import path from 'node:path'
import type { PathParamInputs } from './types'

export function winJoin(...parts: string[]): string {
  const cleaned = parts
    .map(p => String(p ?? '').trim().replace(/\//g, '\\'))
    .filter(Boolean)
  if (!cleaned.length) return ''
  return path.win32.normalize(path.win32.join(...cleaned))
}

export function winDir(p: string): string {
  const n = winJoin(p)
  if (!n) return ''
  return n.endsWith('\\') ? n : `${n}\\`
}

export function pathExists(p: string, kind: 'file' | 'dir'): boolean {
  if (!p?.trim()) return false
  try {
    const st = fs.statSync(p)
    return kind === 'dir' ? st.isDirectory() : st.isFile()
  } catch {
    return false
  }
}

export function listSubdirs(dir: string): string[] {
  if (!pathExists(dir, 'dir')) return []
  try {
    return fs.readdirSync(dir, { withFileTypes: true })
      .filter(e => e.isDirectory() && e.name !== '.' && e.name !== '..')
      .map(e => e.name)
      .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
  } catch {
    return []
  }
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function readMkVar(filePath: string, key: string): { ok: boolean; value?: string; error?: string } {
  if (!pathExists(filePath, 'file')) {
    return { ok: false, error: `文件不存在: ${filePath}` }
  }
  let text: string
  try {
    text = fs.readFileSync(filePath, 'utf-8')
  } catch {
    return { ok: false, error: `无法读取: ${filePath}` }
  }
  const re = new RegExp(`^\\s*${escapeRegExp(key)}\\s*[:?+]?=\\s*(.*)$`)
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(re)
    if (!m) continue
    let value = m[1].trim()
    const quoted = (value.startsWith('"') && value.endsWith('"'))
      || (value.startsWith("'") && value.endsWith("'"))
    if (quoted) {
      value = value.slice(1, -1)
    } else {
      const hash = value.indexOf('#')
      if (hash >= 0) value = value.slice(0, hash).trim()
    }
    if (!value) return { ok: false, error: `${key} 为空` }
    if (/\$\(/.test(value)) {
      return { ok: false, error: `${key} 为 Make 变量引用，无法展开: ${value}` }
    }
    return { ok: true, value }
  }
  return { ok: false, error: `未找到 ${key}` }
}

export function normalizeKernelVersion(raw: string): string {
  return String(raw ?? '').trim().replace(/^kernel-/i, '')
}

/** 比较内核版本号（如 6.12、6.6）。a >= b 时为 true。 */
export function isKernelVersionAtLeast(ver: string, min: string): boolean {
  const parts = (v: string) => v.split('.').map(n => {
    const num = parseInt(n, 10)
    return Number.isFinite(num) ? num : 0
  })
  const a = parts(ver)
  const b = parts(min)
  const len = Math.max(a.length, b.length)
  for (let i = 0; i < len; i++) {
    const da = a[i] ?? 0
    const db = b[i] ?? 0
    if (da !== db) return da > db
  }
  return true
}

/** 新分支项目 dtsi 根：内核 ≥ 6.12 用 transsion，否则 mediatek。 */
export function kernelProjectDtsVendor(kernelVer: string): 'mediatek' | 'transsion' {
  return isKernelVersionAtLeast(kernelVer, '6.12') ? 'transsion' : 'mediatek'
}

export function requireExisting(absPath: string, kind: 'file' | 'dir'): {
  ok: boolean
  value?: string
  error?: string
} {
  const normalized = kind === 'dir' ? winDir(absPath) : winJoin(absPath)
  if (pathExists(normalized, kind)) {
    return { ok: true, value: normalized }
  }
  return {
    ok: false,
    error: `${kind === 'dir' ? '目录' : '文件'}不存在: ${normalized}`,
  }
}

export function matchesProjectPrefix(dirName: string, projectCode: string): boolean {
  const prefix = (dirName.split('_')[0] || dirName).trim()
  if (!prefix || !projectCode.trim()) return false
  return projectCode.toLowerCase().includes(prefix.toLowerCase())
}

export interface PathParamParseResult {
  ok: boolean
  value?: string
  options?: string[]
  error?: string
}

export interface PathParamParseContext {
  inputs: PathParamInputs
  values: Record<string, string>
}

export interface PathParamFieldDef {
  key: string
  label: string
  kind: 'text' | 'select'
  dependsOn: string[]
  parse(ctx: PathParamParseContext): PathParamParseResult
}

function need(ctx: PathParamParseContext, key: string): string {
  return ctx.values[key] || ''
}

function vendorRel(vendorRoot: string, ...rel: string[]): string {
  return winJoin(vendorRoot, ...rel)
}

function parseProjectFull(ctx: PathParamParseContext): PathParamParseResult {
  const projectsDir = vendorRel(ctx.inputs.NEW_VENDOR_ROOT, 'vendor', 'transsion', 'projects')
  if (!pathExists(projectsDir, 'dir')) {
    return { ok: false, error: `目录不存在: ${winDir(projectsDir)}` }
  }
  const options = listSubdirs(projectsDir)
  if (!options.length) {
    return { ok: false, error: `目录为空: ${winDir(projectsDir)}` }
  }

  const override = ctx.inputs.PROJECT_FULL?.trim()
  if (override) {
    const hit = options.find(n => n.toLowerCase() === override.toLowerCase())
    if (hit) return { ok: true, value: hit, options }
    return { ok: false, options, error: `项目目录不存在: ${override}` }
  }

  const matches = options.filter(n => matchesProjectPrefix(n, ctx.inputs.project_code))
  if (!matches.length) {
    return { ok: false, options, error: '未匹配到与项目相似的目录' }
  }
  return { ok: true, value: matches[0], options }
}

function projectsRootOf(vendorRoot: string, projectFull: string): string {
  return vendorRel(vendorRoot, 'vendor', 'transsion', 'projects', projectFull)
}

function dtsRoot(vendorRoot: string, kernelVer: string, vendor: 'mediatek' | 'transsion'): string {
  return vendorRel(
    vendorRoot,
    'kernel',
    `kernel_device_modules-${kernelVer}`,
    'arch',
    'arm64',
    'boot',
    'dts',
    vendor,
  )
}

function ataConfigPath(vendorRoot: string, projectFull: string): string {
  return vendorRel(
    vendorRoot,
    'vendor',
    'mediatek',
    'proprietary',
    'custom',
    projectFull,
    'factory',
  )
}

function readVextTarget(projectsRoot: string, projectFull: string): PathParamParseResult {
  const mk = winJoin(projectsRoot, `vnd_${projectFull}.mk`)
  const parsed = readMkVar(mk, 'VEXT_TARGET_PROJECT')
  if (!parsed.ok) return { ok: false, error: parsed.error }
  return { ok: true, value: parsed.value }
}

export const PATH_PARAM_FIELDS: PathParamFieldDef[] = [
  {
    key: 'PROJECT_FULL',
    label: 'PROJECT_FULL',
    kind: 'select',
    dependsOn: [],
    parse: parseProjectFull,
  },
  {
    key: 'SOC_PLATFORM',
    label: 'SOC_PLATFORM',
    kind: 'text',
    dependsOn: ['NEW_PROJECTS_ROOT'],
    parse(ctx) {
      const mk = winJoin(need(ctx, 'NEW_PROJECTS_ROOT'), 'BoardConfig-vext.mk')
      const parsed = readMkVar(mk, 'TARGET_BOARD_PLATFORM')
      if (!parsed.ok) return { ok: false, error: parsed.error }
      return { ok: true, value: parsed.value!.toLowerCase() }
    },
  },
  {
    key: 'OLD_PROJECTS_ROOT',
    label: 'OLD_PROJECTS_ROOT',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(projectsRootOf(ctx.inputs.OLD_VENDOR_ROOT, need(ctx, 'PROJECT_FULL')), 'dir')
    },
  },
  {
    key: 'NEW_PROJECTS_ROOT',
    label: 'NEW_PROJECTS_ROOT',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(projectsRootOf(ctx.inputs.NEW_VENDOR_ROOT, need(ctx, 'PROJECT_FULL')), 'dir')
    },
  },
  {
    key: 'OLD_KERNEL_VERSION',
    label: 'OLD_KERNEL_VERSION',
    kind: 'text',
    dependsOn: ['OLD_PROJECTS_ROOT'],
    parse(ctx) {
      const mk = winJoin(need(ctx, 'OLD_PROJECTS_ROOT'), 'ProjectConfig.mk')
      const parsed = readMkVar(mk, 'LINUX_KERNEL_VERSION')
      if (!parsed.ok) return { ok: false, error: parsed.error }
      const ver = normalizeKernelVersion(parsed.value!)
      if (!ver) return { ok: false, error: 'LINUX_KERNEL_VERSION 为空' }
      return { ok: true, value: ver }
    },
  },
  {
    key: 'NEW_KERNEL_VERSION',
    label: 'NEW_KERNEL_VERSION',
    kind: 'text',
    dependsOn: ['NEW_PROJECTS_ROOT'],
    parse(ctx) {
      const mk = winJoin(need(ctx, 'NEW_PROJECTS_ROOT'), 'ProjectConfig.mk')
      const parsed = readMkVar(mk, 'LINUX_KERNEL_VERSION')
      if (!parsed.ok) return { ok: false, error: parsed.error }
      const ver = normalizeKernelVersion(parsed.value!)
      if (!ver) return { ok: false, error: 'LINUX_KERNEL_VERSION 为空' }
      return { ok: true, value: ver }
    },
  },
  {
    key: 'OLD_KERNEL_DWS_PATH',
    label: 'OLD_KERNEL_DWS_PATH',
    kind: 'text',
    dependsOn: ['SOC_PLATFORM', 'PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(vendorRel(
        ctx.inputs.OLD_VENDOR_ROOT,
        'vendor', 'mediatek', 'proprietary', 'tools', 'dct', 'dws',
        need(ctx, 'SOC_PLATFORM'),
        `${need(ctx, 'PROJECT_FULL')}.dws`,
      ), 'file')
    },
  },
  {
    key: 'NEW_KERNEL_DWS_PATH',
    label: 'NEW_KERNEL_DWS_PATH',
    kind: 'text',
    dependsOn: ['SOC_PLATFORM', 'PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(vendorRel(
        ctx.inputs.NEW_VENDOR_ROOT,
        'vendor', 'mediatek', 'proprietary', 'tools', 'dct', 'dws',
        need(ctx, 'SOC_PLATFORM'),
        `${need(ctx, 'PROJECT_FULL')}.dws`,
      ), 'file')
    },
  },
  {
    key: 'OLD_PRELOADER_DWS_PATH',
    label: 'OLD_PRELOADER_DWS_PATH',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(vendorRel(
        ctx.inputs.OLD_VENDOR_ROOT,
        'vendor', 'mediatek', 'proprietary', 'bootable', 'bootloader', 'preloader',
        'custom', need(ctx, 'PROJECT_FULL'), 'dct', 'dct', 'codegen.dws',
      ), 'file')
    },
  },
  {
    key: 'NEW_PRELOADER_DWS_PATH',
    label: 'NEW_PRELOADER_DWS_PATH',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(vendorRel(
        ctx.inputs.NEW_VENDOR_ROOT,
        'vendor', 'mediatek', 'proprietary', 'bootable', 'bootloader', 'preloader',
        'custom', need(ctx, 'PROJECT_FULL'), 'dct', 'dct', 'codegen.dws',
      ), 'file')
    },
  },
  {
    key: 'OLD_PRELOADER_PROJECT_CONFIG_PATH',
    label: 'OLD_PRELOADER_PROJECT_CONFIG_PATH',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(vendorRel(
        ctx.inputs.OLD_VENDOR_ROOT,
        'vendor', 'mediatek', 'proprietary', 'bootable', 'bootloader', 'preloader',
        'custom', need(ctx, 'PROJECT_FULL'),
      ), 'dir')
    },
  },
  {
    key: 'NEW_PRELOADER_PROJECT_CONFIG_PATH',
    label: 'NEW_PRELOADER_PROJECT_CONFIG_PATH',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(vendorRel(
        ctx.inputs.NEW_VENDOR_ROOT,
        'vendor', 'mediatek', 'proprietary', 'bootable', 'bootloader', 'preloader',
        'custom', need(ctx, 'PROJECT_FULL'),
      ), 'dir')
    },
  },
  {
    key: 'OLD_LK2_PROJECT_CONFIG_PATH',
    label: 'OLD_LK2_PROJECT_CONFIG_PATH',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(vendorRel(
        ctx.inputs.OLD_VENDOR_ROOT,
        'vendor', 'mediatek', 'proprietary', 'bootable', 'bootloader', 'lk2',
        'project', `${need(ctx, 'PROJECT_FULL')}.mk`,
      ), 'file')
    },
  },
  {
    key: 'NEW_LK2_PROJECT_CONFIG_PATH',
    label: 'NEW_LK2_PROJECT_CONFIG_PATH',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(vendorRel(
        ctx.inputs.NEW_VENDOR_ROOT,
        'vendor', 'mediatek', 'proprietary', 'bootable', 'bootloader', 'lk2',
        'project', `${need(ctx, 'PROJECT_FULL')}.mk`,
      ), 'file')
    },
  },
  {
    key: 'OLD_KERNEL_PROJECT_DTS_PATH',
    label: 'OLD_KERNEL_PROJECT_DTS_PATH',
    kind: 'text',
    dependsOn: ['OLD_KERNEL_VERSION'],
    parse(ctx) {
      return requireExisting(dtsRoot(ctx.inputs.OLD_VENDOR_ROOT, need(ctx, 'OLD_KERNEL_VERSION'), 'mediatek'), 'dir')
    },
  },
  {
    key: 'NEW_KERNEL_PROJECT_DTS_PATH',
    label: 'NEW_KERNEL_PROJECT_DTS_PATH',
    kind: 'text',
    dependsOn: ['NEW_KERNEL_VERSION'],
    parse(ctx) {
      const ver = need(ctx, 'NEW_KERNEL_VERSION')
      return requireExisting(
        dtsRoot(ctx.inputs.NEW_VENDOR_ROOT, ver, kernelProjectDtsVendor(ver)),
        'dir',
      )
    },
  },
  {
    key: 'OLD_KERNEL_SOC_DTS_PATH',
    label: 'OLD_KERNEL_SOC_DTS_PATH',
    kind: 'text',
    dependsOn: ['OLD_KERNEL_VERSION', 'SOC_PLATFORM'],
    parse(ctx) {
      return requireExisting(winJoin(
        dtsRoot(ctx.inputs.OLD_VENDOR_ROOT, need(ctx, 'OLD_KERNEL_VERSION'), 'mediatek'),
        `${need(ctx, 'SOC_PLATFORM')}.dts`,
      ), 'file')
    },
  },
  {
    key: 'NEW_KERNEL_SOC_DTS_PATH',
    label: 'NEW_KERNEL_SOC_DTS_PATH',
    kind: 'text',
    dependsOn: ['NEW_KERNEL_VERSION', 'SOC_PLATFORM'],
    parse(ctx) {
      return requireExisting(winJoin(
        dtsRoot(ctx.inputs.NEW_VENDOR_ROOT, need(ctx, 'NEW_KERNEL_VERSION'), 'mediatek'),
        `${need(ctx, 'SOC_PLATFORM')}.dts`,
      ), 'file')
    },
  },
  {
    key: 'OLD_KO_PACK_SOC_PATH',
    label: 'OLD_KO_PACK_SOC_PATH',
    kind: 'text',
    dependsOn: ['OLD_PROJECTS_ROOT', 'PROJECT_FULL'],
    parse(ctx) {
      const vext = readVextTarget(need(ctx, 'OLD_PROJECTS_ROOT'), need(ctx, 'PROJECT_FULL'))
      if (!vext.ok) return vext
      return requireExisting(vendorRel(
        ctx.inputs.OLD_VENDOR_ROOT,
        'device', 'mediateksample', vext.value!, 'ko_order_table.csv',
      ), 'file')
    },
  },
  {
    key: 'NEW_KO_PACK_SOC_PATH',
    label: 'NEW_KO_PACK_SOC_PATH',
    kind: 'text',
    dependsOn: ['NEW_PROJECTS_ROOT', 'PROJECT_FULL'],
    parse(ctx) {
      const vext = readVextTarget(need(ctx, 'NEW_PROJECTS_ROOT'), need(ctx, 'PROJECT_FULL'))
      if (!vext.ok) return vext
      return requireExisting(vendorRel(
        ctx.inputs.NEW_VENDOR_ROOT,
        'device', 'mediateksample', vext.value!, 'ko_order_table.csv',
      ), 'file')
    },
  },
  {
    key: 'OLD_KO_PACK_PROJECT_PATH',
    label: 'OLD_KO_PACK_PROJECT_PATH',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(vendorRel(
        ctx.inputs.OLD_VENDOR_ROOT,
        'vendor', 'transsion', 'projects', need(ctx, 'PROJECT_FULL'), 'ko_order_table.csv',
      ), 'file')
    },
  },
  {
    key: 'NEW_KO_PACK_PROJECT_PATH',
    label: 'NEW_KO_PACK_PROJECT_PATH',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(vendorRel(
        ctx.inputs.NEW_VENDOR_ROOT,
        'vendor', 'transsion', 'projects', need(ctx, 'PROJECT_FULL'), 'ko_order_table.csv',
      ), 'file')
    },
  },
  {
    key: 'OLD_ATA_CONFIG_PATH',
    label: 'OLD_ATA_CONFIG_PATH',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(ataConfigPath(ctx.inputs.OLD_VENDOR_ROOT, need(ctx, 'PROJECT_FULL')), 'dir')
    },
  },
  {
    key: 'NEW_ATA_CONFIG_PATH',
    label: 'NEW_ATA_CONFIG_PATH',
    kind: 'text',
    dependsOn: ['PROJECT_FULL'],
    parse(ctx) {
      return requireExisting(ataConfigPath(ctx.inputs.NEW_VENDOR_ROOT, need(ctx, 'PROJECT_FULL')), 'dir')
    },
  },
]
