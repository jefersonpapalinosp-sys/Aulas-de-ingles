import { readFile } from 'node:fs/promises'

import openapiTS, { astToString, COMMENT_HEADER } from 'openapi-typescript'

const contractUrl = new URL('../../backend/openapi.json', import.meta.url)
const generatedUrl = new URL('../src/api/schema.d.ts', import.meta.url)

const expected = `${COMMENT_HEADER}${astToString(await openapiTS(contractUrl))}`
const current = await readFile(generatedUrl, 'utf8')

if (current !== expected) {
  console.error('ERRO schema.d.ts está fora de sincronia; execute npm run gen:api.')
  process.exitCode = 1
} else {
  console.log('OK schema.d.ts corresponde ao backend/openapi.json.')
}
