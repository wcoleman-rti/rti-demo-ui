import { copyFile, mkdir, readFile, unlink, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const root = dirname(fileURLToPath(import.meta.url));
const output = join(root, 'assets');
const pythonAssets = join(root, 'python/src/rti_demo_ui_adapter_uplot/_assets');
await mkdir(output, { recursive: true });
await mkdir(pythonAssets, { recursive: true });
await build({
    absWorkingDir: root,
    entryPoints: [join(root, 'src/runtime.js')],
    bundle: true,
    format: 'esm',
    platform: 'browser',
    target: ['es2020'],
    minify: true,
    legalComments: 'none',
    outfile: join(output, 'runtime.js'),
});
const css = await readFile(join(output, 'runtime.css'));
await writeFile(join(output, 'theme.css'), css);
await unlink(join(output, 'runtime.css'));
const license = await readFile(join(root, 'node_modules/uplot/LICENSE'), 'utf8');
await writeFile(join(output, 'LICENSE-uPlot'), `${license.trimEnd()}\n`);
for (const name of ['runtime.js', 'theme.css', 'LICENSE-uPlot']) {
    await copyFile(join(output, name), join(pythonAssets, name));
}
const checksums = [];
for (const name of ['runtime.js', 'theme.css', 'LICENSE-uPlot']) {
    const content = await readFile(join(output, name));
    const digest = createHash('sha256').update(content).digest('hex');
    checksums.push(`${digest}  assets/${name}`);
}
await writeFile(join(root, 'assets.sha256'), `${checksums.join('\n')}\n`);
