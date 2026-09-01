export type RfCalibMetaMode = 'backup' | 'restore'

/** preloader_boot：与 Modem Meta GUI 相同（Smart Phone + Auto Connection，先启动再等插 USB）；meta_port：已在 META；adb_reboot_meta：仅部分工程版 */
export type RfCalibMetaConnectionStrategy =
  | 'preloader_boot'
  | 'meta_port'
  | 'adb_reboot_meta'

export type RfCalibMetaRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface RfCalibMetaRunSummary {
  run_id: string
  label: string
  mode: RfCalibMetaMode
  status: RfCalibMetaRunStatus
  phase?: string
  progress?: number
  message?: string
  cal_file_path?: string
  items_ini_path?: string
  output_cal_path?: string
  created_at: string
  updated_at: string
  completed_at?: string
}

export interface RfCalibMetaRunRecord extends RfCalibMetaRunSummary {
  error?: string
  meta_root?: string
  init_file_path?: string
  com_port?: string
  adb_device_id?: string
  meta_com_connected?: boolean
  connection_strategy?: RfCalibMetaConnectionStrategy
  log_tail: string[]
  duration_ms?: number
  exit_code?: number | null
}

export interface RfCalibMetaProbeResult {
  available: boolean
  reason?: string
  /** 未在一键配置表单配置 Modem Meta 时为 true */
  needs_config?: boolean
  meta_root?: string
  meta_cli?: string
  platform?: string
  adb_devices?: string[]
  mtk_com_ports?: Array<{ port: string; name: string }>
  suggested_com_port?: string
  suggested_items_ini?: string
  connection_hint?: string
}

export interface RfCalibMetaStartInput {
  mode: RfCalibMetaMode
  calFilePath: string
  itemsIniPath: string
  comPort?: string
  /** @deprecated 已废弃：改由一键配置表单 modem_meta_root 提供，启动时忽略 */
  metaRoot?: string
  outputCalPath?: string
  label?: string
  connectionStrategy?: RfCalibMetaConnectionStrategy
}
