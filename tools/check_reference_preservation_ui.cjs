// Real built-App acceptance for reference preservation; loopback static App only.
const {chromium}=require(process.argv[2]),fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const info=JSON.parse(fs.readFileSync(process.argv[3],'utf8')),origin=new URL(info.base).origin,taskPath=`/api/tasks/${info.task_id}`;
const escapeRe=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),materialPatch=new RegExp(`^${escapeRe(taskPath)}/materials/[^/]+$`);
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({viewport:{width:1500,height:1100}});
 const errors=[],writes=[];let foreign=0,unexpected=0;page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const request=route.request(),url=new URL(request.url());
  if(url.origin!==origin){foreign++;return route.abort()}
  if(request.method()==='GET')return route.continue();
  if(request.method()==='POST'&&[`${taskPath}/reference-dsl/preview`,`${taskPath}/reference-dsl/adopt`].includes(url.pathname)){writes.push(`${request.method()} ${url.pathname}`);return route.continue()}
  if(request.method()==='PATCH'&&materialPatch.test(url.pathname)){writes.push(`${request.method()} ${url.pathname}`);return route.continue()}
  unexpected++;return route.abort();
 });
 try{
  await page.goto(info.base,{waitUntil:'networkidle'});
  const taskItem=page.locator('.task-item').filter({hasText:info.task_name});await taskItem.waitFor();await taskItem.click();
  await page.locator('h1').filter({hasText:info.task_name}).waitFor();
  await page.locator('.steps button').filter({hasText:'需求'}).click();
  const panel=page.locator('.reference-dsl-panel');await panel.waitFor();
  const previewWait=page.waitForResponse(response=>new URL(response.url()).pathname===`${taskPath}/reference-dsl/preview`&&response.request().method()==='POST');
  await panel.locator('.upload-reference input[type=file]').setInputFiles(info.source_yaml);
  const preview=await previewWait;if(preview.status()!==200)throw Error('参考 DSL 预览失败：'+await preview.text());
  await panel.getByLabel('DSL 参考方式',{exact:true}).selectOption('preserve');
  await panel.getByLabel('必须保留的节点、规则或内容',{exact:true}).fill('保留完整代码与模板转换节点配置');
  const codeBox=panel.locator('input[type=checkbox][aria-label*="（code）"]');await codeBox.waitFor();
  assert.equal(await codeBox.isDisabled(),false,'根 code 节点必须可选择');await codeBox.check();
  await panel.getByLabel(/我已核对参考方式/).check();
  const adoptWait=page.waitForResponse(response=>new URL(response.url()).pathname===`${taskPath}/reference-dsl/adopt`&&response.request().method()==='POST');
  await panel.getByRole('button',{name:'按选定方式加入参考材料',exact:true}).click();
  const adopted=await adoptWait;if(adopted.status()!==200)throw Error('采用参考 DSL 失败：'+await adopted.text());
  const adoptedTask=await adopted.json(),adoptedRef=adoptedTask.materials.find(material=>material.source_kind==='reference_dsl');
  assert(adoptedRef,'采用后应有参考 DSL 材料');assert.deepEqual(adoptedRef.preserve_node_ids,['code']);
  assert(adoptedTask.revision>info.initial_revision,'采用后修订应增加');
  await page.locator('.material').first().waitFor();
  const editButton=page.getByRole('button',{name:'设置引用方式',exact:true});await editButton.waitFor();assert.equal(await editButton.count(),1);await editButton.click();
  const modal=page.locator('.modal');await modal.waitFor();
  const modalCode=modal.locator('input[type=checkbox][aria-label*="（code）"]'),modalFormat=modal.locator('input[type=checkbox][aria-label*="（format）"]');
  await modalCode.waitFor();assert.equal(await modalCode.isChecked(),true,'单份编辑应回显已选 code');
  assert.equal(await modalFormat.isChecked(),false);await modalFormat.check();
  const patchWait=page.waitForResponse(response=>materialPatch.test(new URL(response.url()).pathname)&&response.request().method()==='PATCH');
  await page.getByRole('button',{name:'保存引用方式',exact:true}).click();
  const patched=await patchWait;if(patched.status()!==200)throw Error('保存材料引用方式失败：'+await patched.text());
  const patchedTask=await patched.json(),patchedRef=patchedTask.materials.find(material=>material.source_kind==='reference_dsl');
  assert(patchedRef,'保存后应有参考 DSL 材料');assert.deepEqual(patchedRef.preserve_node_ids,['code','format']);
  assert(patchedTask.revision>adoptedTask.revision,'保存节点选择后修订应增加');
  assert.equal(patchedTask.requirements_confirmed,false);assert.equal(patchedTask.configuration_confirmed,false);
  await modal.waitFor({state:'detached'});
  await editButton.click();const reopened=page.locator('.modal');await reopened.waitFor();
  assert.equal(await reopened.locator('input[type=checkbox][aria-label*="（code）"]').isChecked(),true);
  assert.equal(await reopened.locator('input[type=checkbox][aria-label*="（format）"]').isChecked(),true);
  await page.screenshot({path:path.join(info.output,'ui-reference-preservation.png')});
  await reopened.getByRole('button',{name:'关闭',exact:true}).click();await reopened.waitFor({state:'detached'});
  const persisted=await page.evaluate(async id=>{const response=await fetch('/api/tasks/'+encodeURIComponent(id),{cache:'no-store'});if(!response.ok)throw Error('读取任务失败');return response.json()},info.task_id);
  const persistedRef=persisted.materials.find(material=>material.source_kind==='reference_dsl');
  assert(persistedRef,'读取任务后应有参考 DSL 材料');assert.deepEqual(persistedRef.preserve_node_ids,['code','format']);
  assert.deepEqual(errors,[]);assert.equal(foreign,0);assert.equal(unexpected,0);
  fs.writeFileSync(path.join(info.output,'ui-proof.json'),JSON.stringify({
   state:'passed',scope:'actual built App integration; task/requirements/intake/plan preseeded via local API',
   base:info.base,task_id:info.task_id,task_name:info.task_name,
   task_seeded_via_local_api_not_ui_creation:true,seed_note:info.seed_note,
   initial_revision:info.initial_revision,adopt_revision:adoptedTask.revision,patch_revision:patchedTask.revision,
   material_id:patchedRef.id,adopt_node_ids:adoptedRef.preserve_node_ids,patched_node_ids:patchedRef.preserve_node_ids,
   reopen_node_ids:['code','format'],requirements_confirmed_after_patch:patchedTask.requirements_confirmed,
   configuration_confirmed_after_patch:patchedTask.configuration_confirmed,
   screenshot:'ui-reference-preservation.png',write_requests:writes,foreign_requests:foreign,
   unexpected_requests:unexpected,page_errors:errors,model_dify_http:0,production_data_changed:false},null,2));
  console.log(JSON.stringify({state:'passed',adopt_node_ids:adoptedRef.preserve_node_ids,patched_node_ids:patchedRef.preserve_node_ids,writes:writes.length}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
