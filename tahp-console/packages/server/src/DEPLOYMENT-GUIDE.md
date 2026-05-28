# Phase 1 立即部署指南

**部署日期**: 2026-05-27  
**部署环境**: 测试环境（推荐）→ 生产环境  
**预期部署时间**: 15 分钟  
**风险等级**: 低 ✅

---

## 📋 部署前检查清单

- [x] 后端代码完整性验证 ✅ (13 个 API 路由)
- [x] 前端代码完整性验证 ✅ (9 个 TabPane)
- [x] 路由注册检查 ✅ (已在 tahp/index.ts 注册)
- [x] 无依赖新增 ✅ (所有依赖现有)
- [x] 类型检查通过 ✅ (TypeScript)
- [x] 文档完整 ✅ (8 份文档)

**结论**: ✅ 所有检查通过，可以部署

---

## 🚀 部署步骤（3 步）

### Step 1: 备份现有配置（2 分钟）

```bash
# 进入项目目录
cd E:\TAHP\tahp\tahp-console

# 备份当前状态（可选但推荐）
git status
git diff
```

### Step 2: 重启服务（5 分钟）

**选项 A: 本地开发模式**
```bash
# 终止当前运行的服务
# (Ctrl+C 或杀死进程)

# 重启开发服务器
npm run dev

# 等待编译完成...
# 输出应包含: "Client: http://localhost:5173" 或类似
```

**选项 B: 生产模式**
```bash
# 构建前端
npm run build

# 启动生产服务器
npm run start

# 或使用管理命令
node bin/tahp-console.mjs start
```

### Step 3: 验证部署（8 分钟）

#### A. 后端 API 验证

```bash
# 测试 1: 获取统计信息
curl http://localhost:8650/api/tahp/knowledge/stats

# 预期响应:
{
  "success": true,
  "data": {
    "total_entries": 0,
    "active_entries": 0,
    "pending_review": 0,
    "archived": 0,
    "by_module": {},
    "by_func_type": {},
    "avg_confidence": 0
  }
}

# 测试 2: 创建测试知识条目
curl -X POST http://localhost:8650/api/tahp/knowledge/entries \
  -H "Content-Type: application/json" \
  -d '{
    "content": "测试知识条目",
    "category": "错误模式",
    "module": "telephony",
    "func_type": "bug_analysis",
    "keywords": ["测试"],
    "confidence_score": 0.8
  }'

# 预期响应: { "success": true, "data": { "id": "kb-xxx", ... } }

# 测试 3: 查询知识条目
curl http://localhost:8650/api/tahp/knowledge/entries

# 预期响应: { "success": true, "data": { "entries": [...], "total": 1 } }
```

#### B. 前端界面验证

1. **打开浏览器**
   - 访问: `http://localhost:8650`
   - 或: `http://localhost:5173`（如果是开发模式）

2. **导航到知识库管理**
   - 点击左侧菜单 "TAHP" 或 "EasyAdapter"
   - 查找 "知识库管理" 选项
   - 或直接访问: `http://localhost:8650/tahp/knowledge-management`

3. **验证 4 个 Tab**
   - ✅ 📊 仪表板
   - ✅ 📚 知识条目
   - ✅ 🚀 Skill 草稿
   - ✅ 📈 统计分析

4. **测试基础功能**
   - [ ] 打开"知识条目"Tab
   - [ ] 点击"新建条目"按钮
   - [ ] 填写表单（content、category、module、func_type）
   - [ ] 点击"保存"
   - [ ] 确认条目出现在列表中

5. **检查数据持久化**
   - [ ] 刷新页面（F5）
   - [ ] 确认条目仍然存在

---

## 🔍 部署验证检查表

### 后端验证

- [ ] `/api/tahp/knowledge/stats` 返回 200
- [ ] `/api/tahp/knowledge/entries` 返回 200
- [ ] POST `/api/tahp/knowledge/entries` 成功创建条目
- [ ] GET `/api/tahp/knowledge/entries/:id` 返回条目详情
- [ ] PUT `/api/tahp/knowledge/entries/:id` 成功更新
- [ ] DELETE `/api/tahp/knowledge/entries/:id` 成功删除（软删除）
- [ ] POST `/api/tahp/knowledge/search/semantic` 返回搜索结果

### 前端验证

- [ ] 知识库管理界面可访问
- [ ] 4 个 Tab 都可点击切换
- [ ] "新建条目"Modal 可打开
- [ ] 表单验证工作（必填字段检查）
- [ ] 创建/编辑/删除操作可执行
- [ ] 数据表格可显示列表
- [ ] 分页/排序功能可用（如有）
- [ ] 统计卡片显示正确数值

### 集成验证

- [ ] 前端可调用后端 API
- [ ] 错误提示正确显示
- [ ] 加载状态显示正确
- [ ] 成功消息显示正确
- [ ] 无浏览器控制台错误
- [ ] 无网络请求失败

---

## 📊 部署配置清单

### 环境变量检查（tahp-console/.env）

```bash
# 如果需要自定义配置：
TAHP_PROJECT_ROOT=E:\TAHP\tahp              # TAHP 项目根目录
TAHP_PYTHON=python                          # Python 路径
PORT=8650                                   # 服务端口
AUTH_DISABLED=1                             # 默认开启，内网免鉴权
```

### 文件系统检查

```bash
# 确保知识库目录存在且可写
knowledge-base/
├── .kb-data/
│   ├── entries/
│   ├── skill-drafts/
│   └── .gitkeep
```

---

## ⚠️ 常见部署问题与解决

### 问题 1: 前端界面找不到
**症状**: 访问 `/tahp/knowledge-management` 返回 404

