/**
 * group-chat stub — Group Chat feature removed from TAHP.
 * Retained as an empty stub so sessions.ts continues to compile.
 */

let _groupChatServer: any = null

export function setGroupChatServer(server: any): void {
  _groupChatServer = server
}

export function getGroupChatServer(): any {
  return _groupChatServer
}
