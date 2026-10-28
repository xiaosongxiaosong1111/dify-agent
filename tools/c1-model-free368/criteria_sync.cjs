// Normal local editing and explicit delegated review; no new model or graph editing.
const assert=require('node:assert/strict');
async function syncCriteria(page,info,taskId){
 const base=info.base+'/api/tasks/'+taskId;let t=await(await page.request.get(base)).json();const old=t.requirements;
 assert.equal(old.tests.split(info.fixture.before_literal).length,2,'Require exactly one obsolete test literal');
 assert(old.output.includes(info.fixture.changed_fallback));assert.equal(t.test_cases[1].expectation.expected,info.fixture.changed_fallback);
 const changed={...old,tests:old.tests.replace(info.fixture.before_literal,info.fixture.changed_fallback)};
 let r=await page.request.patch(base,{data:{expected_revision:t.revision,requirements:{tests:changed.tests}}});assert(r.ok(),'Test prose sync failed');t=await r.json();assert.deepEqual(t.requirements,changed);assert(!t.requirements_confirmed&&t.plan_stale);
 r=await page.request.get(base+'/intake');assert(r.ok());const state=await r.json();assert.deepEqual(state.standard.map(x=>x.id).sort(),[...Object.keys(changed),'retrieval'].sort());
 r=await page.request.post(base+'/intake/manual',{data:{revision:t.revision,context_token:state.context_token,answers:{...changed,retrieval:'指定公开FAQ库、TopK3、无阈值不重排；非空仅一次回答模型，空分支固定新提示。当前输出、验收说明与已保存两例一致，图只沿用原模型候选，不新增分支或资源。'},acknowledge_review:true,actor:'agent_delegated',actor_note:'按常规本机委托及本独立批范围，只同步验收说明中唯一旧固定回复，使其与当前输出和已保存运行样例一致；其余七需求字段/配置/原模型完整图不改。这是代理逐项声明，不是新模型验证、人类签收或平台通过。'}});
 assert(r.ok(),'Normal delegated criterion review failed');t=await r.json();assert.deepEqual(t.requirements,changed);assert.equal(t.intake_review.source,'agent_declared');assert.equal(t.intake_review.review_actor,'agent_delegated');assert(!t.requirements_confirmed&&!t.configuration_confirmed&&t.plan_stale);
 await page.reload({waitUntil:'networkidle'});await page.locator('h1').filter({hasText:info.fixture.task_name}).waitFor();return t;
}
module.exports={syncCriteria};
