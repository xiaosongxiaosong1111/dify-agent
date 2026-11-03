const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const ts=require('../node_modules/typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {filterSavedTasks}=require('../src/taskListFilter.ts');
const tasks=Object.freeze([
 Object.freeze({id:'a',name:'售后 Workflow [Demo]',app_type:'workflow'}),
 Object.freeze({id:'b',name:'售后 Chatflow',app_type:'advanced-chat'}),
 Object.freeze({id:'c',name:'内部 订单 Agent',app_type:'agent'}),
 Object.freeze({id:'d',name:'旧应用',app_type:'legacy'}),
]);
let passed=0;
function check(fn){fn();passed++}
check(()=>assert.deepEqual(filterSavedTasks(tasks,'','all'),tasks));
check(()=>assert.deepEqual(filterSavedTasks(tasks,'  售后  ','all'),[tasks[0],tasks[1]]));
check(()=>assert.deepEqual(filterSavedTasks(tasks,'[demo]','all'),[tasks[0]]));
check(()=>assert.deepEqual(filterSavedTasks(tasks,'.*','all'),[]));
check(()=>assert.deepEqual(filterSavedTasks(tasks,'售后','advanced-chat'),[tasks[1]]));
check(()=>assert.deepEqual(filterSavedTasks(tasks,'售后','agent'),[]));
check(()=>assert.deepEqual(filterSavedTasks(tasks,'','agent'),[tasks[2]]));
check(()=>assert.deepEqual(filterSavedTasks([], '','workflow'),[]));
check(()=>{const result=filterSavedTasks(tasks,'','all');assert.notEqual(result,tasks);assert.equal(result[0],tasks[0]);assert.equal(result[3],tasks[3])});
console.log(JSON.stringify({passed,failed:0}));
