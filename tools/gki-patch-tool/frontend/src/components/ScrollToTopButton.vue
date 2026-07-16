<template>
  <Teleport to="body">
    <div
      v-show="positionReady"
      class="scroll-to-top-overlay scroll-to-top-overlay--fixed"
      :style="overlayStyle"
    >
      <Transition name="scroll-top-fade">
        <button
          v-show="visible"
          type="button"
          class="scroll-to-top-btn scroll-to-top-btn--panel"
          :aria-label="buttonLabel"
          :title="buttonLabel"
          @click="handleClick"
        >
          <span class="scroll-to-top-icon" aria-hidden="true">{{ buttonIcon }}</span>
        </button>
      </Transition>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    scrollTarget?: HTMLElement | null
    anchorEl?: HTMLElement | null
    threshold?: number
    canReturn?: boolean
  }>(),
  { threshold: 120, canReturn: false },
)

const emit = defineEmits<{
  click: []
}>()

const visible = ref(false)
const positionReady = ref(false)
const overlayStyle = ref<Record<string, string>>({})

let scrollEl: HTMLElement | null = null
let anchorEl: HTMLElement | null = null
let resizeObserver: ResizeObserver | null = null

const anchor = computed(() => props.anchorEl ?? props.scrollTarget ?? null)

const buttonLabel = computed(() =>
  props.canReturn ? '回到刚才的位置' : '回到顶部',
)

const buttonIcon = computed(() => (props.canReturn ? '↩' : '↑'))

function updateVisible() {
  if (!scrollEl) {
    visible.value = false
    return
  }
  visible.value = scrollEl.scrollTop > props.threshold || props.canReturn
}

function updateOverlayPosition() {
  const el = anchor.value
  if (!el) {
    positionReady.value = false
    overlayStyle.value = {}
    return
  }

  const rect = el.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) {
    positionReady.value = false
    return
  }

  overlayStyle.value = {
    position: 'fixed',
    right: `${Math.max(12, window.innerWidth - rect.right + 12)}px`,
    bottom: `${Math.max(12, window.innerHeight - rect.bottom + 12)}px`,
    zIndex: '100',
  }
  positionReady.value = true
}

function handleClick() {
  emit('click')
}

function unbindScroll() {
  if (scrollEl) {
    scrollEl.removeEventListener('scroll', onScroll)
    scrollEl = null
  }
}

function unbindAnchor() {
  window.removeEventListener('scroll', updateOverlayPosition, true)
  window.removeEventListener('resize', updateOverlayPosition)
  if (anchorEl) {
    anchorEl.removeEventListener('scroll', updateOverlayPosition)
    anchorEl = null
  }
  resizeObserver?.disconnect()
  resizeObserver = null
  positionReady.value = false
  overlayStyle.value = {}
}

function onScroll() {
  updateVisible()
  updateOverlayPosition()
}

function bindScroll(el: HTMLElement | null) {
  unbindScroll()
  if (!el) {
    visible.value = false
    return
  }
  scrollEl = el
  updateVisible()
  scrollEl.addEventListener('scroll', onScroll, { passive: true })
}

function bindAnchor(el: HTMLElement | null) {
  unbindAnchor()
  if (!el) return

  anchorEl = el
  updateOverlayPosition()

  window.addEventListener('scroll', updateOverlayPosition, { passive: true, capture: true })
  window.addEventListener('resize', updateOverlayPosition, { passive: true })
  el.addEventListener('scroll', updateOverlayPosition, { passive: true })

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(updateOverlayPosition)
    resizeObserver.observe(el)
  }
}

watch(
  () => props.scrollTarget,
  (el) => bindScroll(el),
  { immediate: true },
)

watch(
  anchor,
  (el) => bindAnchor(el),
  { immediate: true },
)

watch(
  () => props.canReturn,
  () => updateVisible(),
)

onBeforeUnmount(() => {
  unbindScroll()
  unbindAnchor()
})
</script>
