#!/usr/bin/env node
/**
 * 评测 CLI —— 触发批跑并与 baseline 对比，回退超阈值时退出码非 0。
 *
 * 评测必须跑在 BFF 进程内（Agent Bridge 只在那里活着），所以本脚本只是 REST 客户端。
 *
 * 用法:
 *   npm run eval:bug
 *   npm run eval:adapt
 *   npm run eval:retrieval
 *   npm run eval:bug -- --cases eval-tel-001 --baseline <runId> --max-regression 0.05
 *
 * 选项:
 *   --suite <name>       bug-analysis | adapt | retrieval（默认：由 npm script 决定）
 *   --cases <a,b>        只跑指定用例（默认全量）
 *   --model <name>       被评模型标签
 *   --judge-model <name> 判官模型（bug / adapt soft LLM；retrieval 忽略）
 *   --concurrency <n>    并发（默认 2；retrieval 可更高）
 *   --baseline <runId>   与该次评测对比并做门禁
 *   --max-regression <f> 允许的最大回退幅度（默认 0.05）
 *   --url <base>         BFF 地址（默认 http://127.0.0.1:${PORT||8650}）
 *   --token <token>      鉴权 token（默认读 ~/.hermes-web-ui/.token）
 *   --json               只输出机器可读 JSON
 */
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, resolve } from 'node:path'

const POLL_INTERVAL_MS = 5000

function parseArgs(argv) {
  const args = {
    cases: [],
    maxRegression: 0.05,
    json: false,
    suite: process.env.TAHP_EVAL_SUITE || 'bug-analysis',
  }
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    const next = () => argv[++i]
    switch (arg) {
      case '--suite': args.suite = next(); break
      case '--cases': args.cases = String(next() || '').split(',').map(s => s.trim()).filter(Boolean); break
      case '--model': args.model = next(); break
      case '--judge-model': args.judgeModel = next(); break
      case '--concurrency': args.concurrency = Number(next()); break
      case '--baseline': args.baseline = next(); break
      case '--max-regression': args.maxRegression = Number(next()); break
      case '--url': args.url = next(); break
      case '--token': args.token = next(); break
      case '--json': args.json = true; break
      case '--help': case '-h': args.help = true; break
      default:
        if (arg.startsWith('--')) throw new Error(`未知参数: ${arg}`)
    }
  }
  if (args.suite !== 'bug-analysis' && args.suite !== 'adapt' && args.suite !== 'retrieval') {
    throw new Error(`非法 suite: ${args.suite}`)
  }
  return args
}

function resolveBaseUrl(explicit) {
  if (explicit) return explicit.replace(/\/+$/, '')
  if (process.env.TAHP_CONSOLE_URL) return process.env.TAHP_CONSOLE_URL.replace(/\/+$/, '')
  return `http://127.0.0.1:${process.env.PORT || 8650}`
}

function resolveToken(explicit) {
  if (explicit) return explicit
  if (process.env.TAHP_TOKEN) return process.env.TAHP_TOKEN
  const appHome = process.env.HERMES_WEB_UI_HOME?.trim() || process.env.HERMES_WEBUI_STATE_DIR?.trim()
  const tokenFile = join(appHome ? resolve(appHome) : join(homedir(), '.hermes-web-ui'), '.token')
  try {
    return readFileSync(tokenFile, 'utf-8').trim()
  } catch {
    return ''
  }
}

async function api(baseUrl, token, path, init = {}) {
  const headers = { 'content-type': 'application/json', ...(init.headers || {}) }
  if (token) headers.authorization = `Bearer ${token}`

  let res
  try {
    res = await fetch(`${baseUrl}${path}`, { ...init, headers })
  } catch (err) {
    throw new Error(`无法连接 BFF ${baseUrl}（${err.message}）。请确认服务已启动，或用 --url 指定地址。`)
  }

  const text = await res.text()
  let body
  try {
    body = text ? JSON.parse(text) : {}
  } catch {
    throw new Error(`${path} 返回非 JSON（HTTP ${res.status}）: ${text.slice(0, 200)}`)
  }
  if (!res.ok || body.success === false) {
    throw new Error(body.error || `${path} 失败（HTTP ${res.status}）`)
  }
  return body.data
}

