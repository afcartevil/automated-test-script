# APN XML Schema Reference

## File Location

- TODO: fill in the default path, e.g. `E:/project/Apn/apns-conf.xml`
| 文件目录 | 代表含义 |
| master_s/apns-conf.xml | 安卓S的APN配置文件 |
| master_u/apns-conf.xml | 安卓U和安卓V的APN配置文件 |
| master_w/apns-conf.xml | 安卓W的APN配置文件 |
| apns-conf.xml | 安卓T的APN配置文件 |

- 你仅被允许修改这4个文件，除了修改记录文件，其他的文件不能修改

### 平台与可修改文件范围

| 平台 | 可修改文件 |
|------|-----------|
| MTK | `apns-conf.xml`、`master_s/`、`master_u/`、`master_w/` 下的 `apns-conf.xml` |
| 高通 | **仅** `master_w/apns-conf.xml`（高通无 W 以下安卓版本，不得修改 `apns-conf.xml`、`master_s/`、`master_u/`） |

### 按 `type` 决定 MTK 修改范围（硬性规则）

| `type` 类别 | 典型值 | MTK 必须修改的文件 |
|------------|--------|-------------------|
| **上网 / 彩信** | `default`、`supl`、`mms`、`dun` 及组合 | **全部 4 个**：`apns-conf.xml`、`master_s/apns-conf.xml`、`master_u/apns-conf.xml`、`master_w/apns-conf.xml` |
| **IMS / XCAP 等** | `ims`、`xcap` | 按需求涉及的安卓版本，修改对应版本文件（可只涉及部分目录） |

- 上网/彩信类：4 个文件中的同一 PLMN + `type` 条目应保持一致。
- 高通：无论 `type`，仅 `master_w/apns-conf.xml`。

## XML Structure

```xml
<apn carrier="VIVO Internet"
      mcc="724"
      mnc="10"
      apn="zap.vivo.com.br"
      user="vivo"
      password="vivo"
      authtype="1"
      type="default,supl"
      protocol="IPV4V6"
      roaming_protocol="IPV4V6"
  />
- 此处仅为一个APN范例，实际不同的APN携带的参数类型不一致

```



## Unique Identifiers (for locating entries)

- 示例：20210运营商上网参数名称变更为NOVA Internet，彩信参数名称变更为NOVA MMS
- 拆解plmn为mcc和mnc，mcc为前三位，剩下部分为mnc，根据mcc和mnc筛选出符合条件的APN参数，再根据type判断是上网/彩信/IMS/补充业务 参数，根据需求做出正确修改

