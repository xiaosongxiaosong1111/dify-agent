// Real built-App acceptance for retiring an obsolete conflict, then separately confirming scope; loopback static App only.
const {chromium}=require(process.argv[2]),fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const info=JSON.parse(fs.readFileSync(process.argv[3],'utf8')),origin=new URL(info.base).origin,taskPath=`/api/tasks/${info.task_id}`;
const dismissPath=`${taskPath}/conflicts/dismiss`,confirmPath=`${taskPath}/conflicts/confirm`;
const waitEnabled=async(locator,page)=>{for(let i=0;i<100&&await locator.isDisabled();i++)await page.waitForTimeout(50);return !(await locator.isDisabled())};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({viewport:{width:1500,height:1100}});
 const errors=[],writes=[],bodies=[];let foreign=0,unexpected=0;page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const request=route.request(),url=new URL(request.url());
  if(url.origin!==origin){foreign++;return route.abort()}
  if(request.method()==='GET')return route.continue();
  if(request.method()==='POST'&&(url.pathname===dismissPath||url.pathname===confirmPath)){
   writes.push(`${request.method()} ${url.pathname}`);bodies.push({path:url.pathname,body:request.postDataJSON()});return route.continue()}
  unexpected++;return route.abort();
 });
 try{
  await page.goto(info.base,{waitUntil:'networkidle'});
  const taskItem=page.locator('.task-item').filter({hasText:info.task_name});await taskItem.waitFor();await taskItem.click();
  await page.locator('h1').filter({hasText:info.task_name}).waitFor();
  await page.locator('.steps button').filter({hasText:'需求'}).click();
  const panel=page.locator('.conflict-panel');await panel.waitFor();
  const reasonBox=panel.getByLabel(`失效冲突撤销说明 ${info.conflict_id}`,{exact:true});await reasonBox.waitFor();
  const panelText=await panel.innerText();
  const statusText=await panel.locator('.listhead small').innerText();
  assert.match(statusText,/(来源.*(变化|失效|移除|删除|不存在)|重新检查|失效|已移除)/,'状态栏应显示来源失效说明');
  assert(panelText.includes(info.conflict_id),'旧冲突 C1 应仍显示');
  assert(panelText.includes(info.missing_material_ids[0]),'旧冲突应保留被移除来源的标识');
  assert(panelText.includes('已从本任务移除'),'应明确说明冲突引用的资料已从任务移除');

  assert.equal(await reasonBox.count(),1,'应只有一个 C1 失效撤销说明输入框');
  const dismissButton=panel.getByRole('button',{name:'明确撤销此失效冲突',exact:true});await dismissButton.waitFor();
  const dismissAck=panel.getByRole('checkbox',{name:/来源/});await dismissAck.waitFor();
  assert.equal(await dismissAck.count(),1,'应只有一个撤销来源复核勾选项');
  const ackLabel=await dismissAck.evaluate(el=>(el.closest('label')?.innerText||el.getAttribute('aria-label')||'').trim());
  assert(/来源/.test(ackLabel)&&/(复核|核对|确认)/.test(ackLabel),'撤销确认须明确复核当前剩余来源');
  assert.equal(await dismissButton.isDisabled(),true,'未填理由且未明确复核时不得提交');
  await reasonBox.fill(info.reason);
  assert.equal(await dismissButton.isDisabled(),true,'仅填理由未明确复核时不得提交');
  await dismissAck.check();
  assert.equal(await waitEnabled(dismissButton,page),true,'填写理由并明确复核后应可提交');
  await page.screenshot({path:path.join(info.output,'ui-conflict-dismissal-ready.png')});

  const dismissWait=page.waitForResponse(response=>new URL(response.url()).pathname===dismissPath&&response.request().method()==='POST');
  await dismissButton.click();
  const dismissedResponse=await dismissWait;if(dismissedResponse.status()!==200)throw Error('撤销失效冲突失败：'+await dismissedResponse.text());
  const dismissed=await dismissedResponse.json();
  assert.deepEqual(writes,[`POST ${dismissPath}`],'撤销后不得自动发起确认请求');
  const dismissBody=bodies.find(item=>item.path===dismissPath)?.body||{};
  assert.equal(dismissBody.revision,info.source_revision,'撤销须携带当前来源修订');
  assert.equal(dismissBody.conflict_id,info.conflict_id);
  assert.equal(dismissBody.reason,info.reason);
  assert.equal(typeof dismissBody.review_token,'string');assert(dismissBody.review_token.length>0);
  assert.equal(dismissBody.acknowledge_review,true);assert.equal(dismissBody.acknowledge_dismissal,true);
  assert.deepEqual(dismissed.requirements,info.requirements_after_delete,'撤销不得改写需求');
  assert.deepEqual(dismissed.materials,info.materials_after_delete,'撤销不得恢复或改动材料');
  assert.equal(dismissed.requirements.rules,info.original_rules);
  assert.notEqual(dismissed.requirements.rules,'Refunds within 30 days.','不得自动采用推荐方案 B 的业务规则');
  assert.equal(dismissed.requirements_confirmed,false);assert.equal(dismissed.configuration_confirmed,false);
  assert.deepEqual(dismissed.conflict_review.confirmation,{},'撤销后当前范围仍须单独确认');
  assert(!dismissed.artifact);assert(!dismissed.dify_app_id);assert(!(dismissed.runs&&dismissed.runs.length));
  const dismissals=dismissed.conflict_dismissals||[];assert.equal(dismissals.length,1,'应只有一条不可变撤销记录');
  const event=dismissals[0];
  assert.deepEqual(event.conflict,info.conflict,'撤销记录须保留完整旧冲突行');
  assert.deepEqual(event.missing_material_ids,info.missing_material_ids);
  assert.equal(event.reason,info.reason);
  assert.equal(event.source_revision,info.source_revision);
  assert.equal(event.result_revision,dismissed.revision);
  assert(dismissed.revision>info.source_revision,'撤销应生成新修订');

  const historyDetails=panel.locator('details').filter({hasText:'已明确撤销的失效冲突'}).first();
  await historyDetails.waitFor();
  if(!(await historyDetails.evaluate(el=>el.open)))await historyDetails.locator('summary').click();
  await panel.getByText(info.reason,{exact:false}).first().waitFor();
  assert(await panel.getByText(info.conflict_id,{exact:false}).count()>0,'旧冲突记录应保留');
  await page.screenshot({path:path.join(info.output,'ui-conflict-dismissal.png')});

  const confirmAck=panel.getByRole('checkbox',{name:'我已复核当前检查范围和决定，未解决的重要分歧已明确列出',exact:true});
  await confirmAck.waitFor();
  for(let i=0;i<100&&await confirmAck.isDisabled();i++)await page.waitForTimeout(50);
  assert.equal(await confirmAck.isDisabled(),false,'撤销完成后当前范围复核应可操作');
  const confirmButton=panel.getByRole('button',{name:'确认当前检查结果',exact:true});await confirmButton.waitFor();
  assert.equal(await confirmButton.isDisabled(),true,'未明确复核当前范围时不得确认');
  await confirmAck.check();
  assert.equal(await waitEnabled(confirmButton,page),true,'明确复核当前范围后应可确认');
  const confirmWait=page.waitForResponse(response=>new URL(response.url()).pathname===confirmPath&&response.request().method()==='POST');
  await confirmButton.click();
  const confirmedResponse=await confirmWait;if(confirmedResponse.status()!==200)throw Error('单独确认当前范围失败：'+await confirmedResponse.text());
  const confirmed=await confirmedResponse.json();
  const confirmBody=bodies.find(item=>item.path===confirmPath)?.body||{};
  assert.equal(confirmBody.revision,dismissed.revision,'确认须携带撤销后的当前修订');
  assert.equal(typeof confirmBody.review_token,'string');assert(confirmBody.review_token.length>0);
  assert.equal(confirmBody.acknowledge_review,true);
  assert.deepEqual(confirmed.requirements,info.requirements_after_delete,'确认范围不得改写需求');
  assert.equal(confirmed.requirements.rules,info.original_rules);
  assert.equal(confirmed.requirements_confirmed,false);assert.equal(confirmed.configuration_confirmed,false);
  assert(!confirmed.artifact);assert(!confirmed.dify_app_id);assert(!(confirmed.runs&&confirmed.runs.length));
  const conflictState=await page.evaluate(async requestPath=>{const response=await fetch(requestPath,{cache:'no-store'});if(!response.ok)throw Error('读取冲突状态失败');return response.json()},`${taskPath}/conflicts`);
  assert.equal(conflictState.confirmed,true,'撤销后须单独确认当前检查范围');
  assert.equal(conflictState.dismissals.length,1);
  assert.deepEqual(conflictState.dismissals[0].missing_material_ids,info.missing_material_ids);
  assert.equal(conflictState.dismissals[0].reason,info.reason);
  await page.screenshot({path:path.join(info.output,'ui-conflict-confirmed.png')});

  assert.deepEqual(writes,[`POST ${dismissPath}`,`POST ${confirmPath}`],'只允许撤销与单独确认两次写入');
  assert.equal(writes.length,2);assert.deepEqual(errors,[]);assert.equal(foreign,0);assert.equal(unexpected,0);
  fs.writeFileSync(path.join(info.output,'ui-proof.json'),JSON.stringify({
   state:'passed',scope:'actual built App integration; task/requirements/intake/confirmation/policy/conflict/delete preseeded via local API',
   base:info.base,task_id:info.task_id,task_name:info.task_name,
   task_seeded_via_local_api_not_ui_creation:true,seed_note:info.seed_note,
   source_revision:info.source_revision,dismiss_revision:dismissed.revision,confirm_revision:confirmed.revision,
   conflict_id:info.conflict_id,missing_material_ids:info.missing_material_ids,reason:info.reason,
   original_rules:info.original_rules,rules_after_dismiss:dismissed.requirements.rules,rules_after_confirm:confirmed.requirements.rules,
   dismissal:{conflict_id:event.conflict.id,missing_material_ids:event.missing_material_ids,reason:event.reason,source_revision:event.source_revision,result_revision:event.result_revision,created_at:event.created_at},
   requirements_confirmed_after_dismiss:dismissed.requirements_confirmed,
   configuration_confirmed_after_dismiss:dismissed.configuration_confirmed,
   conflict_confirmed_after_separate_confirm:conflictState.confirmed,
   old_record_retained:true,retire_history_visible:true,
   dismiss_post_body:dismissBody,confirm_post_body:confirmBody,
   write_requests:writes,post_count:writes.length,foreign_requests:foreign,unexpected_requests:unexpected,
   page_errors:errors,screenshots:['ui-conflict-dismissal-ready.png','ui-conflict-dismissal.png','ui-conflict-confirmed.png'],
   model_dify_http:0,physical_model_dify_http:0,production_data_changed:false},null,2));
  console.log(JSON.stringify({state:'passed',dismiss_revision:dismissed.revision,confirm_revision:confirmed.revision,conflict_confirmed:conflictState.confirmed,writes:writes.length}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
