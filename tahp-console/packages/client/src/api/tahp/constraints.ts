import { tahpGet, tahpPost, tahpPut } from './client'

export interface ConstraintFile {
  module: string
  file: string
  content: string
}

export interface ValidateResult {
  ok: boolean
  stdout: string
  stderr: string
  exitCode: number
}

export function readConstraint(module: string, file: string): Promise<ConstraintFile> {
  return tahpGet<ConstraintFile>(`/api/tahp/constraints/${encodeURIComponent(module)}/${encodeURIComponent(file)}`)
}

export function validateConstraint(module: string, file: string, content: string): Promise<ValidateResult> {
  return tahpPost<ValidateResult>('/api/tahp/constraints/validate', { module, file, content })
}

export function saveConstraint(module: string, file: string, content: string, skipValidate = false): Promise<void> {
  return tahpPut<void>(`/api/tahp/constraints/${encodeURIComponent(module)}/${encodeURIComponent(file)}`, { content, skipValidate })
}
