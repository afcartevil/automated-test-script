/**
 * copilot-models stub — Copilot OAuth integration removed from TAHP.
 */

export type CopilotModelMeta = {
  id: string
  name: string
  vendor?: string
  preview?: boolean
  disabled?: boolean
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function getCopilotModelsDetailed(_envContent: string): Promise<CopilotModelMeta[]> {
  return []
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function resolveCopilotOAuthToken(_envContent: string): Promise<string | null> {
  return null
}
