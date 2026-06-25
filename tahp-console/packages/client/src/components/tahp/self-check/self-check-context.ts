import type { InjectionKey } from 'vue'
import type { useDeviceSelfCheck } from '@/composables/useDeviceSelfCheck'

export type DeviceSelfCheckContext = ReturnType<typeof useDeviceSelfCheck>

export const DEVICE_SELF_CHECK_KEY: InjectionKey<DeviceSelfCheckContext> = Symbol('deviceSelfCheck')
