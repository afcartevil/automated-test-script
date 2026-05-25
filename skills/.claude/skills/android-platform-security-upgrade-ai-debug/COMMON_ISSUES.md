# 常见问题与处置（对照 SOP 场景）

| 序号 | 现象/问题 | 特征 | 根因/处置 |
|------|-----------|------|-----------|
| 1 | 升级后 DA 版本与旧机不一致 | `TRAN_DA_ANTI_ROLLBACK_VER` 仅看了平台未看项目 | 按 SOP 先读项目 mk 再读平台；只改升级后项目 mk |
| 2 | BROM 开关错误 | lk2 `rules.mk` 改了但项目仍错 | SOP 要求升级后**只改** `lk2/project/(project).mk` |
| 3 | 软件防回滚编译/签名失败 | `anti_ver.json` 缺条目或版本号变 | 对齐升级前 JSON；检查衍生项目是否缺键 |
| 4 | 衍生项目无 anti_ver 配置 | x6885b 继承 x6885 | 升级后分支**增加**衍生项目配置（SOP 明确要求） |
| 5 | AVB 宏找不到 | 仍按升级前 `tran_projects/...` 路径找 | 升级后路径切到 `vendor/transsion/projects/.../ProjectConfig.mk` |
| 6 | RPMB 未生效 | dts 未改或 preloader 宏未 export | 按 SOP 三段式同时核对 dts、preloader、ProjectConfig |
| 7 | 宏名拼写疑问 | `TRAN_RPMB_SUPPROT` | 与 SOP 原文一致，勿擅自「纠正」为 SUPPORT，除非仓库统一别名 |

## 与「仅两项宏」Skill 的混淆

若只处理 DA+BROM，范围小于本 SOP；本 Skill 必须覆盖 **软件防回滚、AVB、RPMB** 五项中的适用子集。
