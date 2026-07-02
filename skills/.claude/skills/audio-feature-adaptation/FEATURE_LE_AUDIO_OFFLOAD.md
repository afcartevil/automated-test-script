# 低功耗蓝牙音频

## 路径

配置文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/device-vext.mk
```

## 步骤

如果以下配置不存在，则添加：

```make
PRODUCT_ODM_PROPERTIES += ro.bluetooth.leaudio_offload.supported=true
PRODUCT_ODM_PROPERTIES += persist.bluetooth.leaudio_offload.disabled=false
```

如果任一属性已存在但值不同，除非周围注释显示这是项目有意覆盖，否则修改为 SOP 指定值。意图不明确时必须询问。

## 继续前必须询问

- `device-vext.mk` 不存在。
- 属性已存在且值冲突，同时注释显示可能是有意覆盖。
