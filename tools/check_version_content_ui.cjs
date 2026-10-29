const {chromium}=require(process.argv[2]),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const info=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const cases=['normal','wrong_version','wrong_section','bad_page_hash','changed_next_source','stale','missing','bad_flags','late_old_version'];
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true}),proof=[];let writes=0,foreign=0;
try{for(const mode of cases){const page=await browser.newPage({viewport:{width:1530,height:1150}}),errors=[];let reads=0,release,arrived;const pending=new Promise(r=>arrived=r);
 page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==info.base){foreign++;return route.abort()}if(req.method()!=='GET'){writes++;return route.abort()}
  if(!u.pathname.endsWith('/content'))return route.continue();reads++;
  if(mode==='stale')return route.fulfill({status:409,json:{detail:'公开合成来源已变'}});
  if(mode==='missing')return route.fulfill({status:404,json:{detail:'公开合成未保存'}});
  const response=await route.fetch(),v=await response.json();assert.equal(response.status(),200);
  if(mode==='late_old_version'&&u.pathname.includes(info.old_version_id)){arrived();await new Promise(r=>release=r);try{return await route.fulfill({response,json:v})}catch{return}}
  if(mode==='wrong_version')v.version_id=info.other_version_id;
  if(mode==='wrong_section')v.section='configuration';
  if(mode==='bad_page_hash')v.page_sha256='0'.repeat(64);
  if(mode==='changed_next_source'&&u.searchParams.get('offset')!=='0')v.content_sha256='0'.repeat(64);
  if(mode==='bad_flags')v.network_requested=true;
  return route.fulfill({response,json:v});
 });
 await page.goto(info.base,{waitUntil:'networkidle'});await page.locator('.task-item').filter({hasText:info.task_name}).click();await page.locator('.steps button').filter({hasText:'历史'}).click();
 await page.locator('.version').filter({hasText:'旧版公开长正文'}).getByRole('button',{name:'比较与恢复',exact:true}).click();await page.locator('.restore-preview h4').first().waitFor();const panel=page.locator('.version-content-panel');assert.equal(reads,0,'Compare must not automatically read historical bodies');await panel.locator('summary').click();assert.equal(reads,0,'Opening the reader must not fetch before explicit selection');await panel.getByRole('button',{name:'读取所选历史正文（只读）',exact:true}).click();
 if(mode==='normal'||mode==='changed_next_source'){
  await panel.locator('pre').waitFor();assert.equal(await panel.locator('pre').innerText(),Array.from(info.old_requirements).slice(0,4000).join(''));
  await panel.getByRole('button',{name:'下一页历史正文',exact:true}).click();
  if(mode==='changed_next_source'){await panel.getByRole('alert').waitFor();assert.equal(await panel.locator('pre').count(),0)}
  else{await page.waitForFunction(expected=>document.querySelector('.version-content-panel pre')?.textContent===expected,Array.from(info.old_requirements).slice(4000,8000).join(''));assert.equal(await panel.locator('pre').innerText(),Array.from(info.old_requirements).slice(4000,8000).join(''));await panel.getByRole('button',{name:'上一页历史正文',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.version-content-panel pre')?.textContent.startsWith('{'));assert.equal(await panel.locator('pre').innerText(),Array.from(info.old_requirements).slice(0,4000).join(''));await panel.getByLabel('历史正文分区').selectOption('configuration');assert.equal(await panel.locator('pre').count(),0);await panel.getByRole('button',{name:'读取所选历史正文（只读）',exact:true}).click();await panel.locator('pre').waitFor();assert((await panel.locator('pre').innerText()).includes('9007199254740993'),'Saved large number must remain exact text');await panel.getByLabel('历史正文分区').selectOption('workflow_plan');await panel.getByRole('button',{name:'读取所选历史正文（只读）',exact:true}).click();await panel.locator('pre').waitFor();assert((await panel.locator('pre').innerText()).includes('<script>'));assert.equal(await panel.locator('pre script').count(),0);assert.equal(await page.evaluate(()=>globalThis.__historyCodeRan),undefined);await panel.screenshot({path:path.join(info.output,'version-content-ui.png')})}
 }else if(mode==='late_old_version'){
  await pending;await page.locator('.version').filter({hasText:'另一份公开快照'}).getByRole('button',{name:'比较与恢复',exact:true}).click();await page.locator('.restore-preview h4').first().waitFor();const next=page.locator('.version-content-panel');if(!(await next.getByRole('button',{name:'读取所选历史正文（只读）',exact:true}).isVisible()))await next.locator('summary').click();await next.getByRole('button',{name:'读取所选历史正文（只读）',exact:true}).click();await next.locator('pre').waitFor();assert.equal(await next.locator('pre').innerText(),info.other_requirements);release();await page.waitForTimeout(200);assert.equal(await next.locator('pre').innerText(),info.other_requirements,'Old response must not overwrite newly selected snapshot');
 }else{await panel.getByRole('alert').waitFor();assert.equal(await panel.locator('pre').count(),0);await page.waitForTimeout(100);assert.equal(reads,1,'Failure must not retry')}
 assert.deepEqual(errors,[]);proof.push({case:mode,content_reads:reads,restore_requests:0});await page.close();}
assert.equal(writes,0);assert.equal(foreign,0);fs.writeFileSync(path.join(info.output,'proof.json'),JSON.stringify({state:'passed',cases:proof,mutating_requests:writes,foreign_requests:foreign},null,2));console.log(JSON.stringify({state:'passed',cases:proof.length,mutating_requests:0,foreign_requests:0}));
}finally{await browser.close()}})().catch(e=>{console.error(e.stack);process.exitCode=1});
