/**
 * 路径规范化辅助（mapped-root / Windows 拼接）
 */

/** 规范化 mapped_root（保证盘符根带尾部分隔） */
export function normalizeMappedRoot(mappedRoot: string): string {
  let m = mappedRoot.trim().replace(/\//g, '\\')
  if (/^[A-Za-z]:$/.test(m)) m = `${m}\\`
  else if (/^[A-Za-z]:\\$/.test(m)) { /* ok */ }
  else m = m.replace(/\\+$/, '')
  return m
}

export function joinWinCodePath(mappedRoot: string, workspace: string): string {
  const root = normalizeMappedRoot(mappedRoot)
  const ws = workspace.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '').replace(/\//g, '\\')
  if (/^[A-Za-z]:\\$/.test(root)) return `${root}${ws}`
  return `${root}\\${ws}`
}
