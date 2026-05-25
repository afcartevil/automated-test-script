/**
 * useSpeech / useGlobalSpeech stubs — TTS / Voice feature removed from TAHP.
 */
import { ref } from 'vue'

export function useSpeech() {
  return {
    speak: (_text: string) => {},
    stop: () => {},
    isSpeaking: false,
    isSupported: false,
  }
}

/** Full no-op stub matching the original useGlobalSpeech API surface */
export function useGlobalSpeech() {
  return {
    isSupported: false,
    isPlaying: ref(false),
    isPaused: ref(false),
    isCustomPlaying: ref(false),
    isCustomPaused: ref(false),
    currentMessageId: ref<string | null>(null),
    currentCustomMessageId: ref<string | null>(null),

    // Core controls
    stop: (_showNotice?: boolean) => {},
    toggle: (_id: string, _content: any) => {},
    speakViaBrowser: (_id: string, _text: string, _opts?: any) => {},

    // OpenAI / custom endpoint
    openaiPlay: (_id: string, _content: any, _opts?: any) => {},
    openaiToggle: (_id: string, _content: any, _opts?: any) => {},

    // MiMo TTS
    mimoPlay: (_id: string, _content: any, _opts?: any) => {},
    mimoToggle: (_id: string, _content: any, _opts?: any) => {},

    // Helpers
    extractReadableText: (_content: any): string => '',
  }
}
