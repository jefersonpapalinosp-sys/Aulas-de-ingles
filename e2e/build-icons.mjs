// Deriva PNGs do SVG autoral existente. Requer npm ci e Playwright Chromium.
import { chromium } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'

const root = new URL('../frontend/public/', import.meta.url)
const svg = 'data:image/svg+xml;base64,' + (await readFile(new URL('icon.svg', root))).toString('base64')
const browser = await chromium.launch()
try {
  const page = await browser.newPage()
  for (const size of [180, 192, 512]) {
    const data = await page.evaluate(async ({ svg, size }) => {
      const image = new Image()
      image.src = svg
      await image.decode()
      const canvas = document.createElement('canvas')
      canvas.width = canvas.height = size
      canvas.getContext('2d').drawImage(image, 0, 0, size, size)
      return canvas.toDataURL('image/png').split(',')[1]
    }, { svg, size })
    await writeFile(new URL(`icon-${size}.png`, root), Buffer.from(data, 'base64'))
  }
} finally { await browser.close() }
