const test=require('node:test'),assert=require('node:assert/strict');
const {assertInterviewApplied}=require('./c1-mainline354/interview-result.cjs');
const before={id:'public-test',revision:3,messages:[],interview_attempts:[]};
function valid(){return {id:before.id,revision:4,messages:[{source:'model',context_revision:3}],intake_review:{source:'model',origin_revision:4,review:{checks:[],questions:[]}}};}
test('HTTP200 with exact C1 rejection stops before the next operation',()=>{
  const after={...before,interview_attempts:[{reason:'模型需求检查未通过：需求检查主题数量不匹配：当前标准为 9 项，不能省略。 sk-hidden'}]};
  let reviewCalls=0;
  assert.throws(()=>{assertInterviewApplied(before,after);reviewCalls++},/当前标准为 9 项/);
  assert.equal(reviewCalls,0);
  try{assertInterviewApplied(before,after)}catch(e){assert(!e.message.includes('sk-hidden'));assert(!e.message.includes('undefined'));}
});
test('retained old review cannot conceal a newly rejected candidate',()=>{
  const after=valid();after.interview_attempts=[{reason:'sk-hidden model text'}];
  assert.throws(()=>assertInterviewApplied(before,after),/候选未应用/);
});
for(const [name,mutate] of Object.entries({
  missingReview:x=>delete x.intake_review,
  staleReview:x=>x.intake_review.origin_revision--,
  oldMessage:x=>x.messages[0].context_revision--,
  unrelatedTask:x=>x.id='other',
  systemMessage:x=>x.messages[0].source='system',
  missingQuestions:x=>delete x.intake_review.review.questions,
}))test(name+' stops without dereferencing a null review',()=>{
  const after=valid();mutate(after);assert.throws(()=>assertInterviewApplied(before,after),/本轮有效模型检查/);
});
test('current successful model review proceeds even with older failed attempts',()=>{
  const old={...before,interview_attempts:[{reason:'old failure'}]};const after=valid();after.interview_attempts=old.interview_attempts;
  assert.doesNotThrow(()=>assertInterviewApplied(old,after));
});
