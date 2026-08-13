# 变更记录

本文档记录 `DRV_FP_Check` 的重要版本变更。

## [1.3.0] - 2026-05-19

### 新增

- 扩展人脸调试检查：Face HAL 开机 log 初始化、adb `face-service` 进程、算法 `st_version` 版本。
- 补充人脸代码路径：`hardware/interfaces/biometrics/face/aidl`、`vendor/transsion/vendor_modules/face/face_hal`、`face_st`。
- 明确 `st_auth_get_template_info ret=203/204` 在无录入数据时不作为初始化失败。

### 改进

- 报告模板分为「指纹」「人脸」两个汇总表，保持简洁表格输出。

## [1.2.1] - 2026-05-19

### 改进

- 简化固定输出格式：默认仅「基础信息一行 + 汇总表（检查项/结论/说明）+ 总体结论 + 建议动作」，与 LJ8 检查风格一致。
- 取消默认输出 3.x 分项长文；仅在用户要求详细说明或 FAIL 需展开时补充证据。

## [1.2.0] - 2026-05-19

### 改进

- 新增「固定输出格式」章节（已由 1.2.1 简化为表格汇总为主）。
- 规定结论仅使用 `PASS` / `FAIL` / `BLOCKED`；风险项在汇总表备注列标注。
- 规定 `tran-keys`、DTS、DWS、rc/xml 等每项必须使用固定表格字段，避免不同项目输出版式不一致。
- 规定仅检查单项时仍须输出精简版固定结构，不得只回复自由文本。
- `CHECK_ITEMS.md` 增加第 7 节「固定输出格式」交叉引用。

## [1.1.0] - 2026-05-19

### 改进

- 增加升级前 / 升级后路径定位规则，要求先确认升级前产品根路径和升级后工作区根路径。
- 补充驱动、DTS、Preloader DWS、Kernel DCT DWS、Tools DWS 的升级前后路径模板。
- 增加 X6885 路径示例，明确示例中的项目名、SoC 和 kernel 版本只能作为参考，实际检查必须替换为用户指定目标项目。
- 强调升级前常见 `tran_projects/<family>/<project_variant>/<product>` 结构，不能把升级后 `vendor/mediatek/proprietary/...` 路径直接套到升级前仓库根目录。

## [1.0.1] - 2026-05-19

### 修正

- 修正非归一化驱动 compatible 判断规则：`tran_common` 应检查 `.compatible = "tran_fp_legacy"`，并要求 DTS fingerprint 节点 `compatible` 与 `tran_fp_legacy` 匹配。
- 同步更新 `SKILL.md` 的驱动检查摘要、进度清单和当前版本号。

## [1.0.0] - 2026-05-19

### 新增

- 创建 `DRV_FP_Check` 初始正式版，用于检查 Transsion/MTK Android 升级项目指纹调试项是否正确。
- 增加 rc/xml 配置检查规则：
  - 无指纹 IC 时注释 fingerprint permission、AIDL manifest、init rc、`manifest_transsion.xml`。
  - 非归一化 GOODIX GW9598 保留四行配置。
  - 非归一化其它 IC 注释 `manifest_transsion.xml`。
  - 归一化保留四行配置。
- 增加 DTS 与三处 DWS 指纹 GPIO 检查规则，要求与升级前目标项目配置一致。
- 增加 `adb shell getevent -ltr` 的 `tran-keys` 检查。
- 增加 `tran_common` / `tran_common_v2` 驱动目录与 DTS compatible 匹配检查。
- 新增版本管理文件：
  - `VERSION.md`
  - `CHANGELOG.md`

### 说明

- 本版本为正式版：主流程以用户提供的检查文档内容为依据，格式和项目边界参照 `DRV_FP_Adapt`。
