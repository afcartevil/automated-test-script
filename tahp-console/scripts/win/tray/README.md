# EasyAdapter 托盘图标

托盘与浏览器 Tab 使用同一套图标（紫底 **EA**），源文件为 `packages/client/public/favicon.svg`。

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
