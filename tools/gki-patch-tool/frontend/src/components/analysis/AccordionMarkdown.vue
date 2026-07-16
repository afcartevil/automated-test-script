<template>
  <div class="accordion-markdown">
    <div v-if="toolbarVisible" class="accordion-toolbar">
      <span class="muted accordion-toolbar-meta">{{ sections.length }} 节</span>
      <button type="button" class="btn-link" @click="expandAll">全部展开</button>
      <span class="muted">·</span>
      <button type="button" class="btn-link" @click="collapseAll">全部收起</button>
    </div>

    <div v-if="useSingleExpand" class="expandable-markdown">
      <div
        class="summary-text summary-text-compact expandable-markdown-body"
        :class="{ collapsed: !singleExpanded }"
        v-html="renderedFull"
      />
      <button type="button" class="btn btn-sm accordion-toggle-btn" @click="singleExpanded = !singleExpanded">
        {{ singleExpanded ? '收起' : '展开全文' }}
      </button>
    </div>

    <div v-else class="accordion-list">
      <div v-for="(section, index) in sections" :key="section.id" class="accordion-item">
        <button
          type="button"
          class="accordion-head"
          :class="{ open: isOpen(section.id) }"
          @click="toggle(section.id)"
        >
          <span class="accordion-head-title">{{ section.title }}</span>
          <span v-if="sectionPreview(section)" class="accordion-head-preview muted">
            {{ sectionPreview(section) }}
          </span>
          <span class="accordion-chevron">{{ isOpen(section.id) ? '▼' : '▶' }}</span>
        </button>
        <div v-show="isOpen(section.id)" class="accordion-body">
          <div v-if="nestedSections(section).length" class="accordion-nested">
            <div
              v-for="sub in nestedSections(section)"
              :key="sub.id"
              class="accordion-item accordion-item-nested"
            >
              <button
                type="button"
                class="accordion-head accordion-head-nested"
                :class="{ open: isOpen(sub.id) }"
                @click="toggle(sub.id)"
              >
                <span class="accordion-head-title">{{ sub.title }}</span>
                <span class="accordion-chevron">{{ isOpen(sub.id) ? '▼' : '▶' }}</span>
              </button>
              <div v-show="isOpen(sub.id)" class="accordion-body">
                <div
                  class="summary-text summary-text-compact"
                  v-html="renderSection(sub.content)"
                />
              </div>
            </div>
          </div>
          <div
            v-else
            class="summary-text summary-text-compact"
            v-html="renderSection(section.content)"
          />
        </div>
        <div v-if="index < sections.length - 1" class="accordion-divider" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  isLongMarkdown,
  renderSimpleMarkdown,
  splitMarkdownSections,
  splitMarkdownSubSections,
  type MarkdownSection,
} from '../../utils/analysisDisplay'

const props = withDefaults(
  defineProps<{
    markdown?: string
    defaultOpenCount?: number
    nestedMinLevel?: number
  }>(),
  {
    markdown: '',
    defaultOpenCount: 2,
    nestedMinLevel: 4,
  },
)

const openIds = ref<Set<string>>(new Set())
const singleExpanded = ref(false)

const sections = computed(() => splitMarkdownSections(props.markdown))

const useSingleExpand = computed(
  () => sections.value.length <= 1 && isLongMarkdown(props.markdown),
)

const renderedFull = computed(() => renderSimpleMarkdown(props.markdown))

const toolbarVisible = computed(
  () => !useSingleExpand.value && sections.value.length > 1,
)

function nestedSections(section: MarkdownSection) {
  if (section.level > 3) return []
  return splitMarkdownSubSections(section.content, props.nestedMinLevel)
}

function sectionPreview(section: MarkdownSection) {
  if (isOpen(section.id)) return ''
  const plain = String(section.content || '')
    .replace(/^#+\s+/gm, '')
    .replace(/[*_`>#-]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!plain) return ''
  return plain.length > 56 ? `${plain.slice(0, 56)}…` : plain
}

function renderSection(content: string) {
  return renderSimpleMarkdown(content)
}

function isOpen(id: string) {
  return openIds.value.has(id)
}

function toggle(id: string) {
  const next = new Set(openIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  openIds.value = next
}

function expandAll() {
  const ids = new Set<string>()
  for (const section of sections.value) {
    ids.add(section.id)
    for (const sub of nestedSections(section)) ids.add(sub.id)
  }
  openIds.value = ids
}

function collapseAll() {
  openIds.value = new Set()
}

function applyDefaultOpen() {
  if (useSingleExpand.value) {
    singleExpanded.value = false
    openIds.value = new Set()
    return
  }
  const ids = new Set<string>()
  sections.value.slice(0, Math.max(0, props.defaultOpenCount)).forEach((s) => ids.add(s.id))
  openIds.value = ids
}

watch(
  () => props.markdown,
  () => applyDefaultOpen(),
  { immediate: true },
)
</script>
