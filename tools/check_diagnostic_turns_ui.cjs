const {chromium}=require(process.argv[2]),fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const info=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true}),proof=[];let foreign=0,unexpectedWrites=0,repairReads=0;
try{for(const task of info.tasks){const page=await browser.newPage({viewport:{width:1530,height:1150}}),errors=[],posts=[];
page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==info.base){foreign++;return route.abort()}if(u.pathname.includes('/repair'))repairReads++;if(req.method()!=='GET'){if(req.method()!=='POST'||u.pathname!==`/api/tasks/${task.id}/runs/chat-run/diagnose`){unexpectedWrites++;return route.abort()}posts.push(req.postDataJSON())}return route.continue()});
await page.goto(info.base,{waitUntil:'networkidle'});await page.locator('.task-item').filter({hasText:task.name}).click();await page.locator('.steps button').filter({hasText:'运行'}).click();await page.locator('details[data-run-id="chat-run"] > summary').click();const panel=page.locator('.run-diagnostic').first(),select=panel.getByRole('combobox',{name:'诊断轮次'}),local=panel.getByRole('button',{name:'分析已保存结果',exact:true}),remote=panel.getByRole('button',{name:'读取 Dify 节点轨迹并诊断',exact:true});
await select.waitFor();assert.equal(await select.inputValue(),'');
const showNode=async title=>{const summary=panel.locator('summary').filter({hasText:'节点执行摘要'});await summary.waitFor();if(await summary.locator('..').getAttribute('open')===null)await summary.click();await panel.locator('.diagnostic-node b').filter({hasText:title}).waitFor()};
if(task.mode==='duplicate'){assert.equal(await select.locator('option[value="1"]').count(),0);assert.equal(await select.locator('option[value="2"]').count(),1);assert.equal(posts.length,0)}
else if(task.mode==='normal'){
 await local.click();await panel.getByText(/远端采集：仅本地分析/).waitFor();assert.equal(posts[0].turn_index,undefined);
 await select.selectOption('1');assert.equal(await panel.getByText(/远端采集：/).count(),0);assert.equal(posts.length,1);
 await local.click();await panel.getByText(/所选第 1 轮状态：success/).waitFor();await remote.click();await showNode('首轮节点');assert.equal(await panel.locator('.chatflow-trace-source').count(),1);
 await select.selectOption('2');assert.equal(await panel.locator('.diagnostic-node b').filter({hasText:'首轮节点'}).count(),0);assert.equal(posts.length,3);
 await remote.click();await showNode('补号轮节点');
 await select.selectOption('1');await showNode('首轮节点');assert.equal(posts.length,4);assert.deepEqual(posts.map(p=>p.turn_index),[undefined,1,1,2]);
 await panel.screenshot({path:path.join(info.output,'first-turn-diagnostic.png')});
 await select.selectOption('');await panel.getByText(/远端采集：仅本地分析/).waitFor();assert.equal(posts.length,4);
}else if(task.mode==='whole_failed'){
 await select.selectOption('1');await local.click();await panel.getByText(/本地记录：failed · 所选第 1 轮状态：success/).waitFor();await panel.getByText('本地记录为执行成功',{exact:true}).waitFor();await remote.click();await showNode('首轮节点');assert.equal(posts.length,2);assert.equal(posts[0].turn_index,1);
}else if(task.mode==='pending'){
 await select.selectOption('2');await remote.click();await panel.getByText(/本地记录：unknown · 所选第 2 轮状态：unknown/).waitFor();await showNode('补号轮节点');assert.equal(posts.length,1);
}else{
 await select.selectOption('1');await remote.click();await panel.getByRole('alert').filter({hasText:'源运行或复核记录已变化'}).waitFor();assert.equal(await panel.getByText(/远端采集：/).count(),0);assert.equal(posts.length,1);
}
assert.deepEqual(errors,[]);proof.push({case:task.mode,diagnostic_posts_to_temporary_store:posts.length});await page.close();}
assert.equal(foreign,0);assert.equal(unexpectedWrites,0);assert.equal(repairReads,0);fs.writeFileSync(path.join(info.output,'proof.json'),JSON.stringify({state:'passed',cases:proof,foreign_requests:0,unexpected_writes:0,automatic_repair_reads:0},null,2));console.log(JSON.stringify({state:'passed',cases:proof.length}));}finally{await browser.close()}})().catch(e=>{console.error(e.stack);process.exitCode=1});
