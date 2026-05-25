#!/usr/bin/env bash
# =============================================================================
# TAHP Console — Hermes 冗余功能清理脚本
# 执行前请先备份，或确认已在 git 中有干净的提交
#
# 用法：
#   bash scripts/cleanup-hermes-redundant.sh [--dry-run]
#
# --dry-run 只打印要删除的文件，不实际删除
# =============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

delete() {
  local path="$ROOT/$1"
  if [ -e "$path" ]; then
    if $DRY_RUN; then
      echo "[DRY-RUN] would delete: $1"
    else
      rm -rf "$path"
      echo "✓ deleted: $1"
    fi
  else
    echo "  skip (not found): $1"
  fi
}

echo ""
echo "=============================="
echo " TAHP 冗余功能清理"
echo "=============================="
$DRY_RUN && echo "[DRY-RUN 模式 — 不实际删除]"
echo ""

# ─── 1. Group Chat 群聊（~5000行）─────────────────────────────────────────
echo "--- Group Chat ---"
delete "packages/client/src/components/hermes/group-chat"
delete "packages/client/src/views/hermes/GroupChatView.vue"
delete "packages/client/src/views/hermes/ChannelsView.vue"
delete "packages/client/src/stores/hermes/group-chat.ts"
delete "packages/client/src/api/hermes/group-chat.ts"
delete "packages/server/src/services/hermes/group-chat"
delete "packages/server/src/routes/hermes/group-chat.ts"
delete "tests/server/group-chat-member-sync.test.ts"
delete "tests/server/group-chat-mention-routing.test.ts"

# ─── 2. Kanban 看板（~3000行）─────────────────────────────────────────────
echo "--- Kanban ---"
delete "packages/client/src/components/hermes/kanban"
delete "packages/client/src/views/hermes/KanbanView.vue"
delete "packages/client/src/api/hermes/kanban.ts"
delete "packages/server/src/controllers/hermes/kanban.ts"
delete "packages/server/src/services/hermes/hermes-kanban.ts"
delete "packages/server/src/routes/hermes/kanban.ts"
delete "packages/server/src/routes/hermes/kanban-events.ts"
delete "packages/server/src/db/hermes/kanban-db.ts"
delete "tests/server/hermes-kanban-service.test.ts"
delete "tests/server/kanban-controller.test.ts"
delete "tests/server/kanban-routes.test.ts"
delete "tests/client/kanban-api.test.ts"
delete "tests/client/kanban-create-form.test.ts"
delete "tests/client/kanban-store.test.ts"
delete "tests/client/kanban-task-card.test.ts"
delete "tests/client/kanban-task-drawer.test.ts"
delete "tests/client/kanban-view.test.ts"

# ─── 3. Jobs 定时任务（~1500行）───────────────────────────────────────────
echo "--- Jobs ---"
delete "packages/client/src/components/hermes/jobs"
delete "packages/client/src/views/hermes/JobsView.vue"
delete "packages/client/src/api/hermes/jobs.ts"
delete "packages/server/src/controllers/hermes/jobs.ts"
delete "packages/server/src/routes/hermes/jobs.ts"
delete "packages/server/src/routes/hermes/cron-history.ts"
delete "packages/server/src/controllers/hermes/cron-history.ts"
delete "tests/server/jobs-controller.test.ts"
delete "tests/server/cron-history-controller.test.ts"
delete "tests/client/jobs.test.ts"

# ─── 4. Memory 记忆系统（~800行）──────────────────────────────────────────
echo "--- Memory ---"
delete "packages/client/src/components/hermes/settings/MemorySettings.vue"
delete "packages/client/src/views/hermes/MemoryView.vue"
delete "packages/client/src/api/hermes/conversations.ts"
delete "packages/server/src/controllers/hermes/memory.ts"
delete "packages/server/src/routes/hermes/memory.ts"
delete "packages/server/src/services/hermes/conversations.ts"

# ─── 5. TTS 语音合成（~1000行）────────────────────────────────────────────
echo "--- TTS / Voice ---"
delete "packages/client/src/components/hermes/settings/VoiceSettings.vue"
delete "packages/client/src/composables/useSpeech.ts"
delete "packages/client/src/api/hermes/tts.ts"
delete "packages/server/src/controllers/hermes/tts.ts"
delete "packages/server/src/routes/hermes/tts.ts"
delete "packages/server/src/services/hermes/tts.ts"

