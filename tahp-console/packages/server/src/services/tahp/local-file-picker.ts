/**
 * 本机系统文件选择框（Windows PowerShell / macOS osascript / Linux zenity|kdialog）。
 * 供 Console 需要绝对路径的场景使用（浏览器 <input type=file> 拿不到本机路径）。
 */
import { spawnSync } from 'child_process'

export interface PickLocalFileResult {
  canceled: boolean
  path?: string
  error?: string
}

export interface PickLocalFileOptions {
  title: string
  /** Windows OpenFileDialog.Filter，如 `INI (*.ini)|*.ini|所有文件 (*.*)|*.*` */
  winFilter: string
  macPrompt?: string
  zenityFilters: string[]
  kdialogFilter: string
}

function commandAvailable(cmd: string): boolean {
  const probe = spawnSync(process.platform === 'win32' ? 'where' : 'which', [cmd], {
    encoding: 'utf8',
    windowsHide: true,
  })
  return probe.status === 0
}

function pathPickerError(): string | null {
  if (process.platform === 'linux') {
    if (!process.env.DISPLAY && !process.env.WAYLAND_DISPLAY) {
      return '无图形界面，请手动输入路径'
    }
    if (!commandAvailable('zenity') && !commandAvailable('kdialog')) {
      return '请安装 zenity 或 kdialog，或手动输入路径'
    }
  }
  if (process.platform === 'win32' && !commandAvailable('powershell.exe')) {
    return '未找到 PowerShell，请手动输入路径'
  }
  return null
}

function escapePsSingleQuoted(s: string): string {
  return s.replace(/'/g, "''")
}

function pickPathWindows(title: string, filter: string): PickLocalFileResult {
  const script = `
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class TahpFg {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
  public static void ForceForeground(IntPtr hWnd) {
    keybd_event(0x12, 0, 0, UIntPtr.Zero);
    keybd_event(0x12, 0, 0x0002, UIntPtr.Zero);
    ShowWindow(hWnd, 5);
    BringWindowToTop(hWnd);
    SetForegroundWindow(hWnd);
  }
}
"@
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = 'None'
$owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.StartPosition = 'Manual'
$owner.Location = New-Object System.Drawing.Point(-2000, -2000)
$owner.Add_Shown({ [TahpFg]::ForceForeground($owner.Handle) })
$owner.Show()
$owner.Activate()
[TahpFg]::ForceForeground($owner.Handle)
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.Title = '${escapePsSingleQuoted(title)}'
$dlg.Filter = '${escapePsSingleQuoted(filter)}'
$dlg.FilterIndex = 1
$result = $dlg.ShowDialog($owner)
if ($result -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $dlg.FileName }
$owner.Dispose()
`
  const encoded = Buffer.from(script, 'utf16le').toString('base64')
  const proc = spawnSync(
    'powershell.exe',
    ['-NoProfile', '-STA', '-EncodedCommand', encoded],
    { encoding: 'utf8', windowsHide: false },
  )
  const path = (proc.stdout || '').trim()
  if (path) return { canceled: false, path }
  return { canceled: true }
}

function pickPathDarwin(prompt: string): PickLocalFileResult {
  const proc = spawnSync(
    'osascript',
    [
      '-e',
      'tell application "System Events" to activate',
      '-e',
      `POSIX path of (choose file with prompt "${prompt.replace(/"/g, '\\"')}")`,
    ],
    { encoding: 'utf8', windowsHide: false },
  )
  const path = (proc.stdout || '').trim()
  if (proc.status === 0 && path) return { canceled: false, path }
  return { canceled: true }
}

function pickPathLinux(options: PickLocalFileOptions): PickLocalFileResult {
  if (commandAvailable('zenity')) {
    const proc = spawnSync(
      'zenity',
      ['--file-selection', '--modal', `--title=${options.title}`, ...options.zenityFilters],
      { encoding: 'utf8', windowsHide: false },
    )
    const path = (proc.stdout || '').trim()
    if (proc.status === 0 && path) return { canceled: false, path }
    return { canceled: true }
  }
  const proc = spawnSync(
    'kdialog',
    ['--getopenfilename', '', options.kdialogFilter, options.title],
    { encoding: 'utf8', windowsHide: false },
  )
  const path = (proc.stdout || '').trim()
  if (proc.status === 0 && path) return { canceled: false, path }
  return { canceled: true }
}

export async function pickLocalFilePath(options: PickLocalFileOptions): Promise<PickLocalFileResult> {
  const unavailable = pathPickerError()
  if (unavailable) return { canceled: true, error: unavailable }

  try {
    if (process.platform === 'win32') return pickPathWindows(options.title, options.winFilter)
    if (process.platform === 'darwin') return pickPathDarwin(options.macPrompt || options.title)
    if (process.platform === 'linux') return pickPathLinux(options)
    return { canceled: true, error: '当前平台不支持文件选择，请手动输入路径' }
  } catch (err: any) {
    return { canceled: true, error: err?.message || '路径选择失败' }
  }
}

/** 校准数据恢复：选择本机 .ini 校准文件 */
export async function pickCalibrationIniPath(): Promise<PickLocalFileResult> {
  return pickLocalFilePath({
    title: '选择校准数据文件（.ini）',
    winFilter: '校准数据 (*.ini)|*.ini|所有文件 (*.*)|*.*',
    macPrompt: '选择校准数据文件（.ini）',
    zenityFilters: [
      '--file-filter=校准数据 | *.ini',
      '--file-filter=所有文件 | *',
    ],
    kdialogFilter: '校准数据 (*.ini)|*.ini',
  })
}
