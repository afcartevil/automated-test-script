# test_app ADB 测试命令

包名：`com.android.transsion.tdd.autotest`

本文档汇总 `test_app` 中可通过 **adb 调起** 的测试入口与常用辅助命令。自动化脚本见同目录 `call.py`、`get_result.py`、`init.py`。

---

## 前置条件

1. 已安装 APK（调试包路径：`utils/tdd/apk/app-debug.apk`）
2. 已授予拨号、通话记录、录音、相机等权限（可用 `init.py` 批量处理）
3. **建议设为系统默认电话应用**（否则 InCall 界面可能不可用，或回退到原生 Dialer）

```bash
# 指定设备（多机时必加 -s）
export SERIAL=<device_id>

# 安装
adb -s $SERIAL install -r utils/tdd/apk/app-debug.apk

# 设为默认 Dialer（Android 10+）
adb -s $SERIAL shell cmd role add-role-holder android.app.role.DIALER com.android.transsion.tdd.autotest

# 拉起主界面（申请权限、采集 SIM 入库）
adb -s $SERIAL shell am start -n com.android.transsion.tdd.autotest/.MainActivity
```

---

## 测试入口一览

| 入口 | Activity | 用途 |
|------|----------|------|
| 自动拨号测试 | `.call.autodial.AutoDialActivity` | 主测试：拨号 → 通话记录校验 → Pass/Fail |
| 通过页（调试） | `.PassActivity` | 仅展示通过结果 |
| 失败页（调试） | `.FailActivity` | 仅展示失败结果 |
| 主界面（初始化） | `.MainActivity` | 权限、默认 Dialer、SIM 信息采集 |
| 联系人测试 | `.contacts.ContactActivity` | 新增 / 查询 / 更新 / 删除联系人 → Pass/Fail |
| 网页访问测试 | `.web.WebActivity` | 打开 URL → 加载成功/失败 → Pass/Fail |
| 发送短彩信 | `.message.SendMessageActivity` | 指定卡槽/号码/类型发送 → Pass/Fail |
| 接收短彩信 | `.message.ReceiveMessageActivity` | 前台等待收信 → Pass；60s 超时 → Fail |

`InCallActivity` **未导出**，由系统在通话时通过 `TddInCallService` 拉起，**不可** adb 直接启动。

---

## 1. 自动拨号测试（AUTO_DIAL）

### 基本格式

```bash
adb shell am start \
  -a com.android.transsion.tdd.autotest.action.AUTO_DIAL \
  -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity \
  [--es slot_id <卡槽>] \
  --es number <号码> \
  --ei call_type <0~4>
```

多设备：

```bash
adb -s <device_id> shell am start \
  -a com.android.transsion.tdd.autotest.action.AUTO_DIAL \
  -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity \
  --es slot_id 0 --es number 10086 --ei call_type 2
```

等待启动完成（脚本使用 `-W`）：

```bash
adb -s <device_id> shell am start -W \
  -a com.android.transsion.tdd.autotest.action.AUTO_DIAL \
  -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity \
  --es slot_id 0 --es number 10086 --ei call_type 2
```

### 参数

| 参数 | adb 写法 | 必填 | 说明 |
|------|----------|------|------|
| `slot_id` | `--es slot_id <值>` | 否 | SIM 卡槽：`0`=卡1，`1`=卡2。不传或空字符串表示系统选卡 |
| `number` | `--es number <值>` | **是** | 拨打号码。USSD（`call_type=3`）可写 `*#06#` 等 |
| `call_type` | `--ei call_type <0~4>` | **是** | 通话类型，见下表 |

### `call_type` 取值

| 值 | 含义 | 拨号方式 |
|----|------|----------|
| `0` | 紧急拨号 | `TelecomManager.placeCall()` |
| `1` | 视频通话 | `TelecomManager.placeCall()` + 双向视频 |
| `2` | 语音通话 | `TelecomManager.placeCall()` + 音频 |
| `3` | USSD | `Intent.ACTION_CALL`（`tel:`） |
| `4` | 语音/视频来回切换 | 先语音 `placeCall()`，InCall 内自动升/降视频后挂断 |

### 判定逻辑（AutoDial 自动跳转）

- **非 USSD**：每 3s 轮询 CallLog，最多 30 次（约 90s）
  - 匹配本次去电且 `duration > 0` → **PassActivity**
  - 匹配且 `duration == 0` → **FailActivity**
  - 超时无记录 → **FailActivity**
