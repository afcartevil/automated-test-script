#!/usr/bin/env python3
"""
批量为已导入的 SKILL.md 回填 funcType / category 字段。

策略（优先级从高到低）：
  1. 精准映射表（SOURCE_MAP）：从 E:\\底软集成skills\\skills 目录直接扫描得到
  2. 前缀/关键词兜底规则（PREFIX_RULES）：处理名称略有变化的 skill
  3. 未命中 → 保持不变，打印到 unknown 列表供手动补录
"""

import os
import re
import sys

# ── 路径配置 ──────────────────────────────────────────────────────────────────
SKILLS_DIR = os.path.join(os.path.dirname(__file__), '..', 'skills', '.claude', 'skills')

# ── 1. 精准映射表（key = skill目录名，value = (funcType, category)）──────────
#    完全基于 E:\底软集成skills\skills 的三级目录结构生成
SOURCE_MAP: dict = {

    # ── AI 故障分析 / 内核 ───────────────────────────────────────────────────
    'android-bootup-issue-log-analysis':         ('AI故障分析', '内核'),
    'android-hang-log-analysis':                 ('AI故障分析', '内核'),
    'android-hwr-hwt-log-analysis':              ('AI故障分析', '内核'),
    'android-ke-log-analysis':                   ('AI故障分析', '内核'),
    'android-kernel-api-dump-log-analysis':      ('AI故障分析', '内核'),
    'android-kerneldb-extract':                  ('AI故障分析', '内核'),
    'android-kerneltne-extract':                 ('AI故障分析', '内核'),
    'android-unisoc-kernel-crash-log-analysis':  ('AI故障分析', '内核'),

    # ── AI 故障分析 / 驱动 ───────────────────────────────────────────────────
    'DRV_TP_LargeArea':                          ('AI故障分析', '驱动'),
    'DRV_Vibrator_VibrationFault':               ('AI故障分析', '驱动'),
    'BSP_sensor_ps_anti_touch':                  ('AI故障分析', '驱动'),
    'android-fingerprint-log-analysis':          ('AI故障分析', '驱动'),
    'android-sys-usb-config-gadget':             ('AI故障分析', '驱动'),
    'audio-bug-solver':                          ('AI故障分析', '驱动'),
    'mediatek-mtu3-xhci-host':                   ('AI故障分析', '驱动'),
    'mediatek-pd-typec-analysis':                ('AI故障分析', '驱动'),
    'mediatek-pd-typec-protocol-6-1':            ('AI故障分析', '驱动'),
    'mediatek-pd-typec-protocol-6-12':           ('AI故障分析', '驱动'),
    'mtk-backlight-abnormal-log-analysis':       ('AI故障分析', '驱动'),
    'mtk-battery-gauge-stack':                   ('AI故障分析', '驱动'),
    'mtk-panel-load-abnormal-log-analysis':      ('AI故障分析', '驱动'),
    'mtk-screen-tearing-abnormal-log-analysis':  ('AI故障分析', '驱动'),
    'mtk-suspend-resume-abnormal-log-analysis':  ('AI故障分析', '驱动'),
    'mtk-tp-fod-log-analysis':                   ('AI故障分析', '驱动'),
    'mtk-tp-gesture-log-analysis':               ('AI故障分析', '驱动'),
    'mtk-tp-touch-log-analysis':                 ('AI故障分析', '驱动'),
    'mtk-usb20-musb-otg-core':                   ('AI故障分析', '驱动'),
    'mtu3-usb-device-core':                      ('AI故障分析', '驱动'),
    'power-usb-cross-stack-triage':              ('AI故障分析', '驱动'),
    'qualcomm-adsp-charging-analysis':           ('AI故障分析', '驱动'),
    'qualcomm-adsp-power-usb-triage':            ('AI故障分析', '驱动'),
    'qualcomm-adsp-usb-pd-analysis':             ('AI故障分析', '驱动'),
    'qualcomm-kernel-adsp-bridge':               ('AI故障分析', '驱动'),
    'qualcomm-msm-kernel-charging-supply-analysis':    ('AI故障分析', '驱动'),
    'qualcomm-msm-kernel-dwc3-role-gadget-analysis':   ('AI故障分析', '驱动'),
    'qualcomm-msm-kernel-usb-ucsi-analysis':     ('AI故障分析', '驱动'),
    'sensor-als-autobrightness':                 ('AI故障分析', '驱动'),
    'sensor-als-first-report':                   ('AI故障分析', '驱动'),
    'transsion-batt-high-temp-low-cv-eoc':       ('AI故障分析', '驱动'),
    'transsion-bc12-type-detect':                ('AI故障分析', '驱动'),
    'transsion-charger-orchestrator':            ('AI故障分析', '驱动'),
    'transsion-dcp-fastcharge-probe':            ('AI故障分析', '驱动'),
    'transsion-extcon-usb-role-bridge':          ('AI故障分析', '驱动'),
    'transsion-pe5-vi-tuning':                   ('AI故障分析', '驱动'),
    'transsion-tcpc-adapter':                    ('AI故障分析', '驱动'),
    'transsion-wireless-bypass-fan':             ('AI故障分析', '驱动'),
    'usb-pd-platform-router':                    ('AI故障分析', '驱动'),
    'video-playback-log-analysis':               ('AI故障分析', '驱动'),

    # ── AI 故障分析 / 功耗 ───────────────────────────────────────────────────
    'bug-scenario-power-standby':                ('AI故障分析', '功耗'),
    'power-leak-detector':                       ('AI故障分析', '功耗'),
    'power-backlight-app-optimization':          ('AI故障分析', '功耗'),
    'power-backlight-auto-anomaly':              ('AI故障分析', '功耗'),
    'power-backlight-camera-video':              ('AI故障分析', '功耗'),
    'power-backlight-hbm-enter':                 ('AI故障分析', '功耗'),
    'power-backlight-manual-adjust':             ('AI故障分析', '功耗'),
    'power-backlight-policy-factors':            ('AI故障分析', '功耗'),
    'power-display-double-tap-wake':             ('AI故障分析', '功耗'),
    'power-display-notification-wake':           ('AI故障分析', '功耗'),
    'power-display-power-key-screen':            ('AI故障分析', '功耗'),
    'power-display-timeout-screen-off':          ('AI故障分析', '功耗'),
    'power-sensor-proximity-brightness':         ('AI故障分析', '功耗'),

    # ── AI 故障分析 / 通信 ───────────────────────────────────────────────────
    'com-comm-analysis-foundation':              ('AI故障分析', '通信'),
    'com-comm-sop-source-archive':               ('AI故障分析', '通信'),
    'com-data-datasetupfail':                    ('AI故障分析', '通信'),
    'com-data-dataunstable':                     ('AI故障分析', '通信'),
    'com-data-ddsswitchfail':                    ('AI故障分析', '通信'),
    'com-data-sim-contact-add':                  ('AI故障分析', '通信'),
    'com-data-sim-recognition':                  ('AI故障分析', '通信'),
    'com-dstall-datastall':                      ('AI故障分析', '通信'),
    'com-network-roamingstate':                  ('AI故障分析', '通信'),
    'com-network-signalabnormal':                ('AI故障分析', '通信'),
    'com-network-timezonewrong':                 ('AI故障分析', '通信'),
    'com-sim-apnchange':                         ('AI故障分析', '通信'),
    'com-sim-ussdflow':                          ('AI故障分析', '通信'),
    'com-sim-ussdwrongtext':                     ('AI故障分析', '通信'),
    'com-sms-smsappui':                          ('AI故障分析', '通信'),
    'com-voice-call-dialing':                    ('AI故障分析', '通信'),
    'com-voice-ecc-emergency':                   ('AI故障分析', '通信'),
    'mtk-call-dialfail':                         ('AI故障分析', '通信'),
    'mtk-call-emergencynumber':                  ('AI故障分析', '通信'),
    'mtk-call-incominganswerfail':               ('AI故障分析', '通信'),
    'mtk-fl16-flashcall16':                      ('AI故障分析', '通信'),
    'mtk-modem-ee-modemee':                      ('AI故障分析', '通信'),
    'mtk-network-dataslow':                      ('AI故障分析', '通信'),
    'mtk-sim-operatorname':                      ('AI故障分析', '通信'),
    'mtk-sim-simdetect':                         ('AI故障分析', '通信'),
    'mtk-sim-statusbaricon':                     ('AI故障分析', '通信'),
    'mtk-sms-mmsrecvfail':                       ('AI故障分析', '通信'),
    'mtk-sms-mmssendfail':                       ('AI故障分析', '通信'),
    'mtk-sms-smsrecvfail':                       ('AI故障分析', '通信'),
    'mtk-sms-smssendfail':                       ('AI故障分析', '通信'),
    'near-bt-device-connect':                    ('AI故障分析', '通信'),
    'near-bt-opp-transfer':                      ('AI故障分析', '通信'),
    'near-bt-switch':                            ('AI故障分析', '通信'),
    'uns-call-dialfail':                         ('AI故障分析', '通信'),
    'uns-call-flashcall15':                      ('AI故障分析', '通信'),
    'uns-call-incominganswerfail':               ('AI故障分析', '通信'),
    'uns-sim-operatorname':                      ('AI故障分析', '通信'),
    'uns-sim-simdetect':                         ('AI故障分析', '通信'),
    'uns-sim-statusbaricon':                     ('AI故障分析', '通信'),
    'uns-sms-mmsrecvfail':                       ('AI故障分析', '通信'),
    'uns-sms-mmssendfail':                       ('AI故障分析', '通信'),
    'uns-sms-smsrecvfail':                       ('AI故障分析', '通信'),
    'uns-sms-smssendfail':                       ('AI故障分析', '通信'),
    'telephony-bug-analyzer':                    ('AI故障分析', '通信'),

    # ── AI 自动化适配 / 通信 ─────────────────────────────────────────────────
    'MODEM_P1_Adapt':                            ('AI自动化适配', '通信'),
    'telephony-version-adapter':                 ('AI自动化适配', '通信'),
    'carrier-porting-assistant':                 ('AI自动化适配', '通信'),

    # ── AI 自动化适配 / 内核 ─────────────────────────────────────────────────
    'KRN_LK_CPU_Ddapt':                          ('AI自动化适配', '内核'),
    'KRN_LK_CPU_Adapt':                          ('AI自动化适配', '内核'),

    # ── AI 自动化适配 / 驱动 ─────────────────────────────────────────────────
    'android-platform-security-upgrade-ai-debug': ('AI自动化适配', '驱动'),
    'DRV_Audio_Adapt':                           ('AI自动化适配', '驱动'),
    'audio-self-check':                          ('AI自动化适配', '驱动'),
    'drv-fp-adapt':                              ('AI自动化适配', '驱动'),
    'drv-fp-check':                              ('AI自动化适配', '驱动'),
    'lid-check':                                 ('AI自动化适配', '驱动'),
    'scp-sensor-check':                          ('AI自动化适配', '驱动'),
    'mtk-sensor-dts-config':                     ('AI自动化适配', '驱动'),
    'scp_upgrade':                               ('AI自动化适配', '驱动'),
    'tranprojects-upgrade':                      ('AI自动化适配', '驱动'),
    'aikey-adapt-dts':                           ('AI自动化适配', '驱动'),
    'bsp-adapt-holster-hall':                    ('AI自动化适配', '驱动'),
    'bsp-adapt-lk-key':                          ('AI自动化适配', '驱动'),
    'tp-adapt-dws-pin':                          ('AI自动化适配', '驱动'),
    'tp-adapt-engineering-sysfs':                ('AI自动化适配', '驱动'),
    'tp-adapt-factory-capacitance':              ('AI自动化适配', '驱动'),
    'tp-adapt-factory-sysfs':                    ('AI自动化适配', '驱动'),
    'tp-adapt-gesture-driver':                   ('AI自动化适配', '驱动'),
    'tp-adapt-ko-order':                         ('AI自动化适配', '驱动'),
    'tp-adapt-power-sequence':                   ('AI自动化适配', '驱动'),
    'tp-adapt-selinux':                          ('AI自动化适配', '驱动'),
    'vib-adapt-dts-regulator':                   ('AI自动化适配', '驱动'),
    'vib-adapt-factory-cali':                    ('AI自动化适配', '驱动'),
    'vib-adapt-haptic-rc':                       ('AI自动化适配', '驱动'),
    'vib-adapt-lra-driver':                      ('AI自动化适配', '驱动'),
    'vib-adapt-projectconfig':                   ('AI自动化适配', '驱动'),
    'vib-adapt-rotor-driver':                    ('AI自动化适配', '驱动'),
    'fc-aikey-dts':                              ('AI自动化适配', '驱动'),
    'fc-aikey-event':                            ('AI自动化适配', '驱动'),
    'fc-template':                               ('AI自动化适配', '驱动'),
    'fc-tp-driver':                              ('AI自动化适配', '驱动'),
    'fc-tp-factory-info':                        ('AI自动化适配', '驱动'),
    'fc-tp-factory':                             ('AI自动化适配', '驱动'),
    'fc-tp-gesture':                             ('AI自动化适配', '驱动'),
    'fc-tp-selinux':                             ('AI自动化适配', '驱动'),
    'fc-tp-sysfs':                               ('AI自动化适配', '驱动'),
    'fc-tp-touch':                               ('AI自动化适配', '驱动'),
    'fc-vib-cali':                               ('AI自动化适配', '驱动'),
    'fc-vib-driver':                             ('AI自动化适配', '驱动'),
    'fc-vib-effect':                             ('AI自动化适配', '驱动'),
    'fc-vib-hal':                                ('AI自动化适配', '驱动'),
    'fc-vib-he':                                 ('AI自动化适配', '驱动'),
    'fc-vib-rootperm':                           ('AI自动化适配', '驱动'),
    'fc-vib-rotor':                              ('AI自动化适配', '驱动'),
    'fc-vib-selinux':                            ('AI自动化适配', '驱动'),
    'mtk-adapt-template-basic-charging-capability': ('AI自动化适配', '驱动'),
    'mtk-adapt-template-device-charge-pump':     ('AI自动化适配', '驱动'),
    'mtk-adapt-template-device-charger-ic':      ('AI自动化适配', '驱动'),
    'mtk-adapt-template-device-gauge':           ('AI自动化适配', '驱动'),
    'mtk-adapt-template-device-pd-ic':           ('AI自动化适配', '驱动'),
    'mtk-adapt-template-feature-factory-mode':   ('AI自动化适配', '驱动'),
    'mtk-adapt-template-feature-kpoc-charging':  ('AI自动化适配', '驱动'),
    'mtk-adapt-template-feature-placeholder':    ('AI自动化适配', '驱动'),
    'mtk-adapt-template-router':                 ('AI自动化适配', '驱动'),
    'mtk-adapt-upgrade-branch-orchestrator':     ('AI自动化适配', '驱动'),
    'mtk-adapt-upgrade-inventory-checklist':     ('AI自动化适配', '驱动'),
    'mtk-adapt-upgrade-platform-delta-table':    ('AI自动化适配', '驱动'),
    'transsion-charger-dtsi-driver-bridge':      ('AI自动化适配', '驱动'),
    'transsion-pe5-migrate-dual-cp-k612':        ('AI自动化适配', '驱动'),
    'transsion-sunmao40-customization-features-adapt': ('AI自动化适配', '驱动'),
    'transsion-tran-battery-to-tc-charger-dtsi': ('AI自动化适配', '驱动'),
    'tran-projects-config-migrate-dtsi-dws':     ('AI自动化适配', '驱动'),

    # ── AI 自检工具 ──────────────────────────────────────────────────────────
    'spd-cpu-feature-check':                     ('AI自检工具', '通用'),
    'kernel-panic-tracer':                       ('AI自检工具', '内核'),
}

