import { describe, expect, it } from 'vitest'
import type { PathParams } from '../../packages/client/src/api/tahp/adapt-pipeline'
import {
  applyPathParamResult,
  canParsePathParams,
  copyPathParamInputs,
  createPathParamScope,
  fillFormDataWithPathParams,
  flattenAdaptPathParams,
  isPathParamWorkspace,
  pathParamRequestPayload,
  pathParamsFresh,
  resetPathParamScope,
  setPathParamFieldValue,
  type AdaptPathParamScope,
} from '../../packages/client/src/utils/adapt-path-params'

function scopeWithInputs(): AdaptPathParamScope {
  const scope = createPathParamScope()
  scope.inputs.project_code = 'KM9'
  scope.inputs.OLD_VENDOR_ROOT = 'Z:\\old\\vendor'
  scope.inputs.NEW_VENDOR_ROOT = 'Z:\\new\\vendor'
  return scope
}

function sampleResult(overrides: Partial<PathParams> = {}): PathParams {
  return {
    inputs: {
      project_code: 'KM9',
      OLD_VENDOR_ROOT: 'Z:\\old\\vendor',
      NEW_VENDOR_ROOT: 'Z:\\new\\vendor',
    },
    fields: [
      { key: 'PROJECT_FULL', label: 'PROJECT_FULL', kind: 'select', ok: true, value: 'km9_h123', options: ['km9_h123'] },
      { key: 'SOC_PLATFROM', label: 'SOC_PLATFROM', kind: 'text', ok: true, value: 'mt6878' },
      { key: 'NEW_KERNEL_DWS_PATH', label: 'NEW_KERNEL_DWS_PATH', kind: 'text', ok: false, value: '', error: '文件不存在' },
    ],
    parsed_at: '2026-08-27T10:00:00.000Z',
    ...overrides,
  }
}

describe('adapt path params scope', () => {
  it('只在功能适配与特性适配工作区启用', () => {
    expect(isPathParamWorkspace('adapt-debug')).toBe(true)
    expect(isPathParamWorkspace('feature-adapt')).toBe(true)
    expect(isPathParamWorkspace('carrier-config')).toBe(false)
  })

  it('三个必填输入齐备才可解析', () => {
    const scope = createPathParamScope()
    expect(canParsePathParams(scope)).toBe(false)
    scope.inputs.project_code = 'KM9'
    scope.inputs.OLD_VENDOR_ROOT = 'Z:\\old\\vendor'
    expect(canParsePathParams(scope)).toBe(false)
    scope.inputs.NEW_VENDOR_ROOT = 'Z:\\new\\vendor'
    expect(canParsePathParams(scope)).toBe(true)
  })

  it('输入变化后解析结果视为过期', () => {
    const scope = scopeWithInputs()
    expect(pathParamsFresh(scope)).toBe(false)
    applyPathParamResult(scope, sampleResult())
    expect(pathParamsFresh(scope)).toBe(true)
    scope.inputs.NEW_VENDOR_ROOT = 'Z:\\other\\vendor'
    expect(pathParamsFresh(scope)).toBe(false)
  })

  it('重新解析沿用已选 PROJECT_FULL', () => {
    const scope = scopeWithInputs()
    applyPathParamResult(scope, sampleResult())
    const payload = pathParamRequestPayload(scope)
    expect(payload.PROJECT_FULL).toBe('km9_h123')
    expect(payload.project_code).toBe('KM9')
    expect(payload).not.toHaveProperty('NEW_SYSTEM_ROOT')
  })

  it('展平使用手工覆盖值，且跳过空值', () => {
    const scope = scopeWithInputs()
    applyPathParamResult(scope, sampleResult())
    expect(flattenAdaptPathParams(scope).formData.NEW_KERNEL_DWS_PATH).toBeUndefined()

    setPathParamFieldValue(scope, 'NEW_KERNEL_DWS_PATH', 'Z:\\new\\vendor\\a.dws')
    const flat = flattenAdaptPathParams(scope)
    expect(flat.formData.NEW_KERNEL_DWS_PATH).toBe('Z:\\new\\vendor\\a.dws')
    expect(flat.formData.SOC_PLATFROM).toBe('mt6878')
    expect(flat.formData.NEW_SYSTEM_ROOT).toBeUndefined()
    expect(flat.formFields.map(f => f.name)).toContain('NEW_VENDOR_ROOT')
    expect(flat.formFields.every(f => f.required === false)).toBe(true)
  })

  it('未解析时不注入任何参数', () => {
    expect(flattenAdaptPathParams(createPathParamScope()).formData).toEqual({})
    expect(flattenAdaptPathParams(null).formFields).toEqual([])
  })

  it('补位不覆盖模块已填的同名字段，空值才补', () => {
    const scope = scopeWithInputs()
    applyPathParamResult(scope, sampleResult())
    const merged = fillFormDataWithPathParams(
      { SOC_PLATFROM: 'mt6897', PROJECT_FULL: '', debug_project: 'km9' },
      scope,
    )
    expect(merged.SOC_PLATFROM).toBe('mt6897')
    expect(merged.PROJECT_FULL).toBe('km9_h123')
    expect(merged.debug_project).toBe('km9')
    expect(merged.OLD_VENDOR_ROOT).toBe('Z:\\old\\vendor')
  })

  it('沿用上次输入为值拷贝，清空互不影响', () => {
    const scope = scopeWithInputs()
    const copied = copyPathParamInputs(scope.inputs)
    resetPathParamScope(scope)
    expect(scope.inputs.project_code).toBe('')
    expect(copied.project_code).toBe('KM9')
  })
})
