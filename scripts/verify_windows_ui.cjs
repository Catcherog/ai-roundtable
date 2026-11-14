// Exercise the installed WebView2 window through its loopback DevTools endpoint, enabled only in this test.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const net = require('node:net');
const path = require('node:path');
const {spawn, spawnSync} = require('node:child_process');
const {once} = require('node:events');
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function until(fn, ms=30000) {
  const stop = Date.now()+ms; let last;
  while(Date.now()<stop) {try{const value=await fn();if(value)return value;}catch(e){last=e;}await sleep(150);}
  throw Error('Timed out waiting for the desktop UI'+(last?' ('+last.message+')':''));
}
(async()=>{
 const app=path.resolve(process.argv[2]);const state=fs.mkdtempSync(path.join(os.tmpdir(),'roundtable-ui-'));
 const sock=net.createServer();sock.listen(0,'127.0.0.1');await once(sock,'listening');const port=sock.address().port;
 await new Promise(r=>sock.close(r));
 const proc=spawn(path.join(app,'AI-Roundtable.exe'),[],{cwd:app,env:{...process.env,AI_ROUNDTABLE_HOME:state,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:'--remote-debugging-address=127.0.0.1 --remote-debugging-port='+port},stdio:'ignore'});
 let ws;
 try{
  const page=await until(async()=>{assert.equal(proc.exitCode,null);const arr=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();return arr.find(p=>p.type==='page' && /^http:\/\/127\.0\.0\.1:\d+\//.test(p.url));},60000);
  ws=new WebSocket(page.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let seq=0;const pending=new Map();const errors=[];
  ws.onmessage=e=>{const evt=JSON.parse(e.data);if(evt.method==='Runtime.exceptionThrown')errors.push(evt.params.exceptionDetails.text);const c=pending.get(evt.id);if(c){pending.delete(evt.id);evt.error?c.reject(Error(evt.error.message)):c.resolve(evt.result);}};
  const cmd=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const js=async exp=>{const r=await cmd('Runtime.evaluate',{expression:exp,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;};
  await cmd('Runtime.enable');await until(()=>js("!!document.querySelector('#sseConnDot.online')"));
  const openSettings=async()=>{await js("document.getElementById('railSettingsBtn').click()");await until(()=>js("!document.getElementById('settingsModal').classList.contains('hidden')"));};
  const save=async()=>{await js("document.getElementById('saveSettingsBtn').click()");await until(()=>js("document.getElementById('settingsModal').classList.contains('hidden')"));};
  await openSettings();await js("document.querySelector('[data-settings-tab=seats]').click();const f=document.getElementById('cfgCarbonModel');f.value='gemini-4-argon';f.dispatchEvent(new Event('change',{bubbles:true}));document.getElementById('cfgCarbonEffort').value='medium';");await save();
  const prev=await js('performance.timeOrigin');await cmd('Page.reload');
  await until(()=>js("performance.timeOrigin!=="+prev+" && !!document.querySelector('#sseConnDot.online')"));
  await openSettings();assert.equal(await js("document.getElementById('cfgCarbonModel').value"),'gemini-4-argon');
  assert.equal(await js("document.getElementById('cfgCarbonEffort').value"),'medium');
  for(const [key,count] of [['full_jury_6',6],['classic_triad',3]]){
    await js("document.querySelector('[data-settings-tab=lineup]').click();document.querySelector('[data-modal-lineup="+key+"]').click();");await save();
    await until(()=>js("document.getElementById('ringSeatCountLabel').textContent.startsWith('"+count+"')"));if(count===6)await openSettings();
  }
  const stored=JSON.parse(fs.readFileSync(path.join(state,'config.json'),'utf8'));assert.equal(stored.agents.carbon.model,'gemini-4-argon');assert.deepEqual(errors,[]);
  console.log('PASS native Windows EXE, WebView2 trust bridge, live SSE, saved model after reload, six-to-three roster');
 }finally{
  if(ws)ws.close();
  // Deliberately stop only the fixture UI; its Windows Job owns the backend and CLI tree.
  if(proc.exitCode===null){proc.kill();await Promise.race([once(proc,'exit'),sleep(4000)]);}
  fs.rmSync(state,{recursive:true,force:true,maxRetries:8,retryDelay:250});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
