// Render the independent build; upstream requests are restricted to local GETs.
const {chromium}=require(process.argv[2]),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const project=path.resolve(__dirname,'..'),dist=path.resolve(process.argv[3]),output=path.resolve(process.argv[4]);
assert(dist.startsWith(path.join(project,'work')+path.sep));assert(output.startsWith(path.join(project,'work')+path.sep));fs.mkdirSync(output,{recursive:true});
const id='aa827c91-b683-4a34-9e7f-fa0789f5c252',name='Sierra新空任务完整交付验收';
const cases=[
 ['saved','已有保存流程，可直接核对节点'],
 ['stale','已有保存流程，请先复核过期内容'],
 ['blank','先让 Sierra 准备完整流程，再核对节点'],
 ['unknown','先核实当前保存流程，再决定是否生成'],
 ['loading','正在读取当前保存的流程'],
 ['draft','先核对并保存本页流程草稿'],
];
(async()=>{const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://local'),file=path.resolve(dist,'.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));if(!file.startsWith(dist+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end()}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');fs.createReadStream(file).pipe(res)});await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port,browser=await chromium.launch({channel:'msedge',headless:true});let writes=0,foreign=0;const proof=[];
 try{for(const [mode,heading] of cases){const page=await browser.newPage({viewport:{width:1500,height:1100}}),errors=[];let release,waiting,planReads=0;page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());if(url.origin!==origin){foreign++;return route.abort()}if(req.method()!=='GET'){writes++;return route.abort()}if(!url.pathname.startsWith('/api/'))return route.continue();const isPlan=url.pathname===`/api/tasks/${id}/plan`,isTask=url.pathname===`/api/tasks/${id}`;
  if(isPlan){planReads++;if(mode==='loading'){waiting=new Promise(r=>release=r);await waiting}if(mode==='unknown')return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'公开合成读取失败'})})}
  const response=await route.fetch({url:'http://127.0.0.1:8765'+url.pathname+url.search});
  if((isTask||isPlan)&&response.ok()){const value=await response.json();if(isTask){value.plan_stale=mode==='stale';if(['blank','unknown','loading'].includes(mode)){value.workflow_plan=null;value.plan_text=null}}else{value.stale=mode==='stale';if(mode==='blank'){value.plan=null;value.plan_text=null}}return route.fulfill({response,json:value})}return route.fulfill({response});
 });
 await page.goto(origin,{waitUntil:'networkidle'});await page.locator('.task-item').filter({hasText:name}).click();await page.locator('h1').filter({hasText:name}).waitFor();await page.locator('.steps button').filter({hasText:'流程'}).click();const panel=page.locator('.main-plan-action'),editor=page.locator('textarea.plan-editor');
 if(mode==='draft'){await editor.waitFor();await assert.doesNotReject(()=>editor.inputValue());await page.waitForFunction(()=>!document.querySelector('textarea.plan-editor').disabled);const text=await editor.inputValue();assert(text.includes('nodes'));await editor.fill(text+'\n ')}
 await panel.locator('b').getByText(heading,{exact:true}).waitFor();assert.match(await panel.innerText(),/计入助手预算/);assert.match(await panel.innerText(),/不代表已确认配置或已在Dify运行/);
 if(['saved','stale'].includes(mode))assert.match(await panel.locator('button').innerText(),/重新生成/);
 if(['draft','loading'].includes(mode))assert.equal(await panel.locator('button').isDisabled(),true);
 if(mode==='draft'){const text=await editor.inputValue();await page.locator('.steps button').filter({hasText:'配置'}).click();await page.locator('.steps button').filter({hasText:'流程'}).click();await panel.locator('b').getByText(heading,{exact:true}).waitFor();assert.equal(await editor.inputValue(),text,'Readback must preserve unsaved draft')}
 if(mode==='saved')await page.screenshot({path:path.join(output,'saved-guidance.png')});
 if(release)release();await page.waitForTimeout(200);assert.deepEqual(errors,[]);assert(planReads>=1);proof.push({mode,heading,plan_reads:planReads});await page.close();}
 assert.equal(writes,0);assert.equal(foreign,0);fs.writeFileSync(path.join(output,'proof.json'),JSON.stringify({state:'passed',cases:proof,mutating_requests:writes,foreign_requests:foreign,model_dify_http:0,production_data_changed:false},null,2));console.log(JSON.stringify({state:'passed',cases:proof.length,mutating_requests:writes,foreign_requests:foreign}));
 }finally{await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
