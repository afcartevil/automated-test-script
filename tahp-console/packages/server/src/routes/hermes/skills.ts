import Router from '@koa/router'
import * as ctrl from '../../controllers/hermes/skills'

export const skillRoutes = new Router()

skillRoutes.get('/api/hermes/skills', ctrl.list)
skillRoutes.get('/api/hermes/skills/usage/stats', ctrl.usageStats)
skillRoutes.put('/api/hermes/skills/toggle', ctrl.toggle)
skillRoutes.put('/api/hermes/skills/pin', ctrl.pin_)
skillRoutes.post('/api/hermes/skills/scan-path', ctrl.scanPath)
skillRoutes.post('/api/hermes/skills/import-from-path', ctrl.importFromPath)
skillRoutes.post('/api/hermes/skills/preview-import', ctrl.previewImport)
skillRoutes.post('/api/hermes/skills/import', ctrl.importSkills)
skillRoutes.post('/api/hermes/skills/backfill-categories', ctrl.backfillCategories)
skillRoutes.get('/api/hermes/skills/:category/:skill/history/:hash', ctrl.skillHistoryCommit)
skillRoutes.get('/api/hermes/skills/:category/:skill/history', ctrl.skillHistory)
skillRoutes.get('/api/hermes/skills/:category/:skill/files', ctrl.listFiles)
skillRoutes.get('/api/hermes/skills/{*path}', ctrl.readFile_)
