import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const root = new URL('./', import.meta.url)
const web = new URL('../../../../jiuwenswarm/channels/web/frontend/', root)
const require = createRequire(new URL('package.json', web))
const { build } = require('esbuild')
const read = path => readFile(new URL(path, root), 'utf8')
const out = new URL('dist/', root)
await mkdir(out, { recursive: true })
const manifest = JSON.parse(await read('vendor/SOURCE.json'))
for (const [path, hash] of Object.entries(manifest.sha256)) {
  const bytes = await readFile(new URL('vendor/' + path, root))
  if (createHash('sha256').update(bytes).digest('hex') !== hash) {
    throw new Error('Original SuperAgent asset changed: ' + path)
  }
}
await build({
  absWorkingDir: fileURLToPath(root),
  entryPoints: ['src/panel.tsx'],
  outfile: fileURLToPath(new URL('panel.mjs', out)),
  bundle: true,
  minify: true,
  format: 'esm',
  jsx: 'automatic',
  target: 'chrome107',
  nodePaths: [fileURLToPath(new URL('node_modules/', web))],
  plugins: [{
    name: 'raw-css',
    setup(context) {
      context.onResolve({ filter: /\.css\?raw$/ }, args => ({
        path: fileURLToPath(new URL(args.path.slice(0, -4), 'file://' + args.resolveDir + '/')),
        namespace: 'css-text',
      }))
      context.onLoad({ filter: /.*/, namespace: 'css-text' }, async args => ({
        contents: await readFile(args.path, 'utf8'), loader: 'text',
      }))
    },
  }],
})

const { asset, useCase } = await import(new URL('vendor/workbench/fixtures.mjs', root))
await writeFile(new URL('workbench-fixtures.json', out), JSON.stringify({ asset, useCase }))

const originalBridge = await read('vendor/workbench/standalone-bridge.js')
const originalWorkbench = await read('vendor/workbench/index.html')
const changes = JSON.parse(await read('src/workbench-bridge.json'))
let bridge = originalBridge
for (const [before, after] of changes) {
  if (bridge.split(before).length !== 2) throw new Error('Workbench adapter anchor changed: ' + before)
  bridge = bridge.replace(before, () => after)
}
if (originalWorkbench.split(originalBridge).length !== 2) throw new Error('Original Workbench bridge mismatch')
await writeFile(new URL('workbench.html', out), originalWorkbench.replace(originalBridge, () => bridge))
for (const [from, to] of [
  ['src/panel.html', 'panel.html'], ['vendor/SOURCE.json', 'SOURCE.json'],
  ['vendor/panel/LICENSE', 'SUPERAGENT.LICENSE'],
  ['vendor/workbench/business-catalog.json', 'business-catalog.json'], ['vendor/workbench/experts.json', 'experts.json'],
]) {
  await copyFile(new URL(from, root), new URL(to, out))
}
