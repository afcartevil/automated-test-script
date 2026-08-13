# 审核示例

## 示例 1：注释违规

**现状**：
```java
// 修复空指针
mDateText.setColor(Color.BLACK);
```

**审核输出**：
- 🔴 缺少部门简称、英文原因、bug_id、by、日期、start/end
- **建议**：
```java
// TDD:add fix null pointer when date is empty SLLEL-1705 by jinxian.lei 20220815 start
mDateText.setColor(Color.BLACK);
// TDD:add fix null pointer when date is empty SLLEL-1705 by jinxian.lei 20220815 end
```

---

## 示例 2：直接改 AOSP 字符串

**现状**：修改 `frameworks/base/core/res/res/values/strings.xml` 中 `app_name`

**审核输出**：
- 🔴 违反「原生英文字符串文件不得修改」
- **风险**：升级 merge 冲突；翻译流程断裂
- **建议**：
  1. 在 `vendor/tran_os/overlay/.../values/os_strings.xml` 新增：
     ```xml
     <!-- OS:modify app name display OS-1234 by zhangsan 20240601 start -->
     <string name="app_name">MyApp</string>
     <!-- OS:modify app name display OS-1234 by zhangsan 20240601 end -->
     ```
  2. 确保 overlay 在 product makefile 中启用

---

## 示例 3：C/C++ 命名 + 注释

**现状**：
```c
int suspend_time = 0;
#define FINGERPRINT_SUPPORT 1
```

**审核输出**：
- 🔴 局部变量缺 `tran_` 前缀；宏缺 `TRAN_` 前缀
- **建议**：
```c
//BSP:add fingerprint support FSHSJB-812 by chao.liu2 20180606 start
#define TRAN_FINGERPRINT_SUPPORT 1
unsigned int tran_suspend_time = 0;
//BSP:add fingerprint support FSHSJB-812 by chao.liu2 20180606 end
```

---

## 示例 4：Framework 改动风险

**现状**：在 `ActivityManagerService.java` 内直接新增 80 行传音逻辑

**审核输出**：

| 子系统 | 变更点 | 风险 |
|--------|--------|------|
| AMS | 改 startActivity 分支 | 高：task 栈、后台限制、CTS |

- 🔴 应下沉到 `vendor/tran_os/framework/base/services/.../com/transsion/...`
- 🟡 若必须改 AMS：最小 diff + 注释块；评估 Android 升级 patch
- **建议**：提取 `TranActivityStarter` helper，AMS 仅保留一行 hook 调用

---

## 示例 5：init.rc 违规

**现状**：将整份 `init.rc` copy 到 `device/xxx/init.rc` 修改

**审核输出**：
- 🔴 违反 M.RD-223 7.3
- **风险**：启动顺序错乱、OTA 合入困难
- **建议**：仅在 `device/transsion/ProjectXXX/init.project.rc` 追加差异化 service/action
