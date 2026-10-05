const path = require('path');
const fs = require('fs');
const { spawnSync } = require('child_process');

if (!process.env.PYRAMID_NODE_MODULES) throw new Error('PYRAMID_NODE_MODULES is required');
if (!process.env.PYRAMID_PYTHON) throw new Error('PYRAMID_PYTHON is required');
const { chromium } = require(path.join(process.env.PYRAMID_NODE_MODULES, 'playwright'));

async function main() {
  const [url, project, runtime, screenshot] = process.argv.slice(2);
  if (!url || !project || !runtime || !screenshot) {
    throw new Error('Usage: live_visual_smoke.cjs <url> <project> <pyramid.py> <screenshot>');
  }
  const options = {headless:true};
  if(process.env.PYRAMID_BROWSER)options.executablePath=process.env.PYRAMID_BROWSER;
  const browser = await chromium.launch(options);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(url);
  await page.locator('[data-surface="graph"]').click();
  await page.locator('#node-select').selectOption('TASK-201');
  await page.locator('[data-view="pyramid"]').click();
  await page.locator('[data-filter="working"]').click();
  await page.locator('#node-select').focus();
  await page.locator('#live-status.connected').waitFor({ timeout: 5000 });

  const mutation = spawnSync(process.env.PYRAMID_PYTHON, [
    '-B', runtime, 'take', '--project', project, '--node', 'RESEARCH-101',
    '--actor', 'live-smoke', '--json'
  ], { encoding: 'utf8' });
  if (mutation.status !== 0) throw new Error(`Mutation failed: ${mutation.stderr || mutation.stdout}`);

  await page.waitForFunction(() => document.querySelector('#live-status')?.textContent.includes('graph 2'), null, { timeout: 5000 });
  await page.waitForFunction(() => document.querySelector('#live-status')?.textContent.includes('updated'), null, { timeout: 5000 });
  const selected = await page.locator('#node-select').inputValue();
  const overview = await page.locator('#overview').innerText();
  const liveStatus = await page.locator('#live-status').innerText();
  const retained = {view:await page.locator('[data-view="pyramid"]').getAttribute('aria-pressed'),filter:await page.locator('[data-filter="working"]').getAttribute('aria-pressed'),focus:await page.evaluate(()=>document.activeElement.id)};
  if(retained.view!=='true'||retained.filter!=='true'||retained.focus!=='node-select')throw new Error(`Live state lost: ${JSON.stringify(retained)}`);
  if(process.env.PYRAMID_LIVE_ERROR_CHECK==='1') {
    // Caller must supply an owned disposable fixture, never a user project.
    const graphPath=path.join(project,'.pyramid','graph.json');
    const graph=JSON.parse(fs.readFileSync(graphPath,'utf8'));
    graph.nodes[0].title='Owned invalid-publication test';
    fs.writeFileSync(graphPath,JSON.stringify(graph));
    await page.locator('#live-status.error').waitFor({timeout:5000});
    if(!(await page.locator('#overview').innerText()).includes('1\nWorking')||await page.locator('#node-select').inputValue()!=='TASK-201')throw new Error('Invalid publication replaced the last valid state');
    await page.screenshot({path:screenshot.replace(/\.png$/,'-rejected.png'),fullPage:true});
    const restored=spawnSync(process.env.PYRAMID_PYTHON,['-B',runtime,'compile','--project',project,'--json'],{encoding:'utf8'});
    if(restored.status!==0)throw new Error(`Owned fixture compile failed: ${restored.stderr||restored.stdout}`);
    await page.locator('#live-status.connected').waitFor({timeout:5000});
  }
  await page.screenshot({ path: screenshot, fullPage: true });
  await browser.close();

  if (errors.length) throw new Error(`Page errors: ${errors.join('; ')}`);
  if (selected !== 'TASK-201') throw new Error('Selected node was not preserved across the live update');
  if (!overview.includes('1\nWorking')) throw new Error('Working summary did not update');
  process.stdout.write(JSON.stringify({ ok: true, selected, liveStatus, screenshot,retained,invalidPublication:process.env.PYRAMID_LIVE_ERROR_CHECK==='1'?'rejected and recovered':'not-tested' }) + '\n');
}

main().catch(error => {
  process.stderr.write(error.stack + '\n');
  process.exit(1);
});