# ── 2. 前缀兜底规则（处理名称略有变化的 skill） ─────────────────────────────
PREFIX_RULES = [
    # AI 自动化适配
    ('MODEM_P1_',           'AI自动化适配', '通信'),
    ('KRN_LK_',             'AI自动化适配', '内核'),
    ('carrier-porting',     'AI自动化适配', '通信'),
    ('telephony-version',   'AI自动化适配', '通信'),
    ('tp-adapt-',           'AI自动化适配', '驱动'),
    ('vib-adapt-',          'AI自动化适配', '驱动'),
    ('fc-tp-',              'AI自动化适配', '驱动'),
    ('fc-vib-',             'AI自动化适配', '驱动'),
    ('fc-aikey-',           'AI自动化适配', '驱动'),
    ('mtk-adapt-',          'AI自动化适配', '驱动'),
    ('drv-fp-',             'AI自动化适配', '驱动'),
    ('tranprojects-',       'AI自动化适配', '驱动'),
    ('aikey-adapt',         'AI自动化适配', '驱动'),
    ('bsp-adapt-',          'AI自动化适配', '驱动'),
    ('tran-projects-',      'AI自动化适配', '驱动'),
    ('DRV_Audio_',          'AI自动化适配', '驱动'),
    ('audio-self-check',    'AI自动化适配', '驱动'),
    # AI 自检工具
    ('spd-cpu-',            'AI自检工具', '通用'),
    # AI 故障分析 / 内核
    ('android-bootup',      'AI故障分析', '内核'),
    ('android-hang',        'AI故障分析', '内核'),
    ('android-hwr',         'AI故障分析', '内核'),
    ('android-ke-',         'AI故障分析', '内核'),
    ('android-kernel',      'AI故障分析', '内核'),
    ('android-kerneldb',    'AI故障分析', '内核'),
    ('android-kerneltne',   'AI故障分析', '内核'),
    ('android-unisoc',      'AI故障分析', '内核'),
    ('kernel-panic',        'AI故障分析', '内核'),
    # AI 故障分析 / 驱动
    ('BSP_sensor',          'AI故障分析', '驱动'),
    ('DRV_',                'AI故障分析', '驱动'),
    ('android-fingerprint', 'AI故障分析', '驱动'),
    ('android-sys-usb',     'AI故障分析', '驱动'),
    ('audio-bug',           'AI故障分析', '驱动'),
    ('mediatek-mtu3',       'AI故障分析', '驱动'),
    ('mediatek-pd',         'AI故障分析', '驱动'),
    ('mtk-backlight',       'AI故障分析', '驱动'),
    ('mtk-battery',         'AI故障分析', '驱动'),
    ('mtk-panel',           'AI故障分析', '驱动'),
    ('mtk-screen',          'AI故障分析', '驱动'),
    ('mtk-suspend',         'AI故障分析', '驱动'),
    ('mtk-tp-',             'AI故障分析', '驱动'),
    ('mtk-usb',             'AI故障分析', '驱动'),
    ('mtu3-usb',            'AI故障分析', '驱动'),
    ('qualcomm-',           'AI故障分析', '驱动'),
    ('sensor-als',          'AI故障分析', '驱动'),
    ('transsion-',          'AI故障分析', '驱动'),
    ('usb-pd-',             'AI故障分析', '驱动'),
    ('video-playback',      'AI故障分析', '驱动'),
    ('power-usb-',          'AI故障分析', '驱动'),
    # AI 故障分析 / 功耗
    ('bug-scenario-power',  'AI故障分析', '功耗'),
    ('power-backlight',     'AI故障分析', '功耗'),
    ('power-display',       'AI故障分析', '功耗'),
    ('power-sensor',        'AI故障分析', '功耗'),
    ('power-leak',          'AI故障分析', '功耗'),
    # AI 故障分析 / 通信
    ('com-',                'AI故障分析', '通信'),
    ('mtk-call-',           'AI故障分析', '通信'),
    ('mtk-fl',              'AI故障分析', '通信'),
    ('mtk-modem',           'AI故障分析', '通信'),
    ('mtk-network',         'AI故障分析', '通信'),
    ('mtk-sim',             'AI故障分析', '通信'),
    ('mtk-sms',             'AI故障分析', '通信'),
    ('near-bt',             'AI故障分析', '通信'),
    ('uns-',                'AI故障分析', '通信'),
    ('telephony-bug',       'AI故障分析', '通信'),
]


