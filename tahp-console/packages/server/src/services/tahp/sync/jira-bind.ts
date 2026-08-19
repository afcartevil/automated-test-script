/**
 * 把本机 Jira 账号绑定到中心：校验（中心侧 myself）→ 开通/刷新 business_owner → 落 session。
 * 不把 Jira 密码写入除 bind 请求体外的任何同步接口。
 */
import { logger } from '../../logger'
import { isCentralConfigured, isLocal } from '../runtime-mode'
import { writeCentralUserSession } from '../central-user-session'
import { centralClient } from './central-client'
import { reconnectTaskNotifyClient } from './task-notify-client'
import { ensureDerivedJiraUserConfig, readJiraUserConfig } from '../jira-user-config'

export type JiraBindResult = {
  token: string
  user: { username: string; role: string; auth_source?: string; display_name?: string }
  ticket: string
  consume_path: string
}

function skipBind(): boolean {
  return !isLocal() || !isCentralConfigured() || !!process.env.VITEST || process.env.TAHP_SKIP_JIRA_BIND === '1'
}

export async function bindJiraToCentral(input: {
  username: string
  password: string
  baseUrl?: string
}): Promise<JiraBindResult | null> {
  if (skipBind()) return null
  const username = input.username.trim()
  if (!username || !input.password) return null
  try {
    const data = await centralClient.jiraBind({
      username,
      password: input.password,
      jira_base_url: input.baseUrl,
    })
    writeCentralUserSession({
      username: data.user.username,
      role: data.user.role,
      token: data.token,
    })
    reconnectTaskNotifyClient(data.user.username)
    logger.info({ username: data.user.username, role: data.user.role }, '[jira-bind] bound to central')
    return data
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[jira-bind] failed')
    return null
  }
}

export async function bindStoredJiraIfAny(): Promise<JiraBindResult | null> {
  const stored = ensureDerivedJiraUserConfig() || readJiraUserConfig()
  if (!stored) return null
  return bindJiraToCentral({
    username: stored.username,
    password: stored.password,
    baseUrl: stored.base_url,
  })
}

/** 保存 Jira 后调用；失败不影响本机凭据落盘 */
export function scheduleBindJiraToCentral(input: {
  username: string
  password: string
  baseUrl?: string
}): void {
  void bindJiraToCentral(input)
}
