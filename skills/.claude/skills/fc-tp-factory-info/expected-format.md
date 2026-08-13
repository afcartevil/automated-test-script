# 工模 TP 信息 sysfs 期望格式

与 `adapt/tp-adapt-factory-sysfs` 内核实现一致，供 `fc-tp-factory-info` 判定 Pass/Fail。

## tp_vendor

- **成功**：`supplier_vendor_ICNAME_SUPNUM`
  - 示例：`TM_GT9916_01`、`BOE_FT3681G_02`
  - `ICNAME`：驱动 `cur_ic` 大写，最长约 16 字符
  - `supplier_vendor`：DTS `supplier-vendor-<i>`
  - `SUPNUM`：两位数字 `supplier-<i>` 序号
- **Fail**：`UNKNOWN`、空串、无下划线分隔

## tp_firmware_version

- **非 Goodix**：`0x<fw>,bv:0x<bv>`（十六进制片段非全 0）
- **Goodix**：`0x<fw>_0x<cfg>,bv:0x<fw>_0x<cfg>` 常见
- **可选扩展**（仅 `TRAN_NORMAL_MODE` + algo）：额外 `Algo:` / `Func:` 行；工模工厂模式可能无此行
- **Fail**：`wc -c` 为 0；仅 `0x00,bv:0x00` 类无效值

## tp_name（折叠，可选）

- 形如：`MAIN:... SUB:...`，用于双控并存时对照信息页所在屏

## 路径注意

- 标准：`/sys/devices/platform/mtk-tpd/`（symlink，脚本优先 `readlink -f` 后读）
- 驱动：`/sys/bus/platform/drivers/mtk-tpd/<pdev>/`
- 枚举：`find` 于 `sys/devices/platform` 与 `sys/bus/platform/devices`（深度 ≤5）
- 部分项目另有 `mtk-tpd2` / `TranssionCustom.c` 第二套节点；以 `find` 结果为准，工厂页读哪条就查哪条
