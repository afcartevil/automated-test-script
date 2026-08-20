/**
 * TAHP 路由聚合 — 一次性挂载所有 /api/tahp/* 路由.
 */
import type Koa from 'koa'
import { tahpKnowledgeRoutes } from './knowledge'
import { tahpReportsRoutes } from './reports'
import { tahpAdaptRoutes } from './adapt'
import { tahpSkillsRoutes } from './skills'
import { tahpSkillSyncRoutes } from './skill-sync'
import { tahpBugAnalysisRoutes } from './bug-analysis'
import { tahpSelfCheckRoutes } from './self-check'
import { tahpGerritReviewRoutes } from './gerrit-review'
import { tahpGerritConfigRoutes } from './gerrit-config'
import { tahpSkillConfigRoutes } from './skill-config'
import { tahpDeviceSelfCheckRoutes } from './device-self-check'
import { tahpTestPlanningRoutes } from './test-planning'
import { tahpModemBaselineRoutes } from './modem-baseline'
import { tahpGkiPatchRoutes } from './gki-patch'
import { tahpAdaptPipelineRoutes } from './adapt-pipeline'
import { tahpEvalRoutes } from './eval'
import { tahpCodePullRoutes } from './code-pull'
import { tahpCentralSsoRoutes } from './central-sso'

export function registerTahpRoutes(app: Koa) {
  app.use(tahpKnowledgeRoutes.routes())
  app.use(tahpReportsRoutes.routes())
  app.use(tahpAdaptRoutes.routes())
  // skill-sync 静态路径先于 skills 的 :skillId 挂载，避免未来冲突
  app.use(tahpSkillSyncRoutes.routes())
  app.use(tahpSkillsRoutes.routes())
  app.use(tahpBugAnalysisRoutes.routes())
  app.use(tahpSelfCheckRoutes.routes())
  app.use(tahpGerritReviewRoutes.routes())
  app.use(tahpGerritConfigRoutes.routes())
  app.use(tahpSkillConfigRoutes.routes())
  app.use(tahpDeviceSelfCheckRoutes.routes())
  app.use(tahpTestPlanningRoutes.routes())
  app.use(tahpModemBaselineRoutes.routes())
  app.use(tahpGkiPatchRoutes.routes())
  app.use(tahpAdaptPipelineRoutes.routes())
  app.use(tahpEvalRoutes.routes())
  app.use(tahpCodePullRoutes.routes())
  app.use(tahpCentralSsoRoutes.routes())
}
