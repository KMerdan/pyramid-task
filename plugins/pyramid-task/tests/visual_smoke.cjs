const path = require('path');

if (!process.env.PYRAMID_NODE_MODULES) {
  throw new Error('PYRAMID_NODE_MODULES is required');
}
const { chromium } = require(path.join(process.env.PYRAMID_NODE_MODULES, 'playwright'));

async function main() {
  const input = process.argv[2];
  const screenshot = process.argv[3];
  if (!input || !screenshot) throw new Error('Usage: visual_smoke.cjs <html> <screenshot>');
  const launchOptions = { headless: true };
  if (process.env.PYRAMID_BROWSER) launchOptions.executablePath = process.env.PYRAMID_BROWSER;
  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`file://${path.resolve(input)}`);
  await page.locator('[data-view="pyramid"]').click();
  await page.locator('[data-filter="all"]').click();
  const assuranceOverlay = page.locator('[data-overlay="impact"]');
  if (await assuranceOverlay.isEnabled()) await assuranceOverlay.click();
  await page.locator('#node-select').selectOption('TASK-201');
  await page.screenshot({ path: screenshot, fullPage: true });
  const nodeCount = await page.locator('#node-layer .node').count();
  const detail = await page.locator('#detail').innerText();
  const meta = await page.locator('#page-meta').innerText();
  const reworkFilter = await page.locator('[data-filter="needs-rework"]').count();
  const workPackageFilter = await page.locator('[data-filter="work-package"]').count();
  const assuranceFilter = await page.locator('[data-filter="assurance-blocked"]').count();
  const assurancePanel = await page.locator('#assurance-panel.visible').count();
  await browser.close();
  if (errors.length) throw new Error(`Page errors: ${errors.join('; ')}`);
  if (nodeCount < 1) throw new Error('No graph nodes rendered');
  if (!detail.includes('TASK-201')) throw new Error('Selected-node detail did not update');
  if (!detail.includes('Plan lifecycle')) throw new Error('Lifecycle detail is missing');
  if (!meta.includes('active')) throw new Error('Lifecycle summary is missing');
  if (reworkFilter !== 1) throw new Error('Rework filter is missing');
  if (workPackageFilter !== 1) throw new Error('Work-package filter is missing');
  if (assuranceFilter !== 1) throw new Error('Assurance filter is missing');
  if (assurancePanel && !detail.includes('Assurance status')) throw new Error('Assurance detail is missing');
  process.stdout.write(JSON.stringify({ ok: true, nodeCount, screenshot }) + '\n');
}

main().catch(error => {
  process.stderr.write(error.stack + '\n');
  process.exit(1);
});
