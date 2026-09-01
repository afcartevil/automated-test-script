/**
 * 射频校准 MetaCLI：init 生成与探测
 */
import { describe, expect, it } from 'vitest'
import { buildMetaInitContent, modemActionSectionName, resolveBackupCalPath, validateItemsIniPath, normalizeMetaCliIniPath } from '../../packages/server/src/services/tahp/rf-calib-meta/init-builder'
import { stripImeiFromCalIniText } from '../../packages/server/src/services/tahp/rf-calib-meta/cal-imei-filter'
import { assessMetaCliActionFromLogs, annotateMetaCliLogLine } from '../../packages/server/src/services/tahp/rf-calib-meta/meta-result'
import { pickMetaUsbPort } from '../../packages/server/src/services/tahp/rf-calib-meta/meta-adb-boot'
import { isAdbRecoveryMode, prepareMetaConnection, type MtkComPortInfo } from '../../packages/server/src/services/tahp/rf-calib-meta/meta-connect-prep'
import { probeModemMetaCli, resolveModemMetaRoot } from '../../packages/server/src/services/tahp/rf-calib-meta/meta-cli'

describe('buildMetaInitContent', () => {
  it('builds DUT in META Mode init when meta port known', () => {
    const content = buildMetaInitContent({
      mode: 'backup',
      calFilePath: 'D:\\out\\cal.ini',
      itemsIniPath: 'D:\\cal\\items.ini',
      comPort: 'COM25',
      toolLogDir: 'D:\\logs\\run1\\',
      metaComConnected: true,
    })
    expect(content).toContain('PlatformType = DUT in META Mode')
    expect(content).toContain('ComPort = COM25')
    expect(content).toContain('EnableADBService = 0')
  })

  it('builds Smart Phone init aligned with Modem Meta GUI defaults', () => {
    const content = buildMetaInitContent({
      mode: 'backup',
      calFilePath: 'D:\\out\\cal.ini',
      itemsIniPath: 'D:\\cal\\items.ini',
      comPort: 'Auto Connection',
      toolLogDir: 'D:\\logs\\run1\\',
    })
    expect(content).toContain('PlatformType = Smart Phone')
    expect(content).toContain('ComPort = Auto Connection')
    expect(content).toContain('EnableSwitchModemMode = 1')
    expect(content).toContain('EnableADBService = 0')
    expect(content).toContain('[Modem1Action1]')
    expect(content.split(/\r?\n/).includes('[ModemAction]')).toBe(false)
    expect(content.split(/\r?\n/).includes('[Modem1Action]')).toBe(false)
    expect(content).toContain('DB = Load from target')
    expect(content).toContain('OutputCalibrationDataFilePath = D:/out/cal.ini')
    expect(content).not.toContain('IniFilePath =')
  })

  it('uses Modem1Action1 section (Modem%1Action%2)', () => {
    expect(modemActionSectionName(1)).toBe('Modem1Action1')
    expect(modemActionSectionName(1, 1)).toBe('Modem1Action1')
  })

  it('builds restore init with CalibrationFilePath', () => {
    const content = buildMetaInitContent({
      mode: 'restore',
      calFilePath: 'D:\\backup\\cal.ini',
      itemsIniPath: 'D:\\cal\\items.ini',
      toolLogDir: 'D:\\logs\\run1\\',
    })
    expect(content).toContain('CalibrationFilePath = D:/backup/cal.ini')
    expect(content).not.toContain('OutputCalibrationDataFilePath =')
  })
})

describe('resolveBackupCalPath', () => {
  it('uses default under project reports/rf-calib-meta when explicit empty', () => {
    const p = resolveBackupCalPath('C:\\proj', 'rf-cal-1')
    expect(p.replace(/\\/g, '/')).toBe('C:/proj/reports/rf-calib-meta/rf-cal-1/calibration_data.ini')
  })

  it('appends calibration_data.ini when explicit path is directory-like', () => {
    const p = resolveBackupCalPath('C:\\proj', 'rf-cal-1', 'D:\\out\\bakcup')
    expect(p).toBe('D:\\out\\bakcup\\calibration_data.ini')
  })
})

describe('validateItemsIniPath', () => {
  it('rejects empty path', () => {
    expect(validateItemsIniPath('')).toMatch(/IniFilePath/)
  })
})

describe('normalizeMetaCliIniPath', () => {
  it('uses forward slashes to avoid INI backslash escapes', () => {
    expect(normalizeMetaCliIniPath('D:\\tools\\rf-calib-meta\\new.ini')).toBe('D:/tools/rf-calib-meta/new.ini')
  })
})

