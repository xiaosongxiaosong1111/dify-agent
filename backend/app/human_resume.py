"""Read-only evidence for the original submitted review; never a new execution."""
import asyncio,copy
from fastapi import APIRouter,HTTPException
from .dify import DifyError
from .workflow_waiting import stamp,canonical,TERMINAL
from .schedule_observation import CredentialSnapshot
from .run_diagnostics import binding
from .human_runtime_plan import source
from .diagnostic_graph_source import fingerprint

NOTE='两次只读核对不是原子快照。仅核对原运行的已确认纯文字动作／分支／输出；不能证明哪个人提交或把结果归因于本次请求，不提升客户业务样例为通过，不新运行或重试提交。'


def expectation(root,inputs,node_id,action):
    nodes={n['id']:n['data'] for n in root['workflow']['graph']['nodes']};edges=root['workflow']['graph']['edges'];pool={};path=[]
    for nid,data in nodes.items():
        if data['type']=='start':
            for field in data.get('variables',[]):pool[(nid,field['variable'])]=inputs.get(field['variable'],field.get('default'))
        elif data['type']=='template-transform':pool[(nid,'output')]=data['template']
    branch=[e['target'] for e in edges if e['source']==node_id and e.get('sourceHandle')==action]
    if len(branch)!=1:raise ValueError('选中动作须有唯一明确入口。')
    nid=branch[0]
    while nid not in path and len(path)<=200:
        path.append(nid);data=nodes[nid]
        if data['type']=='end':
            result={}
            for output in data.get('outputs',[]):
                key=tuple(output.get('value_selector',[]));name=output.get('variable')
                if key not in pool or name in result or not isinstance(pool[key],str):raise ValueError('终点输出不是可核对的明确文字。')
                result[name]=pool[key]
            return path,result
        if data['type']!='template-transform':raise ValueError('首批恢复证据仅适配固定模板到终点。')
        following=[e['target'] for e in edges if e['source']==nid]
        if len(following)!=1:raise ValueError('恢复证据不猜测并行／多个终点输出。')
        nid=following[0]
    raise ValueError('恢复路径无法有限核对。')


def compare(root,plan,run,decision,detail,trace):
    form=run['form'];status=detail.get('status');matched=fingerprint(detail.get('graph'))==fingerprint(root['workflow']['graph'])
    result={'platform_status':status,'execution_graph_matched':matched,'confirmed_behavior_matched':False,'request_attribution_verified':False,'business_verified':False,'submit_interface_accepted':decision.get('state')=='accepted','expected_action':decision['action'],'observed_action':None,'node_action_matched':False,'selected_path_matched':False,'output_matched':False,'state':'waiting' if status not in TERMINAL else 'unverified','note':NOTE}
    if not matched:result['state']='different_execution_graph';return result
    rows=trace.get('data') if isinstance(trace,dict) else None
    if not isinstance(rows,list) or len(rows)>500 or any(not isinstance(r,dict) for r in rows):result['state']='trace_unavailable';return result
    human=[r for r in rows if r.get('node_id')==form['node_id'] and r.get('node_type')=='human-input' and r.get('status')=='succeeded']
    if len(human)!=1 or human[0].get('outputs_truncated') is not False or not isinstance(human[0].get('outputs'),dict):result['state']='human_action_unavailable';return result
    outputs=human[0]['outputs'];observed=outputs.get('__action_id')
    result['observed_action']=observed if isinstance(observed,str) and observed in {'approve','reject'} else None
    result['node_action_matched']=observed==decision['action'] and outputs.get('__action_value')==decision['action_title'] and outputs.get('__rendered_content')==form['content']
    try:path,expected=expectation(root,plan['input'],form['node_id'],decision['action'])
    except (ValueError,KeyError,TypeError):result['state']='outcome_rule_unavailable';return result
    succeeded={r.get('node_id') for r in rows if r.get('status')=='succeeded' and isinstance(r.get('node_id'),str)}
    other_entries={e['target'] for e in root['workflow']['graph']['edges'] if e['source']==form['node_id'] and e.get('sourceHandle')!=decision['action']}
    result['selected_path_matched']=set(path)<=succeeded and not succeeded&other_entries
    result['output_matched']=detail.get('outputs')==expected
    result['confirmed_behavior_matched']=status=='succeeded' and result['node_action_matched'] and result['selected_path_matched'] and result['output_matched']
    result['state']='confirmed_behavior_observed' if result['confirmed_behavior_matched'] else 'waiting' if status not in TERMINAL else 'different_or_unverified_behavior'
    return result


class HumanResume:
    def __init__(self,host):self.h=host
    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/human-runtime/runs/{run_id}/resume-evidence')
        async def read(item_id:str,run_id:str):
            with h.store.lock:
                task=h.get_task(item_id);run=copy.deepcopy(h.store.get('human_runtime_run',run_id))
                if not run or run.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该原人工运行。')
                if run.get('state') in {'executing','submitting_decision'}:raise HTTPException(409,'原操作仍处理中，不并发采集恢复证据。')
                decisions=[r for r in h.store.list('human_decision') if r.get('task_id')==item_id and r.get('run_id')==run_id and r.get('write_attempted')]
                if len(decisions)!=1:raise HTTPException(409,'原表单没有唯一一次人工提交尝试，不猜本次恢复动作。')
                decision=copy.deepcopy(decisions[0]);env,form=h.human_decisions.original(task,run,ready=False);root=source(h,task)['root'];plan=h.store.get('human_runtime_plan',run['plan_id'])
                if not plan or plan.get('task_id')!=item_id:raise HTTPException(409,'原资源与输入方案缺失，不猜输出。')
                credentials=CredentialSnapshot(h.store,env['id']);original=stamp(run);decision_stamp=stamp(decision)
            def context():
                with h.store.lock:
                    current=h.store.get('environment',env['id']);latest=h.store.get('human_runtime_run',run_id)
                    if not current or binding(current)!=binding(env) or not credentials.unchanged(h.store) or not latest or stamp(latest)!=original or stamp(h.store.get('human_decision',decision['id']))!=decision_stamp:raise HTTPException(409,'原连接、运行或动作记录改变，未保存旧证据。')
                    h.human_decisions.original(h.get_task(item_id),run,ready=False)
            async def collect():
                context();client=h.DifyClient(env,credentials);detail=await client.workflow_run_detail(run['app_id'],run['workflow_run_id']);context()
                status=detail.get('status') if isinstance(detail,dict) else None
                if not isinstance(detail,dict) or canonical(detail.get('id'))!=run['workflow_run_id'] or not isinstance(status,str) or status not in TERMINAL|{'paused','running'}:raise DifyError('原运行ID或状态不可信，未保存原文。')
                trace=await client.request('GET',f"/console/api/apps/{run['app_id']}/workflow-runs/{run['workflow_run_id']}/node-executions",credential='console_token');context()
                return compare(root,plan,run,decision,detail,trace)
            try:evidence=await asyncio.wait_for(collect(),timeout=60)
            except DifyError as exc:raise HTTPException(502,str(exc)) from None
            except TimeoutError:raise HTTPException(504,'恢复证据只读超时，没有提交动作或重新运行。') from None
            with h.store.lock:
                context();evidence['checked_at']=h.now();run['resume_evidence']=evidence
                if evidence['platform_status'] in TERMINAL:run['state']='platform_finished';run['form']['active']=False
                h.store.put('human_runtime_run',run_id,run)
            return {'task_id':item_id,'run_id':run_id,'workflow_run_id':run['workflow_run_id'],'evidence':evidence}
