import Router from '@koa/router'
import * as ctrl from '../controllers/webhook'
import {
  handleModemBaselineNotify,
  handleModemBaselineNotifyInfo,
} from '../controllers/modem-baseline-notify'
import {
  handleGkiUpgradeNotify,
  handleGkiUpgradeNotifyInfo,
} from '../controllers/gki-upgrade-notify'

export const webhookRoutes = new Router()

webhookRoutes.post('/webhook', ctrl.handleWebhook)
/** Public: TONES / external tools push baseline-complete notice (manual confirm in UI). */
webhookRoutes.get('/webhook/modem-baseline/notify', handleModemBaselineNotifyInfo)
webhookRoutes.post('/webhook/modem-baseline/notify', handleModemBaselineNotify)
/** Public: GKI upgrade interval notice (manual confirm in UI). */
webhookRoutes.get('/webhook/gki-upgrade/notify', handleGkiUpgradeNotifyInfo)
webhookRoutes.post('/webhook/gki-upgrade/notify', handleGkiUpgradeNotify)
