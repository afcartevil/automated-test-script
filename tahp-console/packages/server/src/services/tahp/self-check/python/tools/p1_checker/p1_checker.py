"""P1 驱动自检项检查器（温升 + 功耗 + 关机）。

由 AI 自检用例 cases/power_feature/p1_check/case1.py 调用。
检查顺序：thermal_zone,cool → 新增NTC检测 → Flight mode suspend → 关机电流

功耗测量使用 tpower_auto 中的 TPowerTool（通过 APM.exe 与硬件通信）。
TPowerTool 提供的测量接口：
  - measurestart(pmsn)  开始采集
  - measurestop(pmsn)   停止采集，返回 dict:
      avgcurrent_mA  平均电流
      filtermin      最小电流（底电）
      filtermax      最大电流
      filtermode     众数电流
      filterstd      标准差
      filterperiod   滤波周期
      time_ms        测量时长(ms)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional


class P1Checker:
    """P1 驱动自检项。project_root 指向 tools/p1_checker。"""

    # 检查项定义（按执行顺序）
    ITEMS = [
        {"id": "thermal_zone", "name": "thermal_zone,cool", "expected": "NTC温度在20000-60000范围内"},
        {"id": "new_ntc", "name": "新增NTC检测", "expected": "能正常读取NTC温度"},
        {"id": "flight_suspend", "name": "Flight mode suspend", "expected": "对比MTK datasheet"},
        {"id": "shutdown_current", "name": "关机电流", "expected": "≤0.3mA"},
    ]

    def __init__(self, serial: str, on_step: Optional[Callable[[str], None]] = None):
        if not serial or not str(serial).strip():
            raise ValueError("device serial is required")
        self.serial = str(serial).strip()
        self.on_step = on_step
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = Path(self.project_root) / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # TPowerTool 实例和设备管理器
        self._tpowertool = None
        self._device_manager = None
        self._pmsn = None
        self._load_tpowertool()

    def _emit(self, message: str) -> None:
        if self.on_step:
            try:
                self.on_step(message)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # TPowerTool 加载
    # ------------------------------------------------------------------
    def _load_tpowertool(self) -> None:
        """从 tpower_auto 加载 TPowerTool 和 Device。

        参考 start_env_current_analysis.bat / start_current_analysis_python.py
        的环境初始化方式：添加 tpower_auto 根目录和 tests/current_analysis 到
        sys.path，并 chdir 到 tpower_auto 根目录（PROJ_DIR）。
        """
        tpower_root = Path(self.project_root).parent / "tpower_auto"
        tpower_tests = tpower_root / "tests" / "current_analysis"

        if not tpower_tests.is_dir():
            self._emit(f"TPowerTool 路径不存在: {tpower_tests}")
            self._emit("电流测试将标记为 Blocked")
            return

        try:
            # 与 start_current_analysis_python.py 一致的路径初始化
            tpower_root_str = str(tpower_root)
            tpower_tests_str = str(tpower_tests)
            tpower_plugins_str = str(tpower_root / "plugins")

            for p in (tpower_root_str, tpower_tests_str, tpower_plugins_str):
                if p not in sys.path:
                    sys.path.insert(0, p)

            # 需要 chdir 到 tpower_auto 根目录，与 PROJ_DIR 对齐
            # （powertrde.env 中的相对路径依赖此工作目录）
            saved_cwd = os.getcwd()
            os.chdir(tpower_root_str)

            from device import Device
            from pytpowertool.tpowertool import TPowerTool

            self._tpowertool = TPowerTool()
            self._device_manager = Device()

            # 恢复工作目录
            os.chdir(saved_cwd)

            # 尝试发现设备
            devices = self._device_manager.update()
            if devices:
                for pmsn, info in devices.items():
                    if info.get("serial") == self.serial:
                        self._pmsn = pmsn
                        break
                if not self._pmsn:
                    self._pmsn = list(devices.keys())[0]

            if self._pmsn:
                self._emit(f"TPowerTool 已连接，PMSN={self._pmsn}")
            else:
                self._emit("TPowerTool 已加载但未发现匹配设备，电流测试将标记为 Blocked")
        except Exception as exc:
            self._emit(f"TPowerTool 加载失败: {exc}")
            self._emit("电流测试将标记为 Blocked")
            self._tpowertool = None
            self._device_manager = None

    @property
    def has_tpowertool(self) -> bool:
        """检查 TPowerTool 和设备是否可用。"""
        return (
            self._tpowertool is not None
            and self._device_manager is not None
            and self._pmsn is not None
        )

    # ------------------------------------------------------------------
    # TPowerTool 测量封装
    # ------------------------------------------------------------------
    def _measure_current(self, pmsn: str, duration_s: int, filter_period_s: int = 10, stabilize_s: int = 0) -> Optional[Dict]:
        """使用 tpower_auto 的 Device 封装方法测量电流。

        参考 C01_Sleep 标准流程：
        1. 断开 USB
        2. 等待电流稳定（stabilize_s）
        3. 设置滤波周期
        4. device.start_measure() — 内部断开 USB + TPowerTool.measurestart()
        5. 等待测量时长
        6. device.stop_measure() — 内部 TPowerTool.measurestop() + 重连 USB
        7. 返回结果含 avgcurrent_mA, filtermin(底电), filtermax 等

        Args:
            pmsn: 功耗仪设备序列号
            duration_s: 测量时长（秒）
            filter_period_s: 滤波周期（秒）
            stabilize_s: 测量前等待电流稳定的时间（秒），默认 0

        Returns:
            dict 包含:
                avg_current: 平均电流 (mA)
                min_current: 最小电流/底电 (mA)
                max_current: 最大电流 (mA)
                mode_current: 众数电流 (mA)
                std_current: 标准差 (mA)
                time_ms: 测量时长 (ms)
            失败返回 None
        """
        # 1. 断开 USB（与 C01_Sleep 一致）
        self._emit("断开USB…")
        self._device_manager.usb_disconnect(pmsn)
        
        # 2. 等待电流稳定
        if stabilize_s > 0:
            self._emit(f"等待电流稳定 {stabilize_s}s…")
            time.sleep(stabilize_s)

        # 3. 设置滤波周期
        self._emit(f"设置滤波周期 {filter_period_s}s…")
        self._device_manager.set_filterperiod(pmsn, filter_period_s)
        time.sleep(2)

        # 4. 开始测量（device.start_measure 内部会调用 TPowerTool.measurestart）
        self._emit(f"开始测量 {duration_s}s…")
        start_ok = self._device_manager.start_measure(pmsn)
        if not start_ok:
            self._emit("测量启动失败")
            return None

        # 5. 等待测量时长
        time.sleep(duration_s)

        # 6. 停止测量（device.stop_measure 内部会调用 TPowerTool.measurestop 并重连 USB）
        self._emit("停止测量，获取结果…")
        result = self._device_manager.stop_measure(pmsn)

        if result is None or not isinstance(result, dict):
            self._emit("测量停止失败，未获取到有效数据")
            return None

        # TPowerTool 返回的值都是字符串，需要转换为浮点数
        def _to_float(val) -> Optional[float]:
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        avg_current = _to_float(result.get("avgcurrent_mA"))
        min_current = _to_float(result.get("filtermin"))  # 底电
        max_current = _to_float(result.get("filtermax"))
        mode_current = _to_float(result.get("filtermode"))
        std_current = _to_float(result.get("filterstd"))
        time_ms = _to_float(result.get("time_ms"))

        if avg_current is None:
            self._emit("测量结果中缺少 avgcurrent_mA")
            return None

        self._emit(f"测量完成: 平均={avg_current:.2f}mA, 底电={min_current:.2f}mA, 最大={max_current:.2f}mA")

        return {
            "avg_current": avg_current,
            "min_current": min_current,  # 底电
            "max_current": max_current,
            "mode_current": mode_current,
            "std_current": std_current,
            "time_ms": time_ms,
            "raw": result,
        }

    # ------------------------------------------------------------------
    # ADB 工具
    # ------------------------------------------------------------------
    def _adb(self, command: str, timeout: int = 10) -> str:
        """执行 ADB 命令，返回 stdout。"""
        try:
            if command.startswith("adb "):
                command = command[4:]
            full_command = f"adb -s {self.serial} {command}"
            proc = subprocess.Popen(
                full_command, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            try:
                stdout_bytes, _ = proc.communicate(timeout=timeout)
                return stdout_bytes.decode("utf-8", errors="ignore").strip()
            except subprocess.TimeoutExpired:
                proc.kill()
                return "Timeout expired"
        except Exception as exc:
            return f"Error: {exc}"

    def _adb_shell(self, command: str, timeout: int = 10) -> str:
        return self._adb(f'shell "{command}"', timeout=timeout)

    def _check_device(self) -> bool:
        return self._adb("get-state") == "device"

    # ------------------------------------------------------------------
    # 检查项 1: thermal_zone,cool
    # ------------------------------------------------------------------
    def check_thermal_zone(self) -> Dict:
        """遍历 thermal_zone 节点，验证 NTC 温度在 20000-60000 范围内。"""
        self._emit("开始检查 thermal_zone,cool…")
        evidence_rows = []
        zones_found = []
        all_pass = True
        na_count = 0

        # 获取 thermal_zone 数量
        zone_count_str = self._adb_shell("ls -d /sys/class/thermal/thermal_zone* 2>/dev/null | wc -l")
        try:
            zone_count = int(zone_count_str.strip())
        except (ValueError, AttributeError):
            zone_count = 0

        if zone_count == 0:
            self._emit("未找到任何 thermal_zone 节点")
            return {
                "name": "thermal_zone,cool",
                "status": "Fail",
                "expected": "NTC温度在20000-60000范围内",
                "actual": "未找到任何 thermal_zone 节点",
                "evidence": [],
            }

        for i in range(zone_count):
            zone_path = f"/sys/class/thermal/thermal_zone{i}"
            type_str = self._adb_shell(f"cat {zone_path}/type 2>/dev/null")
            temp_str = self._adb_shell(f"cat {zone_path}/temp 2>/dev/null")

            if not type_str or type_str.startswith("Error") or type_str.startswith("Timeout"):
                evidence_rows.append({
                    "name": f"zone{i} (type)",
                    "expected": "可读",
                    "actual": type_str or "(empty)",
                    "ok": False,
                })
                all_pass = False
                continue

            try:
                temp_val = int(temp_str.strip())
            except (ValueError, AttributeError):
                evidence_rows.append({
                    "name": f"zone{i} ({type_str})",
                    "expected": "NTC温度在20000-60000范围内",
                    "actual": f"temp值无效: {temp_str}",
                    "ok": False,
                })
                all_pass = False
                continue

            # -274000 是传感器未连接的标志值（绝对零度偏移），0 也是无效值
            # 这两种情况标记为 NA，不算失败
            if temp_val <= 0:
                na_count += 1
                evidence_rows.append({
                    "name": f"zone{i} ({type_str})",
                    "expected": "NTC温度在20000-60000范围内",
                    "actual": f"{temp_val} (传感器未连接，NA)",
                    "ok": True,  # NA 不算失败
                })
                zones_found.append({"zone": i, "type": type_str, "temp": temp_val, "status": "NA"})
                continue

            in_range = 20000 <= temp_val <= 60000
            zones_found.append({"zone": i, "type": type_str, "temp": temp_val})
            evidence_rows.append({
                "name": f"zone{i} ({type_str})",
                "expected": "NTC温度在20000-60000范围内",
                "actual": f"{temp_val} ({'OK' if in_range else '超出范围'})",
                "ok": in_range,
            })
            if not in_range:
                all_pass = False

        status = "Pass" if all_pass else "Fail"
        summary = f"共 {zone_count} 个thermal_zone，{na_count} 个NA，{'全部' if all_pass else '部分'}在正常范围内"
        self._emit(f"thermal_zone,cool 检查完成: {summary}")

        return {
            "name": "thermal_zone,cool",
            "status": status,
            "expected": "NTC温度在20000-60000范围内",
            "actual": summary,
            "evidence": evidence_rows,
            "detail": zones_found,
        }

    # ------------------------------------------------------------------
    # 检查项 2: 新增NTC检测
    # ------------------------------------------------------------------
    def check_new_ntc(self) -> Dict:
        """识别新增 NTC 类型，验证能正常读取温度。"""
        self._emit("开始检查新增NTC检测…")
        evidence_rows = []
        new_ntc_found = []
        all_pass = True

        zone_count_str = self._adb_shell("ls -d /sys/class/thermal/thermal_zone* 2>/dev/null | wc -l")
        try:
            zone_count = int(zone_count_str.strip())
        except (ValueError, AttributeError):
            zone_count = 0

        # 已知标准 NTC 类型（根据项目不同可能有差异）
        known_ntc_types = {"skin", "battery", "charger", "usb", "pa", "xo", "ddr", "gpu", "cpu", "mtktz"}

        for i in range(zone_count):
            zone_path = f"/sys/class/thermal/thermal_zone{i}"
            type_str = self._adb_shell(f"cat {zone_path}/type 2>/dev/null").strip().lower()
            temp_str = self._adb_shell(f"cat {zone_path}/temp 2>/dev/null").strip()

            if not type_str or type_str.startswith("error"):
                continue

            # 判断是否为新增NTC（不在已知类型中，且名称包含ntc或thermal相关关键词）
            is_known = any(known in type_str for known in known_ntc_types)
            if is_known:
                continue

            # 尝试读取温度
            try:
                temp_val = int(temp_str)
                readable = True
            except (ValueError, AttributeError):
                readable = False
                temp_val = None

            new_ntc_found.append({
                "zone": i, "type": type_str,
                "temp": temp_val, "readable": readable,
            })

            if readable:
                evidence_rows.append({
                    "name": f"zone{i} ({type_str})",
                    "expected": "能正常读取NTC温度",
                    "actual": f"温度={temp_val}",
                    "ok": True,
                })
            else:
                evidence_rows.append({
                    "name": f"zone{i} ({type_str})",
                    "expected": "能正常读取NTC温度",
                    "actual": f"读取失败: {temp_str}",
                    "ok": False,
                })
                all_pass = False

        if not new_ntc_found:
            self._emit("未发现新增NTC节点")
            return {
                "name": "新增NTC检测",
                "status": "Pass",
                "expected": "能正常读取NTC温度",
                "actual": "未发现新增NTC节点（所有zone均为已知类型）",
                "evidence": [],
                "detail": [],
            }

        status = "Pass" if all_pass else "Fail"
        summary = f"发现 {len(new_ntc_found)} 个新增NTC，{'全部' if all_pass else '部分'}可正常读取"
        self._emit(f"新增NTC检测完成: {summary}")

        return {
            "name": "新增NTC检测",
            "status": status,
            "expected": "能正常读取NTC温度",
            "actual": summary,
            "evidence": evidence_rows,
            "detail": new_ntc_found,
        }

    # ------------------------------------------------------------------
    # 检查项 3: Flight mode suspend
    # ------------------------------------------------------------------
    def check_flight_suspend(self, gesture_state: str = "全闭") -> Dict:
        """飞行模式待机电流测量。

        使用 TPowerTool 测量：
        1. 不插卡，开启飞行模式，关闭所有手势，关闭WiFi,BT,GPS,自动旋转屏
        2. 进入主界面切换至飞行模式，灭屏静置5分钟，等电流稳定后，开始测量记录平均电流，及最小电流(底电流)
        3. 结果备注手势全闭还是全开的数据

        Args:
            gesture_state: 手势状态，"全闭" 或 "全开"
        """
        if not self.has_tpowertool:
            self._emit("TPowerTool 不可用，Flight mode suspend 标记为 Blocked")
            return {
                "name": "Flight mode suspend",
                "status": "Blocked",
                "expected": "对比MTK datasheet",
                "actual": "TPowerTool 功耗仪未连接",
                "evidence": [],
            }

        self._emit(f"开始 Flight mode suspend 测试（手势状态: {gesture_state}）…")
        pmsn = self._pmsn

        # 1. 配置手机环境：不插卡，开启飞行模式，关闭所有手势，关闭WiFi,BT,GPS,自动旋转屏
        self._emit("配置手机环境：关闭WiFi/BT/GPS/自动旋转，开启飞行模式…")
        self._adb_shell("settings put system accelerometer_rotation 0")
        self._adb_shell("svc wifi disable")
        self._adb_shell("svc bluetooth disable")
        self._adb_shell("settings put secure location_mode 0")
        self._adb_shell("settings put global airplane_mode_on 1")
        self._adb_shell("am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true")
        time.sleep(2)

        # 2. 进入主界面
        self._emit("返回主界面…")
        self._adb_shell("input keyevent HOME")
        time.sleep(1)

        # 3. 灭屏
        self._emit("灭屏…")
        self._adb_shell("input keyevent KEYCODE_SLEEP")
        time.sleep(2)

        # 4. 灭屏静置 5 分钟让电流稳定
        self._emit("灭屏静置等待电流稳定（5分钟）…")
        for remaining in range(300, 0, -30):
            self._emit(f"  剩余 {remaining}s…")
            time.sleep(30)

        # 5. 使用 TPowerTool 测量（内部会断开USB、等待稳定、测量、重连USB）
        # 参考 C01_Sleep: 灭屏后断开USB，等待180s稳定，然后测量120s
        result = self._measure_current(pmsn, duration_s=120, filter_period_s=30, stabilize_s=180)

        if result is None:
            self._emit("功耗测量失败，未获取到有效数据")
            return {
                "name": "Flight mode suspend",
                "status": "Fail",
                "expected": "对比MTK datasheet",
                "actual": "功耗测量未返回有效数据",
                "evidence": [],
            }

        avg_current = result.get("avg_current")
        min_current = result.get("min_current")  # 底电
        max_current = result.get("max_current")
        mode_current = result.get("mode_current")

        if avg_current is None:
            self._emit("功耗测量结果中缺少平均电流数据")
            return {
                "name": "Flight mode suspend",
                "status": "Fail",
                "expected": "对比MTK datasheet",
                "actual": "测量结果缺少电流数据",
                "evidence": [{"name": "raw_result", "expected": "含avg_current", "actual": str(result), "ok": False}],
            }

        # 7. 对比 datasheet（使用通用阈值，实际项目应配置）
        # 默认阈值：飞行模式待机电流 ≤ 15mA（根据具体项目 datasheet 调整）
        threshold_ma = 15.0
        is_pass = avg_current <= threshold_ma

        evidence_rows = [
            {
                "name": "平均电流",
                "expected": f"≤ {threshold_ma}mA (datasheet)",
                "actual": f"{avg_current:.2f}mA",
                "ok": is_pass,
            },
        ]
        if min_current is not None:
            evidence_rows.append({
                "name": "最小电流(底电)",
                "expected": "-",
                "actual": f"{min_current:.2f}mA",
                "ok": True,
            })
        if max_current is not None:
            evidence_rows.append({
                "name": "最大电流",
                "expected": "-",
                "actual": f"{max_current:.2f}mA",
                "ok": True,
            })
        if mode_current is not None:
            evidence_rows.append({
                "name": "众数电流",
                "expected": "-",
                "actual": f"{mode_current:.2f}mA",
                "ok": True,
            })

        status = "Pass" if is_pass else "Fail"
        summary = f"飞行模式待机电流: {avg_current:.2f}mA"
        if min_current is not None:
            summary += f"，底电: {min_current:.2f}mA"
        summary += f" (手势{gesture_state}，阈值≤{threshold_ma}mA)"
        self._emit(f"Flight mode suspend 完成: {summary} — {'Pass' if is_pass else 'Fail'}")

        return {
            "name": "Flight mode suspend",
            "status": status,
            "expected": f"≤ {threshold_ma}mA (对比MTK datasheet)",
            "actual": f"{avg_current:.2f}mA" + (f"，底电{min_current:.2f}mA" if min_current else "") + f" (手势{gesture_state})",
            "evidence": evidence_rows,
            "detail": {**result, "gesture_state": gesture_state},
        }

    # ------------------------------------------------------------------
    # 检查项 4: 关机电流（最后执行）
    # ------------------------------------------------------------------
    def check_shutdown_current(self) -> Dict:
        """关机电流测量。

        使用 TPowerTool 测量：
        1. 手机关机
        2. 断开 USB
        3. 等待 30s 稳定
        4. 测量关机电流（30s）
        5. 预期结果 ≤0.3mA
        6. 重连 USB，开机
        """
        if not self.has_tpowertool:
            self._emit("TPowerTool 不可用，关机电流标记为 Blocked")
            return {
                "name": "关机电流",
                "status": "Blocked",
                "expected": "≤0.3mA",
                "actual": "TPowerTool 功耗仪未连接",
                "evidence": [],
            }

        self._emit("开始关机电流测试…")
        pmsn = self._pmsn
        threshold_ma = 0.3

        # 1. 关机
        self._emit("执行关机…")
        self._adb_shell("reboot -p", timeout=15)

        # 2. 等待关机完成（约 30s）
        self._emit("等待设备关机（30s）…")
        time.sleep(30)

        # 3. 断开 USB
        self._emit("断开 USB…")
        self._device_manager.usb_disconnect(pmsn)

        # 4. 测量关机电流（等待 30s 稳定 + 测量 30s）
        self._emit("测量关机电流…")
        result = self._measure_current(pmsn, duration_s=30, filter_period_s=10, stabilize_s=30)

        # _measure_current 会在测量后重连 USB，关机状态下需再次断开
        self._device_manager.usb_disconnect(pmsn)

        # 5. 重连 USB，开机
        self._emit("重新连接 USB，开机…")
        self._device_manager.usb_connect(pmsn)
        time.sleep(3)
        self._adb("reboot", timeout=10)

        # 6. 等待开机完成
        self._emit("等待设备开机…")
        for _ in range(60):
            time.sleep(5)
            if self._check_device():
                break

        if result is None:
            self._emit("关机电流测量失败")
            return {
                "name": "关机电流",
                "status": "Fail",
                "expected": f"≤{threshold_ma}mA",
                "actual": "测量未返回有效数据",
                "evidence": [],
            }

        avg_current = result.get("avg_current")
        min_current = result.get("min_current")
        max_current = result.get("max_current")

        if avg_current is None:
            self._emit("测量结果中缺少平均电流数据")
            return {
                "name": "关机电流",
                "status": "Fail",
                "expected": f"≤{threshold_ma}mA",
                "actual": "测量结果缺少电流数据",
                "evidence": [{"name": "raw_result", "expected": "含 avg_current", "actual": str(result), "ok": False}],
            }

        is_pass = avg_current <= threshold_ma

        evidence_rows = [
            {
                "name": "平均电流",
                "expected": f"≤{threshold_ma}mA",
                "actual": f"{avg_current:.3f}mA",
                "ok": is_pass,
            },
        ]
        if min_current is not None:
            evidence_rows.append({
                "name": "最小电流(底电)",
                "expected": "-",
                "actual": f"{min_current:.3f}mA",
                "ok": True,
            })
        if max_current is not None:
            evidence_rows.append({
                "name": "最大电流",
                "expected": "-",
                "actual": f"{max_current:.3f}mA",
                "ok": True,
            })

        status = "Pass" if is_pass else "Fail"
        summary = f"关机电流：{avg_current:.3f}mA"
        if min_current is not None:
            summary += f"，底电：{min_current:.3f}mA"
        self._emit(f"关机电流完成：{summary} — {'Pass' if is_pass else 'Fail'}")

        return {
            "name": "关机电流",
            "status": status,
            "expected": f"≤{threshold_ma}mA",
            "actual": summary,
            "evidence": evidence_rows,
            "detail": {**result},
        }

    # ------------------------------------------------------------------
    # 运行所有检查
    # ------------------------------------------------------------------
    def run_all(self, gesture_state: str = "全闭") -> Dict:
        """按顺序执行全部 4 项检查，返回结构化结果。

        Args:
            gesture_state: 手势状态，"全闭" 或 "全开"，用于 Flight mode suspend 测试
        """
        if not self._check_device():
            return {
                "ok": False,
                "error": f"设备 {self.serial} 未连接 ADB",
                "total": 0, "passed": 0, "failed": 0,
                "items": [],
            }

        self._emit(f"开始 P1 驱动自检，设备: {self.serial}")

        items = []
        passed = 0
        failed = 0

        # 1. thermal_zone,cool
        items.append(self.check_thermal_zone())

        # 2. 新增NTC检测
        items.append(self.check_new_ntc())

        # 3. Flight mode suspend（传入手势状态）
        items.append(self.check_flight_suspend(gesture_state=gesture_state))

        # 4. 关机电流（最后）
        items.append(self.check_shutdown_current())

        for item in items:
            status = item.get("status", "")
            if status == "Pass":
                passed += 1
            elif status == "Fail":
                failed += 1
            # Blocked 也计入未通过

        total = len(items)
        blocked = total - passed - failed
        # 只有全部通过才 ok，任何一项未通过（Fail 或 Blocked）都是 fail
        ok = passed == total

        result = {
            "ok": ok,
            "total": total,
            "passed": passed,
            "failed": failed,
            "blocked": blocked,
            "items": items,
        }

        # 生成 xlsx 报告
        xlsx_path = self._write_xlsx(items)
        result["xlsx_path"] = str(xlsx_path) if xlsx_path else ""

        summary = f"P1自检完成: {passed} 通过 / {failed} 失败 / {blocked} Blocked / 共 {total} 项"
        self._emit(summary)

        return result

    # ------------------------------------------------------------------
    # XLSX 报告生成
    # ------------------------------------------------------------------
    def _write_xlsx(self, items: List[Dict]) -> Optional[Path]:
        """生成 xlsx 报告。"""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            self._emit("openpyxl 未安装，跳过 xlsx 报告生成")
            return None

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "P1驱动自检"

        # 样式
        header_font = Font(name="微软雅黑", bold=True, size=11, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        pass_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        fail_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        block_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin"),
        )

        # 标题行
        headers = ["序号", "检查项", "检查方法", "预期结果", "自检结果", "实际值", "证据明细"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border

        # 列宽
        col_widths = [6, 25, 50, 30, 12, 30, 60]
        for col, width in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = width

        # 检查方法描述
        methods = {
            "thermal_zone,cool": "adb命令查看所有thermal_zone下的节点，ntc温度是否正常\nadb shell \"i=0 ; while [[ $i -lt 80 ]]; do { type=`cat /sys/class/thermal/thermal_zone$i/type` ; temp=`cat /sys/class/thermal/thermal_zone$i/temp` ; echo \"$i $type : $temp\"; i=$(($i+1));done\"",
            "新增NTC检测": "与硬件确认项目是否有新增NTC，有则需要单独检测能否正常读取NTC温度",
            "Flight mode suspend": "1、不插卡，开启飞行模式，关闭所有手势，关闭WiFi,BT,GPS,自动旋转屏\n2、进入主界面切换至飞行模式，静置五分钟后灭屏，等电流稳定后，开始测量记录平均电流，及最小电流(底电流)\n3、结果备注手势全闭还是全开的数据",
            "关机电流": "1、手机关机\n2、断开USB\n3、等待30s稳定后测量关机电流（30s）\n4、预期结果≤0.3mA",
        }

        # 数据行
        for idx, item in enumerate(items, 1):
            row = idx + 1
            name = item.get("name", "")
            status = item.get("status", "")
            expected = item.get("expected", "")
            actual = item.get("actual", "")
            evidence = item.get("evidence", [])

            evidence_text = ""
            for ev in evidence:
                mark = "OK" if ev.get("ok") else "FAIL"
                evidence_text += f"[{mark}] {ev.get('name', '')}: 预期={ev.get('expected', '')}, 实际={ev.get('actual', '')}\n"

            status_fill = {"Pass": pass_fill, "Fail": fail_fill, "Blocked": block_fill}.get(status)

            values = [
                idx, name, methods.get(name, ""), expected, status, actual, evidence_text.strip(),
            ]
            for col, val in enumerate(values, 1):
                cell = ws.cell(row=row, column=col, value=val)
                cell.border = thin_border
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if col == 5 and status_fill:
                    cell.fill = status_fill

        # 汇总行
        total_row = len(items) + 2
        ws.cell(row=total_row, column=1, value="汇总").font = Font(bold=True)
        ws.cell(row=total_row, column=2, value=f"通过: {sum(1 for i in items if i.get('status') == 'Pass')}")
        ws.cell(row=total_row, column=3, value=f"失败: {sum(1 for i in items if i.get('status') == 'Fail')}")
        ws.cell(row=total_row, column=4, value=f"Blocked: {sum(1 for i in items if i.get('status') == 'Blocked')}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        xlsx_path = self.output_dir / f"p1_check_{timestamp}.xlsx"
        wb.save(str(xlsx_path))
        self._emit(f"xlsx报告已生成: {xlsx_path}")
        return xlsx_path
