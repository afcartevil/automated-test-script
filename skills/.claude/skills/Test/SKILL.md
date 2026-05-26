---
tahp_adapt_skill: true
name: Test
domain_label: "数字修改"
domain_id: "Test"
module: Test
icon: "TEST"
color: "#388bfd"
status: active
description: "测试适配功能可行性"
adapt_fields:
  - name: issue_desc
    label: "问题描述"
    type: textarea
    required: true
    placeholder: "描述需要适配的具体问题"
created_at: "2026-05-26T08:36:06.628Z"
source: user_created
---

# 数字修改

前置条件，需要输入制定的文件
然后将指定文件中所有为0的数字改为1
