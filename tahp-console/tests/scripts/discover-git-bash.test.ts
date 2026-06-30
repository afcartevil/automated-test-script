import { describe, expect, it } from 'vitest'
import {
  bashCandidatesFromGitExe,
  discoverGitBashPath,
  standardWindowsBashCandidates,
} from '../../scripts/lib/discover-git-bash.mjs'

describe('discover-git-bash', () => {
  it('derives bash paths from git.exe under cmd/', () => {
    expect(bashCandidatesFromGitExe('E:\\software\\Git\\cmd\\git.exe')).toEqual([
      'E:\\software\\Git\\bin\\bash.exe',
      'E:\\software\\Git\\usr\\bin\\bash.exe',
    ])
  })

  it('includes portable and Program Files candidates on Windows', () => {
    const candidates = standardWindowsBashCandidates({
      LOCALAPPDATA: 'C:\\Users\\me\\AppData\\Local',
      ProgramFiles: 'C:\\Program Files',
      'ProgramFiles(x86)': 'C:\\Program Files (x86)',
    })
    expect(candidates).toContain('C:\\Program Files\\Git\\bin\\bash.exe')
    expect(candidates).toContain('C:\\Users\\me\\AppData\\Local\\hermes\\git\\bin\\bash.exe')
  })

  it('prefers HERMES_GIT_BASH_PATH when file exists', () => {
    const path = discoverGitBashPath(
      { HERMES_GIT_BASH_PATH: 'D:\\custom\\bash.exe' },
      { exists: p => p === 'D:\\custom\\bash.exe' },
    )
    expect(path).toBe('D:\\custom\\bash.exe')
  })

  it('discovers bash via git.exe on non-standard install path', () => {
    const path = discoverGitBashPath(
      {},
      {
        exists: p => p === 'E:\\software\\Git\\bin\\bash.exe',
        findGitExe: () => 'E:\\software\\Git\\cmd\\git.exe',
        findBashOnPath: () => null,
      },
    )
    expect(path).toBe('E:\\software\\Git\\bin\\bash.exe')
  })

  it('returns null when nothing matches on Windows', () => {
    const path = discoverGitBashPath({}, {
      exists: () => false,
      findGitExe: () => null,
      findBashOnPath: () => null,
    })
    expect(path).toBeNull()
  })
})
