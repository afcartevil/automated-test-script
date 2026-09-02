/**
 * 适配路径参数解析引擎。
 *
 * 字段增删改：只改 path-param-fields.ts 的 PATH_PARAM_FIELDS（文件头有操作说明）。
 * 本文件负责依赖排序、调度 parse()、以及把落盘结果展平给 AI 适配 formData。
 * flattenPathParams() 使用 fields[].value（含用户手填），不要改成只用 ok 的项。
 */
import type { PathParamField, PathParamInputs, PathParams } from './types'
import {
  PATH_PARAM_FIELDS,
  type PathParamFieldDef,
  type PathParamParseContext,
} from './path-param-fields'

export type { PathParamFieldDef, PathParamParseContext }
export { PATH_PARAM_FIELDS } from './path-param-fields'
export {
  isKernelVersionAtLeast,
  kernelProjectDtsVendor,
  listSubdirs,
  matchesProjectPrefix,
  normalizeKernelVersion,
  pathExists,
  readMkVar,
  requireExisting,
  winDir,
  winJoin,
} from './path-param-fields'

function orderFields(fields: PathParamFieldDef[]): PathParamFieldDef[] {
  const remaining = new Set(fields.map(f => f.key))
  const byKey = new Map(fields.map(f => [f.key, f]))
  const result: PathParamFieldDef[] = []
  while (remaining.size) {
    const ready = fields.filter(f =>
      remaining.has(f.key) && f.dependsOn.every(d => !remaining.has(d)),
    )
    if (!ready.length) {
      for (const key of remaining) {
        const def = byKey.get(key)
        if (def) result.push(def)
      }
      break
    }
    for (const def of ready) {
      result.push(def)
      remaining.delete(def.key)
    }
  }
  return result
}

function normalizeInputs(inputs: PathParamInputs): PathParamInputs {
  const system = inputs.NEW_SYSTEM_ROOT?.trim()
  const trsystem = inputs.NEW_TRSYSTEM_ROOT?.trim()
  const projectFull = inputs.PROJECT_FULL?.trim()
  return {
    project_code: String(inputs.project_code ?? '').trim(),
    OLD_VENDOR_ROOT: String(inputs.OLD_VENDOR_ROOT ?? '').trim(),
    NEW_VENDOR_ROOT: String(inputs.NEW_VENDOR_ROOT ?? '').trim(),
    ...(system ? { NEW_SYSTEM_ROOT: system } : {}),
    ...(trsystem ? { NEW_TRSYSTEM_ROOT: trsystem } : {}),
    ...(projectFull ? { PROJECT_FULL: projectFull } : {}),
  }
}

export function parsePathParams(
  inputs: PathParamInputs,
  fieldDefs: PathParamFieldDef[] = PATH_PARAM_FIELDS,
): PathParams {
  const normalized = normalizeInputs(inputs)
  const values: Record<string, string> = {}
  const okKeys = new Set<string>()
  const byKey = new Map<string, PathParamField>()
  const ctx: PathParamParseContext = { inputs: normalized, values }

  for (const def of orderFields(fieldDefs)) {
    const missing = def.dependsOn.filter(d => !okKeys.has(d))
    if (missing.length) {
      byKey.set(def.key, {
        key: def.key,
        label: def.label,
        kind: def.kind,
        ok: false,
        value: '',
        error: `依赖 ${missing.join(', ')} 解析失败`,
      })
      continue
    }

    const parsed = def.parse(ctx)
    const ok = Boolean(parsed.ok && (parsed.value ?? '').trim())
    const value = ok ? String(parsed.value).trim() : ''
    const field: PathParamField = {
      key: def.key,
      label: def.label,
      kind: def.kind,
      ok,
      value,
      ...(ok ? { parsed_value: value } : {}),
      ...(!ok && parsed.error ? { error: parsed.error } : {}),
      ...(parsed.options?.length ? { options: parsed.options } : {}),
    }
    if (ok) {
      values[def.key] = value
      okKeys.add(def.key)
    }
    byKey.set(def.key, field)
  }

  return {
    inputs: normalized,
    fields: fieldDefs.map(d => byKey.get(d.key)!),
    parsed_at: new Date().toISOString(),
  }
}

/** 展平为适配 Agent 的 formData；value 含解析失败后的手工覆盖。 */
export function flattenPathParams(pp?: PathParams | null): {
  formData: Record<string, string>
  formFields: Array<{ name: string; label: string; required?: boolean }>
} {
  const formData: Record<string, string> = {}
  const formFields: Array<{ name: string; label: string; required?: boolean }> = []
  if (!pp) return { formData, formFields }

  const add = (name: string, value: string | undefined) => {
    formData[name] = String(value ?? '')
    formFields.push({ name, label: name, required: false })
  }

  add('project_code', pp.inputs.project_code)
  add('OLD_VENDOR_ROOT', pp.inputs.OLD_VENDOR_ROOT)
  add('NEW_VENDOR_ROOT', pp.inputs.NEW_VENDOR_ROOT)
  add('NEW_SYSTEM_ROOT', pp.inputs.NEW_SYSTEM_ROOT ?? '')
  add('NEW_TRSYSTEM_ROOT', pp.inputs.NEW_TRSYSTEM_ROOT ?? '')
  for (const field of pp.fields ?? []) {
    add(field.key, field.value)
  }
  return { formData, formFields }
}