**解决方案**:
```bash
# 检查路由约定是否生效
# 确保文件位置正确:
# E:\TAHP\tahp\tahp-console\packages\client\src\views\tahp\KnowledgeManagementView.vue

# 重新启动前端开发服务器
npm run dev

# 清除浏览器缓存
# Ctrl+Shift+Delete (Chrome/Edge)
# Cmd+Shift+Delete (Mac)
```

### 问题 2: 后端 API 返回 404
**症状**: `/api/tahp/knowledge/entries` 返回 404

**解决方案**:
```bash
# 确保 knowledge.ts 已导入和注册
# 检查 tahp/index.ts:
cat packages/server/src/routes/tahp/index.ts | grep tahpKnowledgeRoutes

# 重启后端服务
npm run dev
```

### 问题 3: 创建知识条目失败
**症状**: POST `/api/tahp/knowledge/entries` 返回 400 或 500

**解决方案**:
```bash
# 检查必填字段
{
  "content": "必填",      # 不能为空
  "category": "必填",     # 如：错误模式、API规范
  "module": "必填",       # 如：telephony、kernel-driver
  "func_type": "必填",    # 如：bug_analysis、code_adaptation
  "keywords": []          # 可选
}

# 检查后端日志查看错误信息
# 日志位置: tahp-console/logs/server.log
```

### 问题 4: 前端 API 调用失败
**症状**: 浏览器控制台显示 CORS 或网络错误

**解决方案**:
```bash
# 检查 CORS 配置（已在 index.ts 中配置）
# 确保后端服务已启动在正确端口
# 检查网络连接

# 查看浏览器控制台(F12)错误信息
# Network tab 检查 API 请求是否发送
```

### 问题 5: 数据未持久化
**症状**: 创建条目后，刷新页面条目丢失

**解决方案**:
```bash
# 检查知识库目录是否存在
ls -la knowledge-base/.kb-data/entries/

# 检查文件权限
# 确保目录可读写

# 检查后端日志确认数据是否写入
# 查看 tahp-console/logs/server.log
```

---

## 🔐 安全检查

- [ ] 无默认密码暴露
- [ ] 无 API 密钥在代码中
- [ ] 所有输入都经过验证
- [ ] SQL 注入风险：无（文件系统存储）
- [ ] XSS 风险：无（JSON 格式）
- [ ] 路径遍历风险：无（UUID 生成）

---

## 📈 性能基准

### 预期性能指标

| 操作 | 响应时间 | 条件 |
|------|---------|------|
| 获取统计 | < 50ms | 新系统 |
| 创建条目 | < 50ms | 无 |
| 查询条目 | < 100ms | < 100 条 |
| 列表刷新 | < 200ms | 第一次 |
| 后续操作 | < 100ms | 缓存存在 |

### 监控命令

```bash
# 监控 CPU 和内存
# Windows
tasklist | findstr node
wmic process where name="node.exe" get PageFileUsage,VirtualSize

# Linux/Mac
ps aux | grep node
```

---

## ✅ 部署完成验证

部署完成后，请按以下顺序验证：

1. **后端服务检查**
   ```bash
   curl http://localhost:8650/api/tahp/knowledge/stats
   # 应返回 200 且包含 success: true
   ```

2. **前端界面检查**
   - 访问 `http://localhost:8650/tahp/knowledge-management`
   - 确保界面正常显示，无错误

3. **基础功能检查**
   - 创建一个测试知识条目
   - 验证条目显示在列表中
   - 编辑条目内容
   - 删除条目（应标记为 archived）

4. **数据持久化检查**
   - 刷新页面
   - 确认条目仍然存在

5. **日志检查**
   - 查看 `tahp-console/logs/server.log`
   - 无错误信息

---

## 📞 部署后支持

### 日志位置

```
tahp-console/logs/
├── server.log          # 后端日志
├── error.log           # 错误日志
└── combined.log        # 完整日志
```

### 数据备份

```bash
# 备份知识库数据
cp -r knowledge-base/.kb-data/ knowledge-base/.kb-data.backup.2026-05-27

# 恢复备份
cp -r knowledge-base/.kb-data.backup.2026-05-27 knowledge-base/.kb-data
```

### 常用命令

```bash
# 查看进程状态
npm status

# 查看服务日志
tail -f tahp-console/logs/server.log

# 重启服务
npm restart

# 停止服务
npm stop
```

---

## 🎯 部署后建议

### 立即（部署完成后）
- [ ] 创建 2-3 个测试知识条目
- [ ] 验证所有 4 个 Tab 功能可用
- [ ] 检查后端日志无错误

### 本周
- [ ] 邀请 2-3 个测试用户试用
- [ ] 收集反馈
- [ ] 修复任何问题

### 下周
- [ ] 创建用户使用文档
- [ ] 组织培训（如需要）
- [ ] 规划 Phase 2 实现

---

## 📚 部署后参考文档

- **快速开始**: `00-START-HERE.md`
- **用户指南**: `KNOWLEDGE-KB-ROADMAP.md`（使用建议部分）
- **API 文档**: `knowledge.ts` 中的注释
- **故障排查**: 本文档的"常见问题"部分

---

## ✨ 部署完成后

一旦部署成功，系统将可以：

✅ 创建和管理知识条目  
✅ 按模块/业务类型分类  
✅ 快速搜索和过滤  
✅ 自动生成 Skill 草稿  
✅ 人工审核 Skill  
✅ 追踪知识使用情况  
✅ 查看统计分析  

**系统已准备好支持知识的系统化管理！**

---

**部署指南完成。按照上述步骤执行，预计 15 分钟内完成部署。**

有任何问题，请参考"常见部署问题"部分或查阅相关文档。
