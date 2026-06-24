/**
 * 同步 case_info.json 的 case_index 字段，并生成缺失的 .py 用例脚本。
 * case_info.json 数组索引 0-based → case_index 为 1-based。
 */
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const CASE_ROOT = join(__dirname, '..', 'tahp-console', 'packages', 'server', 'src', 'services', 'tahp', 'self-check', 'python', 'cases')

const MODULES = [
  { testType: 'str4', module: 'tdd' },
  { testType: 'str4', module: 'driver_component' },
  { testType: 'str4', module: 'driver_hardware' },
  { testType: 'week', module: 'tdd' },
  { testType: 'week', module: 'driver' },
]

function stubScriptContent(testType, module, caseIndex) {
  return `"""${testType.toUpperCase()} ${module} — 用例${caseIndex}（待实现）。"""


def run(category=None, case_index=None, device_info=None, **context):
    """此用例尚未实现自动化，需人工测试。"""
    return {
        "status": "skip",
        "message": "需人工测试",
        "full_automation": False,
    }
`
}

function processModule(testType, module) {
  const dir = join(CASE_ROOT, testType, module)
  const infoPath = join(dir, 'case_info.json')

  if (!existsSync(infoPath)) {
    console.log(`  SKIP: ${infoPath} not found`)
    return
  }

  // 读取 case_info.json
  const raw = readFileSync(infoPath, 'utf-8')
  const entries = JSON.parse(raw)
  if (!Array.isArray(entries)) {
    console.log(`  SKIP: ${infoPath} is not an array`)
    return
  }

  console.log(`  Processing ${testType}/${module}: ${entries.length} entries`)

  // 添加 case_index
  let modified = false
  entries.forEach((entry, idx) => {
    const caseIndex = idx + 1
    if (entry.case_index !== caseIndex) {
      entry.case_index = caseIndex
      modified = true
    }
  })

  if (modified) {
    writeFileSync(infoPath, JSON.stringify(entries, null, 2), 'utf-8')
    console.log(`    Updated ${infoPath} with case_index`)
  }

  // 检查并生成缺失的 .py 脚本
  const existingFiles = new Set(readdirSync(dir).filter(f => f.endsWith('.py') && f.startsWith('case')))
  let created = 0

  for (let i = 0; i < entries.length; i++) {
    const caseIndex = i + 1
    const fileName = `case${caseIndex}.py`
    if (!existingFiles.has(fileName)) {
      const content = stubScriptContent(testType, module, caseIndex)
      writeFileSync(join(dir, fileName), content, 'utf-8')
      created++
    }
  }

  if (created > 0) {
    console.log(`    Created ${created} missing .py stubs`)
  } else {
    console.log(`    All .py scripts present`)
  }
}

console.log('=== 同步 case_info.json case_index 并补全 .py 脚本 ===\n')
for (const { testType, module } of MODULES) {
  processModule(testType, module)
}
console.log('\n=== 完成 ===')