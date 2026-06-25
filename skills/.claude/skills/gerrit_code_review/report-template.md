# Report Template

> **Note**: Reports are written as **HTML**. Use [report-template.html](report-template.html) as the structure reference.

## Single Change Report

Save as `D:\code_review_report\review-report-{change_id}.html` on Windows (directory auto-created if missing).

See `report-template.html` for the full HTML skeleton with embedded CSS.

Required sections (same as before):

1. 基本信息（含 **模块** 行，取自 `modules_display`）
2. 问题统计
3. 详细问题列表和改善建议
4. 影响范围（含模块影响说明）
5. 测试建议 (P0 / P1 / P2)

## Topic Summary Report

Save as `D:\code_review_report\review-report-topic-{topic_slug}.html` on Windows.

Same 5 sections. Within each section, group by Change number. End with:

- **跨 Change 共性风险**
- **合并测试建议**（去重后的 P0/P1/P2 列表）
