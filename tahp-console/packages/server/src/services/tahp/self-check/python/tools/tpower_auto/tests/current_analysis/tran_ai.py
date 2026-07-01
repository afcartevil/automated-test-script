import os
import re
from openai import OpenAI

SYSTEM_CONTENT = """
你是一名 Android 手机功耗优化工程师
请基于用户提供的系统日志，分析是否存在功耗异常，并判断导致功耗超标的潜在根因
1.分析要求
结合日志内容，推断可能导致功耗偏高的模块、功能或系统行为。明确指出可疑的应用、硬件模块或系统场景
2.输出要求
先给分级判断（功耗正常、轻微异常、中度异常、严重异常），若有异常就再给问题分类（如屏幕、CPU、网络、后台应用等），最后给出详细分析说明
不引入无关背景、不做泛泛而谈，简明扼要,输出纯文本，不能含有加粗等标记符号
"""
class TranAi:
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance'):
            cls.instance = super(TranAi, cls).__new__(cls)
        return cls.instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            openai_api_key = os.getenv("OPENAI_API_KEY")
            self.client = None
            if openai_api_key:
                self.client = OpenAI(
                    api_key=openai_api_key,
                    base_url="https://hk-intra-paas.transsion.com/tranai-proxy/v1"
                )

    def analyze(self, scene:str,ref_data:dict, data:dict, logs:str) -> str:
        if not self.client:
            return ""
        try:
            #print(f"正在使用 TranAi 分析场景:{scene}，参考数据:{ref_data}，测试数据:{data}，日志长度:{len(logs)}")
            response = self.client.chat.completions.create(
                model="gemini-3-pro-thinking-medium",
                messages=[
                    {"role": "system", "content": SYSTEM_CONTENT},
                    {"role": "user", "content": f"测试场景:{scene}，标准功耗:{ref_data}，测试数据:{data}，测试日志:{logs}"}
                ]
            )
            content = response.choices[0].message.content
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).lstrip()
            content = re.sub(r"^\s*\n", "", content, flags=re.MULTILINE)
        except Exception as e:
            raise Exception(f"TranAi：{e}")
        return content

