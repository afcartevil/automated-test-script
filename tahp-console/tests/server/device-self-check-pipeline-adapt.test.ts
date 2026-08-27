import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check pipeline_adapt catalog', () => {
  it('loads pipeline_adapt TP, vibrator, audio, LCM, fingerprint and tdd catalog modules', () => {
    initDeviceSelfCheck()

    const group = getAllCaseCatalogs().find(g => g.testType === 'pipeline_adapt')
    expect(group?.label).toBe('流水线适配自动化测试')
    expect(group?.modules.map(m => m.module)).toEqual([
      'tp', 'vibrator', 'audio', 'lcm', 'fingerprint', 'tdd',
    ])
    expect(group?.modules[0]).toMatchObject({
      module: 'tp',
      moduleLabel: 'TP',
    })
    expect(group?.modules[0]?.cases).toHaveLength(1)
    expect(group?.modules[0]?.cases[0]?.caseName).toBe('TP适配检查')
    expect(group?.modules[1]).toMatchObject({
      module: 'vibrator',
      moduleLabel: '马达',
    })
    expect(group?.modules[1]?.cases).toHaveLength(1)
    expect(group?.modules[1]?.cases[0]?.caseName).toBe('马达适配检查')
    expect(group?.modules[2]).toMatchObject({
      module: 'audio',
      moduleLabel: '音频',
    })
    expect(group?.modules[2]?.cases).toHaveLength(1)
    expect(group?.modules[2]?.cases[0]?.caseName).toBe('音频适配检查')
    expect(group?.modules[3]).toMatchObject({
      module: 'lcm',
      moduleLabel: 'LCM',
    })
    expect(group?.modules[3]?.cases).toHaveLength(1)
    expect(group?.modules[3]?.cases[0]?.caseName).toBe('LCM适配检查')
    expect(group?.modules[4]).toMatchObject({
      module: 'fingerprint',
      moduleLabel: '指纹/人脸',
    })
    expect(group?.modules[4]?.cases).toHaveLength(1)
    expect(group?.modules[4]?.cases[0]?.caseName).toBe('指纹/人脸适配检查')
    expect(group?.modules[5]).toMatchObject({
      module: 'tdd',
      moduleLabel: '通信',
    })
    expect(group?.modules[5]?.cases).toHaveLength(5)
    expect(group?.modules[5]?.cases[0]?.caseName).toBe('基带版本号检查')
    expect(group?.modules[5]?.cases[1]?.caseName).toBe('IMEI号检查')
    expect(group?.modules[5]?.cases[2]?.caseName).toBe('拨打运营商服务号码')
    expect(group?.modules[5]?.cases[3]?.caseName).toBe('检查收发短信')
    expect(group?.modules[5]?.cases[4]?.caseName).toBe('检查上网')

    const detail = getCaseCatalogDetail('pipeline_adapt')
    expect(detail).toHaveLength(10)
    expect(detail[0]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'tp',
      moduleLabel: 'TP',
      caseName: 'TP适配检查',
      automationMode: 'full',
    })
    expect(detail[1]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'vibrator',
      moduleLabel: '马达',
      caseName: '马达适配检查',
      automationMode: 'full',
    })
    expect(detail[2]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'audio',
      moduleLabel: '音频',
      caseName: '音频适配检查',
      automationMode: 'full',
    })
    expect(detail[3]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'lcm',
      moduleLabel: 'LCM',
      caseName: 'LCM适配检查',
      automationMode: 'full',
    })
    expect(detail[4]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'fingerprint',
      moduleLabel: '指纹/人脸',
      caseName: '指纹/人脸适配检查',
      automationMode: 'full',
    })
    expect(detail[5]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'tdd',
      moduleLabel: '通信',
      caseName: '基带版本号检查',
      automationMode: 'full',
    })
    expect(typeof detail[0]?.preconditions).toBe('string')
    expect(typeof detail[0]?.manualSteps).toBe('string')
    expect(typeof detail[0]?.expectedResult).toBe('string')
    expect(typeof detail[1]?.preconditions).toBe('string')
    expect(typeof detail[1]?.manualSteps).toBe('string')
    expect(typeof detail[1]?.expectedResult).toBe('string')
    expect(typeof detail[2]?.preconditions).toBe('string')
    expect(typeof detail[2]?.manualSteps).toBe('string')
    expect(typeof detail[2]?.expectedResult).toBe('string')
    expect(typeof detail[3]?.preconditions).toBe('string')
    expect(typeof detail[3]?.manualSteps).toBe('string')
    expect(typeof detail[3]?.expectedResult).toBe('string')
    expect(detail[2]?.expectedResult).toContain('波形')
    expect(detail[2]?.expectedResult).toContain('PA')
    expect(detail[2]?.expectedResult).toContain('param_path="/odm/etc/vconfig/audio/audio_param"')
    expect(detail[2]?.expectedResult).toContain('tuningPath')
    expect(detail[2]?.expectedResult).toContain('onn-1')
    expect(detail[2]?.manualSteps).toContain('SOUND_SETTINGS')
    expect(detail[2]?.manualSteps).toContain('aurisys_config')
    expect(detail[2]?.manualSteps).toContain('adsp_top_dormant')
    expect(detail[3]?.manualSteps).toContain('/sys/kernel/tran_display')
    expect(detail[3]?.manualSteps).toContain('lcm_setbacklight_cmdq')
    expect(detail[3]?.manualSteps).toContain('lcd-backlight')
    expect(detail[3]?.manualSteps).toContain('connector_id')
    expect(detail[3]?.expectedResult).toContain('lcm_name')
    expect(detail[3]?.expectedResult).toContain('brightness=0')
    expect(detail[3]?.expectedResult).toContain('lcm_setbacklight_cmdq')
    expect(detail[3]?.expectedResult).toContain('sysfs_backlight_file')
    expect(detail[3]?.expectedResult).toContain('sysfs_leds')
    expect(typeof detail[4]?.preconditions).toBe('string')
    expect(typeof detail[4]?.manualSteps).toBe('string')
    expect(typeof detail[4]?.expectedResult).toBe('string')
    expect(detail[4]?.manualSteps).toContain('getevent -li')
    expect(detail[4]?.manualSteps).toContain('tran-keys')
    expect(detail[4]?.manualSteps).toContain('/sys/kernel/tran_fp/vendor_name')
    expect(detail[4]?.manualSteps).toContain('/sys/kernel/tran_fp/ic_name')
    expect(detail[4]?.manualSteps).toContain('android.hardware.biometrics.face')
    expect(detail[4]?.expectedResult).toContain('tran-keys')
    expect(detail[4]?.expectedResult).toContain('android.hardware.biometrics.fingerp')
    expect(detail[4]?.expectedResult).toContain('android.hardware.biometrics.face')
    expect(detail[5]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'tdd',
      moduleLabel: '通信',
      caseName: '基带版本号检查',
      caseIndex: 1,
      automationMode: 'full',
    })
    expect(detail[5]?.manualSteps).toContain('基带版本')
    expect(detail[5]?.expectedResult).toContain('基带版本')
    expect(detail[6]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'tdd',
      moduleLabel: '通信',
      caseName: 'IMEI号检查',
      caseIndex: 2,
      automationMode: 'full',
    })
    expect(detail[6]?.manualSteps).toContain('menu_drawer')
    expect(detail[6]?.manualSteps).toContain('软件信息')
    expect(detail[6]?.manualSteps).toContain('IMEI')
    expect(detail[6]?.expectedResult).toContain('IMEI')
    expect(detail[6]?.expectedResult).toContain('不为空')
    expect(detail[6]?.expectedResult).toContain('全是0')
    expect(detail[7]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'tdd',
      moduleLabel: '通信',
      caseName: '拨打运营商服务号码',
      caseIndex: 3,
      automationMode: 'full',
    })
    expect(detail[7]?.manualSteps).toContain('优先')
    expect(detail[7]?.manualSteps).toContain('10086')
    expect(detail[7]?.manualSteps).toContain('10010')
    expect(detail[7]?.manualSteps).toContain('10000')
    expect(detail[7]?.manualSteps).toContain('DIAL')
    expect(detail[7]?.expectedResult).toContain('服务号码')
    expect(detail[8]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'tdd',
      moduleLabel: '通信',
      caseName: '检查收发短信',
      caseIndex: 4,
      automationMode: 'full',
    })
    expect(detail[8]?.manualSteps).toContain('CXYE')
    expect(detail[8]?.manualSteps).toContain('10086')
    expect(detail[8]?.manualSteps).toContain('10010')
    expect(detail[8]?.manualSteps).toContain('10001')
    expect(detail[8]?.manualSteps).toContain('SENDTO')
    expect(detail[8]?.expectedResult).toContain('运营商回复')
    expect(detail[8]?.expectedResult).toContain('收发')
    expect(detail[9]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'tdd',
      moduleLabel: '通信',
      caseName: '检查上网',
      caseIndex: 5,
      automationMode: 'full',
    })
    expect(detail[9]?.manualSteps).toContain('wifi disable')
    expect(detail[9]?.manualSteps).toContain('data enable')
    expect(detail[9]?.manualSteps).toContain('www.baidu.com')
    expect(detail[9]?.manualSteps).toContain('www.qq.com')
    expect(detail[9]?.expectedResult).toContain('ping')
  })
})
