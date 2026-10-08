import { describe, expect, it } from 'vitest'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import {
  findMissingDependencies,
  findMissingTrayPackages,
  listDeclaredDependencies,
} from '../../scripts/lib/required-npm-deps.mjs'

describe('required-npm-deps', () => {
  it('lists dependencies from package.json', () => {
    const root = mkdtempSync(join(tmpdir(), 'tahp-deps-'))
    try {
      writeFileSync(
        join(root, 'package.json'),
        JSON.stringify({ dependencies: { systray2: '^2.1.4', foo: '1.0.0' } }),
      )
      expect(listDeclaredDependencies(root).sort()).toEqual(['foo', 'systray2'])
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('findMissingDependencies reports packages not in node_modules', () => {
    const root = mkdtempSync(join(tmpdir(), 'tahp-deps-'))
    try {
      writeFileSync(
        join(root, 'package.json'),
        JSON.stringify({ dependencies: { systray2: '^2.1.4', 'installed-pkg': '1.0.0' } }),
      )
      const installedDir = join(root, 'node_modules', 'installed-pkg')
      mkdirSync(installedDir, { recursive: true })
      writeFileSync(join(installedDir, 'package.json'), '{}')

      expect(findMissingDependencies(root)).toEqual(['systray2'])
      expect(findMissingTrayPackages(root)).toEqual(['systray2'])
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('treats monaco-editor as missing when its LSP bundle is absent', () => {
    const root = mkdtempSync(join(tmpdir(), 'tahp-deps-'))
    try {
      writeFileSync(
        join(root, 'package.json'),
        JSON.stringify({ devDependencies: { 'monaco-editor': '^0.55.1' } }),
      )
      const installedDir = join(root, 'node_modules', 'monaco-editor')
      mkdirSync(installedDir, { recursive: true })
      writeFileSync(join(installedDir, 'package.json'), '{"name":"monaco-editor"}')

      expect(findMissingDependencies(root)).toEqual(['monaco-editor'])
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })
})
