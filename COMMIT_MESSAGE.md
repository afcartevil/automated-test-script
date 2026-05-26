feat(tahp): AI 适配调试界面完整实现

## 功能概述
实现 TAHP 平台的 AI 适配调试界面，支持 9 个适配域的动态前置条件表单管理。

## 关键特性

### 前端 (Frontend)
- **AdaptDebugView.vue** - 完整的适配调试主页面
  - 左侧导航：9 个适配域 (TP/振动/指纹/音频/充电/通信/内核/SCP传感器/AI按键) + 进度统计面板
  - 上方上下文栏：项目信息、SoC、Kernel版本、升级路径展示与编辑
  - 中央主内容区：动态表单、关联 Skills 清单、操作按钮
  - 右侧统计面板：总进度、任务历史、实时进度追踪
  - 暗色科技风格，与 TAHP 设计系统一致

- **动态表单系统**
  - 9 个适配域各自定义专属的前置条件字段
  - 字段类型支持：text / number / select / textarea
  - 实时完整性检验（必填字段计数）
  - 对应域只显示该域的前置条件

- **路由集成**
  - 新增路由 `/tahp/adapt-debug`
  - 侧边栏导航项指向新路由
  - 集成现有导航架构

### 前端 API (Frontend API)
- **api/tahp/adapt.ts** - 适配调试 API 接口
  - `launchAdaptTask()` - 启动适配任务
  - `getAdaptTaskStatus()` - 查询任务状态
  - `saveAdaptConfig()` - 保存配置
  - `getAdaptConfig()` - 恢复配置

### 后端 (Backend)
- **routes/tahp/adapt.ts** - 适配调试路由
  - `POST /api/tahp/adapt/launch` - 启动任务
  - `GET /api/tahp/adapt/status/:taskId` - 查询状态
  - `POST /api/tahp/adapt/config/save` - 保存配置
  - `GET /api/tahp/adapt/config/get` - 读取配置
  
- 与 MCP 工具集成 (tahp_execute / tahp_status)
- SafeFileStore 安全存储配置文件

### 路由聚合
- 在 routes/tahp/index.ts 中注册适配路由

## 前置条件定义

### 9 个适配域覆盖所有前置条件
1. **TP触摸屏** - IC型号、接口、GPIO、DTS、DWS三路、ko表
2. **振动马达** - 马达类型、IC、I2C、GPIO、固件目录
3. **指纹** - 架构类型、IC、SoC、参考项目
4. **音频** - Codec型号、I2C地址、拓扑
5. **充电** - IC型号、拓扑、Gauge、PD
6. **通信Modem** - 平台、RF参数、运营商
7. **内核CPU** - CPU型号、LK版本、KDM版本
8. **SCP传感器** - 传感器型号、接口、通道
9. **AI按键** - 按键映射、HAL版本、GPIO

## UI/UX 设计
- 暗色科技主题（#0d1117 背景，#388bfd 主色调）
- 三列布局：左导航 (200px) | 中主内容 (flex:1) | 右统计面板 (240px)
- 状态指示：活跃(蓝脉冲) / 完成(绿点) / 待处理(灰点)
- 流畅的过渡动画和交互反馈

## 后续扩展点
- [ ] 集成 AI 对话调试（跳转至 ChatView）
- [ ] 实现任务执行流（tahp_execute 集成）
- [ ] 前置条件验证规则（字段依赖、格式检查）
- [ ] 历史记录完整化（本地存储）
- [ ] 导出/导入配置功能

## 变更文件清单
```
packages/client/src/views/tahp/AdaptDebugView.vue (NEW - 300+ 行)
packages/client/src/api/tahp/adapt.ts (NEW)
packages/client/src/router/index.ts (修改 - 添加路由)
packages/client/src/components/layout/AppSidebar.vue (修改 - 更新导航)
packages/server/src/routes/tahp/adapt.ts (NEW - 100+ 行)
packages/server/src/routes/tahp/index.ts (修改 - 注册路由)
```

## 技术栈
- Vue 3 + TypeScript + Composition API
- Tailwind CSS / SCSS (TAHP 变量)
- NaiveUI 组件库
- Lucide Vue Icons
- Koa 2 (后端)
