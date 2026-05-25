/**
 * gateway-runner stub — Gateway Runner removed from TAHP.
 */

export type GatewayRunResult = {
  pid?: number
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function startGatewayRunManaged(_hermesBin: string, _options?: Record<string, unknown>): GatewayRunResult {
  return {}
}
