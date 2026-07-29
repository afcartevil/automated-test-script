import type { StageDefinition } from './types'

const REGISTRY = new Map<string, StageDefinition>()

export function registerStage(def: StageDefinition): void {
  if (REGISTRY.has(def.key)) {
    throw new Error(`stage already registered: ${def.key}`)
  }
  REGISTRY.set(def.key, def)
}

export function getStage(key: string): StageDefinition | undefined {
  return REGISTRY.get(key)
}

export function listStages(): StageDefinition[] {
  return [...REGISTRY.values()]
}

/** 仅测试用 */
export function resetRegistryForTest(): void {
  REGISTRY.clear()
}

/** 仅测试用：允许覆盖已注册阶段 */
export function registerStageForTest(def: StageDefinition): void {
  REGISTRY.set(def.key, def)
}
