#!/usr/bin/env node
/**
 * EasyAdapter Windows 系统托盘常驻程序。
 * 菜单：打开控制台 / 重启服务 / 更新并重启 / 停止服务 / 查看日志 / 关闭程序
 *
 * systray2 / Windows 托盘注意：
 * 1) SysTray.separator 是共享单例；菜单中出现两次时必须各自克隆，否则
 *    addInternalId 会覆盖同一对象的 __id，原生右键菜单空白。
 * 2) update-menu 不会给「新创建」的 items 补 __id；菜单项须全程复用首次对象。
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

/** 每次新建分隔线对象，禁止直接复用 SysTray.separator 单例 */
function menuSeparator() {
  return {
    title: SysTray.separator?.title ?? '<SEPARATOR>',
    tooltip: '',
    checked: false,
    enabled: true,
  }
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

  // 菜单项对象只建一次，全程复用（保留 systray2 分配的 __id）
  const menuItems = [
    menuItem('打开控制台', '在浏览器中打开 EasyAdapter', MENU.OPEN, () => openConsole(port)),
    menuSeparator(),
    menuItem('重启服务', '快速重启 BFF（不拉代码）', MENU.RESTART, () => {
      restartService()
      setTimeout(refreshTooltip, 1500)
    }),
    menuItem('更新并重启', '拉取代码、构建并重启（研发用）', MENU.FULL_RESTART, () => {
      setTooltipOnly('EasyAdapter updating...')
      spawnFullRestart()
      setTimeout(() => cleanupAndExit(systray), 500)
    }),
    menuItem('停止服务', '停止后台 BFF 服务', MENU.STOP, () => {
      stopService()
      setTimeout(refreshTooltip, 1000)
    }),
    menuSeparator(),
    menuItem('查看日志', '打开 server.log', MENU.LOG, () => { openLog() }),
    menuItem('关闭程序', '停止服务并退出托盘', MENU.QUIT, () => shutdownApplication(systray)),
  ]

  const setTooltipOnly = (nextTooltip) => {
    if (!systray) return
    if (nextTooltip === tooltip) return
    tooltip = nextTooltip
    // 必须传 menuItems 同一引用，禁止 buildItems() 新建对象
    systray.sendAction({
      type: 'update-menu',
      menu: {
        icon: iconPath,
        title: 'EasyAdapter',
        tooltip,
        items: menuItems,
      },
    })
  }

  const refreshTooltip = () => {
    status = queryServiceStatus()
    setTooltipOnly(buildTooltip(status, port))
  }

  systray = new SysTray({
    menu: {
      icon: iconPath,
      title: 'EasyAdapter',
      tooltip,
      items: menuItems,
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

  // 仅在 tooltip 文案变化时刷新；且复用同一批 menuItems
  setInterval(refreshTooltip, 30_000)
}

main().catch((err) => {
  removeTrayPid()
  console.error('[EasyAdapter] 托盘启动失败:', err)
  process.exit(1)
})
