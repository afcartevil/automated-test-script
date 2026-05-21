<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { NCard, NGrid, NGi, NTag, NSpin, NEmpty, NButton, NSpace } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useTahpModulesStore } from '@/stores/tahp/modules'

const router = useRouter()
const modulesStore = useTahpModulesStore()

const DOMAIN_FILES = [
  { domain: 'bug_analysis', file: 'bug-analysis.yaml', label: 'Bug 分析' },
  { domain: 'code_adaptation', file: 'code-adaptation.yaml', label: '代码适配' },
  { domain: 'version_adaptation', file: 'version-adaptation.yaml', label: '版本适配' },
  { domain: 'carrier_porting', file: 'carrier-porting.yaml', label: '运营商移植' },
]

const matrix = computed(() => modulesStore.modules.map(m => ({
  name: m.name,
  hasModuleYaml: m.hasModuleYaml,
  cells: DOMAIN_FILES.map(d => ({
    domain: d.domain,
    label: d.label,
    file: d.file,
    present: m.domains.some(x => x.domain === d.domain),
  })),
})))

onMounted(() => modulesStore.refresh())

function openConstraint(moduleName: string, file: string) {
  router.push({ name: 'tahp.constraint-editor', params: { module: moduleName, file } })
}

function openModuleYaml(moduleName: string) {
  openConstraint(moduleName, 'module.yaml')
}
</script>

<template>
  <div class="tahp-matrix">
    <div class="page-header">
      <h1>模块与约束矩阵</h1>
      <p class="subtitle">模块 × 4 个 Domain 的约束覆盖度，点击格子进入 YAML 编辑器</p>
    </div>

    <NSpin :show="modulesStore.loading">
      <NEmpty v-if="!matrix.length" description="未检测到模块" />
      <NSpace v-else vertical size="large">
        <NCard v-for="m in matrix" :key="m.name" :bordered="false" size="small">
          <template #header>
            <NSpace align="center">
              <strong>{{ m.name }}</strong>
              <NTag v-if="m.hasModuleYaml" type="success" size="tiny">module.yaml</NTag>
              <NTag v-else type="warning" size="tiny">缺 module.yaml</NTag>
            </NSpace>
          </template>
          <template #header-extra>
            <NButton size="tiny" @click="openModuleYaml(m.name)">编辑 module.yaml</NButton>
          </template>
          <NGrid :cols="4" :x-gap="12" :y-gap="12" responsive="screen">
            <NGi v-for="cell in m.cells" :key="cell.domain">
              <div
                class="matrix-cell"
                :class="{ present: cell.present, missing: !cell.present }"
                @click="cell.present && openConstraint(m.name, cell.file)"
              >
                <div class="cell-label">{{ cell.label }}</div>
                <div class="cell-domain">{{ cell.domain }}</div>
                <NTag v-if="cell.present" type="success" size="tiny">已配置</NTag>
                <NTag v-else type="default" size="tiny">未配置</NTag>
              </div>
            </NGi>
          </NGrid>
        </NCard>
      </NSpace>
    </NSpin>
  </div>
</template>

<style scoped>
.tahp-matrix { padding: 24px; max-width: 1280px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.page-header h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #888; margin: 0; }
.matrix-cell {
  padding: 16px;
  border-radius: 8px;
  border: 1px solid var(--n-border-color);
  text-align: center;
  transition: all 0.2s;
}
.matrix-cell.present { cursor: pointer; background: var(--n-color-modal); }
.matrix-cell.present:hover { transform: translateY(-2px); border-color: var(--n-primary-color); }
.matrix-cell.missing { opacity: 0.55; background: transparent; }
.cell-label { font-weight: 600; margin-bottom: 4px; }
.cell-domain { font-size: 11px; color: #888; margin-bottom: 8px; font-family: monospace; }
</style>
