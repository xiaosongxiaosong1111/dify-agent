"""Source-bound application configuration proposals; adoption never executes Dify writes."""
from __future__ import annotations
from .contract_loading import load_contract
import copy,hashlib,json,math,uuid
from datetime import datetime,timezone
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,StrictBool,StrictInt
from .resources import models_metadata,parameter_metadata,datasets_metadata,provider_path
from .dify import DifyClient,DifyError
from .conversation import memory_configuration
from .intake import summary as intake_summary,require_ready as require_intake
from .run_diagnostics import safe_text
from .model_parameters import needs_task_model

from .discussion_mode import requirement_user

FIELDS={'dify_model_provider','dify_model','temperature','max_tokens','model_parameters','dataset_ids','retrieval_top_k','conversation_memory','memory_turns','opening_statement','suggested_questions','mock_dependencies','resource_plan'}
def hash_value(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def env_stamp(h,task):
    env=h.store.get('environment',task.get('environment_id') or '')
    return hash_value(h.env_snapshot(env)) if env else None
def context_stamp(h,task):
    return hash_value({'revision':task['revision'],'app_type':task['app_type'],'requirements':task['requirements'],'configuration':task['configuration'],'environment':env_stamp(h,task),'intake_token':intake_summary(task)['context_token'],'workflow_plan':task.get('workflow_plan'),'agent_plan':task.get('agent_plan'),'plan_stale':task.get('plan_stale'),'snapshot_id':(h.store.get('configuration_resources',task['id']) or {}).get('id')})

def check_rules(cfg,rules):
    values={'temperature':cfg['temperature'],'max_tokens':cfg['max_tokens'],**cfg.get('model_parameters',{})};known={r['name']:r for r in rules}
    if not {'temperature','max_tokens'}<=set(known):raise ValueError('所选模型未声明 Temperature／Max tokens，当前编译器不能自动采用。')
    if set(values)-set(known):raise ValueError('扩展参数没有实际规则依据：'+'、'.join(sorted(set(values)-set(known))))
    for name,rule in known.items():
        if name not in values:
            if rule.get('required'):raise ValueError('缺少模型声明的必填参数：'+name)
            continue
        v=values[name];kind=rule.get('type')
        if kind in {'int','float'}:
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or (kind=='int' and type(v) is not int):raise ValueError(name+' 的数值类型不符合实际规则。')
            if ('min' in rule and v<rule['min']) or ('max' in rule and v>rule['max']):raise ValueError(name+' 超出实际模型参数范围。')
        elif kind=='boolean' and type(v) is not bool:raise ValueError(name+' 必须为布尔值。')
        elif kind=='string' and not isinstance(v,str):raise ValueError(name+' 必须为文本。')
        if rule.get('options') and not any(type(v) is type(o) and v==o for o in rule['options']):raise ValueError(name+' 不属于实际规则列出的选项。')

class Revision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
class Adopt(Revision):
    proposal_id:str
    proposal_token:str
    acknowledge_changes:StrictBool
    acknowledge_unverified_resources:StrictBool=False
    acknowledge_mock_changes:StrictBool=False

class ConfigurationManager:
    def __init__(self,h):self.h=h
    def busy(self,item_id):return (self.h.store.get('configuration_discovery',item_id) or {}).get('status')=='running'
    def recover(self):
        for job in self.h.store.list('configuration_discovery'):
            if job['status']=='running':job.update(status='interrupted',message='读取因重启中断，未更新目录依据，请重新读取。');self.h.store.put('configuration_discovery',job['id'],job)
    def snapshot(self,item_id):return self.h.store.get('configuration_resources',item_id)
    def snapshot_current(self,task,snap):
        if not snap or snap['environment_id']!=task.get('environment_id') or snap['environment_stamp']!=env_stamp(self.h,task):return False
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(snap['observed_at'])).total_seconds()
        return 0<=age<=900

    async def discover(self,item_id,revision):
        h=self.h
        with h.store.lock:
            task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,revision);env=h.store.get('environment',task.get('environment_id') or '')
            generation=task.get('pause_generation',0);stamp=env_stamp(h,task);job={'id':item_id,'status':'running','revision':revision,'started_at':h.now()};h.store.put('configuration_discovery',item_id,job)
        snap={'id':str(uuid.uuid4()),'environment_id':task.get('environment_id'),'environment_stamp':stamp,'observed_at':h.now(),'models':[],'datasets':[],'errors':[],'models_truncated':False,'datasets_truncated':False,'source':'console' if env else 'offline'}
        def guard():
            current=h.get_task(item_id)
            if current['revision']!=revision or current.get('pause_generation',0)!=generation or env_stamp(h,current)!=stamp:raise HTTPException(409,'读取期间任务、环境或暂停状态变化；旧目录未写入。')
        try:
            if not env:snap['errors'].append('尚未选择目标环境；只能保留用户已填写的模型／知识库标识，无法验证可用性。')
            elif env.get('version')!=h.TARGET_DIFY_VERSION:snap['errors'].append('目标版本与当前适配基线不符，未读取目录。')
            else:
                adapter=DifyClient(env,h.store)
                try:
                    rows=models_metadata(await adapter.models('llm'),'llm');guard()
                    eligible=[r for r in rows if r['selectable']]
                    eligible.sort(key=lambda r:(r['provider']!=task['configuration']['dify_model_provider'] or r['model']!=task['configuration']['dify_model']))
                    snap['models_truncated']=len(eligible)>6
                    for row in eligible[:6]:
                        guard()
                        try:row['rules']=parameter_metadata(await adapter.model_parameters(provider_path(row['provider']),row['model']));row['rules_status']='observed'
                        except (DifyError,ValueError) as exc:row['rules']=[];row['rules_status']='failed';snap['errors'].append(safe_text(f"参数读取失败 {row['model']}：{exc}"))
                        snap['models'].append(row)
                except DifyError as exc:snap['errors'].append(safe_text('模型目录读取失败：'+str(exc)))
                for page in range(1,4):
                    guard()
                    try:
                        payload=datasets_metadata(await adapter.console_datasets(page,100));snap['datasets']+=payload['data']
                        if not payload['has_more']:break
                        if page==3:snap['datasets_truncated']=True
                    except DifyError as exc:snap['errors'].append(safe_text('知识库目录读取失败：'+str(exc)));break
            with h.store.lock:
                guard();snap['observed_at']=h.now();h.store.put('configuration_resources',item_id,snap);job.update(status='succeeded',completed_at=h.now());h.store.put('configuration_discovery',item_id,job)
            return self.state(h.get_task(item_id))
        except BaseException:
            with h.store.lock:job.update(status='interrupted',completed_at=h.now(),message='读取中断或来源变化，已有目录未覆盖；没有 Dify 写入。');h.store.put('configuration_discovery',item_id,job)
            raise

    def validate(self,task,value):
        errors=[]
        try:
            if not isinstance(value,dict) or set(value)!={'schema_version','configuration','reasons','open_issues','notes'} or type(value['schema_version']) is not int or value['schema_version']!=1:raise ValueError('配置方案须按指定契约返回完整 JSON。')
            patch=value['configuration']
            if not isinstance(patch,dict) or set(patch)-FIELDS:raise ValueError('方案包含未知或搭建助手连接字段；不能改变 Key、环境或用户应用类型。')
            self.h.validate_config(patch);cfg={**copy.deepcopy(task['configuration']),**copy.deepcopy(patch)};memory_configuration(task['app_type'],cfg)
            if task['app_type']!='advanced-chat' and (cfg.get('opening_statement') or cfg.get('suggested_questions')):raise ValueError('开场白和建议问题当前只支持 Chatflow；其他类型不能静默忽略。')
            if not isinstance(value['notes'],str) or len(value['notes'])>4000:raise ValueError('方案说明须为最多 4000 字的文本。')
            reasons=value['reasons'];seen=set()
            if not isinstance(reasons,list) or len(reasons)!=len(patch):raise ValueError('每个拟议字段须有理由和体验／费用／人工影响。')
            for row in reasons:
                if not isinstance(row,dict) or set(row)!={'field','reason','experience','cost','manual_work'} or not all(isinstance(v,str) and 0<len(v.strip())<=3000 for v in row.values()):raise ValueError('配置理由字段不符合契约。')
                if row['field'] not in patch or row['field'] in seen:raise ValueError('方案理由与字段必须完整、唯一对应。')
                seen.add(row['field'])
            issues=value['open_issues']
            if not isinstance(issues,list) or len(issues)>12:raise ValueError('待决定事项最多 12 项。')
            for row in issues:
                if not isinstance(row,dict) or set(row)!={'question','recommendation','experience','cost','manual_work'} or not all(isinstance(v,str) and 0<len(v.strip())<=3000 for v in row.values()):raise ValueError('待决定事项须包含问题、建议和各项影响。')
            snap=self.snapshot(task['id'])
            if not self.snapshot_current(task,snap):raise ValueError('配置依据缺失／过期或环境变化，请先重新读取并生成。')
            old=task['configuration'];pair=(cfg['dify_model_provider'],cfg['dify_model']);oldpair=(old['dify_model_provider'],old['dify_model'])
            if pair!=oldpair and not {'dify_model_provider','dify_model','temperature','max_tokens','model_parameters'}<=set(patch):raise ValueError('更换模型须显式给出成对模型标识、Temperature、Max tokens 及完整扩展参数，不能沿用旧模型隐藏参数。')
            choice=next((m for m in snap['models'] if (m['provider'],m['model'])==pair and m['rules_status']=='observed'),None)
            if choice:check_rules(cfg,choice['rules'])
            elif pair!=oldpair:raise ValueError('新模型不在已读取且有参数规则的目录中，不能编造或采用未读取的候选。')
            from .iteration import plan_nodes
            needs_model=task['app_type']=='agent' or needs_task_model(task.get('workflow_plan'))
            if needs_model and not cfg['dify_model'] and not issues:raise ValueError('尚未指定模型，应保留明确待决定事项，不能宣称方案可采纳。')
            known={d['id'] for d in snap['datasets']}|set(old['dataset_ids'])
            if len(cfg['dataset_ids'])!=len(set(cfg['dataset_ids'])) or any(not x.strip() or x not in known for x in cfg['dataset_ids']):raise ValueError('知识库 ID 必须唯一且来自实际目录或用户已有配置。')
        except (ValueError,HTTPException) as exc:errors.append(str(exc.detail) if isinstance(exc,HTTPException) else str(exc))
        return {'valid':not errors,'errors':errors}

    def warnings(self,task,value,snap):
        cfg={**task['configuration'],**value['configuration']};result=[]
        from .iteration import plan_nodes
        independent=[n['id'] for n in plan_nodes(task.get('workflow_plan') or {}) if n.get('type')=='llm' and isinstance(n.get('config'),dict) and 'model' in n['config']]
        if independent:result.append('本配置方案只调整任务默认模型；独立模型节点保持其流程配置，请在流程页另行核对：'+'、'.join(independent))
        retrieval=[n['id'] for n in plan_nodes(task.get('workflow_plan') or {}) if n.get('type')=='knowledge-retrieval']
        if retrieval:result.append('本配置方案只调整任务默认选库／Top K；节点独立选库、阈值及重排保持流程配置，请另行核对：'+'、'.join(retrieval))
        if cfg['dify_model'] and not any(m['provider']==cfg['dify_model_provider'] and m['model']==cfg['dify_model'] and m['rules_status']=='observed' for m in snap['models']):result.append('模型来自用户当前填写，实际目录／参数规则未验证。')
        unknown=[x for x in cfg['dataset_ids'] if x not in {d['id'] for d in snap['datasets']}]
        if unknown:result.append('保留的知识库未在本次目录中核对：'+'、'.join(unknown))
        empty=[d['id'] for d in snap['datasets'] if d['id'] in cfg['dataset_ids'] and (d.get('available_document_count')==0 or d.get('document_count')==0)]
        if empty:result.append('目录显示文档未就绪／为空，不能当作已可检索：'+'、'.join(empty))
        return result

    def state(self,task):
        records=[r for r in self.h.store.list('configuration_proposal') if r['task_id']==task['id']];record=records[0] if records else None;snap=self.snapshot(task['id'])
        stale=bool(record and record['context_stamp']!=context_stamp(self.h,task));current=self.snapshot_current(task,snap)
        diffs=[]
        if record:
            for row in record['candidate']['reasons']:
                field=row['field'];diffs.append({**row,'before':record['before'][field],'after':record['candidate']['configuration'][field],'changed':record['before'][field]!=record['candidate']['configuration'][field]})
        return {'revision':task['revision'],'snapshot':snap,'snapshot_current':current,'discovery':self.h.store.get('configuration_discovery',task['id']),'record':record,'stale':stale,'diffs':diffs,'can_adopt':bool(record and record['status']=='proposed' and not stale and current and not record['candidate']['open_issues'] and any(d['changed'] for d in diffs)),'history':[{'id':r['id'],'status':r['status'],'origin_revision':r['origin_revision'],'created_at':r['created_at'],'applied_revision':r.get('applied_revision')} for r in records],'scope_note':'方案是本任务全局配置建议；检索为 multiple／Top K、关闭重排与阈值。节点级模型、复杂检索和凭据自动配置尚未支持。采纳只写本地配置，不执行 Dify 资源操作，也不代表已验证交付。'}

    def save(self,task,value):
        record={'id':str(uuid.uuid4()),'task_id':task['id'],'origin_revision':task['revision'],'created_at':self.h.now(),'status':'proposed','context_stamp':context_stamp(self.h,task),'candidate':copy.deepcopy(value),'before':copy.deepcopy(task['configuration']),'resource_warnings':self.warnings(task,value,self.snapshot(task['id']))}
        record['proposal_token']=hash_value(record);self.h.store.put('configuration_proposal',record['id'],record)
        return task

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/configuration-proposal')
        def get_proposal(item_id:str):return self.state(h.get_task(item_id))
        @h.app.post('/api/tasks/{item_id}/configuration-proposal/resources')
        async def resources(item_id:str,payload:Revision):return await self.discover(item_id,payload.revision)
        @h.app.post('/api/tasks/{item_id}/configuration-proposal/generate')
        async def generate(item_id:str,payload:Revision):
            from .bounded_suggestions import suggest
            def messages(task):
                require_intake(task)
                if not task['requirements_confirmed']:raise HTTPException(422,'请先明确确认当前需求，再集中讨论具体配置。')
                snap=self.snapshot(item_id)
                if not self.snapshot_current(task,snap):raise HTTPException(422,'请先读取本任务的配置依据；目录快照有效期为 15 分钟。')
                prompt=load_contract(h.PROJECT_ROOT,'configuration-model-contract.md')
                return [{'role':'system','content':prompt},{'role':'user','content':json.dumps({'app_type':task['app_type'],'requirements':task['requirements'],'intake':intake_summary(task),'configuration':task['configuration'],'user_discussion':[m.get('content','')[:6000] for m in task['messages'] if requirement_user(m)][-12:],'workflow_plan':task.get('workflow_plan'),'agent_plan':task.get('agent_plan'),'resources':snap},ensure_ascii=False)}]
            return await suggest(h,item_id,payload.revision,'configuration',messages,self.validate,self.save)
        @h.app.post('/api/tasks/{item_id}/configuration-proposal/adopt')
        def adopt(item_id:str,payload:Adopt):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);value=self.state(task);record=value['record']
                if not record or record['id']!=payload.proposal_id or record['proposal_token']!=payload.proposal_token or not value['can_adopt']:raise HTTPException(409,'方案已变化、过期、已采纳或仍有待决定事项；请重新读取并生成，不应用旧方案。')
                checked=self.validate(task,record['candidate'])
                if not checked['valid']:raise HTTPException(422,'；'.join(checked['errors']))
                if not payload.acknowledge_changes:raise HTTPException(422,'请明确接受所有字段的修改前后内容及影响。')
                if record['resource_warnings'] and not payload.acknowledge_unverified_resources:raise HTTPException(422,'请明确接受用户填写资源尚未验证的限制，不能当作实际可用。')
                patch=record['candidate']['configuration']
                if 'mock_dependencies' in patch and patch['mock_dependencies']!=task['configuration']['mock_dependencies'] and not payload.acknowledge_mock_changes:raise HTTPException(422,'模拟依赖改变体验与交付范围，请单独明确接受。')
                h.invalidate(task,'集中配置方案采纳前保存',preserve_requirements=True);task['configuration'].update(copy.deepcopy(patch))
                if task.get('workflow_plan') or task.get('agent_plan'):task['plan_stale']=True
                record.update(status='adopted',applied_revision=task['revision'],adopted_at=h.now(),acknowledgements={'changes':True,'unverified_resources':payload.acknowledge_unverified_resources,'mock_changes':payload.acknowledge_mock_changes});h.store.put_many([('task',item_id,task),('configuration_proposal',record['id'],record)])
                return h.save_task(task)
