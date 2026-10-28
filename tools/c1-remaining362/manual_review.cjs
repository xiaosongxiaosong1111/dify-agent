// Existing normal product API; an explicit agent declaration, never model or human validation.
const assert=require('node:assert/strict');
async function manualReview(page,info,taskId,changed,original){
 assert.equal(changed.output,original.output.replace(info.fixture.before_literal,info.fixture.changed_fallback));
 for(const key of Object.keys(original))if(key!=='output')assert.equal(changed[key],original[key],'Other requirement changed');
 const base=info.base+'/api/tasks/'+taskId;
 const t=await(await page.request.get(base)).json();assert.deepEqual(t.requirements,changed);
 const r=await page.request.get(base+'/intake');assert(r.ok());const current=await r.json();
 assert.deepEqual(current.standard.map(x=>x.id).sort(),[...Object.keys(changed),'retrieval'].sort(),'Manual review cannot hide a new topic');
 const answers={...changed,retrieval:'沿用原公开FAQ库、TopK3、无阈值不重排；先检索，非空只调用一次已声明回答模型，政策事实只来自资料；为空固定文字。仅无命中提示增加商品型号，其余业务及配置保持。'};
 const saved=await page.request.post(base+'/intake/manual',{data:{revision:t.revision,context_token:current.context_token,answers,acknowledge_review:true,actor:'agent_delegated',actor_note:'按用户常规开发委托及本独立批明确范围，代理逐项复核当前八字段与检索专项；仅输出固定文案增加商品型号。不是模型验证、人类声明或最终业务签收；仍需根代理读当前来源、再确认需求及模型生成修改版。'}});
 assert(saved.ok(),'Normal manual intake API failed');const result=await saved.json();
 assert.deepEqual(result.requirements,changed);assert.equal(result.intake_review.source,'agent_declared');assert.equal(result.intake_review.review_actor,'agent_delegated');assert(!result.requirements_confirmed&&!result.configuration_confirmed&&result.plan_stale);
 await page.reload({waitUntil:'networkidle'});await page.locator('h1').filter({hasText:info.fixture.task_name}).waitFor();
 return result;
}
module.exports={manualReview};
