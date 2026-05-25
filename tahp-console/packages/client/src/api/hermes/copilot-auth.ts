/**
 * copilot-auth stub — Copilot OAuth removed from TAHP.
 */

export type CopilotTokenSource = 'env' | 'gh-cli' | 'apps-json'

export type CopilotTokenStatus = {
  available: boolean
  source?: CopilotTokenSource
}

export async function checkCopilotToken(): Promise<CopilotTokenStatus> {
  return { available: false }
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function enableCopilot(): Promise<void> {}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function disableCopilot(): Promise<void> {}
