import { existsSync, mkdirSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { tahpPaths } from './paths'

interface FailedCaseItem {
  caseKey: string
  caseName: string
  module: string
  status: string
  message: string
}

/**
 * Build a failure evidence bundle from a self-check report for bug-analysis consumption.
 *
 * Output: reports/self-check/{deviceId}/{ts}/failure-bundle/
 *   - failed-cases.json  (from detail.json failedCaseItems)
 *   - README.md           (problem description for bug-analysis)
 *   - copies of any case logs found nearby
 */
export async function buildFailureBundle(
  reportDir: string,
): Promise<{ dir: string; description: string } | null> {
  const detailPath = join(reportDir, 'detail.json')
  if (!existsSync(detailPath)) return null

  let detail: Record<string, unknown>
  try {
    detail = JSON.parse(readFileSync(detailPath, 'utf-8'))
  } catch {
    return null
  }

  const failedCases = (detail.failedCaseItems ?? []) as FailedCaseItem[]
  if (!failedCases.length) return null

  const bundleDir = join(reportDir, 'failure-bundle')
  mkdirSync(bundleDir, { recursive: true })

  writeFileSync(
    join(bundleDir, 'failed-cases.json'),
    JSON.stringify(failedCases, null, 2),
    'utf-8',
  )

  // Copy any logcat or case log files from the report dir
  const logFiles = ['logcat.txt', 'logcat_main.txt', 'test_log.txt']
  for (const name of logFiles) {
    const src = join(reportDir, name)
    if (existsSync(src)) {
      copyFileSync(src, join(bundleDir, name))
    }
  }

  const description = buildDescription(failedCases)
  writeFileSync(join(bundleDir, 'README.md'), description, 'utf-8')

  return { dir: bundleDir, description }
}

function buildDescription(failedCases: FailedCaseItem[]): string {
  const lines = [
    '# 自检失败证据包',
    '',
    `共 ${failedCases.length} 条失败用例：`,
    '',
  ]
  for (const c of failedCases.slice(0, 20)) {
    lines.push(`- **${c.caseName}** (${c.module}): ${c.message || c.status}`)
  }
  if (failedCases.length > 20) {
    lines.push(`- …及其他 ${failedCases.length - 20} 条`)
  }
  return lines.join('\n')
}

/**
 * Resolve the report directory for a given device and self-check session.
 */
export function resolveReportDir(deviceId: string, startTime: string): string {
  const ts = startTime.replace(/[:.]/g, '-')
  return join(tahpPaths.reportsDir, 'self-check', deviceId, ts)
}