# 示例用法
if __name__ == "__main__":
    TranAi_instance = TranAi()
    completion = TranAi_instance.analyze(
        scene="灭屏待机",
        ref_data={
            "avgcurrent_ma": 6,
        },
        data={
            "time_ms": 120000,
            "filterperiod": 30000,
            "avgcurrent_ma": 8,
            "filterstd": 3.2,
            "filtermax": 13.1,
            "filtermin": 6.2,
            "filtermode": 6.2
        },
        logs="""
            [  498.384711][ T2973] tran_test_check_psy: get primary_dvchg failed
            [  498.386264][ T2973] tran_test_check_psy: get primary_dvchg failed
            [  498.388122][ T2973] tran_test_check_psy: get primary_dvchg failed
            [  498.439216][  T109] [tran_touch-INFO]state_change_machine 171:[main]: TRAN_SUSPEND_MODE --> TRAN_ACTIVE_MODE
            [  498.506820][ T4805] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  499.014702][   T27] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  499.301718][  T110] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  499.465541][   T39] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  499.650729][   T39] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  499.934739][ T8870] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  500.746474][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 99, r13 = 0xa6040400, debug_flag = 0x191000 0x0, r12 = 0x10000, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0xf3,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x40069055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  500.813206][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 19, r13 = 0xa6040400, debug_flag = 0x191000 0x0, r12 = 0x10000, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1f3,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x40069055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  501.879070][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 24, r13 = 0xa6000400, debug_flag = 0x191000 0x0, r12 = 0x10000, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1f3,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x40069055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  501.890421][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SCP_IPC_MD2SPM_B, timer_out = 26, r13 = 0xa6000400, debug_flag = 0x191000 0x0, r12 = 0x800, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1f3,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x40069055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  501.924388][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 7, r13 = 0x84000400, debug_flag = 0x11000 0x0, r12 = 0x10000, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0xf3,  req_sta =  0x2000000, event_reg = 0x30000000, isr = 0x0, raw_ext_sta = 0x40069055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  501.968823][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 7, r13 = 0xa6040400, debug_flag = 0x11000 0x0, r12 = 0x10000, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1f3,  req_sta =  0x2000000, event_reg = 0x30000000, isr = 0x0, raw_ext_sta = 0x40069055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  502.054975][ T9140] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  502.166268][  T110] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  502.486750][   T27] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  502.744157][ T1405] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  503.051963][ T8870] mt6768-audio 11220000.mt6768-afe-pcm: mt6768_afe_runtime_suspend()
            [  504.895790][   T39] mt6768-audio 11220000.mt6768-afe-pcm: mt6768_afe_runtime_suspend()
            [  504.943588][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 19, r13 = 0xa6040400, debug_flag = 0x191000 0x0, r12 = 0x10000, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0xf3,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x40069055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  505.415071][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 27, r13 = 0x86040400, debug_flag = 0x191000 0x0, r12 = 0x10000, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1f3,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x40069055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  505.515074][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 32, r13 = 0x86000400, debug_flag = 0x191000 0x0, r12 = 0x10000, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1f3,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x40069055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  505.750410][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SCP_IPC_MD2SPM_B, timer_out = 538, r13 = 0x6040000, debug_flag = 0x191300 0x0, r12 = 0x801, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1fb,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x4006a055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  505.755057][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 29, r13 = 0x6040000, debug_flag = 0x191300 0x0, r12 = 0x10001, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1fb,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x4006a055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  505.854156][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 7, r13 = 0x26040000, debug_flag = 0x11000 0x0, r12 = 0x10000, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1fb,  req_sta =  0x2000000, event_reg = 0x30000000, isr = 0x0, raw_ext_sta = 0x4006a055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  506.155055][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 31, r13 = 0x6040000, debug_flag = 0x191300 0x0, r12 = 0x10001, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1fb,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x4006a055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  506.215075][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 26, r13 = 0x86040400, debug_flag = 0x191000 0x0, r12 = 0x10000, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0xf3,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x40069055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  506.554458][ T8870] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  506.635059][    T0] [name:spm&][SPM] IdleDram wake up by  R12_SYS_TIMER_EVENT_B, timer_out = 26, r13 = 0x6040000, debug_flag = 0x191300 0x0, r12 = 0x10001, r12_ext = 0x0, raw_sta = 0x0, idle_sta = 0x1fb,  req_sta =  0x2000000, event_reg = 0x90100000, isr = 0x0, raw_ext_sta = 0x4006a055, wake_misc = 0x0, pcm_flag = 0x204182 0x0, req = 0x18
            [  507.358921][   T27] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  507.582307][ T8870] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  507.647089][ T4805] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  507.766741][   T27] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  507.932233][ T5499] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  508.230417][  T882] [tran_touch-INFO]nvt_disp_notifier_callback 165:[main]: drm notify tp suspends start
            [  508.230464][  T882] [tran_touch-INFO]state_change_machine 171:[main]: TRAN_ACTIVE_MODE --> TRAN_SUSPEND_MODE
            [  508.230476][  T882] <I>CTS-SPIDrv Suspend
            [  508.230485][  T882] <I>CTS-Core Suspend device
            [  508.230497][  T882] <I>CTS-Core Set suspend mode:sleep
            [  508.230831][  T882] <I>CTS-Core Device suspended ...
            [  508.231847][  T888] healthd: battery l=71 v=3942 t=28.0 h=2 st=3 c=-439100 fc=670000 cc=6 chg=
            [  508.232737][ T2973] tran_test_check_psy: get primary_dvchg failed
            [  508.233723][ T2973] tran_test_check_psy: get primary_dvchg failed
            [  508.234522][ T2973] tran_test_check_psy: get primary_dvchg failed
            [  508.240826][   T27] [pm_qos_debug] msdc_runtime_suspend+0x248/0x2d8 [tran_mtk_mmc_mod] request PMQOS = -1
            [  508.258446][  T882] [tran_touch-INFO]nvt_disp_notifier_callback 175:[main]: drm notify tp suspends end
            [  508.400387][  T882] [DISP]CRTC0 release wakelock mtk_drm_crtc_suspend 16405 cnt(0)
        """
    )
    print(completion)