- **`call_type=4`**：CallLog 通过后还需 InCall 内切换流程成功（额外等待约 3s），否则 Fail
- **`call_type=3`（USSD）**：仅发起拨号，**不**自动跳转 Pass/Fail

结果页文案格式：`拨号：<slot> <number> <通话类型>`（示例：`拨号：0 10086 语音通话`）

### 示例命令

**卡1 视频**

```bash
adb shell am start \
  -a com.android.transsion.tdd.autotest.action.AUTO_DIAL \
  -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity \
  --es slot_id 0 --es number 10086 --ei call_type 1
```

**卡2 语音**

```bash
adb shell am start \
  -a com.android.transsion.tdd.autotest.action.AUTO_DIAL \
  -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity \
  --es slot_id 1 --es number 10010 --ei call_type 2
```

**不指定 SIM**

```bash
adb shell am start \
  -a com.android.transsion.tdd.autotest.action.AUTO_DIAL \
  -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity \
  --es number 13800138000 --ei call_type 2
```

**紧急拨号（号码按当地规范替换）**

```bash
adb shell am start \
  -a com.android.transsion.tdd.autotest.action.AUTO_DIAL \
  -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity \
  --es number 112 --ei call_type 0
```

**USSD**

```bash
adb shell am start \
  -a com.android.transsion.tdd.autotest.action.AUTO_DIAL \
  -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity \
  --es slot_id 0 --es number "*#06#" --ei call_type 3
```

**语音/视频来回切换（call_type=4）**

```bash
adb shell am start \
  -a com.android.transsion.tdd.autotest.action.AUTO_DIAL \
  -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity \
  --es slot_id 0 --es number 10086 --ei call_type 4
```

### 一行命令（便于复制）

```bash
# 视频 / 卡1
adb shell am start -a com.android.transsion.tdd.autotest.action.AUTO_DIAL -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity --es slot_id 0 --es number 10086 --ei call_type 1

# 语音 / 不指定卡
adb shell am start -a com.android.transsion.tdd.autotest.action.AUTO_DIAL -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity --es number 10010 --ei call_type 2

# 语音视频切换
adb shell am start -a com.android.transsion.tdd.autotest.action.AUTO_DIAL -n com.android.transsion.tdd.autotest/.call.autodial.AutoDialActivity --es slot_id 0 --es number 10086 --ei call_type 4
```

### 测试前清理进程

Python 封装（`call.py` / `message.py` / `web.py`）**不再**在拉起 Activity 前执行 `force-stop`；`contact.py` 在执行联系人操作前仍会 `force-stop` 以避免残留状态。若需手动清理：

```bash
adb -s <device_id> shell am force-stop com.android.transsion.tdd.autotest
```

---

## 2. 测试结果页（Pass / Fail）

一般由 `AutoDialActivity` 自动跳转；也可 adb 单独拉起用于 UI 调试。

**通过**

```bash
adb shell am start -n com.android.transsion.tdd.autotest/.PassActivity \
  --es test_content "视频通话接通"
```

**失败**

```bash
adb shell am start -n com.android.transsion.tdd.autotest/.FailActivity \
  --es test_content "视频通话：对端无画面"
```

| 参数 | adb 写法 | 必填 | 说明 |
|------|----------|------|------|
| `test_content` | `--es test_content "<文案>"` | 否 | 结果页显示的测试内容；为空时显示默认占位文案 |

### 轮询当前结果页（与 `get_result.py` 一致）

```bash
adb -s <device_id> shell dumpsys activity activities | findstr topResumedActivity
```

- 含 `com.android.transsion.tdd.autotest/.PassActivity` → 通过
- 含 `com.android.transsion.tdd.autotest/.FailActivity` → 失败

---

## 3. 联系人测试（ContactActivity）

需 `READ_CONTACTS` / `WRITE_CONTACTS`（可 `pm grant` 或界面内申请）。

