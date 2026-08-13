# 阶段 4：alps/vendor/mediatek/proprietary/tools/dct DWS

**目标 repo**：`MTK_CODE/alps/vendor/mediatek/proprietary/tools/dct`

**目标文件**：`{base_code_sunmao}/vendor/mediatek/proprietary/tools/dct/dws/{platform_name}/{project_name_sunmao}.dws`

数据源：[references/dws-gpio-rules.md](../references/dws-gpio-rules.md)。

## 一、执行

复用阶段 3 已经定位的"需移植 GPIO 列表"与"升级前 DWS 中对应节点"，仅 **写入位置不同**。

1. Read 升级后目标 DWS。
2. 对每个 GPIO 节点，用与阶段 3 完全一致的字段值做 StrReplace 替换；目标 DWS 中无该节点 → 跳出问开发者。

## 二、阶段 4 Checkpoint

| 项 | 内容 |
| --- | --- |
| 本阶段改了什么 | 列出升级后 tools/dct DWS 中改动的 GPIO（编号 + 关键字段值） |
| 还差什么 | 同阶段 3 |
| 是否继续 | 默认询问"是否进入阶段 5（custom DWS + factory.ini）？" |

## 三、跳出条款

- 阶段 3 与本阶段对同一 GPIO 的字段值出现差异（任何字段不一致） → 跳出，问开发者哪一份准。**不要** 自动以最新一次写入为准。
