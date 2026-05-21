import { tahpGet } from './client'

export interface PipelineSummary {
  name: string
  file: string
  size: number
}

export interface PipelineDetail {
  name: string
  file: string
  content: string
}

export function listPipelines(): Promise<PipelineSummary[]> {
  return tahpGet<PipelineSummary[]>('/api/tahp/pipelines')
}

export function getPipeline(file: string): Promise<PipelineDetail> {
  return tahpGet<PipelineDetail>(`/api/tahp/pipelines/${encodeURIComponent(file)}`)
}
