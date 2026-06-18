import { ref } from 'vue'

const isDark = ref(false)
const isComic = ref(false)

export function useTheme() {
  return {
    brightness: ref('light' as const),
    style: ref('v26' as const),
    isDark,
    isComic,
    themeName: ref('v26-light'),
    setBrightness: () => {},
    setStyle: () => {},
    toggleBrightness: () => {},
    toggleStyle: () => {},
  }
}