def classify(name):
    if name in SOURCE_MAP:
        return SOURCE_MAP[name]
    for prefix, ft, cat in PREFIX_RULES:
        if name.startswith(prefix):
            return ft, cat
    return None, None


def inject_frontmatter(path, fields):
    """把 fields 写入 SKILL.md 的 YAML frontmatter，返回是否有修改。"""
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    fm_match = re.match(r'^---\r?\n([\s\S]*?)\r?\n---(\r?\n|$)', content)
    if fm_match:
        fm_lines = fm_match.group(1).split('\n')
        rest = content[len(fm_match.group(0)):]
    else:
        fm_lines = []
        rest = content

    changed = False
    for key, value in fields.items():
        escaped = value.replace('"', '\\"')
        line = f'{key}: "{escaped}"'
        idx = next((i for i, l in enumerate(fm_lines) if l.startswith(f'{key}:')), -1)
        if idx >= 0:
            if fm_lines[idx] == line:
                continue
            fm_lines[idx] = line
        else:
            fm_lines.append(line)
        changed = True

    if not changed:
        return False

    new_content = '---\n' + '\n'.join(fm_lines) + '\n---\n' + rest
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return True


def main():
    skills_dir = os.path.abspath(SKILLS_DIR)
    if not os.path.isdir(skills_dir):
        print(f'[ERROR] skills dir not found: {skills_dir}')
        sys.exit(1)

    updated = skipped = already_ok = 0
    unknown = []

    for skill_name in sorted(os.listdir(skills_dir)):
        skill_dir = os.path.join(skills_dir, skill_name)
        skill_md = os.path.join(skill_dir, 'SKILL.md')
        if not os.path.isfile(skill_md):
            continue

        ft, cat = classify(skill_name)
        if not ft:
            unknown.append(skill_name)
            skipped += 1
            continue

        modified = inject_frontmatter(skill_md, {'funcType': ft, 'category': cat})
        if modified:
            print(f'  [更新] {skill_name:<60} -> {ft} / {cat}')
            updated += 1
        else:
            already_ok += 1

    print(f'\n完成：更新 {updated} 个，已是正确值 {already_ok} 个，跳过 {skipped} 个')

    if unknown:
        print(f'\n未命中（需手动补充分类或添加到 SOURCE_MAP）:')
        for n in unknown:
            print(f'  - {n}')


if __name__ == '__main__':
    main()
