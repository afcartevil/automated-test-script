<template>
  <div ref="rootEl" class="conflict-gerrit-view">
    <div class="conflict-gerrit-head">
      <span>{{ leftHead }}</span>
      <span>{{ rightHead }}</span>
    </div>
    <div class="conflict-gerrit-body">
      <div class="conflict-gerrit-split">
        <div class="conflict-gerrit-pane">
          <div ref="leftScroll" class="conflict-gerrit-pane-vscroll">
            <div ref="leftTrack" class="conflict-gerrit-pane-htrack">
              <div v-for="(row, idx) in rows" :key="'l' + idx" class="conflict-gerrit-line">
                <span class="conflict-gerrit-num">{{ row.left?.num ?? '' }}</span>
                <span class="conflict-gerrit-code" :class="row.left?.cls || 'ctx'">{{ row.left?.text || '' }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="conflict-gerrit-pane-divider"></div>
        <div class="conflict-gerrit-pane">
          <div ref="rightScroll" class="conflict-gerrit-pane-vscroll">
            <div ref="rightTrack" class="conflict-gerrit-pane-htrack">
              <div v-for="(row, idx) in rows" :key="'r' + idx" class="conflict-gerrit-line">
                <span class="conflict-gerrit-num">{{ row.right?.num ?? '' }}</span>
                <span class="conflict-gerrit-code" :class="row.right?.cls || 'ctx'">{{ row.right?.text || '' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div ref="hScroll" class="conflict-gerrit-hscroll">
        <div ref="hSpacer" class="conflict-gerrit-hscroll-spacer"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  rows: Array<{ left?: { num?: number | null; text?: string; cls?: string }; right?: { num?: number | null; text?: string; cls?: string } }>
  hasMerged?: boolean
  leftTitle?: string
  rightTitle?: string
}>()

const leftHead = computed(() => props.leftTitle || '合入前（Vendor 当前）')
const rightHead = computed(() =>
  props.rightTitle
  || (props.hasMerged ? '合入后（合并结果）' : '合入后（GKI patch 期望）'),
)

const rootEl = ref<HTMLElement | null>(null)
const leftScroll = ref<HTMLElement | null>(null)
const rightScroll = ref<HTMLElement | null>(null)
const leftTrack = ref<HTMLElement | null>(null)
const rightTrack = ref<HTMLElement | null>(null)
const hScroll = ref<HTMLElement | null>(null)
const hSpacer = ref<HTMLElement | null>(null)

let ro: ResizeObserver | null = null
let syncingV = false

function syncRowHeights() {
  const leftLines = leftTrack.value?.querySelectorAll('.conflict-gerrit-line') || []
  const rightLines = rightTrack.value?.querySelectorAll('.conflict-gerrit-line') || []
  const n = Math.min(leftLines.length, rightLines.length)
  for (let i = 0; i < n; i++) {
    ;(leftLines[i] as HTMLElement).style.minHeight = ''
    ;(rightLines[i] as HTMLElement).style.minHeight = ''
  }
  for (let i = 0; i < n; i++) {
    const h = Math.max((leftLines[i] as HTMLElement).offsetHeight, (rightLines[i] as HTMLElement).offsetHeight)
    ;(leftLines[i] as HTMLElement).style.minHeight = `${h}px`
    ;(rightLines[i] as HTMLElement).style.minHeight = `${h}px`
  }
}

function updateLayout() {
  const tracks = [leftTrack.value, rightTrack.value].filter(Boolean) as HTMLElement[]
  if (!hScroll.value || !hSpacer.value || !tracks.length) return
  syncRowHeights()
  let contentW = 0
  for (const track of tracks) {
    let max = track.clientWidth || 0
    track.querySelectorAll('.conflict-gerrit-code').forEach((cell) => {
        max = Math.max(max, (cell as HTMLElement).scrollWidth || 0) + 44
    })
    contentW = Math.max(contentW, max)
  }
  const paneW = leftScroll.value?.clientWidth || 0
  const scrollW = Math.max(paneW + 1, contentW)
  hSpacer.value.style.width = `${scrollW}px`
  hScroll.value.style.visibility = contentW > paneW + 2 ? 'visible' : 'hidden'
}

function bindScroll() {
  if (!hScroll.value || !leftTrack.value || !rightTrack.value) return
  hScroll.value.onscroll = () => {
    const x = hScroll.value!.scrollLeft
    leftTrack.value!.style.transform = x ? `translateX(-${x}px)` : ''
    rightTrack.value!.style.transform = x ? `translateX(-${x}px)` : ''
  }
  if (leftScroll.value && rightScroll.value) {
    leftScroll.value.onscroll = () => {
      if (syncingV) return
      syncingV = true
      rightScroll.value!.scrollTop = leftScroll.value!.scrollTop
      syncingV = false
    }
    rightScroll.value.onscroll = () => {
      if (syncingV) return
      syncingV = true
      leftScroll.value!.scrollTop = rightScroll.value!.scrollTop
      syncingV = false
    }
  }
}

function scheduleUpdate() {
  requestAnimationFrame(() => requestAnimationFrame(updateLayout))
}

onMounted(async () => {
  await nextTick()
  bindScroll()
  scheduleUpdate()
  if (typeof ResizeObserver !== 'undefined' && rootEl.value) {
    ro = new ResizeObserver(scheduleUpdate)
    ro.observe(rootEl.value)
    if (leftTrack.value) ro.observe(leftTrack.value)
    if (rightTrack.value) ro.observe(rightTrack.value)
  }
})

onBeforeUnmount(() => {
  ro?.disconnect()
})

watch(() => props.rows, () => nextTick(scheduleUpdate), { deep: true })
</script>
