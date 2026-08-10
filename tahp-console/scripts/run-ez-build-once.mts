/**
 * 单独跑 ez-build（不经流水线 UI）
 *
 * Usage:
 *   npx tsx scripts/run-ez-build-once.mts
 */
import { setTimeout as sleep } from 'timers/promises'

process.env.TAHP_PROJECT_ROOT ||= 'D:\\code\\EA\\easyadapter'

const { buildCapability } = await import(
  '../packages/server/src/services/tahp/adapt-pipeline/build-capability.ts'
)

const input = {
  pipelineRunId: `manual-ez-${Date.now()}`,
  project: 'cl6_h898',
  systemPath: 'Z:\\a14-rdtool\\system',
  vendorPath: 'Z:\\a14-rdtool\\system',
  variant: 'userdebug',
  buildFlag: 'stable',
  buildTargets: ['krn', 'vext', 'hal', 'odm'],
  needPack: true,
}

console.log('[ez-build-once] start', input)
const probe = await buildCapability.probe()
console.log('[ez-build-once] probe', probe)

const { runId } = await buildCapability.start(input)
console.log('[ez-build-once] runId=', runId)

const unsub = buildCapability.subscribe?.(runId, (ev) => {
  if (ev.line) console.log('[log]', ev.line)
  else if (ev.status?.message) console.log('[status]', ev.status.state, ev.status.phase, ev.status.message)
})

for (;;) {
  const st = await buildCapability.getStatus(runId)
  if (st.state === 'success' || st.state === 'failed' || st.state === 'cancelled') {
    console.log('[ez-build-once] final', JSON.stringify(st, null, 2))
    unsub?.()
    process.exit(st.state === 'success' ? 0 : 1)
  }
  await sleep(5000)
}
