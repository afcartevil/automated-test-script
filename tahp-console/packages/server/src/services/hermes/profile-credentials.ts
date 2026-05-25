/**
 * profile-credentials stub — Third-party credential management removed from TAHP.
 */

export type SmartCloneCleanupResult = {
  strippedCredentials: string[]
  disabledPlatforms: string[]
  strippedConfigCredentials: string[]
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function smartCloneCleanup(_profile: string): SmartCloneCleanupResult {
  return {
    strippedCredentials: [],
    disabledPlatforms: [],
    strippedConfigCredentials: [],
  }
}