```bash
# 新增到手机联系人
adb shell am start -W -n com.android.transsion.tdd.autotest/.contacts.ContactActivity \
  --es operation add --es storage phone \
  --es contact_name "张三" --es contact_number "13800138000"

# 查询 SIM1 联系人
adb shell am start -W -n com.android.transsion.tdd.autotest/.contacts.ContactActivity \
  --es operation query --es storage sim1 \
  --es contact_name "SIM张三" --es contact_number "13800138001"

# 更新（改号+改名；SIM 按匹配到的 recordNumber 更新）
adb shell am start -W -n com.android.transsion.tdd.autotest/.contacts.ContactActivity \
  --es operation update --es storage sim1 \
  --es contact_name "SIM张三" --es contact_number "13800138001" \
  --es new_contact_name "SIM张三-新" --es new_contact_number "13900139001"

# 删除（可不传 contact_name；SIM 按匹配到的 recordNumber 删除）
adb shell am start -W -n com.android.transsion.tdd.autotest/.contacts.ContactActivity \
  --es operation delete --es storage sim1 \
  --es contact_number "13900139001" --es contact_name "SIM张三-新"
```

| 参数 | adb 写法 | 必填 | 说明 |
|------|----------|------|------|
| `operation` | `--es operation add\|query\|update\|delete` | 是 | CRUD 操作 |
| `storage` | `--es storage phone\|sim1\|sim2` | 是 | `phone`/`手机`、`sim1`/`卡1`、`sim2`/`卡2` |
| `contact_name` | `--es contact_name "<姓名>"` | add/query/update 必填；delete 可选 | 匹配/写入用姓名 |
| `contact_number` | `--es contact_number "<号码>"` | 是 | 匹配/写入用号码 |
| `new_contact_name` | `--es new_contact_name "<新姓名>"` | update 可选 | 更新后的姓名 |
| `new_contact_number` | `--es new_contact_number "<新号码>"` | update 可选 | 更新后的号码（update 时 `new_*` 至少传一个） |

执行完成后自动跳转 **PassActivity**（成功）或 **FailActivity**（失败），可用 `get_result.py` 轮询。

---

## 4. 网页访问测试（WebActivity）

```bash
adb shell am start -n com.android.transsion.tdd.autotest/.web.WebActivity \
  --es url "https://www.baidu.com"
```

| 参数 | adb 写法 | 必填 | 说明 |
|------|----------|------|------|
| `url` | `--es url "<地址>"` | 是 | 网页 URL（可简写 `web_url`；无协议时默认 `https://`） |
| `force_refresh` | `--ez force_refresh true\|false` | 否 | 是否强制刷新，默认 `true` |
| `timeout_seconds` | `--ei timeout_seconds 60` | 否 | 加载超时秒数，默认 60 |

主框架 `onPageFinished` 且无 HTTP/网络错误 → **PassActivity**；超时、DNS/SSL/HTTP 错误 → **FailActivity**。

---

## 5. 短彩信测试（SendMessageActivity / ReceiveMessageActivity）

需 `SEND_SMS`、`RECEIVE_SMS`、`READ_SMS`、`WRITE_SMS`、`RECEIVE_MMS` 等权限；**接收**与 **MMS 写库** 建议将本 APK 设为 **默认短信应用**（`RoleManager.ROLE_SMS`）。Activity 内可点按钮申请权限与默认应用角色，也可用 adb 预授：

```bash
adb shell pm grant com.android.transsion.tdd.autotest android.permission.SEND_SMS
adb shell pm grant com.android.transsion.tdd.autotest android.permission.RECEIVE_SMS
adb shell pm grant com.android.transsion.tdd.autotest android.permission.READ_SMS
adb shell pm grant com.android.transsion.tdd.autotest android.permission.WRITE_SMS
adb shell pm grant com.android.transsion.tdd.autotest android.permission.RECEIVE_MMS

# 设为默认短信应用（Android 10+，接收 SMS_DELIVER 需要）
adb shell cmd role add-role-holder android.app.role.SMS com.android.transsion.tdd.autotest
```

### 5.1 发送（SendMessageActivity）

```bash
# 卡1 发短信
adb shell am start -n com.android.transsion.tdd.autotest/.message.SendMessageActivity \
  --es sim sim1 \
  --es number 10086 \
  --es message_type sms \
  --es content "测试短信"

# 卡2 发彩信（附件为本 APK 图标，content 可省略）
adb shell am start -n com.android.transsion.tdd.autotest/.message.SendMessageActivity \
  --es sim sim2 \
  --es number 13800138000 \
  --es message_type mms
```

| 参数 | adb 写法 | 必填 | 说明 |
|------|----------|------|------|
| `sim` | `--es sim sim1\|sim2` | 是 | 发送卡槽（别名 `sim_slot`；`sim1`/`卡1`/`0`，`sim2`/`卡2`/`2`） |
| `number` | `--es number "<号码>"` | 是 | 接收号码（别名 `dest_number`） |
| `message_type` | `--es message_type sms\|mms` | 是 | `sms`/`短信` 或 `mms`/`彩信` |
| `content` | `--es content "<正文>"` | 否 | 短信正文；彩信可选（彩信默认发送应用图标） |