# ─── 6. Usage / SkillsUsage 统计（~2000行）───────────────────────────────
echo "--- Usage Statistics ---"
delete "packages/client/src/views/hermes/UsageView.vue"
delete "packages/client/src/views/hermes/SkillsUsageView.vue"
delete "tests/client/skills-usage-view.test.ts"
delete "tests/client/usage-components-cache-visuals.test.ts"
delete "tests/client/usage-store.test.ts"
delete "tests/client/usage-view-period.test.ts"
delete "tests/server/usage-analytics-db.test.ts"
delete "tests/server/usage-store.test.ts"
delete "tests/server/skill-usage-stats-db.test.ts"

# ─── 7. Weixin 微信集成（~500行）──────────────────────────────────────────
echo "--- Weixin ---"
delete "packages/server/src/controllers/hermes/weixin.ts"
delete "packages/server/src/routes/hermes/weixin.ts"
delete "tests/server/weixin-controller.test.ts"

# ─── 8. 第三方 OAuth（Codex/Copilot/Nous/XAI）（~3000行）────────────────
echo "--- Third-party OAuth ---"
delete "packages/client/src/components/hermes/models/CodexLoginModal.vue"
delete "packages/client/src/components/hermes/models/CopilotLoginModal.vue"
delete "packages/client/src/components/hermes/models/NousLoginModal.vue"
delete "packages/client/src/components/hermes/models/XaiOAuthLoginModal.vue"
delete "packages/client/src/api/hermes/codex-auth.ts"
delete "packages/client/src/api/hermes/copilot-auth.ts"
delete "packages/client/src/api/hermes/nous-auth.ts"
delete "packages/client/src/api/hermes/xai-auth.ts"
delete "packages/server/src/controllers/hermes/codex-auth.ts"
delete "packages/server/src/controllers/hermes/copilot-auth.ts"
delete "packages/server/src/controllers/hermes/nous-auth.ts"
delete "packages/server/src/controllers/hermes/xai-auth.ts"
delete "packages/server/src/routes/hermes/codex-auth.ts"
delete "packages/server/src/routes/hermes/copilot-auth.ts"
delete "packages/server/src/routes/hermes/nous-auth.ts"
delete "packages/server/src/routes/hermes/xai-auth.ts"
delete "packages/server/src/services/hermes/copilot-device-flow.ts"
delete "packages/server/src/services/hermes/copilot-models.ts"
delete "packages/server/src/services/hermes/profile-credentials.ts"
delete "tests/server/codex-credential-pool-auth.test.ts"
delete "tests/server/copilot-auth-controller.test.ts"
delete "tests/server/copilot-device-flow.test.ts"
delete "tests/server/copilot-models.test.ts"
delete "tests/server/xai-auth-controller.test.ts"
delete "tests/server/profile-credentials.test.ts"

# ─── 9. Gateway Manager/Autostart（~2000行）──────────────────────────────
echo "--- Gateway Manager/Autostart (now replaced by direct LLM config) ---"
delete "packages/server/src/services/hermes/gateway-manager.ts"
delete "packages/server/src/services/hermes/gateway-autostart.ts"
delete "packages/server/src/services/hermes/gateway-runner.ts"
delete "tests/server/gateway-autostart.test.ts"
delete "tests/server/gateway-manager-diagnostics.test.ts"
delete "tests/server/gateway-manager.test.ts"

# ─── 10. i18n 非中英文语言包（~7700行）───────────────────────────────────
echo "--- i18n: remove non-zh/en locales ---"
delete "packages/client/src/i18n/locales/zh-TW.ts"
delete "packages/client/src/i18n/locales/ja.ts"
delete "packages/client/src/i18n/locales/ko.ts"
delete "packages/client/src/i18n/locales/fr.ts"
delete "packages/client/src/i18n/locales/de.ts"
delete "packages/client/src/i18n/locales/es.ts"
delete "packages/client/src/i18n/locales/pt.ts"

echo ""
echo "=============================="
if $DRY_RUN; then
  echo " DRY-RUN 完成（未实际删除）"
  echo " 运行不带 --dry-run 参数执行实际清理"
else
  echo " 清理完成！"
  echo " 后续需要手动处理："
  echo "   1. 移除 routes/index.ts 中已删除模块的 import 和注册"
  echo "   2. 移除 server/src/index.ts 中的 gateway/group-chat 初始化"
  echo "   3. 更新 i18n 配置，移除已删除的语言包引用"
  echo "   4. 运行: npx tsc --noEmit 确认编译通过"
fi
echo "=============================="
