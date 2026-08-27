/**
 * AI 适配调试「路径参数解析」按模块作用域状态。
 *
 * 解析逻辑本身仍在服务端 adapt-pipeline（POST /parse-path-params），此处只负责：
 * 每个「工作区:模块」各自持有一份输入与解析结果，并展平成注入关联 Skill 的 formData。
 * 展平规则与服务端 flattenPathParams 一致：用 fields[].value（含解析失败后的手工覆盖）。
 */
import type { PathParamField, PathParamInputs, PathParams } from '@/api/tahp/adapt-pipeline'

/** 提供路径解析面板的工作区（运营商配置不需要 vendor 树解析） */
export const PATH_PARAM_WORKSPACES = ['adapt-debug', 'feature-adapt'] as const

export type PathParamWorkspaceId = typeof PATH_PARAM_WORKSPACES[number]

export interface AdaptPathParamInputs {
  project_code: string
  OLD_VENDOR_ROOT: string
  NEW_VENDOR_ROOT: string
  NEW_SYSTEM_ROOT: string
}

export interface AdaptPathParamScope {
  inputs: AdaptPathParamInputs
  fields: PathParamField[]
  parsedAt: string
  /** 解析当时的输入签名；与当前输入不一致说明结果已过期 */
  parsedSignature: string
  parsing: boolean
  expanded: boolean
}

export function createPathParamInputs(): AdaptPathParamInputs {
  return {
    project_code: '',
    OLD_VENDOR_ROOT: '',
    NEW_VENDOR_ROOT: '',
    NEW_SYSTEM_ROOT: '',
  }
}

export function createPathParamScope(): AdaptPathParamScope {
  return {
    inputs: createPathParamInputs(),
    fields: [],
    parsedAt: '',
    parsedSignature: '',
    parsing: false,
    expanded: false,
  }
}

export function isPathParamWorkspace(workspaceId: string): boolean {
  return (PATH_PARAM_WORKSPACES as readonly string[]).includes(workspaceId)
}

/** 参与解析的三个必填输入构成签名；NEW_SYSTEM_ROOT 只随结果保存，不影响新鲜度 */
export function pathParamSignature(inputs: AdaptPathParamInputs): string {
  return [
    inputs.project_code.trim(),
    inputs.OLD_VENDOR_ROOT.trim(),
    inputs.NEW_VENDOR_ROOT.trim(),
  ].join('||')
}

export function canParsePathParams(scope: AdaptPathParamScope): boolean {
  const { project_code, OLD_VENDOR_ROOT, NEW_VENDOR_ROOT } = scope.inputs
  return Boolean(project_code.trim() && OLD_VENDOR_ROOT.trim() && NEW_VENDOR_ROOT.trim())
}

export function pathParamsFresh(scope: AdaptPathParamScope): boolean {
  if (!scope.fields.length || !scope.parsedSignature) return false
  return scope.parsedSignature === pathParamSignature(scope.inputs)
}

export function pathParamOkCount(scope: AdaptPathParamScope): number {
  return scope.fields.filter(f => f.ok).length
}

export function pathParamFailCount(scope: AdaptPathParamScope): number {
  return scope.fields.filter(f => !f.ok).length
}

/** 再次解析时沿用用户已选/已手填的项目目录 */
export function pathParamRequestPayload(scope: AdaptPathParamScope): PathParamInputs {
  const projectFull = scope.fields.find(f => f.key === 'PROJECT_FULL')?.value?.trim()
  const systemRoot = scope.inputs.NEW_SYSTEM_ROOT.trim()
  return {
    project_code: scope.inputs.project_code.trim(),
    OLD_VENDOR_ROOT: scope.inputs.OLD_VENDOR_ROOT.trim(),
    NEW_VENDOR_ROOT: scope.inputs.NEW_VENDOR_ROOT.trim(),
    ...(systemRoot ? { NEW_SYSTEM_ROOT: systemRoot } : {}),
    ...(projectFull ? { PROJECT_FULL: projectFull } : {}),
  }
}

export function applyPathParamResult(scope: AdaptPathParamScope, data: PathParams) {
  scope.fields = data.fields.map(f => ({ ...f }))
  scope.parsedAt = data.parsed_at
  scope.parsedSignature = pathParamSignature(scope.inputs)
}

export function setPathParamFieldValue(scope: AdaptPathParamScope, key: string, value: string) {
  scope.fields = scope.fields.map(f => (f.key === key ? { ...f, value } : f))
}

export function resetPathParamScope(scope: AdaptPathParamScope) {
  scope.inputs = createPathParamInputs()
  scope.fields = []
  scope.parsedAt = ''
  scope.parsedSignature = ''
}

export function copyPathParamInputs(from: AdaptPathParamInputs): AdaptPathParamInputs {
  return {
    project_code: from.project_code,
    OLD_VENDOR_ROOT: from.OLD_VENDOR_ROOT,
    NEW_VENDOR_ROOT: from.NEW_VENDOR_ROOT,
    NEW_SYSTEM_ROOT: from.NEW_SYSTEM_ROOT,
  }
}

export function pathParamFieldOptions(field: PathParamField): Array<{ label: string; value: string }> {
  return (field.options ?? []).map(v => ({ label: v, value: v }))
}

/**
 * 展平为注入关联 Skill 的 formData / formFields。
 * 只输出非空项：未解析或留空的字段不进入模块表单，避免污染提示词。
 */
export function flattenAdaptPathParams(scope?: AdaptPathParamScope | null): {
  formData: Record<string, string>
  formFields: Array<{ name: string; label: string; required?: boolean }>
} {
  const formData: Record<string, string> = {}
  const formFields: Array<{ name: string; label: string; required?: boolean }> = []
  if (!scope) return { formData, formFields }

  const add = (name: string, value: string) => {
    const v = String(value ?? '').trim()
    if (!v) return
    formData[name] = v
    formFields.push({ name, label: name, required: false })
  }

  add('project_code', scope.inputs.project_code)
  add('OLD_VENDOR_ROOT', scope.inputs.OLD_VENDOR_ROOT)
  add('NEW_VENDOR_ROOT', scope.inputs.NEW_VENDOR_ROOT)
  add('NEW_SYSTEM_ROOT', scope.inputs.NEW_SYSTEM_ROOT)
  for (const field of scope.fields) {
    add(field.key, field.value)
  }
  return { formData, formFields }
}

/** 路径解析结果补位到模块 formData：模块自身已填的同名字段优先保留 */
export function fillFormDataWithPathParams(
  formData: Record<string, string>,
  scope?: AdaptPathParamScope | null,
): Record<string, string> {
  const merged = { ...formData }
  for (const [key, value] of Object.entries(flattenAdaptPathParams(scope).formData)) {
    if (String(merged[key] ?? '').trim() === '') merged[key] = value
  }
  return merged
}
