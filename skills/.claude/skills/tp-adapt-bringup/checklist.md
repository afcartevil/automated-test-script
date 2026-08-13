# TP Bring-up 执行 Checklist

与 [SKILL.md](SKILL.md) 配合使用。每项都记录“文件路径或命令证据”，没有证据不算完成。

## 0. 输入与 Done

- [ ] 目标项目 / 平台 / 分支：
- [ ] 参考项目：
- [ ] TP IC / 总线 / LCM：
- [ ] RST / INT / 电源 GPIO：
- [ ] 产品范围：基础触摸 / 工模信息 / 手势 / FOD / 大面积 / 容值
- [ ] 基础 Done：`fc-tp-driver`、`fc-tp-touch`、`fc-tp-sysfs`

## 1. 参考差异清单

- [ ] KO 表：目标与参考 `ko_order_table.csv`
- [ ] DTS：目标与参考 `*_touch.dtsi`
- [ ] DWS：目标与参考三份 DWS / `codegen.dws`
- [ ] 固件：目标与参考 `tp_fw/` 或等价目录
- [ ] 拷贝规则：目标与参考 `device-vext.mk` / 项目 `*.mk`
- [ ] 驱动：目标与参考 `transsion/vendor/<ic>/` 与 `core/`
- [ ] 已列出待改文件清单：

## 2. KO 与构建

- [ ] vendor TP `.ko` 行存在
- [ ] `adaptive-ts.ko` 行存在
- [ ] `KO path` 指向当前 `kernel_device_modules-*`
- [ ] `Odm/Ramdisk`、`BootTime.completed`、`Recovery` 与参考模式一致
- [ ] `BUILD.bazel` / `Makefile` 覆盖 vendor 和 core 目录
- [ ] 编译结果或失败日志：
- [ ] 上机证据：`lsmod` / dmesg modprobe 行

## 3. Touch DTS

- [ ] 板级 DTS include 目标 `*_touch.dtsi`
- [ ] I2C/SPI 总线、地址、CS 与硬件一致
- [ ] `reset-gpios`、`irq-gpios`、`interrupt-parent` 正确
- [ ] `vdd-supply`、`vio-supply` 或电源 GPIO 正确
- [ ] `supplier-num` 数量正确
- [ ] `supplier-<i>` 与 LCM 名、vendor 匹配逻辑一致
- [ ] `supplier-vendor-<i>` 是期望模组厂显示文案
- [ ] `supplier-vendor-fwname-<i>` 与真实固件文件名一致
- [ ] 折叠项目已确认主副 controller 和 `mtk-tpd` 读取路径

## 4. DWS 与引脚（总线 + GPIO）

- [ ] 已从 DTS 列出 TP 全部相关线：SPI 或 I2C + RST + INT + 电源 GPIO（若有）
- [ ] 工具侧 DWS：
- [ ] Preloader custom `codegen.dws`：
- [ ] Kernel DCT `codegen.dws`：
- [ ] SPI（若适用）：CLK / MOSI / MISO / CS — MODE 为 SPI 复用，GPIO 号与 DTS `spi@` / `cs-gpios` / pinctrl 一致
- [ ] I2C（若适用）：SCL / SDA — MODE 为 I2C 复用，与 DTS `i2c@` / `reg` / pinctrl 一致
- [ ] RST：GPIO 号、方向、上下拉、默认态与 DTS/原理图一致
- [ ] INT：GPIO/EINT 号、输入、上拉与 DTS/原理图一致
- [ ] AVDD/VDDI：若有 GPIO，配置与 DTS/原理图一致
- [ ] 仓库内 `TP_` / `CTP_` / `TOUCH` / `SPI` / `I2C` 关键字已搜，无遗漏 net
- [ ] 三份 DWS 上述 net 逐项一致

## 5. 固件与拷贝

- [ ] 固件源文件存在
- [ ] `PRODUCT_COPY_FILES` 目标分区与参考一致，常见为 `odm/firmware/`
- [ ] DTS fwname、驱动 request 名、打包文件名三者一致
- [ ] 多 supplier 的每个 fwname 都有对应文件
- [ ] 上机证据：`adb shell ls -l /odm/firmware/` 或实际目录

## 6. Vendor 驱动匹配

- [ ] `vendor_name` 与 DTS supplier 匹配
- [ ] `support_ic[]` 包含目标 IC
- [ ] `tran_controller_ops` 挂接基础 probe / suspend / resume
- [ ] `get_firmware_version` 已实现或沿用可靠参考
- [ ] `get_base_version` 已实现且能对应 BV/固件文件
- [ ] dmesg 无 `not support` / `match failed`
- [ ] dmesg 有 probe success / input registered 证据

## 7. 上机门禁

| 检查 | 结果 | 证据 |
|------|------|------|
| `fc-tp-driver` | | |
| `fc-tp-touch` | | |
| `fc-tp-sysfs` | | |
| `fc-tp-factory-info` | | |
| `fc-tp-selinux` | | |

## 8. 可选能力

仅在基础 Done 后勾选。

- [ ] 手势：`tp-adapt-gesture-driver` + `fc-tp-gesture`
- [ ] 容值：`tp-adapt-factory-capacitance` + `fc-tp-factory`
- [ ] FOD：专项日志/需求确认后处理
- [ ] 大面积：专项日志/需求确认后处理

## 9. 当前阻塞

- 阻塞现象：
- 已停在层级：KO / DTS / DWS / 固件 / 驱动匹配 / probe / touch / sysfs / SELinux / 可选功能
- 缺失证据：
- 下一步单一 skill 或检查：
