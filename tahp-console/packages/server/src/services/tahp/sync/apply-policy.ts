/**
 * 本机 Skill 是否允许被中心包覆盖。
 * 规则：字节一致或仅换行不同 → 不写盘；相对上次已对齐版本有改动 → 跳过（force 除外）。
 */
export type SkillApplyAction = 'apply' | 'skip_synced' | 'skip_dirty'

export function decideSkillApply(input: {
  localHash: string | null
  localNormHash?: string | null
  centralHash: string | null
  lastAppliedHash: string | null
  force: boolean
}): SkillApplyAction {
  if (!input.localHash) return 'apply'
  if (
    input.centralHash
    && (input.localHash === input.centralHash || input.localNormHash === input.centralHash)
  ) {
    return 'skip_synced'
  }
  if (input.force) return 'apply'
  if (input.lastAppliedHash && input.localHash === input.lastAppliedHash) return 'apply'
  return 'skip_dirty'
}
