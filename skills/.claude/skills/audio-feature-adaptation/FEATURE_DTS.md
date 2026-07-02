# DTS 音效

## 路径

升级后宏控文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

升级前 tuning 目录：

```text
{base_code}/vendor/prjconfig/vendor/dts/tuning/{project_name1}/
```

升级后 tuning 目录：

```text
{base_code_sunmao}/vendor/transsion/vendor_modules/common/audiodts/tuning/{project_name1}/
```

## 步骤

1. 在升级后宏控文件中配置以下宏控：

```make
TRAN_DTS_SUPPORT := yes
TRAN_DTS_TUNING_PATH := {project_name1}
```

2. 将升级前 tuning 目录中的所有文件复制到升级后 tuning 目录。
3. 在升级后的 `customer.cfg` 中，如果末尾不存在以下内容，则追加：

```text
tuningPath=/odm/etc/asset/audio/dts
```

## 继续前必须询问

- 升级前 tuning 目录不存在。
- 升级后 tuning 目录中已有不同文件，继续会覆盖。
- 复制后仍不存在 `customer.cfg`。
- `customer.cfg` 中已存在不同的 `tuningPath`。

## 开发者提醒

- 在 SCM 中配置 `ro.tr_audio.dts.feature.support=1`。
- 如果 DTS 库升级过，需要重新调试 DTS 参数。