发送成功 → **PassActivity**；失败（权限不足、无 SIM、发送回调失败等）→ **FailActivity**。

### 5.2 接收（ReceiveMessageActivity）

```bash
adb shell am start -n com.android.transsion.tdd.autotest/.message.ReceiveMessageActivity \
  --ei timeout_seconds 60
```

| 参数 | adb 写法 | 必填 | 说明 |
|------|----------|------|------|
| `timeout_seconds` | `--ei timeout_seconds 60` | 否 | 等待超时秒数，默认 60；超时跳转 **FailActivity** |

仅当 **本 Activity 在前台**（`onResume` 后监听）时收到短信或彩信才会跳转 **PassActivity**；**60 秒内未收到**则跳转 **FailActivity**。若未启动接收页，系统仍会投递到默认短信应用，但 **不会** 自动打开 Pass/Fail。

Python `run_receive_message_test()` 通过 `get_result.wait_test_result()` 轮询 `PassActivity` / `FailActivity`（轮询超时 90s，与发送等用例一致）；APK 内接收等待默认 60s 超时进 Fail。

**连续互发间隔**：`case/str4_tdd`、`case/week_tdd` 中若连续多次 `exchange_sms` / `exchange_mms`（中间无其它 UI 操作），两次之间应调用 `wait_message_exchange_interval()`（默认 2s，见 `MESSAGE_EXCHANGE_INTERVAL_SECONDS`）。

---

## 6. 主界面（初始化，非用例本身）

```bash
adb shell am start -n com.android.transsion.tdd.autotest/.MainActivity
```

作用：权限状态展示、申请默认 Dialer、启动后自动采集各卡槽 SIM 信息写入 `tdd_autotest.db`。

### 读取 SIM 数据库（调试用）

```bash
adb shell run-as com.android.transsion.tdd.autotest sqlite3 databases/tdd_autotest.db \
  "SELECT slot_index,subscription_id,carrier_name,phone_number,display_name,country_iso FROM sim_info ORDER BY slot_index;"
```

---

## 7. Python 封装

| 模块 | 函数 | 说明 |
|------|------|------|
| `init.py` | `init_device(device_id)` | 安装 APK、授权、设默认 Dialer、拉主界面、读 SIM 库与 `camera_count`（dumpsys media.camera） |
| `call.py` | `start_auto_dial(device_id, sim_slot, call_type, number)` | 等价于 AUTO_DIAL adb |
| `contact.py` | `start_contact_test(...)` / `run_contact_test(...)` | 等价于 ContactActivity adb（拉起前 `force-stop`） |
| `contact.py` | `add_contact` / `query_contact` / `update_contact` / `delete_contact` | 新增 / 查询 / 更新 / 删除联系人并等待 Pass/Fail |
| `web.py` | `start_web_test` / `run_web_test` | 等价于 WebActivity adb |
| `message.py` | `start_send_message_test` / `run_send_message_test` | 等价于 SendMessageActivity adb |
| `message.py` | `start_receive_message_test` / `run_receive_message_test` | 等价于 ReceiveMessageActivity adb；`wait_test_result` 轮询 Pass/Fail（90s） |
| `message.py` | `send_sms` / `send_mms` | 发送短彩信并等待 Pass/Fail |
| `message.py` | `exchange_sms` / `exchange_mms` / `exchange_sms_dut_to_aux` 等 | 接收端监听 + 发送端互发 |
| `message.py` | `wait_message_exchange_interval()` | 连续短彩信互发间隔（2s） |
| `message.py` | `grant_sms_permissions` / `set_default_sms_app` | adb 授权与设默认短信应用 |
| `get_result.py` | `wait_test_result(device_id)` | 轮询 Pass/Fail Activity，超时约 90s |

`call.py` 中 `sim_slot` 约定：`0`/`卡1`/`SIM1` → 卡槽 0；`1`/`2`/`卡2`/`SIM2` → 卡槽 1。

---

## 8. 相关说明

- 来电接听、通话中视频升级等由应用内 `TddInCallService` / `InCallActivity` 处理，**无**单独 adb 入口。
- 更详细的通话模块设计见：`test_app/app/src/main/java/com/android/transsion/tdd/autotest/call/readme.md`
