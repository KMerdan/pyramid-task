const path = require('path');
const { spawnSync } = require('child_process');

if (!process.env.PYRAMID_NODE_MODULES) throw new Error('PYRAMID_NODE_MODULES is required');
if (!process.env.PYRAMID_PYTHON) throw new Error('PYRAMID_PYTHON is required');
const { chromium } = require(path.join(process.env.PYRAMID_NODE_MODULES, 'playwright'));

async function main() {
  const [url, project, runtime, screenshot] = process.argv.slice(2);
  if (!url || !project || !runtime || !screenshot) {
    throw new Error('Usage: live_visual_smoke.cjs <url> <project> <pyramid.py> <screenshot>');
  }
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(url);
  await page.locator('#node-select').selectOption('TASK-201');
  await page.locator('#live-status.connected').waitFor({ timeout: 5000 });

  const mutation = spawnSync(process.env.PYRAMID_PYTHON, [
    '-B', runtime, 'take', '--project', project, '--node', 'RESEARCH-101',
    '--actor', 'live-smoke', '--json'
  ], { encoding: 'utf8' });
  if (mutation.status !== 0) throw new Error(`Mutation failed: ${mutation.stderr || mutation.stdout}`);

  await page.waitForFunction(() => document.querySelector('#page-meta')?.textContent.includes('graph 2'), null, { timeout: 5000 });
  await page.waitForFunction(() => document.querySelector('#live-status')?.textContent.includes('updated'), null, { timeout: 5000 });
  const selected = await page.locator('#node-select').inputValue();
  const overview = await page.locator('#overview').innerText();
  const liveStatus = await page.locator('#live-status').innerText();
  await page.screenshot({ path: screenshot, fullPage: true });
  await browser.close();

  if (errors.length) throw new Error(`Page errors: ${errors.join('; ')}`);
  if (selected !== 'TASK-201') throw new Error('Selected node was not preserved across the live update');
  if (!overview.includes('1\nWorking')) throw new Error('Working summary did not update');
  process.stdout.write(JSON.stringify({ ok: true, selected, liveStatus, screenshot }) + '\n');
}

main().catch(error => {
  process.stderr.write(error.stack + '\n');
  process.exit(1);
});
