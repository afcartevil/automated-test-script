# Phase 1 部署 — 快速参考卡

**部署时间**: 15 分钟 | **风险等级**: 低 ✅ | **回滚时间**: < 2 分钟

---

## 🚀 3 步快速部署

### 1️⃣ 备份（1 分钟）
```bash
cd E:\TAHP\tahp\tahp-console
git status  # 查看当前状态
```

### 2️⃣ 重启（5 分钟）
```bash
# 开发模式
npm run dev

# 或生产模式
npm run build && npm run start
```

### 3️⃣ 验证（2 分钟）
```bash
# 测试后端
curl http://localhost:8650/api/tahp/knowledge/stats

# 打开前端
浏览器访问: http://localhost:8650/tahp/knowledge-management
```

---

## ✅ 部署验证清单（5 分钟）

- [ ] 后端 API `/api/tahp/knowledge/stats` 返回 200
- [ ] 前端界面可访问（无 404）
- [ ] 4 个 Tab 都可显示
  - [ ] 📊 仪表板
  - [ ] 📚 知识条目
  - [ ] 🚀 Skill 草稿
  - [ ] 📈 统计分析
- [ ] 创建测试知识条目成功
- [ ] 刷新页面后数据持久化

---

## 📋 测试知识条目（一键测试）

```bash
# 创建测试条目
curl -X POST http://localhost:8650/api/tahp/knowledge/entries \
  -H "Content-Type: application/json" \
  -d '{
    "content": "RIL通话丢失故障修复指南",
    "category": "错误模式",
    "module": "telephony",
    "func_type": "bug_analysis",
    "keywords": ["RIL", "通话", "丢失"],
    "confidence_score": 0.85,
    "source_file": "ReleaseNote_v13.2.pdf"
  }'

# 查询测试条目
curl http://localhost:8650/api/tahp/knowledge/entries

# 预期: { "success": true, "data": { "total": 1, "entries": [...] } }
```

---

## 🔧 常见问题 Quick Fix

| 问题 | 快速修复 |
|------|---------|
| 前端找不到 | 清缓存 + 刷新 + 重启 dev 服务 |
| 后端 404 | 检查 tahp/index.ts 中 tahpKnowledgeRoutes 导入 |
| API 调用失败 | 查看浏览器 F12 → Network 标签 |
| 数据未保存 | 检查 knowledge-base/.kb-data/ 目录权限 |
| 服务占用端口 | 更改 PORT 环境变量或杀死进程 |

---

## 📊 核心数据模型

### 知识条目 (KnowledgeEntry)
```json
{
  "id": "kb-abc123",
  "content": "知识内容",           // 必填
  "category": "错误模式",         // 必填
  "module": "telephony",          // 必填
  "func_type": "bug_analysis",    // 必填
  "keywords": ["关键词"],
  "confidence_score": 0.8,        // 0-1
  "status": "pending_review",     // active/archived
  "created_at": "2026-05-27T..."
}
```

### 支持的模块 (module)
- `telephony` - 通信
- `kernel-driver` - 驱动
- `power-mgmt` - 功耗温升
- `shared` - 共享
- `custom` - 自定义

### 支持的业务类型 (func_type)
- `bug_analysis` - Bug 分析
- `code_adaptation` - 代码适配
- `version_adaptation` - 版本适配
- `carrier_porting` - 运营商移植
- `ai_self_check` - AI 自检

---

## 🎯 部署成功的标志

✅ 后端 API 可访问（所有 11 个 endpoints）  
✅ 前端界面可打开（4 个 Tab）  
✅ 可创建知识条目  
✅ 数据持久化（刷新后存在）  
✅ 无浏览器错误（F12 控制台）  
✅ 无后端错误（logs/server.log）  

---

## 📁 关键文件位置

| 文件 | 路径 |
|------|------|
| 后端 API | `packages/server/src/routes/tahp/knowledge.ts` |
| 前端 UI | `packages/client/src/views/tahp/KnowledgeManagementView.vue` |
| 路由注册 | `packages/server/src/routes/tahp/index.ts` |
| 知识库数据 | `knowledge-base/.kb-data/entries/` |
| 后端日志 | `tahp-console/logs/server.log` |

---

## 🔄 回滚方案（如需要）

```bash
# 完全回滚（< 2 分钟）
cd E:\TAHP\tahp\tahp-console
git checkout packages/server/src/routes/tahp/knowledge.ts
git checkout packages/client/src/views/tahp/KnowledgeManagementView.vue
npm run dev  # 重启

# 数据备份恢复
cp -r knowledge-base/.kb-data.backup/ knowledge-base/.kb-data
```

---

## 📞 部署支持

**部署文档**: `DEPLOYMENT-GUIDE.md`（完整指南）  
**用户指南**: `00-START-HERE.md`（快速开始）  
**问题排查**: 见本卡片"常见问题"或完整指南

---

## 预计完成时间表

| 阶段 | 时间 | 检查点 |
|------|------|--------|
| 备份 | 1 min | `git status` ✅ |
| 重启 | 5 min | 服务启动 ✅ |
| 验证后端 | 2 min | API 返回 200 ✅ |
| 验证前端 | 2 min | UI 界面打开 ✅ |
| 功能测试 | 5 min | 创建/查询成功 ✅ |
| **总计** | **15 min** | **部署完成** ✅ |

---

**准备好部署了！按照上述步骤执行，预计 15 分钟内完成。** 🚀

有问题？查看 DEPLOYMENT-GUIDE.md 的"常见部署问题"部分。
