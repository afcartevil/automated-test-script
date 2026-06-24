# 频繁上报类问题分析流程

## 适用场景
某个消息/事件频繁上报导致功耗异常、性能下降或日志刷屏（如 MIPC_STK_PAC_IND、SIM 状态变化等）

---

## 6步分析流程

### 1. 统计频率特征
**目标：** 量化"频繁"程度，识别规律

**操作：**
- 统计时间窗内次数（如 10分钟 50次）
- 计算上报间隔
- 识别模式：周期性（固定间隔）/ 突发性（短时密集）/ 持续性（长时间不停）

**日志：** AP Log / radio_log

---

### 2. 解析上报内容
**目标：** 理解上报的是什么

**操作：**
- 解析消息结构（TLV/MIPC 格式）
- 提取关键字段：消息类型、Device IDs、数据内容
- 对比多次上报：内容相同（重复）/ 内容变化（不同请求）

**日志：** AP Log / radio_log

**示例：**
```
MIPC_STK_PAC_IND {
    PAC_TYPE = 0x13 (SEND SHORT MESSAGE)
    Device IDs: UICC (0x81) → Network (0x83)
    内容：6MMCB/:5BsQgB3.WDJ.18.1
}
```

---

### 3. 追溯上报来源
**目标：** 确定谁发起的

**判断依据：**
- **Device IDs 方向**：
  - `UICC → Terminal/Network` → SIM 卡主动
  - `Terminal → UICC/Network` → AP/Modem 主动
  - `Network → Terminal` → 网络侧主动
- **触发条件**：
  - 有用户操作 → 可能是正常响应
  - 无触发条件 → 可能是自主行为

**日志：** AP Log / radio_log

---

### 4. 分析处理链路
**目标：** 理解消息流转

**追踪路径：**
```
MIPC_STK_PAC_IND 上报
    ↓
MtkCatService 接收
    ↓
handleStkInd 处理
    ↓
Terminal Response / 后续动作
```

**关键日志：**
- `MIPC_STK_PAC_IND`
- `MtkCatService`
- `handleStkInd`
- `Terminal Response`

**日志：** AP Log / radio_log

---

### 5. 判断根因类型
**目标：** 软件问题 vs 外部因素

| 特征 | 软件问题 | 外部因素 |
|------|---------|---------|
| Device IDs | Terminal → | UICC/Network → |
| 触发条件 | 有代码逻辑 | 无软件触发 |
| 换卡测试 | 问题依然 | 问题消失 |
| 换设备测试 | 问题消失 | 问题依然 |

---

### 6. 输出结论
**包含：**
1. **问题分类**：软件问题 / 外部因素（SIM卡/网络）
2. **根本原因**：一句话 + 关键证据
3. **影响范围**：功耗/性能/用户体验
4. **解决建议**：
   - 软件问题：修改代码、调整配置
   - 外部因素：更换 SIM 卡、联系运营商、软件侧屏蔽

---

## 关键日志搜索

**AP Log / radio_log：**
- `MIPC_STK_PAC_IND` - STK 命令上报
- `MtkCatService` - STK 服务
- `handleStkInd` - 处理函数
- `Terminal Response` - 终端响应
- `Proactive Command` - 主动命令

---

## 典型案例：STK_PAC_IND 频繁上报

**现象：** 周期性（12秒）上报 SEND SHORT MESSAGE

**分析：**
1. 频率：每 12 秒一次，周期性
2. 内容：固定（设备型号、ID、版本号）
3. 来源：Device IDs = UICC → Network（SIM 卡主动）
4. 链路：MIPC → MtkCatService → 正常处理
5. 根因：SIM 卡自主行为（Proactive Command）

**结论：** 外部因素，非软件问题

**建议：** 更换 SIM 卡 / 软件侧可考虑限频或过滤
