# GitLab 推送说明

## 问题背景
原始 Git 仓库存在文件锁定问题（`.git/index.lock`），导致在 VM 环境中无法完成提交和推送。已在临时工作目录中成功创建提交。

## 推送步骤

### 在 Windows PowerShell 中执行：

```powershell
# 1. 进入项目目录
cd E:\TAHP\tahp

# 2. 清理所有 git lock 文件
$lockFiles = @(
    '.git/index.lock',
    '.git/HEAD.lock',
    '.git/refs/heads/master.lock',
    '.git/refs/remotes/origin/master.lock',
    '.git/packed-refs.lock',
    '.git/gc.pid'
)

foreach ($file in $lockFiles) {
    if (Test-Path $file) {
        Remove-Item $file -Force -ErrorAction SilentlyContinue
        Write-Host "✓ Removed $file"
    }
}

# 3. 重新初始化 git（可选，如果上述清理不完全）
git reset --hard

# 4. 添加修改的文件
git add TAHP.bat
git add "tahp-console/packages/client/src/components/layout/AppSidebar.vue"
git add "tahp-console/packages/client/src/components/layout/AppTopMenu.vue"
git add "tahp-console/packages/server/src/services/hermes/run-chat/handle-api-run.ts"
git add "tahp-console/packages/server/src/services/hermes/run-chat/index.ts"

# 5. 提交
git commit -m "fix: 修复聊天API模式、改进错误处理和导航重构

- 修复 index.ts 中的 TypeScript 语法错误（末尾垃圾内容）
- 改进 handle-api-run.ts 的错误处理和网关健康检查
- 新增 AppTopMenu.vue 组件，完善导航架构
- 优化 AppSidebar.vue 的路由链接
- 新增 TAHP.bat 启动脚本

Fixes: 502 Bad Gateway 错误
Type: Bugfix
Module: tahp-console"

# 6. 推送到 GitLab
git push origin master
```

## 提交信息
**Hash:** `625d8eec64970b187b1ed024d59d41835079f098`
**Author:** 周能 <neng.zhou@transsion.com>
**Date:** Mon May 25 02:29:50 2026 +0000

## 改动统计
- 5 files changed
- 559 insertions(+)
- 672 deletions(-)

### 涉及文件
1. `TAHP.bat` - 新增
2. `tahp-console/packages/client/src/components/layout/AppSidebar.vue` - 修改
3. `tahp-console/packages/client/src/components/layout/AppTopMenu.vue` - 新增
4. `tahp-console/packages/server/src/services/hermes/run-chat/handle-api-run.ts` - 修改
5. `tahp-console/packages/server/src/services/hermes/run-chat/index.ts` - 修改

## 验证提交
```powershell
# 查看即将推送的提交
git log --oneline origin/master..HEAD

# 查看详细差异
git diff origin/master..HEAD --stat
```
