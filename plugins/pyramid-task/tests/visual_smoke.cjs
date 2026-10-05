const path = require('path');
const fs = require('fs');
const os = require('os');

if (!process.env.PYRAMID_NODE_MODULES) {
  throw new Error('PYRAMID_NODE_MODULES is required');
}
const { chromium } = require(path.join(process.env.PYRAMID_NODE_MODULES, 'playwright'));

async function main() {
  const input = process.argv[2];
  const screenshot = process.argv[3];
  if (!input || !screenshot) throw new Error('Usage: visual_smoke.cjs <html> <screenshot>');
  const selectedNode = process.env.PYRAMID_SMOKE_NODE || 'TASK-201';
  const launchOptions = { headless: true };
  if (process.env.PYRAMID_BROWSER) launchOptions.executablePath = process.env.PYRAMID_BROWSER;
  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  const qualification = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`file://${path.resolve(input)}`);
  const historySurface = await page.locator('[data-surface="history"]').count();
  if (process.env.PYRAMID_SCREENSHOT_SURFACE === 'history') {
    await page.locator('[data-surface="history"]').click();
    await page.screenshot({ path: screenshot, fullPage: true });
  }
  await page.locator('[data-surface="graph"]').click();
  const focusPressed = await page.locator('[data-view="focus"]').getAttribute('aria-pressed');
  const focusNodeCount = await page.locator('#node-layer .node').count();
  await page.locator('[data-filter="all"]').click();
  const assuranceOverlay = page.locator('[data-overlay="impact"]');
  if (await assuranceOverlay.isEnabled()) await assuranceOverlay.click();
  await page.locator('#node-select').selectOption(selectedNode);
  if (process.env.PYRAMID_SCREENSHOT_SURFACE !== 'history') {
    await page.locator('[data-surface="observer"]').click();
    if (process.env.PYRAMID_EXPECT_PROOF === '1') {
      const proof = await page.locator('#observer-detail').innerText();
      if (!proof.includes('RUN-') || !proof.includes('Candidate inputs:') || !proof.includes('Scope:')) {
        throw new Error('Recorded proof metadata is not reachable from the selected work');
      }
      if (!proof.includes('Not checked against current source')) throw new Error('Display falsely implies current-source verification');
      if (!(await page.locator('#observer-detail a', {hasText: /referenced artifact/}).count())) {
        throw new Error('Resolved proof artifact is not navigable');
      }
    }
    await page.screenshot({ path: screenshot, fullPage: true });
    if (process.env.PYRAMID_DECISION_CHECKS === '1') {
      for (const theme of ['light', 'dark']) {
        await page.emulateMedia({colorScheme:theme,reducedMotion:'reduce'});
        const ratios = await page.evaluate(() => {
          const style=getComputedStyle(document.documentElement);
          function luminance(hex) {
            const values=hex.trim().slice(1).match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
            return .2126*values[0]+.7152*values[1]+.0722*values[2];
          }
          const ratio=(a,b)=>{a=luminance(style.getPropertyValue(a));b=luminance(style.getPropertyValue(b));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
          return {body:ratio('--fg','--bg'),mutedPanel:ratio('--muted','--panel'),mutedBackground:ratio('--muted','--bg'),link:ratio('--focus','--panel'),focus:ratio('--focus','--bg')};
        });
        if (Object.entries(ratios).some(([key,value])=>value<(key==='focus'?3:4.5))) throw new Error(`Contrast failure ${theme}: ${JSON.stringify(ratios)}`);
        await page.screenshot({path:screenshot.replace(/\.png$/,`-${theme}.png`),fullPage:true});
        qualification.push({theme,ratios,reducedMotion:true});
      }
      await page.emulateMedia({colorScheme:'light',reducedMotion:'reduce'});
      await page.locator('[data-surface="observer"]').focus();
      await page.keyboard.press('Tab');
      const keyboard = await page.evaluate(()=>({tag:document.activeElement.tagName,outline:getComputedStyle(document.activeElement).outlineStyle,width:getComputedStyle(document.activeElement).outlineWidth}));
      if (!['BUTTON','A','SUMMARY','SELECT'].includes(keyboard.tag) || keyboard.outline==='none' || keyboard.width==='0px') throw new Error(`Keyboard focus missing: ${JSON.stringify(keyboard)}`);
      qualification.push({keyboard});
      const selectedTree=page.locator('#structure-tree .tree-node.selected');
      const selectedTitle=await page.locator('#observer-detail h2').innerText();
      await selectedTree.focus();
      await page.keyboard.press('Enter');
      if(await page.locator('#observer-detail h2').innerText()!==selectedTitle)throw new Error('Keyboard tree activation lost detail');
      const proofSummary=page.locator('#observer-detail [data-proof-id] > summary').first();
      if(await proofSummary.count()) {
        await proofSummary.focus();
        const before=await proofSummary.evaluate(el=>el.parentElement.open);
        await page.keyboard.press('Enter');
        if(await proofSummary.evaluate(el=>el.parentElement.open)===before)throw new Error('Keyboard evidence disclosure failed');
        await page.keyboard.press('Enter');
      }
      qualification.push({keyboardTreeActivation:true,keyboardProofDisclosure:!!(await proofSummary.count())});
      const semantic=await page.evaluate(()=>{
        const d=document.querySelector('#observer-detail'),tree=document.querySelector('#structure-tree');
        return {detailBeforeTree:!!(d.compareDocumentPosition(tree)&Node.DOCUMENT_POSITION_FOLLOWING),arrows:[...document.querySelectorAll('.outcome-step')].some(el=>getComputedStyle(el,'::after').content.includes('→'))};
      });
      if (!semantic.detailBeforeTree || semantic.arrows) throw new Error(`False hierarchy/sequence: ${JSON.stringify(semantic)}`);
      qualification.push({semantic});
      if((await page.locator('#observer-detail').innerText()).includes('Execution: Awaiting audit'))throw new Error('Execution must not imply pending acceptance after a recorded pass');
      const images = page.locator('#observer-detail .evidence-capture img');
      if (process.env.PYRAMID_EXPECT_CAPTURE==='1' && !(await images.count())) throw new Error('Claim-linked capture preview missing');
      for(let i=0;i<await images.count();i++) {
        const image=images.nth(i);
        if (!(await image.isVisible())) continue;
        await image.scrollIntoViewIfNeeded();
        await image.evaluate(img=>new Promise((resolve,reject)=>img.complete?(img.naturalWidth?resolve():reject(new Error('Broken capture'))):(img.addEventListener('load',resolve,{once:true}),img.addEventListener('error',()=>reject(new Error('Broken capture')),{once:true}))));
        qualification.push({capture:await image.getAttribute('src'),loaded:true});
        await image.locator('..').locator('..').screenshot({path:screenshot.replace(/\.png$/,`-claim-capture-${i}.png`)});
      }
      await page.screenshot({path:screenshot.replace(/\.png$/,'-capture.png'),fullPage:true});
      await page.setViewportSize({width:1280,height:900});
      await page.evaluate(()=>document.documentElement.style.zoom='200%');
      await page.screenshot({path:screenshot.replace(/\.png$/,'-zoom200.png'),fullPage:true});
      const zoomOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth);
      if(zoomOverflow)throw new Error('Horizontal overflow with actual 200% CSS zoom');
      qualification.push({cssZoom:'200%',overflow:false,nativeBrowserToolbarZoom:'not-tested'});
      await page.evaluate(()=>document.documentElement.style.zoom='');
    }
    for (const width of (process.env.PYRAMID_CAPTURE_WIDTHS || '').split(',').filter(Boolean).map(Number)) {
      await page.setViewportSize({width, height:900});
      await page.screenshot({path: screenshot.replace(/\.png$/, `-${width}.png`), fullPage:true});
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
      if (overflow) throw new Error(`Horizontal overflow at ${width}px`);
      const clipping = await page.locator('.proof-grid').evaluateAll(items=>items.some(el=>el.scrollWidth>el.clientWidth));
      if(clipping)throw new Error(`Proof metrics clipped at ${width}px`);
    }
    await page.locator('[data-surface="graph"]').click();
  }
  await page.locator('[data-view="pyramid"]').click();
  const nodeCount = await page.locator('#node-layer .node').count();
  const detail = await page.locator('#detail').innerText();
  const meta = await page.locator('#page-meta').innerText();
  const reworkFilter = await page.locator('[data-filter="needs-rework"]').count();
  const pausedFilter = await page.locator('[data-filter="paused"]').count();
  const workPackageFilter = await page.locator('[data-filter="work-package"]').count();
  const assuranceFilter = await page.locator('[data-filter="assurance-blocked"]').count();
  const assurancePanel = await page.locator('#assurance-panel.visible').count();
  await browser.close();
  if(process.env.PYRAMID_DECISION_CHECKS==='1') {
    // Chromium stores page zoom by storage-partition key. Use an owned profile,
    // never the user's profile; measure actual zoom instead of trusting a setting.
    const profile=fs.mkdtempSync(path.join(os.tmpdir(),'pyramid-visual-zoom-'));
    fs.mkdirSync(path.join(profile,'Default'));
    fs.writeFileSync(path.join(profile,'Default','Preferences'),JSON.stringify({partition:{default_zoom_level:{x:Math.log(2)/Math.log(1.2)}}}));
    const context=await chromium.launchPersistentContext(profile,{...launchOptions,viewport:null,args:['--window-size=1280,900']});
    try {
      const zoomPage=context.pages()[0];
      await zoomPage.goto(`file://${path.resolve(input)}`);
      await zoomPage.locator('[data-surface="graph"]').click();
      await zoomPage.locator('#node-select').selectOption(selectedNode);
      await zoomPage.locator('[data-surface="observer"]').click();
      const nativeZoom=await zoomPage.evaluate(()=>({innerWidth,outerWidth,devicePixelRatio,media920:matchMedia('(max-width:920px)').matches,overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth}));
      if(nativeZoom.innerWidth!==640||nativeZoom.outerWidth!==1280||nativeZoom.devicePixelRatio!==2||!nativeZoom.media920||nativeZoom.overflow)throw new Error(`Actual browser zoom/reflow failed: ${JSON.stringify(nativeZoom)}`);
      const session=await context.newCDPSession(zoomPage);
      const capture=await session.send('Page.captureScreenshot',{format:'png'});
      fs.writeFileSync(screenshot.replace(/\.png$/,'-browser-zoom200.png'),Buffer.from(capture.data,'base64'));
      qualification.push({nativePageZoom:'200%',measured:nativeZoom,ownedProfile:profile});
    } finally {await context.close();}
  }
  if (errors.length) throw new Error(`Page errors: ${errors.join('; ')}`);
  if (focusPressed !== 'true') throw new Error('Focus view is not the default');
  if (historySurface !== 1) throw new Error('History Observer surface is missing');
  if (focusNodeCount < 1) throw new Error('Focus view rendered no nodes');
  if (nodeCount < 1) throw new Error('No graph nodes rendered');
  if (!detail.includes(selectedNode)) throw new Error('Selected-node detail did not update');
  if (!detail.includes('Plan lifecycle')) throw new Error('Lifecycle detail is missing');
  if (!['active', 'completed', 'archived'].some(status => meta.includes(status))) {
    throw new Error('Lifecycle summary is missing');
  }
  if (reworkFilter !== 1) throw new Error('Rework filter is missing');
  if (pausedFilter !== 1) throw new Error('Paused filter is missing');
  if (workPackageFilter !== 1) throw new Error('Work-package filter is missing');
  if (assuranceFilter !== 1) throw new Error('Assurance filter is missing');
  if (assurancePanel && !detail.includes('Assurance status')) throw new Error('Assurance detail is missing');
  process.stdout.write(JSON.stringify({ ok: true, nodeCount, screenshot, qualification }) + '\n');
}

main().catch(error => {
  process.stderr.write(error.stack + '\n');
  process.exit(1);
});
