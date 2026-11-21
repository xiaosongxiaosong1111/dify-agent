// Real built-App acceptance for reading a trusted import source from history; loopback static App only.
const {chromium}=require(process.argv[2]),fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const info=JSON.parse(fs.readFileSync(process.argv[3],'utf8')),origin=new URL(info.base).origin;
const taskPath=id=>`/api/tasks/${id}`;
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({viewport:{width:1500,height:1100}});
 const errors=[],writes=[];let foreign=0,unexpected=0;page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const request=route.request(),url=new URL(request.url());
  if(url.origin!==origin){foreign++;return route.abort()}
  if(request.method()==='GET')return route.continue();
  if(request.method()==='POST'&&url.pathname===taskPath(info.positive.id)+'/dsl-reference'){writes.push({method:request.method(),path:url.pathname,body:JSON.parse(request.postData()||'{}')});return route.continue()}
  unexpected++;return route.abort();
 });
 const waitEnabled=async locator=>{for(let i=0;i<200;i++){if(await locator.isEnabled())return true;await page.waitForTimeout(50)}return false};
 const waitIdle=async name=>{await page.locator('h1').filter({hasText:name}).waitFor();for(let i=0;i<200;i++){if(await page.locator('.busy').count()===0)return;await page.waitForTimeout(50)}throw Error('任务加载后仍处于忙碌状态：'+name)};
 const readTask=id=>page.evaluate(async taskId=>{const response=await fetch('/api/tasks/'+encodeURIComponent(taskId),{cache:'no-store'});if(!response.ok)throw Error('读取任务失败');return response.json()},id);
 try{
  await page.goto(info.base,{waitUntil:'networkidle'});
  await page.locator('.task-item').filter({hasText:info.positive.name}).waitFor();
  await page.locator('.task-item').filter({hasText:info.positive.name}).click();
  await waitIdle(info.positive.name);
  const before=await readTask(info.positive.id);
  assert.equal(before.dify_app_id??null,null,'读取前不应有当前 App');
  assert.equal(before.dsl_reference??null,null,'读取前不应有参考来源');
  assert(before.runs.some(run=>run.kind==='import'&&run.status==='success'),'读取前应有成功导入历史');
  assert(before.workflow_plan,'读取前应保留完整代码计划');
  assert(Object.values(before.requirements||{}).every(value=>String(value||'').trim()),'读取前公开需求应非空');
  await page.locator('.steps button').filter({hasText:'构建'}).click();
  const panel=page.locator('.dsl-roundtrip');await panel.waitFor();
  const readButton=panel.getByRole('button',{name:'读取当前 Dify 编辑草稿',exact:true});
  await readButton.waitFor();
  assert.equal(await waitEnabled(readButton),true,'有可信导入历史且无当前 App 时读取按钮应启用');
  const readWait=page.waitForResponse(response=>new URL(response.url()).pathname===taskPath(info.positive.id)+'/dsl-reference'&&response.request().method()==='POST');
  await readButton.click();
  const readResponse=await readWait;
  if(readResponse.status()!==200)throw Error('读取当前 Dify 编辑草稿失败：'+await readResponse.text());
  const body=await readResponse.json(),task=body.task??body;
  assert(task.dsl_reference,'读取后应有参考来源');
  assert.equal(task.dsl_reference.source_app_id,info.known_app_id,'读取来源应为成功导入的已知 App');
  assert.equal(task.dsl_reference.source,'dify_draft','读取来源应为实际 Dify 草稿');
  assert.equal(task.dify_app_id??null,null,'读取不应伪造当前 App ID');
  assert(task.revision>info.positive.initial_revision,'读取后修订应增加');
  assert.equal(writes.length,1,'读取只应派发一次引用请求');
  assert.equal(writes[0].path,taskPath(info.positive.id)+'/dsl-reference');
  assert.deepEqual(writes[0].body,{revision:info.positive.initial_revision},'读取请求体只应包含当前修订');
  await page.screenshot({path:path.join(info.output,'ui-dsl-source-history.png')});
  const negatives=[['nohistory',info.negative_no_history,'无成功导入历史时读取按钮应禁用'],['noenv',info.negative_no_environment,'无当前环境时读取按钮应禁用']];
  const negativeProof={};
  for(const [key,fixture,message] of negatives){
   await page.locator('.task-item').filter({hasText:fixture.name}).click();
   await waitIdle(fixture.name);
   await page.locator('.steps button').filter({hasText:'构建'}).click();
   const negativePanel=page.locator('.dsl-roundtrip');await negativePanel.waitFor();
   const negativeButton=negativePanel.getByRole('button',{name:'读取当前 Dify 编辑草稿',exact:true});
   await negativeButton.waitFor();
   assert.equal(await negativeButton.isDisabled(),true,message);
   negativeProof[key]={disabled:true,task_id:fixture.id};
  }
  assert.deepEqual(errors,[]);assert.equal(foreign,0);assert.equal(unexpected,0);
  fs.writeFileSync(path.join(info.output,'ui-proof.json'),JSON.stringify({
   state:'passed',scope:'actual built App integration; task/environment/import receipt preseeded via local API and temporary Store',
   base:info.base,setup_disclosed_not_full_import_or_pure_ui:true,seed_note:info.seed_note,
   positive:{task_id:info.positive.id,task_name:info.positive.name,initial_revision:info.positive.initial_revision,
    had_current_app:false,had_reference:false,button_enabled:true,
    read_revision:task.revision,reference_source:task.dsl_reference.source,reference_source_app_id:task.dsl_reference.source_app_id},
   negative:negativeProof,screenshot:'ui-dsl-source-history.png',write_requests:writes,
   foreign_requests:foreign,unexpected_requests:unexpected,page_errors:errors,
   fake_dify_export_only:true,model_dify_http:0,production_data_changed:false},null,2));
  console.log(JSON.stringify({state:'passed',read_revision:task.revision,reference_source_app_id:task.dsl_reference.source_app_id,writes:writes.length}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
