# regulator_vibrator DTS 参考

## 单位

- `regulator-*-microvolt` 使用 **微伏（µV）**。
- `V × 1_000_000 = µV`（整数，无小数时用整型 cell）。

## 常见注意点

- **固定电压**：`min-microvolt` 与 `max-microvolt` 设为相同值。
- **命名**：`regulator-name` 字符串可与驱动/regulator core 调试信息一致；设备树 label `regulator_vibrator` 用于 `&regulator_vibrator` 引用。
- **与 TP 同文件**：touch dtsi 中常汇总 GPIO、regulator、pinctrl；新增时避免与同文件其他 regulator 标签冲突。
- **若_regulator 已由 board dts 引用**：只可改电压或状态，不要随意移动节点导致 include 顺序破坏。
