/**
 * 从编译产物判断可刷类型：完整 ROM / 单镜像 / 不可刷
 */
import { existsSync, readdirSync, statSync } from 'fs'
import { basename, extname, join } from 'path'

export type FlashArtifactKind = 'full_rom' | 'single_img' | 'none'

export interface FlashArtifactClassification {
  kind: FlashArtifactKind
  /** 整包路径（目录 / zip / scatter） */
  pkgPath?: string
  /** 单镜像源路径 */
  imgPath?: string
  /** 从文件名推断的分区；无法推断时为空，需人工补 */
  partition?: string
  reason?: string
}

/** 与 skills/.../harness-flash-single-img 路线 A 对齐 */
export const SINGLE_IMG_PARTITIONS = [
  'boot', 'recovery', 'system', 'system_ext', 'vendor', 'vendor_boot',
  'product', 'odm', 'dtbo', 'vbmeta', 'vbmeta_system', 'super',
  'persist', 'modem', 'preloader', 'logo',
] as const

const PARTITION_SET = new Set<string>(SINGLE_IMG_PARTITIONS)

export function inferPartitionFromImgName(fileName: string): string | undefined {
  const base = basename(fileName).replace(/\.img$/i, '').toLowerCase()
  if (PARTITION_SET.has(base)) return base
  return undefined
}

function isImgPath(p: string): boolean {
  return /\.img$/i.test(p)
}

function dirLooksLikeFullRom(dir: string): boolean {
  if (!existsSync(dir)) return false
  let st
  try {
    st = statSync(dir)
  } catch {
    return false
  }
  if (!st.isDirectory()) return false

  let entries: string[] = []
  try {
    entries = readdirSync(dir)
  } catch {
    return false
  }
  const lower = entries.map(e => e.toLowerCase())
  if (lower.some(n => n.includes('scatter') && n.endsWith('.xml'))) return true
  if (lower.includes('android-info.txt')) return true
  if (lower.includes('flash_all.bat') || lower.includes('flash_all.sh')) return true

  const romImgs = ['boot.img', 'super.img', 'vendor.img', 'system.img', 'userdata.img']
  const hit = romImgs.filter(n => lower.includes(n)).length
  return hit >= 2
}

function findScatterOrZip(dir: string): string | null {
  if (!existsSync(dir) || !statSync(dir).isDirectory()) return null
  let entries: string[] = []
  try {
    entries = readdirSync(dir)
  } catch {
    return null
  }
  for (const name of entries) {
    const lower = name.toLowerCase()
    if (lower.endsWith('.zip') && ['flashfiles.zip', 'package.zip', 'images.zip'].includes(lower)) {
      return join(dir, name)
    }
  }
  for (const name of entries) {
    if (name.toLowerCase().includes('scatter') && name.toLowerCase().endsWith('.xml')) {
      return join(dir, name)
    }
  }
  return null
}

function listImgFiles(dir: string): string[] {
  if (!existsSync(dir) || !statSync(dir).isDirectory()) return []
  try {
    return readdirSync(dir)
      .filter(n => /\.img$/i.test(n))
      .map(n => join(dir, n))
  } catch {
    return []
  }
}

export function classifyFlashArtifacts(input: {
  pkgPath?: string
  artifactsDir?: string
  artifacts?: Array<{ name?: string; path: string }>
  partitionHint?: string
}): FlashArtifactClassification {
  const partitionHint = input.partitionHint?.trim().toLowerCase() || undefined

  const candidates: string[] = []
  if (input.pkgPath?.trim()) candidates.push(input.pkgPath.trim())
  if (input.artifactsDir?.trim()) candidates.push(input.artifactsDir.trim())
  for (const a of input.artifacts ?? []) {
    if (a?.path?.trim()) candidates.push(a.path.trim())
  }

  // 显式 zip / scatter 文件
  for (const p of candidates) {
    if (!existsSync(p)) continue
    const lower = p.toLowerCase()
    if (lower.endsWith('.zip')) {
      return { kind: 'full_rom', pkgPath: p }
    }
    if (lower.includes('scatter') && lower.endsWith('.xml')) {
      return { kind: 'full_rom', pkgPath: p }
    }
  }

  // 目录级完整 ROM
  for (const p of candidates) {
    if (!existsSync(p)) continue
    try {
      if (!statSync(p).isDirectory()) continue
    } catch {
      continue
    }
    if (dirLooksLikeFullRom(p)) {
      const nested = findScatterOrZip(p)
      return { kind: 'full_rom', pkgPath: nested ?? p }
    }
  }

  // 单镜像：路径本身是 .img
  for (const p of candidates) {
    if (existsSync(p) && isImgPath(p)) {
      const partition = partitionHint || inferPartitionFromImgName(p)
      return {
        kind: 'single_img',
        imgPath: p,
        partition,
        reason: partition ? undefined : '无法从文件名推断分区，请指定 partition',
      }
    }
  }

  // 目录内仅有一个 .img，且不像整包
  for (const p of candidates) {
    if (!existsSync(p)) continue
    try {
      if (!statSync(p).isDirectory()) continue
    } catch {
      continue
    }
    const imgs = listImgFiles(p)
    if (imgs.length === 1 && !dirLooksLikeFullRom(p)) {
      const imgPath = imgs[0]
      const partition = partitionHint || inferPartitionFromImgName(imgPath)
      return {
        kind: 'single_img',
        imgPath,
        partition,
        reason: partition ? undefined : '无法从文件名推断分区，请指定 partition',
      }
    }
  }

  // artifacts 元数据里唯一 .img
  const imgArts = (input.artifacts ?? []).filter(a => a?.path && isImgPath(a.path))
  if (imgArts.length === 1) {
    const imgPath = imgArts[0].path
    const partition = partitionHint
      || inferPartitionFromImgName(imgArts[0].name || imgPath)
    return {
      kind: 'single_img',
      imgPath,
      partition,
      reason: existsSync(imgPath)
        ? (partition ? undefined : '无法从文件名推断分区，请指定 partition')
        : `镜像路径不存在: ${imgPath}`,
    }
  }

  return {
    kind: 'none',
    reason: '未识别到完整刷机包或单个 .img 产物',
  }
}
