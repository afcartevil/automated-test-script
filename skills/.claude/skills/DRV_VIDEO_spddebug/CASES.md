# 移植典型案例

> 案例在 Wiki 同步后补充真实链接；以下为 **流程模板**。

---

## 案例 1：单提交 cherry-pick 到项目基线

### 输入

- Wiki：`TC-03` → Gerrit 链接  
- 目标：`/path/to/vendor` 分支 `tOS_mtk_A15_project_x`

### 过程

1. `git fetch` + `git cherry-pick -x <hash>`  
2. 2 个文件冲突：`foo.cpp` 保留目标宏，并入源函数体  
3. `git cherry-pick --continue`

### 结果

- 状态：完成  
- 验证：建议编 `libfoo` 模块

---

## 案例 2：Wiki 多提交按依赖顺序移植

### 输入

- `TC-10` 依赖 `TC-09`（Wiki 依赖列）

### 过程

1. 先 pick `TC-09`，再 pick `TC-10`  
2. `TC-10` 无需冲突处理

### 结果

- 两笔 Change-Id 均在目标 `git log --grep` 可查到

---

## 案例 3：路径不一致 — 手工移植

### 输入

- 源修改 `vendor/transsion/.../A.cpp`  
- 目标仅有 `vendor/transsion/.../legacy/A.cpp`

### 过程

1. cherry-pick 失败  
2. 对照源 diff 手工改 `legacy/A.cpp` + 对应头文件  
3. 单独 commit，message 引用源 Gerrit 链接

### 结果

- 报告注明：未使用 cherry-pick，路径已适配

---

## 案例 4：阻塞 — 无法访问 Gerrit

### 输入

- 仅 Wiki 标题，链接失效或无权限

### 过程

1. 停止移植  
2. 请用户提供 `.patch` 或 `repo download` 命令

### 结果

- 状态：阻塞
