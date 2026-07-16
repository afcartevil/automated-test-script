## GKI Patch Tool In EA

该目录是 `EasyAdapter` 内维护的 `GKI Patch Tool` 仓内版本。

### 目录定位
- 工具根目录：`tools/gki-patch-tool`
- `EA` 的 `GKI Patch` 页面与后端默认调用这里的脚本和配置
- 不再依赖研发个人机器上的外部 GKI Patch Tool 路径

### 两种启动方式

#### 1. 独立运行（Standalone）
不启动 EasyAdapter，单独使用 GKI Patch Tool：

```bat
REM Windows
run_windows.bat

REM Linux
./run_linux.sh
```

- 使用 `run_windows.bat` / `run_linux.sh` 完整流程（安装依赖、构建前端、启动服务、打开浏览器）
- 默认监听 `0.0.0.0:8000`，数据写在工具目录 `web_app/data/`
- 适合只做 GKI patch 分析、不依赖 EA 的场景

#### 2. EasyAdapter 集成运行（Integrated）
随 EasyAdapter 一并启动，无需再单独拉起：

- `run_adapter.bat` 或 `npm run start` 启动 EA 时，tahp-console 会自动拉起 GKI Patch 服务
- 默认监听 `127.0.0.1:8651`，运行数据写在 `tools/gki-patch-tool/`（与独立模式相同目录）
- 点击 EA 导航「GKI Patch」直接进入页面，无需等待启动
- 关闭 EA 时 GKI Patch 子进程一并回收

### 使用约定
- 默认配置来源：`gki-patch-tool.yaml`
- 集成模式启动：`tahp-console` 以 `python -m uvicorn web_app.app:app` 子进程拉起
- 独立模式启动：`run_windows.bat` / `run_linux.sh` 前台运行同一 uvicorn 命令
- 前端构建产物：`frontend/dist`（集成模式由 `npm run setup:gki-patch` 在 EA 启动前检查/构建）

### 数据库路径（重要）

| 模式 | `gki_patch.db` 实际路径 |
|------|-------------------------|
| 独立运行 | `tools/gki-patch-tool/web_app/data/gki_patch.db` |
| EA 集成 | `tools/gki-patch-tool/web_app/data/gki_patch.db`（与独立模式相同） |

查看当前实际路径：请求 `/api/tahp/gki-patch/status`，看返回的 `dbPath`。

### 环境变量

| 变量 | 说明 |
|------|------|
| `GKI_PATCH_TOOL_ROOT` | 覆盖工具根目录 |
| `GKI_PATCH_PORT` | 集成模式端口（默认 `8651`） |
| `GKI_PATCH_DATA_DIR` | 覆盖运行时数据根目录（默认 `tools/gki-patch-tool`） |
| `GKI_SETTINGS` | 配置文件路径 |
| `GKI_PATCH_AUTO_START=0` | 禁用 EA 启动时自动拉起 GKI |
| `GKI_PATCH_STANDALONE=1` | 标记独立运行模式（EA 内部使用） |
| `TAHP_SKIP_GKI_PATCH_DEPS=1` | 跳过依赖检查，同时禁用自动启动 |

独立模式另支持：`GKI_HOST`、`GKI_PORT`（默认 8000）、`GKI_VENV`、`GKI_WORKERS`

### 页面模式

| 模式 | 页面壳层 | 导航 |
|------|----------|------|
| 独立运行 | GKI 原 `App.vue` 顶部导航（首页 / 看板 / …） | 工具自带 |
| EA 集成 | EasyAdapter `GkiPatchView` 左侧导航 + iframe 嵌入 | EA 侧栏切换，GKI 仅渲染内容区（`embedded=1`） |

集成模式默认进入看板，左侧按钮：patch分析、故障诊断、patch入库、数据库、设置。

### 维护约束
- 该目录源码随 easyadapter 主仓一并维护，更新时在 `gki_patch_tool` 独立仓开发完成后，将代码手动同步到 `tools/gki-patch-tool` 并提交 easyadapter
- 不提交本机缓存、运行历史、`node_modules`、`__pycache__`、`.venv`、`.env` 等运行态文件

### EasyAdapter 启动检查
- `run_adapter.bat` 与 `npm run prestart` / `npm run predev` 会自动执行 `npm run setup:gki-patch`
- 检查项：Python venv（`.venv`）+ `requirements.txt` 依赖、前端 `frontend/dist` 构建产物
- 依赖就绪后，EA 主服务 bootstrap 阶段自动启动 GKI Patch 后端
