// Isolated browser check for the presentational reference-node selector. Local static page only; no production API.
const {chromium}=require(process.argv[2]),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http'),{pathToFileURL}=require('node:url');
const project=path.resolve(__dirname,'..'),frontend=path.join(project,'frontend'),modules=path.join(frontend,'node_modules'),component=path.join(frontend,'src','ReferenceNodeChoices.tsx'),work=path.join(project,'work'),output=path.resolve(process.argv[3]);
const relativeOutput=path.relative(work,output);assert(relativeOutput&&!relativeOutput.startsWith('..')&&!path.isAbsolute(relativeOutput)&&path.dirname(relativeOutput)==='.','output must be a new direct child directory of work/');
assert(fs.existsSync(work)&&fs.statSync(work).isDirectory(),'work/ directory is missing');assert(!fs.existsSync(output),'output already exists; refusing to reuse or delete it');
fs.mkdirSync(output);assert(path.dirname(fs.realpathSync(output))===fs.realpathSync(work),'output must resolve directly inside the real work/ directory');
const pageDir=path.join(output,'reference-node-choices-page'),entry=path.join(pageDir,'Harness.tsx'),bundleFile=path.join(pageDir,'app.js');
fs.mkdirSync(pageDir);
const alias={'react/jsx-runtime':path.join(modules,'react','jsx-runtime.js'),'react-dom/client':path.join(modules,'react-dom','client.js'),'react':path.join(modules,'react','index.js'),'reference-node-choices':component};
const harness=`import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import ReferenceNodeChoices from 'reference-node-choices';
const summary={source:{filename:'reference.yml',app_name:'参考应用',app_type:'workflow',dsl_version:'0.7.0',sha256:'a'.repeat(64)},target_type:'workflow',verification:'local_structure_only',edges:[],inputs:[],outputs:[],resources:[],warnings:[],nodes:[
 {id:'start',type:'start',label:'开始',title:'开始',planning_supported_type:true,details:[]},
 {id:'code',type:'code',label:'代码',title:'处理代码',planning_supported_type:true,details:[]},
 {id:'tpl',type:'template-transform',label:'模板转换',title:'模板',planning_supported_type:true,details:[]},
 {id:'nested',type:'code',label:'代码',title:'容器内代码',parent_id:'iter',planning_supported_type:true,details:[]},
 {id:'llm',type:'llm',label:'大模型',title:'模型',planning_supported_type:true,details:[]}
]};
const mismatch={...summary,target_type:'advanced-chat'};
function Harness(){
 const [mode,setMode]=useState('preserve'),[kind,setKind]=useState('reference'),[target,setTarget]=useState('workflow'),[selected,setSelected]=useState([]),[open,setOpen]=useState(true); const changeMode=next=>{setMode(next);if(next!=='preserve')setSelected([])};
 const changeTarget=next=>{setTarget(next);setSelected([])};
 return <div>
  <label>参考方式<select aria-label="参考方式" value={mode} onChange={e=>changeMode(e.target.value)}><option value="">请选择</option><option value="borrow">borrow</option><option value="preserve">preserve</option><option value="replicate">replicate</option></select></label>
  <label>材料类型<select aria-label="材料类型" value={kind} onChange={e=>setKind(e.target.value)}><option value="reference">参考 DSL</option><option value="text">普通文字</option></select></label>
  <label>目标类型<select aria-label="目标类型" value={target} onChange={e=>changeTarget(e.target.value)}><option value="workflow">Workflow</option><option value="advanced-chat">Chatflow</option></select></label>
  <button onClick={()=>{setOpen(false);setSelected([])}}>关闭</button>
  {open&&kind==='reference'&&mode==='preserve'&&<ReferenceNodeChoices summary={target==='workflow'?summary:mismatch} selected={selected} onChange={setSelected}/>}
  {open&&kind==='text'&&mode==='preserve'&&<p>普通文字材料：可保存讨论，不能自动规划／构建。</p>}
  <output id="selected">{selected.join(',')}</output>
 </div>;
}
createRoot(document.getElementById('root')).render(<Harness/>);
`;
fs.writeFileSync(entry,harness);
fs.writeFileSync(path.join(pageDir,'index.html'),'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ReferenceNodeChoices check</title><div id="root"></div><script src="app.js"></script></html>');
async function bundlePage(){
 const esbuildArg=process.argv[4]?require.resolve(path.resolve(process.argv[4])):null;
 let esbuildPath=esbuildArg;if(!esbuildPath){try{esbuildPath=require.resolve('esbuild',{paths:[frontend]})}catch{}}
 if(esbuildPath){const esbuild=require(esbuildPath);await esbuild.build({entryPoints:[entry],bundle:true,outfile:bundleFile,format:'iife',platform:'browser',jsx:'automatic',nodePaths:[modules],alias,define:{'process.env.NODE_ENV':'"production"'}});return 'esbuild'}
 const {rolldown}=await import(pathToFileURL(require.resolve('rolldown',{paths:[frontend]})).href);
 const built=await rolldown({input:entry,platform:'browser',transform:{jsx:'react-jsx',define:{'process.env.NODE_ENV':'"production"'}},resolve:{modules:[modules],alias}});
 try{await built.write({file:bundleFile,format:'iife'})}finally{await built.close()}return 'rolldown';
}
(async()=>{const bundler=await bundlePage(),server=http.createServer((req,res)=>{const url=new URL(req.url,'http://local'),file=path.resolve(pageDir,'.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));if(!file.startsWith(pageDir+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end()}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':'text/html');fs.createReadStream(file).pipe(res)});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const origin='http://127.0.0.1:'+server.address().port,browser=await chromium.launch({channel:'msedge',headless:true});let writes=0,foreign=0;
 try{const page=await browser.newPage({viewport:{width:1200,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',route=>{const req=route.request(),url=new URL(req.url());if(url.origin!==origin){foreign++;return route.abort()}if(req.method()!=='GET'){writes++;return route.abort()}return route.continue()});
  await page.goto(origin,{waitUntil:'networkidle'});
  const panel=page.locator('.reference-node-choices'),boxes=panel.locator('input[type=checkbox]'),selected=page.locator('#selected');
  await panel.waitFor();assert.equal(await boxes.count(),5);
  const enabled=[];for(let i=0;i<await boxes.count();i++)if(!await boxes.nth(i).isDisabled())enabled.push(await boxes.nth(i).getAttribute('aria-label'));
  assert.deepEqual(enabled,['选择参考节点 处理代码（code）','选择参考节点 模板（tpl）']);
  for(const label of ['选择参考节点 开始（start）','选择参考节点 容器内代码（nested）','选择参考节点 模型（llm）'])assert.equal(await panel.getByLabel(label,{exact:true}).isDisabled(),true,label+' must be disabled');
  await panel.getByLabel('选择参考节点 处理代码（code）',{exact:true}).check();assert.equal(await selected.textContent(),'code');
  await panel.getByLabel('选择参考节点 模板（tpl）',{exact:true}).check();assert.equal(await selected.textContent(),'code,tpl');assert.match(await panel.innerText(),/已选 2 个节点/);
  await panel.getByLabel('选择参考节点 处理代码（code）',{exact:true}).uncheck();assert.equal(await selected.textContent(),'tpl');
  await page.getByLabel('目标类型',{exact:true}).selectOption('advanced-chat');await page.getByText(/参考应用类型与当前任务不同/).waitFor();assert.equal(await selected.textContent(),'');
  let enabledAfterMismatch=0;for(let i=0;i<await boxes.count();i++)if(!await boxes.nth(i).isDisabled())enabledAfterMismatch++;assert.equal(enabledAfterMismatch,0);
  await page.getByLabel('目标类型',{exact:true}).selectOption('workflow');assert.equal(await panel.locator('input[type=checkbox]:checked').count(),0);
  await page.getByLabel('参考方式',{exact:true}).selectOption('borrow');await panel.waitFor({state:'detached'});assert.equal(await selected.textContent(),'');
  await page.getByLabel('参考方式',{exact:true}).selectOption('preserve');await panel.waitFor();assert.equal(await panel.locator('input[type=checkbox]:checked').count(),0);assert.equal(await selected.textContent(),'');
  await page.getByLabel('材料类型',{exact:true}).selectOption('text');await panel.waitFor({state:'detached'});assert.match(await page.locator('body').innerText(),/普通文字材料：可保存讨论，不能自动规划／构建/);
  await page.getByLabel('材料类型',{exact:true}).selectOption('reference');await panel.waitFor();await panel.getByLabel('选择参考节点 模板（tpl）',{exact:true}).check();assert.equal(await selected.textContent(),'tpl');
  await page.getByRole('button',{name:'关闭',exact:true}).click();await panel.waitFor({state:'detached'});assert.equal(await selected.textContent(),'');
  assert.deepEqual(errors,[]);assert.equal(writes,0);assert.equal(foreign,0);
  fs.writeFileSync(path.join(output,'proof.json'),JSON.stringify({state:'passed',scope:'component and synthetic harness only; not App end-to-end',bundler,component:'ReferenceNodeChoices.tsx',cases:['only-root-code-and-template-selectable','controlled-onChange-order','unsupported-and-container-disabled','mismatched-app-type-disabled','mode-switch-and-close-reset','plain-text-no-selection'],mutating_requests:writes,foreign_requests:foreign,model_dify_http:0,production_data_changed:false},null,2));
  console.log(JSON.stringify({state:'passed',bundler,cases:6,mutating_requests:writes,foreign_requests:foreign}));
 }finally{await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
