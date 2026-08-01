<script setup lang="ts">
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSkillConfigReadiness } from '@/composables/useSkillConfigReadiness'

const route = useRoute()
const router = useRouter()
const { loading, hasUnconfigured, unconfiguredCount, refresh } = useSkillConfigReadiness()

watch(
  () => route.fullPath,
  () => {
    if (route.name !== 'login') void refresh()
  },
)

import { CONFIG_ROUTE_NAME } from '@/utils/config-navigation'

function goConfigure() {
  router.push({ name: CONFIG_ROUTE_NAME, query: { tab: 'skills' } })
}
</script>

<template>
  <div
    v-if="!loading && hasUnconfigured"
    class="skill-config-warning-bar"
    role="status"
  >
    常用 Skill 配置尚未完成（{{ unconfiguredCount }} 项未配置），智能诊断、Jira 操作等完整功能需在
    <button type="button" class="skill-config-warning-bar__link" @click="goConfigure">
      配置 → 常用 Skill 配置
    </button>
    中完成全部 Skill 配置。
  </div>
</template>

<style scoped lang="scss">
.skill-config-warning-bar {
  flex-shrink: 0;
  background: var(--warn-soft);
  color: var(--warn);
  text-align: center;
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
}

.skill-config-warning-bar__link {
  display: inline;
  padding: 0;
  margin: 0 2px;
  border: none;
  background: none;
  color: inherit;
  font: inherit;
  font-weight: 700;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;

  &:hover {
    opacity: 0.88;
  }
}
</style>