function pct(value) {
  return `${(value * 100).toFixed(1)}%`
}

function signed(value) {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(1)}pp`
}

function printSummary(run) {
  const { variant } = run
  console.log('')
  console.log(`评测 ${run.run_id}  状态=${run.status}`)
  console.log(`变体: model=${variant.model || '(profile 默认)'} judge=${variant.judge_model || '(profile 默认)'} skills=${variant.skills_hash} prompt=${variant.prompt_version}`)
  console.log(`用例 ${run.total}  通过 ${run.passed}  警告 ${run.warned}  失败 ${run.failed}  异常 ${run.errored}`)
  console.log(`通过率 ${pct(run.pass_rate)}  平均分 ${run.avg_score.toFixed(3)}`)

  const problems = run.cases.filter(c => c.status !== 'passed')
  if (problems.length) {
    console.log('')
    console.log('未通过用例:')
    for (const item of problems) {
      const score = typeof item.total === 'number' ? item.total.toFixed(2) : '-'
      const detail = item.error ? ` ${item.error}` : ''
      console.log(`  [${item.status}] ${item.case_id}  score=${score}  task=${item.task_id || '-'}${detail}`)
    }
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  if (args.help) {
    console.log(readFileSync(new URL(import.meta.url), 'utf-8').split('*/')[0].replace(/^#!.*\n/, ''))
    return 0
  }

  const baseUrl = resolveBaseUrl(args.url)
  const token = resolveToken(args.token)
  const log = args.json ? () => {} : (...a) => console.log(...a)

  const started = await api(baseUrl, token, '/api/tahp/eval/runs', {
    method: 'POST',
    body: JSON.stringify({
      suite: args.suite,
      case_ids: args.cases.length ? args.cases : undefined,
      model: args.model,
      judge_model: args.judgeModel,
      concurrency: Number.isFinite(args.concurrency) ? args.concurrency : undefined,
    }),
  })

  const runId = started.run_id
  log(`评测已启动: ${runId}（suite=${args.suite}, ${started.total} 个用例）`)

  let run
  let lastDone = -1
  for (;;) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS))
    run = await api(baseUrl, token, `/api/tahp/eval/runs/${runId}?suite=${encodeURIComponent(args.suite)}`)
    const done = run.cases.length
    if (done !== lastDone) {
      log(`  进度 ${done}/${run.total}`)
      lastDone = done
    }
    if (run.status !== 'running') break
  }

  if (!args.json) printSummary(run)

  let comparison = null
  let regressionExceeded = false

  if (args.baseline) {
    comparison = await api(
      baseUrl,
      token,
      `/api/tahp/eval/runs/${runId}/compare?baseline=${encodeURIComponent(args.baseline)}`,
    )

    log('')
    log(`与 baseline ${comparison.baseline_run_id} 对比:`)
    log(`  通过率 ${signed(comparison.pass_rate_delta)}   平均分 ${signed(comparison.avg_score_delta)}`)
    if (comparison.regressed.length) log(`  回归用例: ${comparison.regressed.join(', ')}`)
    if (comparison.improved.length) log(`  改善用例: ${comparison.improved.join(', ')}`)
    if (!comparison.variant_matched) {
      log('  注意: 变体指纹与 baseline 不一致（模型或 skill 改过），分数差异不能单一归因。')
    }

    const limit = -Math.abs(args.maxRegression)
    regressionExceeded =
      comparison.pass_rate_delta < limit || comparison.avg_score_delta < limit
  }

  if (args.json) {
    console.log(JSON.stringify({ run, comparison, regression_exceeded: regressionExceeded }, null, 2))
  }

  if (run.status === 'failed') {
    if (!args.json) console.error(`\n评测执行失败: ${run.error || '未知错误'}`)
    return 1
  }
  if (regressionExceeded) {
    if (!args.json) {
      console.error(`\n质量回退超过阈值 ${args.maxRegression}，门禁不通过。`)
    }
    return 1
  }
  return 0
}

main()
  .then(code => { process.exitCode = code })
  .catch(err => {
    console.error(`[eval] ${err.message}`)
    process.exitCode = 1
  })
