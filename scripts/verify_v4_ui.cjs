// UI regression against the real HTTP server. Only agent answers are replaced by a test double.
// Requires playwright-core and a matching Chromium (optional PLAYWRIGHT_CHROMIUM_EXECUTABLE).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {randomBytes} = require('node:crypto');
const {chromium} = require('playwright-core');
const root = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const py = `import asyncio,os,socket,signal,sys
from backend.server import AsyncHTTPServer,MAX_REQUEST_LINE_BYTES,MAX_HEADER_LINE_BYTES
async def main():
    s=socket.socket(); s.bind(('127.0.0.1',0)); p=s.getsockname()[1]
    app=AsyncHTTPServer('127.0.0.1',p,workspace_dir=os.environ['RT_UI_PROJECT'])
    async def fixture(**kwargs):
        yield {'type':'done','full_text':'UI fixture complete','badge':'完成','ttft_ms':1,'elapsed_ms':1}
    app.orchestrator.runner.stream_discussion_turn=fixture
    server=await asyncio.start_server(app.handle_client,sock=s,limit=max(MAX_REQUEST_LINE_BYTES,MAX_HEADER_LINE_BYTES)+256)
    print(p,flush=True)
    stop=asyncio.Event(); asyncio.get_running_loop().add_signal_handler(signal.SIGTERM,stop.set)
    try: await stop.wait()
    finally:
        server.close(); await server.wait_closed(); await app.orchestrator.shutdown()
asyncio.run(main())`;
function checkDOM() {
  const files=['app.js','v4_ui.js'].map(f=>fs.readFileSync(path.join(root,'frontend',f),'utf8'));
  const html=fs.readFileSync(path.join(root,'frontend','index.html'),'utf8');
  const ids=[...html.matchAll(/\sid="([^"]+)"/g)].map(m=>m[1]), known=new Set(ids);
  assert.equal(ids.length,known.size,'Duplicate HTML IDs');
  const refs=new Set(), seats=['Carbon','Grok','Astra','Vega','Titan','Prism'];
  for(const src of files){
    for(const m of src.matchAll(/(?:\bel|\$id|\bgetElementById)\(\s*["']([^"']+)["']\s*\)/g)) refs.add(m[1]);
    for(const m of src.matchAll(/(?:\bel|\$id|\bgetElementById)\(\s*`([^`]+)`\)/g)){
      const key=m[1];
      if(key.startsWith('msg-') || key.startsWith('wb-editor-')) continue; // created when the message/editor is rendered
      for(const seat of seats){
        let x=key.replace(/\$\{(?:cap|seatCap)\}/g,seat).replace(/\$\{(?:agentId|aid|msg\.speaker)\}/g,seat.toLowerCase());
        if(x==='settings-pane-${k}') for(const tab of ['seats','concurrency','diagnostics']) refs.add('settings-pane-'+tab);
        else refs.add(x);
      }
    }
  }
  assert.ok(files[0].includes('id="wbTopicEditInput"') && files[0].includes('card.id = `msg-${msg.id}`') && files[0].includes('wb-editor-'));
  const missing=[...refs].filter(id=>id!=='wbTopicEditInput'&&!known.has(id));
  assert.deepEqual(missing,[],'Missing DOM references');
  console.log('PASS DOM: '+known.size+' unique HTML IDs, '+refs.size+' static/expanded references and dynamic message/editor IDs');
}
async function run(){
  checkDOM();
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'roundtable-v4-ui-'));
  const project=path.join(tmp,'project'); fs.mkdirSync(project);
  const code=randomBytes(24).toString('hex');
  const server=spawn(process.env.PYTHON || 'python3',['-u','-c',py],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',AI_ROUNDTABLE_HOME:path.join(tmp,'state'),AI_ROUNDTABLE_BOOTSTRAP_CODE:code,RT_UI_PROJECT:project},stdio:['ignore','pipe','inherit']});
  let browser;
  try{
    const port=await new Promise((resolve,reject)=>{
      let data='';const timer=setTimeout(()=>reject(Error('UI server startup timeout')),20000);
      server.stdout.on('data',b=>{data+=b;if(/^\d+\n/.test(data)){clearTimeout(timer);resolve(Number(data.split('\n')[0]));}});
      server.once('exit',code=>{clearTimeout(timer);reject(Error('server exited '+code));});server.once('error',reject);
    });
    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});
    const page=await browser.newPage({viewport:{width:1500,height:920}}); page.setDefaultTimeout(8000);
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto('http://127.0.0.1:'+port+'/#bootstrap='+code,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('#sseConnDot.online',{state:'attached',timeout:20000});
    const activeTab=()=>page.locator('#settingsNav .active').getAttribute('data-settings-tab');
    await page.locator('#railSettingsBtn').click();
    assert.equal(await activeTab(),'seats');
    assert.equal(await page.locator('#cfgShowAllSixSeats').isChecked(),false);
    const visible=()=>page.locator('[data-cfg-seat-card]:visible').evaluateAll(nodes=>nodes.map(n=>n.dataset.cfgSeatCard));
    const enabled=await page.locator('[data-cfg-seat-enable]:checked').evaluateAll(nodes=>nodes.map(n=>n.dataset.cfgSeatEnable));
    assert.deepEqual(await visible(),enabled);assert.equal(enabled.length,3);
    await page.locator('#cfgShowAllSixSeats').check();assert.equal((await visible()).length,6);
    await page.locator('#cfgShowAllSixSeats').uncheck();assert.deepEqual(await visible(),enabled);
    await page.locator('#v4ModelChipsCarbon [data-chip-model="gemini-4-argon"]').click();
    assert.equal(await page.locator('#cfgCarbonModel').inputValue(),'gemini-4-argon');
    await page.locator('#cfgCarbonModel').evaluate(el=>{el.value='gemini-4-carbon';el.dispatchEvent(new Event('input',{bubbles:true}));});
    await page.waitForSelector('#v4ModelChipsCarbon [data-chip-model="gemini-4-carbon"].active',{state:'attached'});
    await page.locator('#v4EffortSegCarbon [data-eff-val="medium"]').click();
    assert.equal(await page.locator('#cfgCarbonEffort').inputValue(),'medium');
    assert.equal(await page.locator('#cfgCarbonExecEffort').inputValue(),'medium');
    await page.locator('#cfgCarbonEffort').evaluate(el=>{el.value='high';el.dispatchEvent(new Event('change',{bubbles:true}));});
    await page.waitForSelector('#v4EffortSegCarbon [data-eff-val="high"].active',{state:'attached'});
    await page.locator('[data-settings-tab=diagnostics]').click();
    await page.locator('#closeSettingsBtn').click();
    await page.evaluate(()=>window.__roundtableMenu('settings'));assert.equal(await activeTab(),'seats');
    assert.equal(await page.locator('#v4ModelChipsCarbon .active').count(),1);
    await page.locator('[data-modal-lineup="solo_focus"]').click();
    await page.locator('#closeSettingsBtn').click();
    assert.match(await page.locator('[data-scenario-pack="arch_code"] .scenario-mode-tag').innerText(), /当前 3 席/);
    console.log('PASS settings: rail and native menu default seats, 3/6 filter, model and effort round-trip');

    const calls=[];
    let releaseSlow;
    const holdSlow=new Promise(resolve=>{releaseSlow=resolve;});
    await page.route('**/api/cli/test', async route=>{
      const data=route.request().postDataJSON(), aid=data.agent_id;
      calls.push(aid);
      const fail=aid==='astra' && calls.filter(a=>a==='astra').length===1;
      if (fail) await holdSlow;
      const result=fail ? {ok:false,error_kind:'service_unavailable',error:'模型服务暂时没有可用容量（503）'}
        : {ok:true,elapsed_ms:400,request_elapsed_ms:390,reply:'连接正常'};
      await route.fulfill({json:{results:{[aid]:result}}});
    });
    await page.locator('#readySummaryBar').click();
    await page.locator('#testCliBtn').click();
    await page.waitForFunction(()=>document.querySelector('#readySummaryBar').textContent.includes('2 席实测通过'));
    assert.match(await page.locator('#readySummaryBar').innerText(),/1 席实测中/);
    releaseSlow();
    await page.waitForFunction(()=>document.querySelector('#seat-badge-astra').textContent==='服务繁忙');
    assert.match(await page.locator('#readySummaryBar').innerText(),/1 席实测未通过/);
    assert.deepEqual([...calls].sort(),['astra','carbon','grok']);
    await page.locator('#cliEngineCards .cli-retest-btn').click();
    await page.waitForFunction(()=>document.querySelector('#readySummaryBar').textContent.includes('3 席实测通过'));
    assert.deepEqual(calls.slice(3),['astra']);
    await page.locator('#openSettingsBtn').click();
    await page.locator('[data-cfg-seat-enable=grok]').uncheck();
    await page.locator('[data-cfg-seat-enable=astra]').uncheck();
    await page.locator('#v4ModelChipsCarbon [data-chip-model="gemini-4-argon"]').click();
    assert.equal(await page.locator('#cfgStatusCarbon').textContent(),'待实测');
    await page.locator('#modalTestCliBtn').click();
    await page.waitForFunction(()=>document.querySelector('#cfgStatusCarbon').textContent==='实测通过');
    assert.deepEqual(calls.slice(4),['carbon']);
    await page.locator('#cancelSettingsBtn').click();
    assert.match(await page.locator('#readySummaryBar').textContent(),/3 席实测通过/);
    const ws=await page.locator('#workspaceBadge').getAttribute('title');
    assert.equal(ws,project);
    await page.locator('[data-scenario-pack=incident_doc]').click();
    await page.waitForFunction(()=>document.querySelector('#readySummaryBar').textContent.startsWith('2 席 ·'));
    assert.equal(await page.locator('#workspaceBadge').getAttribute('title'),ws);
    await page.locator('#openSettingsBtn').click();
    await page.locator('[data-modal-lineup=full_jury_6]').click();
    await page.locator('#saveSettingsBtn').click();
    await page.waitForFunction(()=>document.querySelector('[data-scenario-pack=incident_doc] .scenario-mode-tag').textContent.includes('当前 6 席'));
    assert.equal(await page.locator('#cliEngineCards .cli-card').count(),6);
    await page.locator('[data-scenario-pack=arch_code]').click();
    await page.waitForFunction(()=>document.querySelector('#readySummaryBar').textContent.startsWith('3 席 ·'));
    console.log('PASS partial results, 503, single-seat retry, draft scope, cancelled settings, actual lineup and project retained');
    const chooserReady=page.waitForEvent('filechooser');
    await page.locator('#v4PlusAttachBtn').click();
    await page.locator('[data-v4-attach-cmd=file]').click();
    const chooser=await chooserReady;
    await chooser.setFiles({name:'probe.py',mimeType:'text/plain',buffer:Buffer.from('answer = 42\n')});
    await page.waitForSelector('#v4AttachmentTray .v4-att-card:not(.is-uploading)');
    await page.evaluate(async()=>{
      const canvas=document.createElement('canvas');canvas.width=640;canvas.height=360;
      const ctx=canvas.getContext('2d');ctx.fillStyle='teal';ctx.fillRect(0,0,640,360);
      const blob=await new Promise(r=>canvas.toBlob(r,'image/png'));
      const dt=new DataTransfer();dt.items.add(new File([blob],'shot.png',{type:'image/png'}));
      document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
    });
    await page.waitForFunction(()=>document.querySelectorAll('#v4AttachmentTray .v4-att-card:not(.is-uploading)').length===2);
    await page.evaluate(()=>{
      const dt=new DataTransfer();dt.items.add(new File(['synthetic log\n'],'run.log',{type:'text/plain'}));
      window.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}));
    });
    await page.waitForFunction(()=>document.querySelectorAll('#v4AttachmentTray .v4-att-card:not(.is-uploading)').length===3);
    assert.equal(await page.locator('#topicInput').inputValue(),'');
    const sent=page.waitForResponse(r=>r.request().method()==='POST' && /\/start$/.test(r.url()));
    await page.locator('#primaryActionBtn').click();
    const reply=await sent, req=reply.request().postDataJSON();assert.equal(reply.status(),200);assert.equal(new Set(req.attachment_ids).size,3);
    await page.waitForFunction(()=>document.querySelectorAll('.v4-msg-attachments .v4-msg-img-card').length===1 && document.querySelectorAll('.v4-msg-attachments .v4-msg-doc-pill').length===2);
    assert.equal(await page.locator('#v4AttachmentTray .v4-att-card').count(),0);
    const img=page.locator('.v4-msg-img-card img').first();await img.click();
    assert.equal(await page.locator('#v4LightboxModal').isVisible(),true);
    await page.locator('#v4LightboxCloseBtn').click();
    if (!await page.locator('#exportMdBtn').isVisible()) {
      await page.locator('#toggleRightBtn').click();
    }
    const downloadReady=page.waitForEvent('download');
    await page.locator('#exportMdBtn').click();
    const download=await downloadReady;
    const minutes=fs.readFileSync(await download.path(),'utf8');
    assert.match(minutes,/probe\.py/);assert.match(download.suggestedFilename(),/\.md$/);
    console.log('PASS downloaded meeting minutes contain the actual attachment topic');
    assert.deepEqual(errors,[]);
    console.log('PASS picker, synthetic screenshot paste and log drop, 3 files in authenticated start, persisted gallery and preview; no JS errors');
  } finally {
    if(browser)await browser.close();
    if(server.exitCode===null && !server.signalCode){const ended=once(server,'exit');server.kill('SIGTERM');await ended;}
    fs.rmSync(tmp,{recursive:true,force:true});
  }
}
run().catch(e=>{console.error(e);process.exitCode=1;});
