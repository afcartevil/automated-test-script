#!/usr/bin/env node
/**
 * EasyAdapter Windows 系统托盘常驻程序。
 * 菜单：打开控制台 / 重启服务 / 更新并重启 / 停止服务 / 查看日志 / 关闭程序
 */
import { existsSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import systrayModule from 'systray2'
import {
  buildTooltip,
  getPort,
  getTrayIconPath,
  openConsole,
  openLog,
  queryServiceStatus,
  readTrayPid,
  removeTrayPid,
  restartService,
  spawnFullRestart,
  stopService,
  writeTrayPid,
} from '../scripts/lib/tray-actions.mjs'

const SysTray = systrayModule.default ?? systrayModule

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = resolve(__dirname, '..')

const MENU = {
  OPEN: 'open',
  RESTART: 'restart',
  FULL_RESTART: 'full_restart',
  STOP: 'stop',
  LOG: 'log',
  QUIT: 'quit',
}

function menuItem(title, tooltip, id, click) {
  return { title, tooltip, checked: false, enabled: true, clickId: id, click }
}

function ensureSingleInstance() {
  const existing = readTrayPid()
  if (existing && existing !== process.pid) {
    try {
      process.kill(existing, 0)
      process.exit(0)
    } catch {
      /* stale pid */
    }
  }
  writeTrayPid(process.pid)
}

function cleanupAndExit(systray) {
  removeTrayPid()
  try { systray.kill(false) } catch { /* ignore */ }
  setTimeout(() => process.exit(0), 200)
}

function shutdownApplication(systray) {
  stopService()
  cleanupAndExit(systray)
}

async function main() {
  if (process.platform !== 'win32') {
    process.exit(0)
  }

  ensureSingleInstance()

  const iconPath = getTrayIconPath()
  if (!existsSync(iconPath)) {
    console.error(`[EasyAdapter] 托盘图标不存在: ${iconPath}`)
    console.error('  请执行: cd tahp-console && npm run tray:icon')
    process.exit(1)
  }

  const port = getPort()
  let status = queryServiceStatus()
  let tooltip = buildTooltip(status, port)
  let systray

  const refreshTooltip = () => {
    status = queryServiceStatus()
    tooltip = buildTooltip(status, port)
    if (!systray) return
    systray.sendAction({
      type: 'update-menu',
      menu: {
        icon: iconPath,
        title: 'EasyAdapter',
        tooltip,
        items: buildItems(),
      },
    })
  }

  const buildItems = () => [
    menuItem('打开控制台', '在浏览器中打开 EasyAdapter', MENU.OPEN, () => openConsole(port)),
    SysTray.separator,
    menuItem('重启服务', '快速重启 BFF（不拉代码）', MENU.RESTART, () => {
      restartService()
      setTimeout(refreshTooltip, 1500)
    }),
    menuItem('更新并重启', '拉取代码、构建并重启（研发用）', MENU.FULL_RESTART, () => {
      if (systray) {
        systray.sendAction({
          type: 'update-menu',
          menu: { icon: iconPath, title: 'EasyAdapter', tooltip: 'EasyAdapter 更新中…', items: buildItems() },
        })
      }
      spawnFullRestart()
      setTimeout(() => cleanupAndExit(systray), 500)
    }),
    menuItem('停止服务', '停止后台 BFF 服务', MENU.STOP, () => {
      stopService()
      setTimeout(refreshTooltip, 1000)
    }),
    SysTray.separator,
    menuItem('查看日志', '打开 server.log', MENU.LOG, () => { openLog() }),
    menuItem('关闭程序', '停止服务并退出托盘', MENU.QUIT, () => shutdownApplication(systray)),
  ]

  systray = new SysTray({
    menu: {
      icon: iconPath,
      title: 'EasyAdapter',
      tooltip,
      items: buildItems(),
    },
    debug: false,
    copyDir: false,
  })

  systray.onClick((action) => {
    if (action?.item?.click) action.item.click()
  })

  await systray.ready()

  systray.onError((err) => {
    console.error('[EasyAdapter] 托盘错误:', err)
  })

  process.on('SIGINT', () => cleanupAndExit(systray))
  process.on('SIGTERM', () => cleanupAndExit(systray))

  setInterval(refreshTooltip, 30_000)
}

main().catch((err) => {
  removeTrayPid()
  console.error('[EasyAdapter] 托盘启动失败:', err)
  process.exit(1)
})
