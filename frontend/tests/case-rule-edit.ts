import assert from 'node:assert/strict';
import {casesToDrafts,draftsToCases,type TestCase} from '../src/AcceptancePanel';
let passed=0,failed=0;
function check(name:string,fn:()=>void){try{fn();passed++;console.log('PASS '+name)}catch(e){failed++;console.log('FAIL '+name+': '+String(e))}}
const base=(expected:unknown,mode:'contains'|'json_keys'='contains'):TestCase=>({id:'public-case',name:'公开样例',required:true,input:{query:'公开输入'},expectation:{mode,target:'answer',expected}});
for(const expected of ['退货','政策第一行\n政策第二行',' 前后空格 ',['连续\n两行'],['\t边界\r\n',' 🙂 '],[' ']])check('完整关键词 '+JSON.stringify(expected),()=>{const c=base(expected);const drafts=casesToDrafts([c]);drafts[0].name='仅改名称';assert.deepEqual(draftsToCases(drafts),[{...c,name:'仅改名称'}])});
for(const expected of [['field\nname'],[' data ','\tkey']])check('完整字段 '+JSON.stringify(expected),()=>{const c=base(expected,'json_keys');assert.deepEqual(draftsToCases(casesToDrafts([c])),[c])});
check('普通列表仍每行一项',()=>{const c=base(['七天','未拆封']);const drafts=casesToDrafts([c]);assert.equal(drafts[0].expectedText,'七天\n未拆封');assert.deepEqual(draftsToCases(drafts),[c])});
check('输出路径不裁剪',()=>{const c=base(['公开']);c.expectation.target=' answer ';assert.deepEqual(draftsToCases(casesToDrafts([c])),[c])});
check('人工原文字不裁剪',()=>{const c=base([]);c.expectation={mode:'manual',description:'  逐项核对\n '};assert.deepEqual(draftsToCases(casesToDrafts([c])),[c])});
check('追问保留各自规则',()=>{const c=base(['正常']);c.followups=[{input:{query:'追问'},expectation:{mode:'contains',target:' answer ',expected:['包含\n两行',' 首尾 ']}},{input:{query:'再问'},expectation:{mode:'manual',description:' 完整判断 '}}];assert.deepEqual(draftsToCases(casesToDrafts([c])),[c])});
for(const text of ['{"bad":true}','[1]','[""]','["a",]','{"a":1,"a":2}','"公开","ignored":true','["a"],"ignored":true'])check('JSON规则拒绝 '+text,()=>{const draft=casesToDrafts([base('公开')])[0];draft.expectedText=text;assert.throws(()=>draftsToCases([draft]))});
console.log(JSON.stringify({passed,failed,physical_model_dify_http:0}));if(failed)process.exitCode=1;
