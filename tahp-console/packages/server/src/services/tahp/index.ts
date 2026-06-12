/**
 * TAHP 服务层入口 — task stream 与路径解析。
 */
export { tahpPaths, hasTahpProject } from './paths'
export { TAHP_MODULES } from './constants'
export type { TahpModuleInfo } from './constants'
export { getTaskStream } from './task-stream'
export type { TaskEvent } from './task-stream'
