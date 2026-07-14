#!/usr/bin/env node
/**
 * 从 packages/client/public/favicon.svg 生成托盘与浏览器用 .ico
 */
import { mkdirSync, writeFileSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = resolve(__dirname, '..', '..', '..')
const svgPath = join(consoleRoot, 'packages', 'client', 'public', 'favicon.svg')
const trayIcoPath = join(__dirname, 'easyadapter.ico')
const faviconIcoPath = join(consoleRoot, 'packages', 'client', 'public', 'favicon.ico')
const traySizes = [16, 32, 48]
const faviconSizes = [16, 32, 48, 256]

async function main() {
  let sharp
  let toIco
  try {
    sharp = (await import('sharp')).default
    toIco = (await import('to-ico')).default
  } catch (err) {
    console.error('[tray:icon] 需要 devDependencies: sharp, to-ico')
    console.error(err instanceof Error ? err.message : err)
    process.exit(1)
  }

  const trayPngs = await Promise.all(
    traySizes.map(size => sharp(svgPath).resize(size, size).png().toBuffer()),
  )
  const faviconPngs = await Promise.all(
    faviconSizes.map(size => sharp(svgPath).resize(size, size).png().toBuffer()),
  )
  const trayIco = await toIco(trayPngs)
  const faviconIco = await toIco(faviconPngs)

  mkdirSync(dirname(trayIcoPath), { recursive: true })
  writeFileSync(trayIcoPath, trayIco)
  writeFileSync(faviconIcoPath, faviconIco)
  console.log(`[tray:icon] 已生成 ${trayIcoPath} (${trayIco.length} bytes, sizes=${traySizes.join(',')})`)
  console.log(`[tray:icon] 已生成 ${faviconIcoPath} (${faviconIco.length} bytes)`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
