export interface FlashProgressState {
  progress: number
  phase: string
  detail: string
  partitionDone: number
  inSuperFlash: boolean
  superIndex: number
  superTotal: number
  fastbootRound: number
  /** Fastboot 主流程已成功（出现 Fastboot刷机成功 / 跳过OOBE） */
  flashSucceeded: boolean
}

export function createFlashProgressState(): FlashProgressState {
  return {
    progress: 2,
    phase: '准备刷机',
    detail: '',
    partitionDone: 0,
    inSuperFlash: false,
    superIndex: 0,
    superTotal: 0,
    fastbootRound: 0,
    flashSucceeded: false,
  }
}

function bump(
  state: FlashProgressState,
  progress: number,
  phase?: string,
  detail?: string
): void {
  state.progress = Math.max(
    state.progress,
    Math.min(progress >= 100 ? 100 : 99, Math.round(progress))
  )
  if (phase) state.phase = phase
  if (detail !== undefined) state.detail = detail
}

/** 根据 device_update / TAHP 刷机日志行更新进度状态。 */
export function parseFlashLogLine(state: FlashProgressState, line: string): FlashProgressState {
  const normalized = line.trim()
  if (!normalized) return state

  if (normalized.includes('[刷机]')) {
    if (normalized.includes('已提交') || normalized.includes('开始准备')) {
      bump(state, 5, '准备刷机', '初始化刷机环境')
    } else if (/开始复制\s+(ZIP|Root 包)/.test(normalized)) {
      bump(state, 6, '缓存版本包', '从网络盘复制版本包')
    } else if (/复制\s+(ZIP|Root 包)\s+进度:/.test(normalized)) {
      const pctMatch = normalized.match(/进度:\s*(\d+)%/)
      const pct = pctMatch ? parseInt(pctMatch[1], 10) : 0
      const label = normalized.includes('Root 包') ? 'Root 包' : '版本包'
      bump(state, 6 + pct * 0.06, '缓存版本包', `复制${label} ${pct}%`)
    } else if (/复制\s+(ZIP|Root 包)\s+完成/.test(normalized)) {
      bump(state, 12, '缓存版本包', '版本包已缓存到本地')
    } else if (normalized.includes('解压')) {
      bump(state, 12, '准备刷机包', '解压或缓存版本包')
    } else if (normalized.includes('启动命令')) {
      bump(state, 14, '启动工具', '拉起 device_update')
    } else if (normalized.includes('正常结束')) {
      bump(state, 100, '刷机完成', '')
    } else if (normalized.includes('异常') || normalized.includes('失败')) {
      bump(state, state.progress, '刷机失败', normalized.replace(/^\[刷机\]\s*/, ''))
    }
    return state
  }

  if (normalized.includes('[T卡升级]')) {
    if (normalized.includes('已提交') || normalized.includes('开始推送') || normalized.includes('开始 T卡升级')) {
      bump(state, 8, '推送 ZIP', 'adb push 到 /sdcard')
    } else if (/推送进度:\s*(\d+)%/.test(normalized) || /\[T卡升级\] \[\s*(\d+)\s*%\]/.test(normalized)) {
      const pctMatch = normalized.match(/推送进度:\s*(\d+)%/) || normalized.match(/\[T卡升级\] \[\s*(\d+)\s*%\]/)
      const pct = pctMatch ? parseInt(pctMatch[1], 10) : 0
      bump(state, 8 + pct * 0.32, '推送 ZIP', `推送 ${pct}%`)
    } else if (normalized.includes('推送完成')) {
      bump(state, 42, '打开系统更新', 'SystemUpdateActivity')
    } else if (normalized.includes('点击本地升级')) {
      bump(state, 50, '本地升级', 'ota_local')
    } else if (normalized.includes('点击 file_name')) {
      bump(state, 54, '选择文件', 'file_name')
    } else if (normalized.includes('选择刷机包')) {
      bump(state, 58, '选择升级包', '点击 ZIP 文件名')
    } else if (normalized.includes('确认安装')) {
      bump(state, 68, '确认安装', 'btn_positive')
    } else if (normalized.includes('再次打开系统更新')) {
      bump(state, 75, '系统更新', '等待立即重启')
    } else if (normalized.includes('打开系统更新')) {
      bump(state, 45, '系统更新', 'SystemUpdateActivity')
    } else if (normalized.includes('等待立即重启')) {
      bump(state, 82, '等待重启按钮', 'reboot_now')
    } else if (normalized.includes('点击立即重启')) {
      bump(state, 90, '立即重启', '等待设备重启')
    } else if (normalized.includes('等待设备重启')) {
      bump(state, 94, '等待重连', '升级后设备回连')
    } else if (normalized === '[T卡升级] 完成') {
      bump(state, 100, 'T卡升级完成', '')
    } else if (normalized.includes('失败')) {
      bump(state, state.progress, 'T卡升级失败', normalized.replace(/^\[T卡升级\]\s*/, ''))
    }
    return state
  }

  if (
    /\[ERROR\]/.test(normalized) &&
    (/升级失败|fastboot升级失败|刷机失败/.test(normalized))
  ) {
    const detail = normalized.replace(/^.*---\s*/, '')
    bump(state, state.progress, '刷机失败', detail)
    return state
  }

  if (normalized.includes('DeviceUpdate 刷机工具开始运行')) {
    bump(state, 15, '启动刷机工具', 'device_update 已启动')
    return state
  }

  if (
    normalized.includes('开始第一次刷机测试') ||
    normalized.includes('开始第二次刷机测试')
  ) {
    bump(
      state,
      16,
      '刷机流程',
      normalized.includes('第二次') ? '第二阶段刷机' : '第一阶段刷机'
    )
    return state
  }

  if (/开始解压(版本|root)/.test(normalized)) {
    bump(state, 17, '准备刷机包', '解压版本包')
    return state
  }

  if (normalized.includes('开始解析scatter')) {
    bump(state, 18, '解析配置', '解析 scatter 分区表')
    return state
  }

  if (normalized.includes('开始获取刷入Image信息')) {
    bump(state, 19, '解析配置', '读取待刷入镜像列表')
    return state
  }

  if (normalized.includes('开始执行 fastboot 升级')) {
    state.fastbootRound += 1
    state.partitionDone = 0
    state.inSuperFlash = false
    state.superIndex = 0
    state.superTotal = 0
    state.flashSucceeded = false
    const roundLabel = state.fastbootRound > 1 ? `第 ${state.fastbootRound} 轮` : ''
    bump(state, 20, 'Fastboot 刷机', roundLabel ? `${roundLabel} fastboot 流程` : '进入 fastboot 流程')
    return state
  }

  // 刷机前等待设备重启 / 进入 fastboot（勿与刷机后开机混淆）
  if (/等待手机完全重启|等待手机:.*重启(?!进入fastboot)/.test(normalized)) {
    bump(state, 22, '设备准备', '等待设备重启')
    return state
  }

  if (/等待手机:.*重启进入fastboot|进入fastboot模式|reboot.*bootloader/i.test(normalized)) {
    bump(state, 24, '设备准备', '等待进入 fastboot')
    return state
  }

  if (/开机动画完成|bootani等待|init\.svc\.bootanim/.test(normalized) && !state.flashSucceeded) {
    bump(state, 23, '设备准备', '等待设备就绪')
    return state
  }

  if (/getprop sys\.boot_completed/.test(normalized) && !state.flashSucceeded) {
    bump(state, 24, '设备准备', '检查设备启动状态')
    return state
  }

  if (/Erasing|执行 erase/.test(normalized)) {
    bump(state, 26, '擦除分区', '擦除旧分区数据')
    return state
  }

  const partitionDone = normalized.match(/刷入分区:(\S+)\s+完成/)
  if (partitionDone) {
    const name = partitionDone[1]
    if (name === 'super') {
      state.inSuperFlash = false
      bump(state, 90, '刷写 super', 'super 分区刷写完成')
    } else {
      state.partitionDone += 1
      state.inSuperFlash = false
      const ratio = Math.min(state.partitionDone, 22) / 22
      bump(state, 28 + ratio * 17, '刷写分区', `${name}（已完成 ${state.partitionDone} 个）`)
    }
    return state
  }

  if (/开始 flash 分区:super/.test(normalized)) {
    state.inSuperFlash = true
    state.superIndex = 0
    bump(state, 45, '刷写 super', '开始刷写 super（通常最耗时）')
    return state
  }

  const partitionStart = normalized.match(/开始 flash 分区:(\S+)/)
  if (partitionStart && partitionStart[1] !== 'super') {
    bump(state, Math.max(state.progress, 28), '刷写分区', `正在刷写 ${partitionStart[1]}`)
    return state
  }

  const sparse = normalized.match(/Sending sparse 'super'\s+(\d+)\/(\d+)/)
  if (sparse) {
    state.inSuperFlash = true
    state.superIndex = parseInt(sparse[1], 10)
    state.superTotal = parseInt(sparse[2], 10)
    const ratio = state.superTotal > 0 ? state.superIndex / state.superTotal : 0
    bump(state, 45 + ratio * 45, '刷写 super', `super 分片 ${state.superIndex}/${state.superTotal}`)
    return state
  }

  if (normalized.includes('Fastboot刷机成功')) {
    state.flashSucceeded = true
    bump(state, 93, '收尾', 'Fastboot 刷机成功')
    return state
  }

  if (/跳过OOBE/.test(normalized)) {
    state.flashSucceeded = true
    bump(state, 95, '配置设备', '跳过 OOBE')
    return state
  }

  if (state.flashSucceeded && /开机动画完成|等待手机完全重启/.test(normalized)) {
    bump(state, 97, '等待开机', '等待系统启动完成')
    return state
  }

  return state
}

export function flashPhaseLabel(state: FlashProgressState): string {
  return state.detail ? `${state.phase} · ${state.detail}` : state.phase
}

const TCARD_PUSH_PROGRESS_RE = /\[T卡升级\] (?:推送进度:\s*\d+%|\[\s*\d+\s*%\])/

/** 推送百分比原地覆盖最后一行，避免日志刷屏。 */
export function mergeFlashLogLine(logs: string[], line: string): string[] {
  const trimmed = line.trim()
  if (!trimmed) return logs
  if (
    TCARD_PUSH_PROGRESS_RE.test(trimmed)
    && logs.length > 0
    && TCARD_PUSH_PROGRESS_RE.test(logs[logs.length - 1])
  ) {
    const next = logs.slice()
    next[next.length - 1] = trimmed
    return next
  }
  return [...logs, trimmed]
}