describe('assessMetaCliActionFromLogs', () => {
  it('fails when only connect/disconnect without upload', () => {
    const r = assessMetaCliActionFromLogs([
      'Connect target success',
      'DisConnect target success',
    ], 'backup')
    expect(r.ok).toBe(false)
    expect(r.reason).toMatch(/Upload and Save/)
  })

  it('treats IMEI-only upload failure as success with warning when RF saved', () => {
    const r = assessMetaCliActionFromLogs([
      'Connect target success',
      'Upload and save calibration data start',
      'Read Category: General Item(20)- item: IMEI Failed',
      'Read Category: General Item(40)- item: Barcode Done',
      'Read Category: GSM Item(12)- item: RX Path Loss Done',
      'Read Category: LTE Item(100)- item: Self Cal Done',
      'Error: There are items reading from target failed',
      'Start writing the data to file...',
      'Write Category: GSM Item(12)- item: RX Path Loss Done',
      'Error: Backup flow failed in step1: upload from target failed.',
      'Error: Upload and save calibration data failed',
    ], 'backup')
    expect(r.ok).toBe(true)
    expect(r.allowNonZeroExit).toBe(true)
    expect(r.warning).toBeUndefined()
  })

  it('treats new MetaCLI category format GSM(n) IMEI-only failure as success', () => {
    const r = assessMetaCliActionFromLogs([
      'Connect target success',
      'Upload and save calibration data start',
      'Read Category: General(16)- item: IMEI Failed',
      'Read Category: General(32)- item: Barcode Done',
      'Read Category: GSM(14)- item: RX Path Loss Done',
      'Read Category: LTE(100)- item: TAS Rx Done',
      'Read Category: NR(100)- item: Max PA Input Done',
      'Error: There are items reading from target failed',
      'Start writing the data to file...',
      'Write Category: General(16)- item: IMEI Failed',
      'Write Category: GSM(14)- item: RX Path Loss Done',
      'Write Category: LTE(100)- item: TAS Rx Done',
      'Write Category: NR(100)- item: Max PA Input Done',
      'Error: Backup flow failed in step1: upload from target failed.',
      'Error: Backup flow failed in step2: save to file failed.',
      'Error: Upload and save calibration data failed',
      'DisConnect target success',
    ], 'backup')
    expect(r.ok).toBe(true)
    expect(r.allowNonZeroExit).toBe(true)
    expect(r.warning).toBeUndefined()
  })

  it('treats restore Write calibration file done as success', () => {
    const r = assessMetaCliActionFromLogs([
      'Connect target success',
      'Write calibration file start',
      'Write Category: GSM Item(22)- item: RX Path Loss Done',
      'Write Category: LTE Item(100)- item: Self Cal Done',
      'Write calibration file done',
      'DisConnect target success',
    ], 'restore')
    expect(r.ok).toBe(true)
  })
})

describe('annotateMetaCliLogLine', () => {
  it('annotates IMEI-related MetaCLI error lines as default skip', () => {
    expect(annotateMetaCliLogLine('Error: Backup flow failed in step1: upload from target failed.')).toMatch(/已默认跳过/)
    expect(annotateMetaCliLogLine('Error: Backup flow failed in step2: save to file failed.')).toMatch(/已默认跳过/)
    expect(annotateMetaCliLogLine('Error: Upload and save calibration data failed')).toMatch(/已默认跳过/)
    expect(annotateMetaCliLogLine('Connect target success')).toBe('Connect target success')
  })
})

describe('stripImeiFromCalIniText', () => {
  it('removes IMEI sections and keys', () => {
    const raw = [
      '[Barcode]',
      'Barcode = ABC',
      '',
      '[IMEI]',
      'IMEI = 123456789012345',
      '',
      '[GSM850 Sub band, RX loss]',
      'RX loss = 0',
      'IMEI2 = should-remove-key',
      'OK = keep',
    ].join('\n')
    const { text, removed } = stripImeiFromCalIniText(raw)
    expect(removed).toBeGreaterThan(0)
    expect(text).toContain('[Barcode]')
    expect(text).toContain('[GSM850 Sub band, RX loss]')
    expect(text).toContain('OK = keep')
    expect(text).not.toMatch(/\[IMEI\]/i)
    expect(text).not.toMatch(/IMEI\s*=/)
    expect(text).not.toMatch(/IMEI2\s*=/)
  })
})

describe('pickMetaUsbPort', () => {
  it('prefers MediaTek USB Port over PreLoader', () => {
    const ports: MtkComPortInfo[] = [
      { port: 'COM45', name: 'MediaTek PreLoader USB VCOM (Android) (COM45)' },
      { port: 'COM48', name: 'MediaTek USB Port (COM48)' },
    ]
    expect(pickMetaUsbPort(ports)).toBe('COM48')
  })

  it('matches lone MediaTek USB Port (meta-only scan)', () => {
    const ports: MtkComPortInfo[] = [
      { port: 'COM48', name: 'MediaTek USB Port (COM48)' },
    ]
    expect(pickMetaUsbPort(ports)).toBe('COM48')
  })
})

describe('isAdbRecoveryMode', () => {
  it('exports recovery probe helper', () => {
    expect(typeof isAdbRecoveryMode()).toBe('boolean')
  })
})

describe('prepareMetaConnection', () => {
  it('accepts manual COM without adb', () => {
    const r = prepareMetaConnection({ comPort: 'COM9', connectionStrategy: 'meta_port' })
    expect(r.ok).toBe(true)
    expect(r.suggested_com_port).toBe('COM9')
  }, 15000)
})

describe('probeModemMetaCli', () => {
  it('resolves meta root from explicit override path helper', () => {
    const root = resolveModemMetaRoot('C:\\ModemMeta')
    expect(root).toMatch(/ModemMeta/i)
  })

  it('normalizes MetaCLI.exe path to install root', () => {
    const root = resolveModemMetaRoot('C:\\ModemMeta\\bin\\MetaCLI.exe')
    expect(root.replace(/\\/g, '/')).toMatch(/ModemMeta$/i)
    expect(root.toLowerCase()).not.toContain('metacli.exe')
  })

  it('reports needs_config when unified config has no modem_meta_root', () => {
    if (process.platform !== 'win32') return
    const r = probeModemMetaCli()
    // 本机若已在一键配置保存过 modem_meta_root，则可能 available；否则应提示配置
    if (!r.available && r.needs_config) {
      expect(r.reason).toMatch(/一键配置/)
    }
  })

  it('reports unavailable on non-windows', () => {
    if (process.platform === 'win32') return
    const r = probeModemMetaCli()
    expect(r.available).toBe(false)
    expect(r.reason).toMatch(/Windows/)
  })
})
