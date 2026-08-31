import { describe, expect, it } from 'vitest'
import { homedir } from 'os'
import { join, resolve } from 'path'
import { deriveDataDir, getListenHost, getTahpConsoleHome, getWebUiHome } from '../../packages/server/src/config'

describe('server config', () => {
  it('defaults to an IPv4 bind host', () => {
    expect(getListenHost({})).toBe('0.0.0.0')
  })

  it('uses BIND_HOST when provided', () => {
    expect(getListenHost({ BIND_HOST: ' :: ' })).toBe('::')
  })

  it('ignores blank BIND_HOST values', () => {
    expect(getListenHost({ BIND_HOST: ' ' })).toBe('0.0.0.0')
  })

  it('defaults web-ui home to ~/.hermes-web-ui', () => {
    expect(getWebUiHome({})).toBe(join(homedir(), '.hermes-web-ui'))
  })

  it('uses HERMES_WEB_UI_HOME when provided', () => {
    expect(getWebUiHome({ HERMES_WEB_UI_HOME: ' ./tmp/hermes-ui ' })).toBe(resolve('./tmp/hermes-ui'))
  })

  it('uses HERMES_WEBUI_STATE_DIR as a compatibility alias', () => {
    expect(getWebUiHome({ HERMES_WEBUI_STATE_DIR: ' ./tmp/hermes-state ' })).toBe(resolve('./tmp/hermes-state'))
  })

  it('defaults console home to ~/.tahp-console', () => {
    expect(getTahpConsoleHome({})).toBe(join(homedir(), '.tahp-console'))
  })

  it('derives dataDir under console home when HERMES_WEB_UI_HOME is set', () => {
    expect(deriveDataDir({ HERMES_WEB_UI_HOME: 'C:/tmp/tahp-home' })).toBe(resolve('C:/tmp/tahp-home/data'))
  })

  it('prefers explicit TAHP_SERVER_DATA_DIR over console home', () => {
    expect(deriveDataDir({
      HERMES_WEB_UI_HOME: 'C:/tmp/tahp-home',
      TAHP_SERVER_DATA_DIR: 'C:/tmp/explicit-data',
    })).toBe(resolve('C:/tmp/explicit-data'))
  })
})
