# EasyAdapter 托盘图标

托盘与浏览器 Tab 使用同一套图标（紫底 **EA**），源文件为 `packages/client/public/favicon.svg`。

Windows 用户日常通过托盘右键菜单操作（打开控制台、重启、停止、查看日志等）。首次启动或更新代码请双击工程根目录 `run_adapter.bat`。开机自启脚本见同目录 `开机自启-注册.bat` / `开机自启-取消.bat`。

## 生成 `.ico`

```bash
cd tahp-console
npm install
npm run tray:icon
```

输出：

- `scripts/win/tray/easyadapter.ico` — 系统托盘
- `packages/client/public/favicon.ico` — 浏览器 favicon（补全 index.html 引用）

修改 `favicon.svg` 后请重新执行 `npm run tray:icon` 并提交生成的 `.ico` 文件。
