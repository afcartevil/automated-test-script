/**
 * 同步 case_config/*.json 的 cases 数组，从 case_info.json 中读取用例名称。
 */
import { readFileSync, writeFileSync, existsSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, '..', 'tahp-console', 'packages', 'server', 'src', 'services', 'tahp', 'self-check')

const MODULES = [
  { testType: 'str4', module: 'tdd', moduleLabel: '通信框架', conditions: { dutSimCount: 2, auxRequired: 1, auxSimCount: 1 }, defaultCaseMode: 'aux_for_dut_mirror' },
  { testType: 'str4', module: 'driver_component', moduleLabel: '驱动-器件', conditions: { dutSimCount: 0, auxRequired: 0, auxSimCount: 0 }, defaultCaseMode: 'solo' },
  { testType: 'str4', module: 'driver_hardware', moduleLabel: '驱动-硬测', conditions: { dutSimCount: 0, auxRequired: 0, auxSimCount: 0 }, defaultCaseMode: 'solo' },
  { testType: 'week', module: 'tdd', moduleLabel: '通信框架', conditions: { dutSimCount: 1, auxRequired: 1, auxSimCount: 1 }, defaultCaseMode: 'aux_for_dut_mirror' },
  { testType: 'week', module: 'driver', moduleLabel: '驱动', conditions: { dutSimCount: 0, auxRequired: 0, auxSimCount: 0 }, defaultCaseMode: 'solo' },
]

const CONFIG_DIR = join(ROOT, 'case_config')

for (const { testType, module, moduleLabel, conditions, defaultCaseMode } of MODULES) {
  const infoPath = join(ROOT, 'python', 'cases', testType, module, 'case_info.json')
  const configPath = join(CONFIG_DIR, `${testType}_${module}.json`)

  let cases = []
  if (existsSync(infoPath)) {
    const infoList = JSON.parse(readFileSync(infoPath, 'utf-8'))
    cases = infoList.map((entry, idx) => ({
      caseIndex: idx + 1,
      caseName: entry['用例名'] || entry.case_name || `用例${idx + 1}`,
      canReuse: isReusable(entry['用例名'] || '')
    }))
  }

  const config = {
    testType,
    module,
    moduleLabel,
    conditions,
    defaultCaseMode,
    cases
  }

  writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf-8')
  console.log(`  Updated ${testType}_${module}.json: ${cases.length} cases`)
}

function isReusable(name) {
  const lower = (name || '').toLowerCase()
  // 可复用特征：主被叫、收发、互测
  const reusableKeywords = ['主被叫', '发送&接收', '收发', '来电', '互测', 'mirror', '双向']
  return reusableKeywords.some(kw => lower.includes(kw))
}

console.log('\n完成')