"""reviewed-remaining394: reuse one successful first case; platform-only leftovers.

No import-time side effect. prepare reads the original machine read-only and writes a new
canonical package; approve binds a direct reply; run is the only consumer. One prior App,
Key and first-case run are reused without re-dispatch; only the modified graph creates one
new App/publish/Key. No Sierra model, new Task, library or interview is used. Public checks
are synthetic only.
"""
from __future__ import annotations
import argparse, contextlib, copy, hashlib, json, os, sqlite3, subprocess, sys
from pathlib import Path

BATCH='reviewed-remaining394'
PROJECT=Path(__file__).resolve().parents[2]
REAL_PROJECT=Path(r'E:\workSpace\dify-agent')
TASK_ID='1154f0c0-5e01-4492-b5c7-97bfbbbc2a61'
ENVIRONMENT_ID='202bfb35-2f92-47c1-bc1b-eac32082181d'
WORKSPACE_ID='c3306c18-ceb2-4bee-b2d1-796ce2048f17'
LIMITS={'new_tasks':0,'model':0,'reads':103,'login':1,'import':1,'publish':1,'key':1,'run':13}
CURRENT_UPPER={'model':57,'reads':1730,'login':51,'import':30,'publish':30,'key':30,'run':148}
PROPOSED_UPPER={**CURRENT_UPPER,'login':52}
MODEL_BOOK='3.355473652'
DIFY_ESTIMATE='0.100'
WALL_SECONDS=3600
RUNTIME_BUILD='0.413.0-bdb32c6761fe3102d582'
RUNTIME_VERSION='0.413.0'
RUNTIME_FILE_COUNT=298
RUNTIME_BACKEND=REAL_PROJECT/'.runtime'/'snapshots'/RUNTIME_BUILD/'backend'
SEAL_INDEX_SHA='87ed9ec71d7487704d39360d723048d220bb64b81952e91e2ea9237493d2868f'
SEAL_385_INDEX_SHA='97f93e940d03826930a910be7e6b8a5ad9505da2ba0b4413a7843fa5c6de0b42'
SEAL_391_PATH='work/reviewed-run391-seal-after-review.json'
SEAL_391_MEMBER_COUNT=16
PARENT_SEALED_COUNT=909
SEALED_COUNT=926
OLD_892_COUNT=892
SEAL_MEMBER_COUNT=16
ROOT_PLAN='work/autonomous-dual375/plan.json'
OLD_892_PATH='work/isolated-modification385/protected-892.json'
SEAL_385_PATH='work/isolated-modification385/seal-after-review.json'
FIXED_CANDIDATE_PATH='work/isolated-modification385/live-output/model-response-modified.txt'
ORIGINAL_GRAPH_SHA='dd71f629c0d6a1e82d8e88aa424341fbe751369fbe0cedf19a9f1b5f44198c69'
MODIFIED_GRAPH_SHA='3940d8496c6ff7c6dd14ddf3b62fb9deeff556114b81ca65b1d437d22976ede5'
NO_ANSWER_OLD='知识库暂无相关信息，请联系人工客服。'
NO_ANSWER_NEW='知识库暂无相关信息，请联系人工客服并提供商品型号。'
MODEL_TEMPERATURE=0.2
MODEL_MAX_TOKENS=512
MODEL_THINKING=False
MODEL_COMPLETION={'temperature':MODEL_TEMPERATURE,'max_tokens':MODEL_MAX_TOKENS,'thinking':MODEL_THINKING}
KB_TOP_K=3
REVIEW_ACTOR='root_agent'
# Existing successful first case; only this frozen App may be reused.
EXISTING_APP_ID='9242435f-e66f-4292-86ba-0834a495dab7'
EXISTING_IMPORT_RUN='832bc5c0-2e40-4360-b3d0-39f13f67d025'
EXISTING_PUBLISH_RUN='ae2c8219-b94a-4ee3-808b-356f2312ec51'
EXISTING_FIRST_RUN='836b9394-9260-4d6a-b123-81a629cc6795'
EXISTING_MESSAGE='94cceec5-beb7-40ef-8df9-8629030df20c'
EXISTING_SESSION='a3656da5-d4d7-4183-bc30-e9cb8cd5fb17'
EXISTING_RUN_COUNT=3
DIAGNOSTIC_PURPOSE='run_diagnostic_redaction'
DIAGNOSTIC_MAX_READS=14
SCOPE_FIELDS=frozenset({'provider_id','purpose','memory_only','model_calls','max_reads'})
SECRET_FIELDS=('api_key','console_token','csrf_token','service_api_key','dataset_api_key')
HELPER='reviewed_diagnostic_redaction.py'
HELPER_COMMIT='bfc0c3b1e614a32d2212552b2e42d476ab003652'
HELPER_PATH='tools/reviewed_diagnostic_redaction.py'
# Copied verbatim from the trusted tools/autonomous-dual375/derivation.py ISOLATED set.
ROOT_PATHS={'data':'data',
 '391':'work/chatflow-model391/live-output/data',
 '394':'work/clarified-chatflow394/live-output/data',
 '399':'work/bounded-chatflow399/live-output/data',
 '401':'work/reviewed-chatflow401/live-output/data',
 '405':'work/offline-candidate405/data',
 '408':'work/reviewed-planning408/live-output/data',
 '409':'work/offline-candidate409/data',
 '414':'work/autonomous-chatflow414/live-output/data',
 '416':'work/autonomous-chatflow416/live-output/data',
 '418':'work/recovered-chatflow418/live-output/data',
 '420':'work/reviewed-spec-planning420/live-output/data'}
ROOT_IGNORE={'flowcraft.sqlite3','flowcraft.sqlite3-wal','flowcraft.sqlite3-shm','server.pid','server.out.log','server.err.log'}
SOURCE_FILES=('tool.py','boundary.py','journey.py','storage_guard.py','checks.py',HELPER,'README.md')
PACKAGE_FILES=SOURCE_FILES+('plan.json','reviewed.json','protected.json')
PINS={'337':'f0e7beefb331db0b9c07f24cf19786b85d05b13c','374':'4ac8e3282093fe0ba6a5298fcac9cc279e3e03bf','386-boundary':'d1dc2cde7fc4ea1d81e8dd8a55a5909ea1559d98'}
PIN_PATHS={'337':'tools/autonomous-dual337/common.py','374':'tools/autonomous-dual374/journey.py','386-boundary':'tools/stateful-chatflow386/boundary.py'}
JOURNEY_REUSE=('norm','capture_failed_turn','assert_diagnostic','export_bundle')
BOUNDARY_IMPORT_OLD=b'from common import LIMITS,digest,require,uuid\n'
BOUNDARY_IMPORT_NEW=b'from tool import LIMITS,digest,require,uuid\n'
# The 386 zero-model protocol stays the whole base class as the deterministic prefix;
# this explicit narrow subclass is the only 394 addition.  verify_source binds the
# entire file (prefix+suffix) to Git at prepare/run.
BOUNDARY_394_SUFFIX=(b"\n"
 b"class ReviewedBoundary(Boundary):\n"
 b"    \"\"\"394 narrow gate: reuse only the frozen first App after its native source is verified.\"\"\"\n"
 b"    def __init__(self,env,fixture,contract,record,old_apps=()):\n"
 b"        super().__init__(env,fixture,contract,record,old_apps);self.source_verified=False\n"
 b"    def admit(self,request):\n"
 b"        from urllib.parse import urlsplit\n"
 b"        from tool import EXISTING_APP_ID\n"
 b"        path=urlsplit(str(request.url)).path\n"
 b"        if request.method=='POST':\n"
 b"            if path=='/console/api/apps/imports' and self.version!='modified':raise RuntimeError('Only the reviewed modified version may import a new App')\n"
 b"            if path.endswith('/workflows/publish') and self.version!='modified':raise RuntimeError('The original App must not be published again')\n"
 b"            if path.endswith('/api-keys') and self.version!='modified':raise RuntimeError('The original App must not create another key')\n"
 b"            if path=='/v1/chat-messages':\n"
 b"                require(self.source_verified is True,'First saved native source must be verified before any new Service')\n"
 b"                if self.version=='original':\n"
 b"                    require(self.current==EXISTING_APP_ID and EXISTING_APP_ID in self.old_apps and self.apps.get(self.current,{}).get('version')=='original','Only the frozen existing App may be reused')\n"
 b"                else:\n"
 b"                    require(self.current is not None and self.current not in self.old_apps,'Only the reviewed new App may run the modified version')\n"
 b"        return super().admit(request)\n"
 b"\n"
 b"Boundary=ReviewedBoundary")
ANY_OF_ANCHOR=b"                'Required node did not succeed')\n"
ANY_OF_BLOCK=(b"        groups = expected.get('any_of')\n"
              b"        if groups is not None:\n"
              b"            require(isinstance(groups, list) and groups\n"
              b"                    and all(isinstance(group, list) and group\n"
              b"                            and all(isinstance(node, str) and node for node in group)\n"
              b"                            for group in groups),\n"
              b"                    'Trace any_of malformed')\n"
              b"            require(any(set(group) <= ids and all(statuses.get(node) == 'succeeded' for node in group)\n"
              b"                        for group in groups), 'No allowed alternative terminal group succeeded')\n")
KNOWN_APPS_START=b"            for key in ('app_id','dify_app_id','service_app_id'):\n"
KNOWN_APPS_END=b"                if isinstance(value,dict) and uuid(value.get('app_id')):result.add(value['app_id'])\n"
FAILURE_POLICY={'business_rule_failure_only':True,'max_reports':1,'max_management_reads':4,'post_failure_service_requests':0,'post_failure_remote_writes':0,'stop_after_capture':True}
APPROVAL_PHRASE='允许将391未派发资源明确改授394复用已成功首例的独立剩余平台收尾批，仅新增一次加密登录与内存诊断脱敏'
EXECUTION_POLICY={'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None}
OLD_REFS=(
 'call_f5b63df1752f441284ac9ee97f031930/q0',
 'call_653c3204d2c842648bbfaddba3d298b4/q0',
 'call_a7ee288e3a8b474b8b8d3dbc99c2f729/q0',
 'call_3d00360306e848a6bff6357de379a9c6/q0',
 'call_90ac87674e9a4a4eb0fc35ea048b5314/q0',
)
APPROVAL_KEYS={'schema_version','batch_id','authorization_source','scope','question_ref','literal','plan_sha256','manifest_sha256','limits','failure_policy','execution_policy','wall_seconds','dify_estimate','dify_is_billing_limit','host_cost_known','current_upper','proposed_upper','old_reservations_preserved','new_model_calls','new_tasks','new_libraries','only_new_login','failure_exception','single_use','retry','diagnostic_scope','diagnostic_provider_sha256','diagnostic_key_cipher_sha256','created_at'}
EXISTING_SOURCE_KEYS={'app_id','import_run_id','publish_run_id','first_run_id','message_id','conversation_id','first_run_sha256','provider_id','provider_sha256','key_cipher_sha256','execution_limits_sha256','known_apps_contains'}

def require(value,message):
    if not value:raise RuntimeError(message)
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def uuid(value):
    from uuid import UUID
    try:return isinstance(value,str) and str(UUID(value))==value
    except (ValueError,AttributeError):return False
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def now():
    from datetime import datetime,timezone
    return datetime.now(timezone.utc).isoformat()
def norm_lf(raw):return raw.replace(b'\r\n',b'\n').replace(b'\r',b'\n')
def safe_path(project,rel):
    require(isinstance(rel,str) and rel and not Path(rel).is_absolute() and '..' not in Path(rel).parts,'unsafe relative path')
    current=Path(project);require(not current.is_symlink(),'project symlink')
    for part in Path(rel).parts:
        current=current/part;require(not current.is_symlink(),'symlink in path')
    path=Path(project)/rel;require(path.resolve().is_relative_to(Path(project).resolve()),'path escape');return path
def read_json(path,label='JSON'):
    path=Path(path);require(path.is_file() and not path.is_symlink(),label+' missing/linked')
    raw=path.read_bytes()
    try:
        def unique(pairs):
            out={}
            for k,v in pairs:require(k not in out,label+' duplicate key');out[k]=v
            return out
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    except (ValueError,UnicodeError,RecursionError) as exc:raise RuntimeError(label+' invalid JSON') from exc
    return value,raw
def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),'utf-8');os.replace(tmp,path)
def exclusive_json(path,value):
    with Path(path).open('x',encoding='utf-8') as handle:json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False)
def git_blob(project,commit,rel):
    result=subprocess.run(['git','-C',str(project),'cat-file','blob',commit+':'+rel],capture_output=True,check=False)
    require(result.returncode==0,'git blob missing: '+rel);return result.stdout
def verify_source(project,commit):
    require(isinstance(commit,str) and len(commit)==40 and all(c in '0123456789abcdef' for c in commit),'full source commit required')
    code=subprocess.run(['git','-C',str(project),'rev-parse','--verify',commit+'^{commit}'],capture_output=True,check=False)
    require(code.returncode==0 and code.stdout.decode().strip()==commit,'source commit mismatch')
    files={}
    for name in SOURCE_FILES:
        rel='tools/'+BATCH+'/'+name;raw=norm_lf(safe_path(project,rel).read_bytes());blob=norm_lf(git_blob(project,commit,rel))
        require(raw==blob,'source worktree differs from Git: '+name);files[rel]=hashlib.sha256(raw).hexdigest()
    return {'commit':commit,'files':files,'line_endings':'LF'}
def run_without_diagnostics(run):
    require(isinstance(run,dict),'run must be mapping');return {k:v for k,v in run.items() if k!='diagnostics'}
RUN_SOURCE_FIELDS=('id','kind','revision','environment_id','app_id','app_type','environment_binding','status','input','test_case','conversation_context','result','error','http_status','evaluation','manual_review')
def run_source_hash(run):
    require(isinstance(run,dict),'run must be mapping')
    return hashlib.sha256(json.dumps({k:run.get(k) for k in RUN_SOURCE_FIELDS},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def check_existing_runs_prefix(old_runs,new_runs,first_run_id=None,seen=None):
    require(isinstance(old_runs,list) and isinstance(new_runs,list) and len(new_runs)>=len(old_runs),'Task runs prefix changed')
    matched=0
    for index,old_run in enumerate(old_runs):
        new_run=new_runs[index]
        require(isinstance(old_run,dict) and isinstance(new_run,dict),'Task run record malformed')
        if first_run_id is not None and old_run.get('id')==first_run_id:
            matched+=1
            require(matched==1,'First run duplicated in history')
            require(new_run.get('id')==first_run_id,'First run identity changed')
            require(digest(run_without_diagnostics(new_run))==digest(run_without_diagnostics(old_run)),'Original first run fields changed')
            old_diag=old_run.get('diagnostics',[]);new_diag=new_run.get('diagnostics',[])
            require(isinstance(old_diag,list) and isinstance(new_diag,list),'Diagnostics malformed')
            require(new_diag[:len(old_diag)]==old_diag,'Existing diagnostics changed')
            extra=new_diag[len(old_diag):]
            accepted=seen.get(first_run_id) if seen is not None else None
            if accepted is not None:
                # Once the single report is accepted it can never be removed, cleared or
                # replaced -- not even by omitting it from a later write.
                require(isinstance(accepted,dict),'Accepted diagnostics malformed')
                held=sum(1 for item in old_diag if isinstance(item,dict) and digest(item)==digest(accepted))
                require(held<=1,'Accepted diagnostics duplicated')
                if held==1:require(len(extra)==0,'Only one diagnostics append allowed')
                else:require(len(extra)==1 and isinstance(extra[0],dict) and digest(extra[0])==digest(accepted),'Accepted diagnostics changed or removed')
            else:
                require(len(extra)<=1,'Only one diagnostics append allowed')
                if extra:
                    report=extra[0];require(isinstance(report,dict),'Diagnostics report malformed')
                    require(report.get('run_id')==first_run_id,'Diagnostics bound to wrong run')
                    require(report.get('source_hash')==run_source_hash(old_run),'Diagnostics source hash changed')
                    require(report.get('app_id')==old_run.get('app_id') and report.get('source_revision')==old_run.get('revision') and report.get('environment_id')==old_run.get('environment_id'),'Diagnostics identity mismatch')
                    if seen is not None:seen[first_run_id]=copy.deepcopy(report)
        else:
            require(digest(new_run)==digest(old_run),'Original run changed')
    if first_run_id is not None:require(matched==1,'First run missing from history')
    return True
def _safe_stage(boundary):
    if boundary is None:return None
    return {'version':getattr(boundary,'version',None),'phase':getattr(boundary,'phase',None),
            'case_index':getattr(boundary,'case_index',None),'halted':bool(getattr(boundary,'halted',False))}
def safe_failure_report(record,boundary,provider_reads,counts,failure_type):
    """Stopped summary keeping only obtained protection evidence and safe counters.

    It deliberately accepts no exception object, message, key or provider body, so a
    failure report cannot leak any of them.  The consumption markers stay in place.
    """
    require(isinstance(record,dict),'failure record must be mapping')
    require(isinstance(failure_type,str) and failure_type,'failure type required')
    return {'schema_version':1,'batch_id':BATCH,'state':'stopped','failure_type':failure_type,
            'stage':_safe_stage(boundary) or record.get('stage'),
            'physical_http':record.get('physical_http') if type(record.get('physical_http')) is int else 0,
            'provider_key_reads':provider_reads if type(provider_reads) is int else 0,
            'counts':dict(counts) if isinstance(counts,dict) else {},
            'protection':copy.deepcopy(record.get('protection')) if isinstance(record.get('protection'),dict) else None,
            'protection_error':record.get('protection_error') if isinstance(record.get('protection_error'),str) else None,
            'model_http_started':record.get('model_http_started') if type(record.get('model_http_started')) is int else 0,
            'automatic_retry':False,'business_acceptance_complete':False,'approval_consumed':True,'rollback':False,'completed_at':now()}
def _function_fragment(text,name):
    marker=('    def '+name+'(').encode()
    require(text.count(marker)==1,'pinned function not unique: '+name)
    start=text.index(marker);end=text.find(b'\n    def ',start+len(marker))
    require(end>start,'pinned function boundary missing: '+name)
    return text[start:end+1]
def _adapted_assert_fragment(fragment):
    require(fragment.count(b"'version': version,")==1,'pinned assert_diagnostic binding changed')
    value=fragment.replace(b"'version': version,",b"'version': b.version,")
    require(value.count(ANY_OF_ANCHOR)==1,'pinned assert_diagnostic any_of anchor changed')
    return value.replace(ANY_OF_ANCHOR,ANY_OF_ANCHOR+ANY_OF_BLOCK)
def _known_apps_fragment(text):
    require(text.count(KNOWN_APPS_START)==1 and text.count(KNOWN_APPS_END)==1,'pinned known_apps fragment changed')
    start=text.index(KNOWN_APPS_START);end=text.index(KNOWN_APPS_END)
    require(end>start,'pinned known_apps fragment order')
    return text[start:end+len(KNOWN_APPS_END)]
def verify_fixed_reuse(project,files=None):
    project=Path(project);files=files or {}
    def content(rel):
        raw=files.get(rel)
        return norm_lf(raw if raw is not None else safe_path(project,rel).read_bytes())
    result={}
    pin=PINS['386-boundary'];rel=PIN_PATHS['386-boundary'];blob=norm_lf(git_blob(project,pin,rel))
    require(blob.count(BOUNDARY_IMPORT_OLD)==1,'pinned boundary import derivation changed')
    expected=blob.replace(BOUNDARY_IMPORT_OLD,BOUNDARY_IMPORT_NEW)
    actual=content('tools/reviewed-remaining394/boundary.py')
    require(actual.startswith(expected),'boundary no longer keeps the pinned zero-model protocol as its prefix')
    require(actual.rstrip(b'\n')==(expected+BOUNDARY_394_SUFFIX).rstrip(b'\n'),'boundary 394 gate is not the reviewed narrow suffix')
    result['386-boundary']={'commit':pin,'file':rel,'sha256':hashlib.sha256(blob).hexdigest(),'derived_sha256':hashlib.sha256(expected).hexdigest(),'394_suffix_sha256':hashlib.sha256(BOUNDARY_394_SUFFIX).hexdigest()}
    pin=PINS['374'];rel=PIN_PATHS['374'];blob=norm_lf(git_blob(project,pin,rel));actual=content('tools/reviewed-remaining394/journey.py');functions={}
    for name in JOURNEY_REUSE:
        fragment=_function_fragment(blob,name)
        expected=_adapted_assert_fragment(fragment) if name=='assert_diagnostic' else fragment
        require(actual.count(expected)==1,'pinned journey fragment not reused exactly: '+name)
        functions[name]=hashlib.sha256(expected).hexdigest()
    result['374']={'commit':pin,'file':rel,'sha256':hashlib.sha256(blob).hexdigest(),'functions':functions}
    pin=PINS['337'];rel=PIN_PATHS['337'];blob=norm_lf(git_blob(project,pin,rel));fragment=_known_apps_fragment(blob)
    require(content('tools/reviewed-remaining394/tool.py').count(fragment)==1,'pinned known_apps fragment not reused exactly')
    result['337']={'commit':pin,'file':rel,'sha256':hashlib.sha256(blob).hexdigest(),'fragment_sha256':hashlib.sha256(fragment).hexdigest()}
    helper_blob=norm_lf(git_blob(project,HELPER_COMMIT,HELPER_PATH))
    require(content('tools/reviewed-remaining394/'+HELPER)==helper_blob,'diagnostic helper not the pinned 393 source')
    result['393-helper']={'commit':HELPER_COMMIT,'file':HELPER_PATH,'sha256':hashlib.sha256(helper_blob).hexdigest()}
    result['matched']=True
    return result
def _strict_int(value):return type(value) is int
def _strict_map(value,expected,label):
    require(isinstance(value,dict) and set(value)==set(expected),label+' fields changed')
    for key,want in expected.items():
        got=value[key]
        if isinstance(want,bool):require(type(got) is bool and got==want,label+' '+key+' changed')
        elif want is None:require(got is None,label+' '+key+' changed')
        elif isinstance(want,int):require(_strict_int(got) and got==want,label+' '+key+' changed')
        elif isinstance(want,dict):_strict_map(got,want,label+' '+key)
        else:require(got==want,label+' '+key+' changed')
def _validate_scope(scope,provider_id=None):
    require(isinstance(scope,dict) and set(scope)==SCOPE_FIELDS,'diagnostic scope fields changed')
    require(uuid(scope.get('provider_id')),'diagnostic scope provider id')
    if provider_id is not None:require(scope['provider_id']==provider_id,'diagnostic scope provider mismatch')
    require(scope.get('purpose')==DIAGNOSTIC_PURPOSE,'diagnostic scope purpose changed')
    require(scope.get('memory_only') is True,'diagnostic scope must be memory only')
    require(_strict_int(scope.get('model_calls')) and scope['model_calls']==0,'diagnostic scope model calls must be int 0')
    require(_strict_int(scope.get('max_reads')) and scope['max_reads']==DIAGNOSTIC_MAX_READS,'diagnostic scope max reads must be int 14')
    return True
def _sha256_hex(value,label):
    require(isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value),label+' must be sha256 hex')
    return True
def _package_links(project,root):
    root=Path(root);work=Path(project)/'work'
    require(root.is_dir() and not root.is_symlink(),'package missing/linked')
    require(work.is_dir() and not work.is_symlink(),'work missing/linked')
    require(root.resolve().parent==work.resolve(),'package not under work')
    for path in [root,*root.rglob('*')]:
        require(not path.is_symlink(),'package symlink')
def validate_package(project,root,backend=None):
    project=Path(project);root=Path(root);_package_links(project,root)
    manifest,_=read_json(root/'manifest.json','manifest');plan,_=read_json(root/'plan.json','plan')
    require(set(manifest)=={'schema_version','batch_id','plan_sha256','files'},'manifest fixed fields changed')
    require(manifest.get('schema_version')==1 and manifest.get('batch_id')==BATCH,'manifest identity')
    require(isinstance(manifest.get('files'),dict) and set(manifest['files'])==set(PACKAGE_FILES),'manifest fixed members required')
    allowed=set(PACKAGE_FILES)|{'manifest.json','approval.json','attempt.json','worker-started.json','live-output'}
    require({p.name for p in root.iterdir()}<=allowed,'extra package member')
    for name,value in manifest['files'].items():
        require('/' not in name and '\\' not in name,'manifest path invalid')
        path=safe_path(root,name);require(path.is_file() and not path.is_symlink() and sha(path)==value,'manifest SHA mismatch: '+name)
    manifest_sha=sha(root/'manifest.json');plan_sha=sha(root/'plan.json')
    require(manifest.get('plan_sha256')==plan_sha,'manifest plan SHA')
    require(plan.get('schema_version')==1 and plan.get('batch_id')==BATCH,'plan identity')
    require(plan.get('task_id')==TASK_ID and plan.get('environment_id')==ENVIRONMENT_ID,'target Task/environment changed')
    require(plan.get('task_revision')==8,'target Task revision changed')
    require(plan.get('workspace_id')==WORKSPACE_ID,'workspace changed')
    _strict_map(plan.get('limits'),LIMITS,'limits')
    _strict_map(plan.get('current_upper'),CURRENT_UPPER,'current_upper');_strict_map(plan.get('proposed_upper'),PROPOSED_UPPER,'proposed_upper')
    require(plan.get('model_estimate_book_upper_usd')==MODEL_BOOK,'model book upper changed')
    require(plan.get('estimated_new_dify_usd')==DIFY_ESTIMATE and plan.get('dify_is_billing_limit') is False and plan.get('host_cost_known') is False,'Dify estimate/boundary changed')
    require(plan.get('wall_seconds')==WALL_SECONDS and plan.get('old_reservations_preserved') is True,'wall/old reservations changed')
    require(_strict_int(plan.get('new_model_calls')) and plan['new_model_calls']==0 and _strict_int(plan.get('new_tasks')) and plan['new_tasks']==0 and _strict_int(plan.get('new_libraries')) and plan['new_libraries']==0,'new model/task/library must be zero')
    _strict_map(plan.get('execution_policy'),EXECUTION_POLICY,'execution_policy');_strict_map(plan.get('failure_policy'),FAILURE_POLICY,'failure_policy')
    _strict_map(plan.get('failure_exception'),FAILURE_POLICY,'failure_exception')
    runtime=plan.get('runtime');require(isinstance(runtime,dict) and runtime.get('build')==RUNTIME_BUILD and runtime.get('version')==RUNTIME_VERSION and _strict_int(runtime.get('file_count')) and runtime['file_count']==RUNTIME_FILE_COUNT and runtime.get('backend_path')==str(RUNTIME_BACKEND) and isinstance(runtime.get('manifest_sha256'),str) and len(runtime['manifest_sha256'])==64 and all(c in '0123456789abcdef' for c in runtime['manifest_sha256']),'runtime fixed identity changed')
    existing=plan.get('existing_source')
    require(isinstance(existing,dict) and set(existing)==EXISTING_SOURCE_KEYS,'existing source shape changed')
    require(existing.get('app_id')==EXISTING_APP_ID and existing.get('import_run_id')==EXISTING_IMPORT_RUN and existing.get('publish_run_id')==EXISTING_PUBLISH_RUN and existing.get('first_run_id')==EXISTING_FIRST_RUN and existing.get('message_id')==EXISTING_MESSAGE and existing.get('conversation_id')==EXISTING_SESSION,'existing source identity changed')
    _sha256_hex(existing.get('first_run_sha256'),'existing first run');_sha256_hex(existing.get('provider_sha256'),'provider metadata');_sha256_hex(existing.get('key_cipher_sha256'),'provider key cipher');_sha256_hex(existing.get('execution_limits_sha256'),'execution limits')
    require(existing.get('known_apps_contains') is True and uuid(existing.get('provider_id')),'existing provider/known-app binding changed')
    scope=plan.get('diagnostic_scope');_validate_scope(scope,existing['provider_id'])
    require(plan.get('diagnostic_provider_sha256')==existing['provider_sha256'] and plan.get('diagnostic_key_cipher_sha256')==existing['key_cipher_sha256'],'diagnostic provider binding changed')
    sources=verify_source(project,plan.get('source_commit'));require(plan.get('source_files')==sources['files'],'source commit binding changed')
    for name in SOURCE_FILES:
        rel='tools/'+BATCH+'/'+name;canonical=norm_lf(safe_path(root,name).read_bytes());work=norm_lf(safe_path(project,rel).read_bytes());blob=norm_lf(git_blob(project,plan['source_commit'],rel))
        require(canonical==work==blob and hashlib.sha256(work).hexdigest()==sources['files'][rel],'package source not bound to Git: '+name)
    reviewed,_=read_json(root/'reviewed.json','reviewed');protected,_=read_json(root/'protected.json','protected')
    require(plan.get('reviewed_files')=={'reviewed.json':sha(root/'reviewed.json'),'protected.json':sha(root/'protected.json')},'reviewed/protected SHA mismatch')
    require(reviewed.get('source')=='original=existing successful first-case r8 App reused without re-dispatch; modified=385 candidate + 388 manual save','reviewed source label changed')
    require(digest(reviewed.get('original_plan'))==plan.get('original_plan_sha256') and digest(reviewed.get('modified_plan'))==plan.get('modified_plan_sha256'),'reviewed plan digest changed')
    validate_contract(plan,reviewed,backend)
    require(isinstance(protected,dict) and set(protected)=={'parent_909_sha256','old_892_sha256','seal_index_sha256','parent_member_count','seal_member_count','files'},'926 sealed shape changed')
    require(protected==plan.get('protected'),'protected file differs from plan')
    require(protected.get('seal_index_sha256')==SEAL_INDEX_SHA and _sha256_hex(protected.get('parent_909_sha256'),'parent seal') and _sha256_hex(protected.get('old_892_sha256'),'old 892'),'926 seal anchors changed')
    require(_strict_int(protected.get('seal_member_count')) and protected['seal_member_count']==SEAL_391_MEMBER_COUNT,'391 seal member count changed')
    require(_strict_int(protected.get('parent_member_count')) and protected['parent_member_count']==PARENT_SEALED_COUNT,'909 parent count changed')
    require(isinstance(protected.get('files'),dict) and len(protected['files'])==SEALED_COUNT,'926 sealed map changed')
    require(all(isinstance(k,str) and isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v) for k,v in protected['files'].items()),'sealed map values invalid')
    for rel in protected['files']:safe_path(project,rel)
    require(plan.get('protected_sha256')==digest(protected),'protected summary mismatch')
    root_paths=plan.get('root_paths');require(root_paths==ROOT_PATHS,'12 root paths changed')
    roots=plan.get('roots');require(isinstance(roots,dict) and set(roots)==set(ROOT_PATHS),'12 roots changed')
    for label,rel in ROOT_PATHS.items():
        desc=roots[label];require(isinstance(desc,dict) and set(desc)=={'path','kind','objects','secrets','files'} and desc.get('path')==rel and desc.get('kind')=='sqlite','root description changed: '+label)
        for field in ('objects','secrets'):
            value=desc.get(field);require(isinstance(value,dict) and all(isinstance(k,str) and isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v) for k,v in value.items()),'root '+field+' invalid: '+label)
        files=desc.get('files');require(isinstance(files,dict) and all(isinstance(k,str) and k and isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v) for k,v in files.items()),'root assets invalid: '+label)
        for name in files:safe_path(project,str(Path(rel)/name))
    require(plan.get('roots_sha256')==digest({'paths':root_paths,'roots':roots}),'roots summary mismatch')
    refs=plan.get('old_refs');require(isinstance(refs,list) and refs==list(OLD_REFS),'old refs not frozen')
    require(plan.get('approval_phrase')==APPROVAL_PHRASE and plan.get('pins')==PINS,'approval phrase/pins changed')
    return {'plan':plan,'manifest':manifest,'plan_sha256':plan_sha,'manifest_sha256':manifest_sha}
def validate_approval(root,approval,plan,plan_sha,manifest_sha,*,stored=False):
    require(isinstance(approval,dict),'approval must be object')
    if stored:require(set(approval)==APPROVAL_KEYS,'approval fixed fields changed')
    else:require(APPROVAL_KEYS-{'created_at'}<=set(approval),'direct approval metadata incomplete')
    require(approval.get('schema_version')==1,'approval schema changed')
    require(approval.get('authorization_source')=='direct_user_reply','direct user reply required')
    require(approval.get('scope')==BATCH and approval.get('batch_id')==BATCH,'scope/batch mismatch')
    ref=approval.get('question_ref');require(isinstance(ref,str) and __import__('re').fullmatch(r'call_[0-9a-f]{32}/q0',ref),'new call_ID/q0 required')
    require(ref not in OLD_REFS and ref not in (plan.get('old_refs') or []),'old authorization reference refused')
    require(approval.get('literal')==APPROVAL_PHRASE,'approval literal mismatch')
    require(approval.get('plan_sha256')==plan_sha and approval.get('manifest_sha256')==manifest_sha,'plan/manifest binding mismatch')
    _strict_map(approval.get('limits'),LIMITS,'approval limits');_strict_map(approval.get('failure_policy'),FAILURE_POLICY,'approval failure policy')
    _strict_map(approval.get('execution_policy'),EXECUTION_POLICY,'approval execution policy')
    _strict_map(approval.get('failure_exception'),FAILURE_POLICY,'approval failure_exception')
    require(approval.get('wall_seconds')==WALL_SECONDS,'wall seconds changed')
    require(approval.get('dify_estimate')==DIFY_ESTIMATE and approval.get('dify_is_billing_limit') is False and approval.get('host_cost_known') is False,'Dify estimate boundary changed')
    _strict_map(approval.get('current_upper'),CURRENT_UPPER,'current upper');_strict_map(approval.get('proposed_upper'),PROPOSED_UPPER,'proposed upper')
    require(approval.get('old_reservations_preserved') is True and _strict_int(approval.get('new_model_calls')) and approval['new_model_calls']==0 and _strict_int(approval.get('new_tasks')) and approval['new_tasks']==0 and _strict_int(approval.get('new_libraries')) and approval['new_libraries']==0 and approval.get('only_new_login') is True,'scope counts changed')
    require(approval.get('single_use') is True and approval.get('retry') is False,'single-use/no-retry required')
    _validate_scope(approval.get('diagnostic_scope'),plan['existing_source']['provider_id'])
    require(approval.get('diagnostic_scope')==plan['diagnostic_scope'],'approval diagnostic scope differs')
    require(approval.get('diagnostic_provider_sha256')==plan['diagnostic_provider_sha256'] and approval.get('diagnostic_key_cipher_sha256')==plan['diagnostic_key_cipher_sha256'],'approval diagnostic provider binding changed')
    return True
def preflight_run(project,root,backend=None):
    project=Path(project);root=Path(root)
    pkg=validate_package(project,root,backend)
    approval,_=read_json(root/'approval.json','approval');validate_approval(root,approval,pkg['plan'],pkg['plan_sha256'],pkg['manifest_sha256'],stored=True)
    verify_roots_protected(project,pkg['plan'])
    require(not (root/'attempt.json').exists() and not (root/'worker-started.json').exists() and not (root/'live-output').exists(),'batch already consumed')
    return pkg
def _runtime_path(value):
    require(isinstance(value,(str,os.PathLike)) and str(value),'runtime path missing')
    return os.path.normcase(str(Path(value).resolve()))
def _windows_argv(command):
    """Restricted CommandLineToArgvW-style split for the frozen uvicorn command."""
    require(isinstance(command,str) and command.strip() and '\x00' not in command and len(command)<=32767,'runtime command missing/invalid')
    args=[];i=0;n=len(command)
    while i<n:
        while i<n and command[i] in ' \t':i+=1
        if i>=n:break
        arg=[];quoted=False
        while i<n:
            char=command[i]
            if char=='\\':
                start=i
                while i<n and command[i]=='\\':i+=1
                count=i-start
                if i<n and command[i]=='"':
                    arg.append('\\'*(count//2))
                    if count%2==0:quoted=not quoted;i+=1
                    else:arg.append('"');i+=1
                else:arg.append('\\'*count)
            elif char=='"':
                if quoted and i+1<n and command[i+1]=='"':arg.append('"');i+=2
                else:quoted=not quoted;i+=1
            elif char in ' \t' and not quoted:break
            else:arg.append(char);i+=1
        require(not quoted,'unterminated runtime command quote')
        args.append(''.join(arg))
    require(args and len(args)<=64 and all(args),'runtime command empty/invalid')
    return args
def _runtime_process_matches(exe,argv,backend):
    require(isinstance(argv,list) and argv and all(isinstance(token,str) for token in argv) and _runtime_path(argv[0])==_runtime_path(exe),'runtime executable argument mismatch')
    require(_runtime_path(exe)==_runtime_path(REAL_PROJECT/'.venv/Scripts/python.exe'),'runtime executable mismatch')
    require(argv[1:4]==['-m','uvicorn','app.main:app'],'runtime command signature mismatch')
    rest=argv[4:];flags={};index=0
    while index<len(rest):
        token=rest[index]
        if '=' in token:name,value=token.split('=',1)
        else:name=token;index+=1;require(index<len(rest) and rest[index] not in {'--app-dir','--host','--port'},'runtime flag value missing');value=rest[index]
        require(name in {'--app-dir','--host','--port'} and name not in flags,'runtime unexpected/duplicate flag')
        flags[name]=value;index+=1
    require(set(flags)=={'--app-dir','--host','--port'},'runtime fixed flags missing')
    require(_runtime_path(flags['--app-dir'])==_runtime_path(backend),'runtime app-dir mismatch')
    require(flags['--host']=='127.0.0.1' and flags['--port']=='8765','runtime host/port mismatch')
def _runtime_process_matches_command(exe,command,backend):
    return _runtime_process_matches(exe,_windows_argv(command),backend)
def verify_runtime(project,plan,live=True):
    project=Path(project);runtime=plan['runtime'];root=safe_path(project,'.runtime/snapshots/'+runtime['build']);manifest,_=read_json(root/'runtime-manifest.json','runtime manifest')
    require(sha(root/'runtime-manifest.json')==runtime['manifest_sha256'],'runtime manifest SHA changed')
    require(manifest.get('build_id')==runtime['build'] and manifest.get('version')==runtime['version'] and isinstance(manifest.get('files'),dict) and len(manifest['files'])==runtime['file_count'],'runtime manifest identity changed')
    for rel,value in manifest['files'].items():
        require(isinstance(rel,str) and isinstance(value,str) and len(value)==64,'runtime member invalid')
        source=safe_path(project,rel);saved=safe_path(root,rel);require(source.is_file() and saved.is_file() and sha(source)==value and sha(saved)==value,'runtime source/snapshot mismatch: '+rel)
    require(Path(runtime['backend_path']).resolve()==(root/'backend').resolve(),'runtime backend path changed')
    if live:
        import urllib.request
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*a,**kw):return None
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)
        with opener.open('http://127.0.0.1:8765/api/runtime',timeout=10) as response:status=json.load(response)
        require(status.get('build_id')==runtime['build'] and status.get('version')==runtime['version'],'health/runtime identity changed')
        pid=int(safe_path(project,'data/server.pid').read_text('ascii').strip())
        script="$ErrorActionPreference='Stop'; $p=Get-CimInstance Win32_Process -Filter 'ProcessId = "+str(pid)+"'; @{exe=$p.ExecutablePath;cmd=$p.CommandLine} | ConvertTo-Json -Compress"
        import base64
        encoded=base64.b64encode(script.encode('utf-16-le')).decode()
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=20)
        require(result.returncode==0,'CIM process query failed');facts=json.loads(result.stdout.decode('utf-8-sig'))
        _runtime_process_matches_command(facts['exe'],facts['cmd'],runtime['backend_path'])
    return True
@contextlib.contextmanager
def ReadOnly(root):
    db=sqlite3.connect((Path(root)/'flowcraft.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:yield db
    finally:db.close()
def ro_get(root,kind,item):
    with ReadOnly(root) as db:row=db.execute('SELECT value FROM objects WHERE kind=? AND id=?',(kind,item)).fetchone()
    return json.loads(row[0]) if row else None
def ro_list(root,kind):
    with ReadOnly(root) as db:return [json.loads(row[0]) for row in db.execute('SELECT value FROM objects WHERE kind=?',(kind,))]
def ro_secret_cipher(root,item,key):
    with ReadOnly(root) as db:row=db.execute('SELECT value FROM secrets WHERE id=?',(item+':'+key,)).fetchone()
    return bytes(row[0]) if row else None
def capture(root):
    base=Path(root);require(base.is_dir() and not base.is_symlink(),'capture root missing/linked')
    with ReadOnly(base) as db:
        objects={k+':'+i:digest(json.loads(v)) for k,i,v in db.execute('SELECT kind,id,value FROM objects')}
        secrets={i:hashlib.sha256(bytes(v)).hexdigest() for i,v in db.execute('SELECT id,value FROM secrets')}
    files={}
    for path in base.rglob('*'):
        require(not path.is_symlink() and path.resolve().is_relative_to(base.resolve()),'capture symlink/escape: '+str(path))
        if path.is_file():
            rel=path.relative_to(base)
            if len(rel.parts)==1 and rel.name in ROOT_IGNORE:continue
            files[rel.as_posix()]=sha(path)
    return {'objects':objects,'secrets':secrets,'files':files}
def verify_root_paths(project):
    project=Path(project);plan,_=read_json(safe_path(project,ROOT_PLAN),'375 root plan')
    fixed={label:rel for label,rel in ROOT_PATHS.items() if label!='data'}
    raw=plan.get('isolated_paths')
    if isinstance(raw,dict):
        actual={key:value for key,value in raw.items()}
    elif isinstance(raw,list):
        require(all(isinstance(value,str) and value for value in raw) and len(raw)==len(fixed) and len(set(raw))==len(raw),'375 isolated root list changed')
        require(set(raw)==set(fixed.values()),'375 isolated root set changed')
        actual={label:path for label,path in fixed.items()}
    else:raise RuntimeError('375 isolated root map missing')
    require(actual==fixed,'375 isolated root paths changed')
    for rel in ROOT_PATHS.values():safe_path(project,rel)
    return dict(ROOT_PATHS)
def capture_root(project,label,rel):
    path=safe_path(project,rel);require(path.is_dir() and not path.is_symlink(),'root missing/linked: '+rel)
    db=safe_path(project,str(Path(rel)/'flowcraft.sqlite3'));require(db.is_file() and not db.is_symlink(),'root SQLite missing: '+rel)
    value=capture(path);value.update(path=rel,kind='sqlite');return value
def capture_roots(project,include_data=True):
    paths=verify_root_paths(project);labels=[label for label in ROOT_PATHS if include_data or label!='data']
    return {label:capture_root(project,label,paths[label]) for label in labels}
def _seal_member_rel(key):
    require(isinstance(key,str) and key and not Path(key).is_absolute() and '..' not in Path(key).parts,'seal member path invalid')
    prefix='work/isolated-modification385/'
    rel=key if key.startswith(prefix) else prefix+key
    require(rel!=SEAL_385_PATH and not Path(rel).is_absolute() and '..' not in Path(rel).parts,'seal member path invalid')
    return rel
def _verify_sealed_909(project,seal_sha=None):
    project=Path(project);seal_path=safe_path(project,SEAL_385_PATH);seal,seal_raw=read_json(seal_path,'385 seal')
    actual=hashlib.sha256(seal_raw).hexdigest();require(actual==(seal_sha or SEAL_385_INDEX_SHA),'385 seal SHA changed')
    require(isinstance(seal,dict) and len(seal)==SEAL_MEMBER_COUNT,'385 seal must have 16 members')
    members={}
    for key,value in seal.items():
        require(isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value),'385 seal member invalid')
        rel=_seal_member_rel(key)
        require(rel not in members,'385 seal duplicate member');safe_path(project,rel);members[rel]=value
    require(OLD_892_PATH in members,'385 seal omits protected-892')
    old_path=safe_path(project,OLD_892_PATH);old,old_raw=read_json(old_path,'protected-892')
    require(isinstance(old,dict) and len(old)==OLD_892_COUNT,'protected-892 must have 892 members')
    require(members[OLD_892_PATH]==hashlib.sha256(old_raw).hexdigest(),'protected-892 file SHA changed')
    old_map={}
    for rel,value in old.items():
        require(isinstance(rel,str) and rel and not Path(rel).is_absolute() and '..' not in Path(rel).parts,'892 member path invalid')
        require(isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value),'892 member SHA invalid')
        require(rel not in old_map,'892 duplicate member');safe_path(project,rel);old_map[rel]=value
    merged=dict(old_map)
    for rel,value in members.items():
        require(rel not in merged,'sealed map duplicate');merged[rel]=value
    require(SEAL_385_PATH not in merged,'seal self duplicate');merged[SEAL_385_PATH]=actual
    require(len(merged)==PARENT_SEALED_COUNT,'sealed map must total 909')
    for rel,value in merged.items():
        path=safe_path(project,rel);require(path.is_file() and not path.is_symlink() and sha(path)==value,'sealed file SHA changed: '+rel)
    return {'seal_index_sha256':actual,'old_892_sha256':hashlib.sha256(old_raw).hexdigest(),'seal_member_count':len(members),'files':merged}
def verify_sealed(project,seal_sha=None):
    """Verify the 909 parent seal, then merge the fixed 16-member 391 seal (926)."""
    project=Path(project);parent=_verify_sealed_909(project)
    seal_path=safe_path(project,SEAL_391_PATH);seal,seal_raw=read_json(seal_path,'391 seal')
    actual=hashlib.sha256(seal_raw).hexdigest();require(actual==(seal_sha or SEAL_INDEX_SHA),'391 seal SHA changed')
    require(isinstance(seal,dict) and len(seal)==SEAL_391_MEMBER_COUNT,'391 seal must have 16 members')
    members={}
    for key,value in seal.items():
        require(isinstance(key,str) and key and not Path(key).is_absolute() and '..' not in Path(key).parts,'391 seal member path invalid')
        require(key!=SEAL_391_PATH,'391 seal self reference')
        require(isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value),'391 seal member invalid')
        path=safe_path(project,key);require(path.is_file() and not path.is_symlink() and sha(path)==value,'391 sealed file SHA changed: '+key)
        require(key not in members,'391 seal duplicate member');members[key]=value
    merged=dict(parent['files'])
    for rel,value in members.items():
        require(rel not in merged,'391 sealed map duplicate');merged[rel]=value
    require(SEAL_391_PATH not in merged,'391 seal self duplicate');merged[SEAL_391_PATH]=actual
    require(len(merged)==SEALED_COUNT,'merged sealed map must total 926')
    for rel,value in merged.items():
        path=safe_path(project,rel);require(path.is_file() and not path.is_symlink() and sha(path)==value,'merged sealed file SHA changed: '+rel)
    return {'parent_909_sha256':digest(parent['files']),'old_892_sha256':parent['old_892_sha256'],'seal_index_sha256':actual,'parent_member_count':len(parent['files']),'seal_member_count':len(members),'files':merged}
def known_apps(root):
    result=set()
    for kind in ('environment','task','app_runtime_credential','workflow_publication','app_runtime_key_creation','runtime_key_previous_binding'):
        for row in ro_list(root,kind):
            for key in ('app_id','dify_app_id','service_app_id'):
                if uuid(row.get(key)):result.add(row[key])
            for run in row.get('runs',[]):
                if uuid(run.get('app_id')):result.add(run['app_id'])
                value=run.get('result')
                if isinstance(value,dict) and uuid(value.get('app_id')):result.add(value['app_id'])
    return result
def non_secret(value):
    require(isinstance(value,dict),'provider metadata must be mapping')
    return {k:v for k,v in value.items() if k not in SECRET_FIELDS}
def inspect_existing(project):
    """Read-only derivation of the frozen existing App/first-case facts."""
    project=Path(project);data=project/'data'
    task=ro_get(data,'task',TASK_ID);budget=ro_get(data,'task_budget',TASK_ID);env=ro_get(data,'environment',ENVIRONMENT_ID)
    require(isinstance(task,dict) and isinstance(budget,dict) and isinstance(env,dict),'task/budget/env missing')
    require(task.get('id')==TASK_ID and budget.get('id')==TASK_ID and env.get('id')==ENVIRONMENT_ID and env.get('console_workspace_id')==WORKSPACE_ID,'fixed Task/environment/workspace required')
    require(task.get('revision')==8 and task.get('plan_source')=='manual' and task.get('status')=='run_completed','target Task revision/source/status changed')
    # Restored 390 read-only artifact preconditions: reject a missing/changed real
    # artifact before any secret reads or external dispatch.
    plan=task.get('workflow_plan');require(isinstance(plan,dict) and digest(plan)==ORIGINAL_GRAPH_SHA,'original workflow plan changed')
    artifact=task.get('artifact');require(isinstance(artifact,dict) and artifact.get('revision')==8,'artifact revision changed')
    filename=artifact.get('filename');require(isinstance(filename,str) and filename and not Path(filename).is_absolute(),'artifact filename missing')
    real_sha=artifact.get('sha256');require(isinstance(real_sha,str) and real_sha,'artifact sha256 missing')
    artifact_path=safe_path(project,'data/'+task.get('id')+'/'+filename)
    require(artifact_path.is_file() and not artifact_path.is_symlink() and sha(artifact_path)==real_sha,'artifact bytes changed')
    require(task.get('requirements_confirmed') is True and task.get('configuration_confirmed') is True,'target requirements/configuration not confirmed')
    require(task.get('dify_app_id')==EXISTING_APP_ID and task.get('environment_id')==ENVIRONMENT_ID,'existing App binding changed')
    require(len(ro_list(data,'task'))==27,'27 Task baseline changed')
    entries=budget.get('entries');require(isinstance(entries,list) and len(entries)==5,'5 settled budget required')
    require(all(e.get('status')=='settled' and e.get('call_status')=='returned' for e in entries),'settled ledger changed')
    require(budget.get('limit_usd')=='0.600' and budget.get('policy_revision')==1,'budget policy changed')
    limits=ro_get(data,'execution_limits',TASK_ID);require(isinstance(limits,dict) and limits.get('id')==TASK_ID,'existing execution policy missing')
    require(_strict_int(limits.get('policy_revision')) and limits['policy_revision']==1 and limits.get('max_started_runs')==12 and limits.get('max_total_minutes')==45 and limits.get('max_reported_cost_usd') is None,'existing execution policy changed')
    runs=task.get('runs');require(isinstance(runs,list) and len(runs)==EXISTING_RUN_COUNT,'exactly three prior run records required')
    by_id={r.get('id'):r for r in runs if isinstance(r,dict)}
    require(set(by_id)=={EXISTING_IMPORT_RUN,EXISTING_PUBLISH_RUN,EXISTING_FIRST_RUN},'prior run identities changed')
    import_run=by_id[EXISTING_IMPORT_RUN];publish_run=by_id[EXISTING_PUBLISH_RUN];first=by_id[EXISTING_FIRST_RUN]
    require(import_run.get('kind')=='import' and import_run.get('status')=='success' and (import_run.get('result') or {}).get('app_id')==EXISTING_APP_ID,'prior import evidence changed')
    require(publish_run.get('kind')=='publish' and publish_run.get('status')=='success' and (publish_run.get('result') or {}).get('app_id')==EXISTING_APP_ID,'prior publish evidence changed')
    require(first.get('kind')=='run' and first.get('status')=='success' and (first.get('evaluation') or {}).get('status')=='passed','first case did not pass')
    require(first.get('revision')==8 and first.get('app_id')==EXISTING_APP_ID and first.get('environment_id')==ENVIRONMENT_ID and first.get('app_type')=='advanced-chat','first run source changed')
    require(first.get('environment_binding')==_binding(env),'first run environment binding changed')
    require(not first.get('diagnostics'),'first run already has diagnostics')
    result=first.get('result') or {};require(isinstance(result,dict),'first run result missing')
    require((result.get('message_id') or result.get('id'))==EXISTING_MESSAGE and result.get('conversation_id')==EXISTING_SESSION,'first message/session changed')
    require(result.get('workflow_run_id') is None,'first run unexpectedly has a native workflow_run_id')
    require(env.get('version')=='1.17.1' and env.get('service_app_id')==EXISTING_APP_ID,'existing service App not bound')
    require(isinstance(env.get('console_login_binding'),dict) and env['console_login_binding'].get('workspace_id')==WORKSPACE_ID,'saved login binding changed')
    raw_key=ro_secret_cipher(data,ENVIRONMENT_ID,'service_api_key');require(raw_key,'existing runtime key missing')
    auth=ro_get(data,'app_runtime_credential',ENVIRONMENT_ID+':app-runtime:'+EXISTING_APP_ID)
    key_creation=[r for r in ro_list(data,'app_runtime_key_creation') if r.get('app_id')==EXISTING_APP_ID and r.get('state')=='succeeded']
    require(isinstance(auth,dict) and auth.get('app_id')==EXISTING_APP_ID or key_creation,'existing key provenance missing')
    known=known_apps(data);require(EXISTING_APP_ID in known,'existing App not in frozen known set')
    configuration=task.get('configuration');require(isinstance(configuration,dict),'task configuration missing')
    provider_id=configuration.get('assistant_provider_id');require(uuid(provider_id),'assistant provider id invalid')
    provider=ro_get(data,'provider',provider_id);require(isinstance(provider,dict) and provider.get('id')==provider_id,'assistant provider missing')
    key_cipher=ro_secret_cipher(data,provider_id,'api_key');require(key_cipher,'provider key cipher missing')
    return {'task':task,'budget':budget,'env':env,'limits':limits,'known_apps':known,'first_run':first,
            'provider_id':provider_id,'provider_sha256':digest(non_secret(provider)),
            'key_cipher_sha256':hashlib.sha256(key_cipher).hexdigest(),'first_run_sha256':run_source_hash(first),
            'task_sha256':digest(task),'budget_sha256':digest(budget),'environment_sha256':digest(env),'limits_sha256':digest(limits)}
def _binding(env):
    return hashlib.sha256(json.dumps({k:env.get(k) for k in ('id','base_url','version')},sort_keys=True).encode()).hexdigest()
def _source_files(project,commit):
    return verify_source(project,commit)
_COMPILERS={}
def _backend_modules(backend):
    backend=str(Path(backend).resolve())
    app=sys.modules.get('app')
    if app is not None:
        app_file=Path(str(getattr(app,'__file__','') or '')).resolve()
        require(app_file.parent==Path(backend)/'app','different app package already imported: '+str(app_file))
    if backend in _COMPILERS:return _COMPILERS[backend]
    require(Path(backend).is_dir() and not Path(backend).is_symlink(),'fixed runtime backend missing')
    if backend in sys.path:sys.path.remove(backend)
    sys.path.insert(0,backend)
    from app.workflow_plan import compile_workflow_plan
    from app.workflow_publication import core
    from app.dsl_roundtrip import parse
    _COMPILERS[backend]=(compile_workflow_plan,core,parse)
    return _COMPILERS[backend]
_INTAKE={}
def _backend_intake(backend):
    backend=str(Path(backend).resolve())
    _backend_modules(backend)
    if backend not in _INTAKE:
        from app import intake
        _INTAKE[backend]=intake
    return _INTAKE[backend]
def _standard_topics(backend,task,plan,requirements):
    intake=_backend_intake(backend)
    return [row['id'] for row in intake.topics({**task,'workflow_plan':plan,'requirements':requirements})]
def _validate_topic_answers(backend,task,plan,requirements,answers,label):
    intake=_backend_intake(backend)
    require(isinstance(answers,dict),'topic answers must be mapping: '+label)
    standard=_standard_topics(backend,task,plan,requirements)
    require(len(standard)==len(set(standard)),'standard topics duplicated: '+label)
    require(set(answers)==set(standard),'topic answers differ from current standard: '+label)
    for key,value in answers.items():
        require(isinstance(value,str) and value.strip(),'topic answer must be non-empty string: '+label+' '+str(key))
        require(not intake.unknown_placeholder(value),'topic answer is unknown placeholder: '+label+' '+key)
        require(not value.strip().startswith(intake.UNKNOWN),'topic answer is unknown/placeholder: '+label+' '+key)
    for key in intake.BASE:
        require(key in requirements,'requirements missing base topic: '+key)
        require(key in answers and answers[key]==requirements[key],'base topic answer differs from requirements: '+label+' '+key)
    return answers
def _compile_graph(backend,task,plan):
    compile_workflow_plan,core,parse=_backend_modules(backend)
    content,validation=compile_workflow_plan({**task,'workflow_plan':plan})
    require(isinstance(validation,dict) and validation.get('valid') is True,'static compile failed: '+'; '.join(validation.get('errors') or []))
    try:root=parse(content,'advanced-chat')
    except ValueError as exc:raise RuntimeError('compiled DSL invalid: '+str(exc)) from exc
    return root,core(root['workflow'])
def _derived_core(backend,root):
    core=_backend_modules(backend)[1]
    try:return core(root['workflow'])
    except Exception as exc:raise RuntimeError('core derivation failed') from exc
def _expected_model(task):
    config=task.get('configuration')
    require(isinstance(config,dict),'task configuration missing')
    require(config.get('temperature')==MODEL_TEMPERATURE and config.get('max_tokens')==MODEL_MAX_TOKENS,'model temperature/max_tokens changed')
    require(config.get('model_parameters')=={'thinking':MODEL_THINKING},'model thinking parameter changed')
    provider=config.get('dify_model_provider');name=config.get('dify_model')
    require(isinstance(provider,str) and provider.strip() and isinstance(name,str) and name.strip(),'Dify model provider/name missing')
    return {'provider':provider,'name':name,'mode':'chat','completion_params':dict(MODEL_COMPLETION)}
def _validate_native(task,plan,root,core=None):
    require(isinstance(root,dict) and isinstance(root.get('app'),dict) and root['app'].get('mode')=='advanced-chat' and root['app'].get('name')==task.get('name'),'compiled app identity changed')
    workflow=root.get('workflow') if isinstance(root,dict) else None
    graph=workflow.get('graph') if isinstance(workflow,dict) else None
    require(isinstance(graph,dict) and isinstance(graph.get('nodes'),list) and isinstance(graph.get('edges'),list),'native workflow missing')
    if core is not None:
        require(isinstance(core,dict) and isinstance(core.get('nodes'),list) and {node.get('id') for node in core['nodes']}=={node.get('id') for node in graph['nodes']},'compiled core graph changed')
    require('http-request' not in {node.get('type') for node in plan.get('nodes',[])},'planned http-request not allowed')
    rows=[node for node in graph['nodes'] if isinstance(node,dict) and isinstance(node.get('data'),dict)]
    require('http-request' not in {node['data'].get('type') for node in rows},'compiled http-request not allowed')
    expected=_expected_model(task)
    plan_models=[node for node in plan.get('nodes',[]) if node.get('type') in ('llm','question-classifier','parameter-extractor')]
    native_models=[node['data']['model'] for node in rows if 'model' in node['data']]
    require(len(plan_models)==len(native_models) and native_models,'compiled model nodes changed')
    for model in native_models:require(model==expected,'compiled model provider/parameters changed')
    plan_kb=[node for node in plan.get('nodes',[]) if node.get('type')=='knowledge-retrieval']
    native_kb=[node['data'] for node in rows if node['data'].get('type')=='knowledge-retrieval']
    require(len(plan_kb)==len(native_kb),'compiled knowledge nodes changed')
    for source,data in zip(plan_kb,native_kb):
        config=source.get('config') or {}
        require(data.get('dataset_ids')==config.get('dataset_ids') and isinstance(data.get('dataset_ids'),list) and data['dataset_ids'],'compiled dataset ids changed')
        multi=data.get('multiple_retrieval_config') or {}
        require(multi.get('top_k')==KB_TOP_K and multi.get('score_threshold') is None and multi.get('reranking_enable') is False,'knowledge retrieval settings changed')
    declared=[{'name':row.get('name'),'value':row.get('initial_value')} for row in plan.get('conversation_variables',[])]
    native_state=[{'name':row.get('name'),'value':row.get('value')} for row in workflow.get('conversation_variables',[])]
    require(declared==native_state,'conversation state declarations changed')
    require(workflow.get('environment_variables')==[],'http environment declarations present')
    return True
def _sentence_changes(original,candidate):
    require(digest(original)==ORIGINAL_GRAPH_SHA,'original graph SHA changed')
    require(digest(candidate)==MODIFIED_GRAPH_SHA,'fixed candidate graph SHA changed')
    nodes=original.get('nodes');require(isinstance(nodes,list) and nodes and all(isinstance(node,dict) for node in nodes),'original nodes missing')
    candidate_nodes=candidate.get('nodes');require(isinstance(candidate_nodes,list) and all(isinstance(node,dict) for node in candidate_nodes),'candidate nodes missing')
    ids=[node.get('id') for node in nodes]
    require([node.get('id') for node in candidate_nodes]==ids,'node order/ids changed')
    require(ids.count('no_hit_text')==1 and ids.count('faq_llm')==1,'fixed text nodes missing')
    no_hit=ids.index('no_hit_text');faq=ids.index('faq_llm')
    require(nodes[no_hit].get('type')=='template-transform' and nodes[faq].get('type')=='llm','fixed text node types changed')
    changes=_diff(original,candidate)
    want=[('nodes',no_hit,'config','template'),('nodes',faq,'config','system_prompt')]
    require(len(changes)==2 and {tuple(path) for path,_,_ in changes}==set(want),'modified plan has changes beyond the two reviewed sentences')
    by={tuple(path):(old,new) for path,old,new in changes}
    old,new=by[want[0]]
    require(old==NO_ANSWER_OLD and new==NO_ANSWER_NEW,'no_hit template sentence changed')
    old,new=by[want[1]]
    require(isinstance(old,str) and isinstance(new,str) and old.count(NO_ANSWER_OLD)==1,'faq system prompt sentence missing')
    require(new==old.replace(NO_ANSWER_OLD,NO_ANSWER_NEW),'faq system prompt sentence not replaced exactly once')
    require(candidate.get('conversation_variables')==original.get('conversation_variables'),'conversation state declarations changed')
    return changes
def _diff(left,right,path=()):
    if type(left) is not type(right):return [(path,left,right)]
    if isinstance(left,dict):
        if set(left)!=set(right):return [(path,left,right)]
        out=[]
        for key in sorted(left):out+=_diff(left[key],right[key],path+(key,))
        return out
    if isinstance(left,list):
        if len(left)!=len(right):return [(path,left,right)]
        out=[]
        for i,(a,b) in enumerate(zip(left,right)):out+=_diff(a,b,path+(i,))
        return out
    return [] if left==right else [(path,left,right)]
def _changed_cases(cases):
    copy_cases=copy.deepcopy(cases);hits=[]
    for index,case in enumerate(copy_cases):
        expectation=case.get('expectation') if isinstance(case,dict) else None
        expected=expectation.get('expected') if isinstance(expectation,dict) else None
        if expected==NO_ANSWER_OLD:hits.append(index)
    require(len(hits)==1,'unique no-answer expectation required')
    copy_cases[hits[0]]['expectation']['expected']=NO_ANSWER_NEW
    return copy_cases
def _modified_requirements(requirements):
    value=copy.deepcopy(requirements)
    require(isinstance(value.get('output'),str) and value['output'].count(NO_ANSWER_OLD)==1,'requirements output lacks the single sentence')
    value['output']=value['output'].replace(NO_ANSWER_OLD,NO_ANSWER_NEW)
    return value
def _validate_trace(expectations,cases,native_ids):
    require(isinstance(expectations,dict) and expectations,'trace expectations required')
    require(isinstance(cases,list) and cases,'six cases required')
    ids=[];total=0
    for case in cases:
        require(isinstance(case,dict) and isinstance(case.get('id'),str) and case['id'],'case identity missing')
        ids.append(case['id']);table=expectations.get(case['id'])
        turns={'1','2'} if case.get('followups') else {'1'}
        require(isinstance(table,dict) and set(table)==turns,'case/turn trace expectations incomplete: '+case['id'])
        for entry in table.values():
            require(isinstance(entry,dict) and set(entry)<={'must','must_not','any_of'} and 'must' in entry and 'must_not' in entry,'trace expectation shape changed')
            for field in ('must','must_not'):
                rows=entry[field]
                require(isinstance(rows,list) and all(isinstance(node,str) and node for node in rows) and len(set(rows))==len(rows),'trace node list malformed')
                require(set(rows)<=native_ids,'trace expectation names unknown native node')
            require(not set(entry['must'])&set(entry['must_not']),'trace must/must_not conflict')
            groups=entry.get('any_of')
            if groups is not None:
                require(isinstance(groups,list) and groups,'trace any_of malformed')
                seen=set()
                for group in groups:
                    require(isinstance(group,list) and group and all(isinstance(node,str) and node for node in group) and len(set(group))==len(group),'trace any_of group malformed')
                    require(set(group)<=native_ids,'trace any_of names unknown native node')
                    require(not set(group)&set(entry['must_not']) and not seen&set(group),'trace any_of conflict')
                    seen|=set(group)
            total+=1
    require(set(expectations)==set(ids),'trace expectations contain unknown/missing cases')
    require(total==7,'seven turns per version required')
    return True
def reviewed_inputs(project,task,budget,env,review,backend=None):
    require(isinstance(review,dict) and review.get('schema_version')==1 and review.get('batch_id')==BATCH,'review identity')
    require(review.get('task_id')==TASK_ID and review.get('environment_id')==ENVIRONMENT_ID,'review target changed')
    require(review.get('review_authority')=='standing_delegated_content_review','standing delegated content review required')
    require(review.get('actor')==REVIEW_ACTOR and review.get('human_signoff') is False and review.get('decision')=='proceed','root agent review incomplete')
    require(digest(task)==review.get('task_sha256') and digest(budget)==review.get('budget_sha256') and digest(env)==review.get('environment_sha256'),'task/budget/environment digest changed')
    require(review.get('existing_app_id')==EXISTING_APP_ID,'review existing App changed')
    runs=[r for r in task.get('runs',[]) if isinstance(r,dict) and r.get('id')==EXISTING_FIRST_RUN]
    require(len(runs)==1 and review.get('first_run_sha256')==run_source_hash(runs[0]),'review first run binding changed')
    _validate_scope(review.get('diagnostic_scope'),(task.get('configuration') or {}).get('assistant_provider_id'))
    _sha256_hex(review.get('diagnostic_provider_sha256'),'review provider metadata');_sha256_hex(review.get('diagnostic_key_cipher_sha256'),'review provider key cipher')
    cases=task.get('test_cases');requirements=task.get('requirements')
    require(isinstance(cases,list) and len(cases)==6 and isinstance(requirements,dict),'six task cases/requirements required')
    require(review.get('cases_sha256')==digest(cases),'task cases digest changed')
    require(review.get('original_plan_sha256')==ORIGINAL_GRAPH_SHA and review.get('modified_plan_sha256')==MODIFIED_GRAPH_SHA,'review graph SHA changed')
    original=task.get('workflow_plan');require(isinstance(original,dict),'r8 workflow missing')
    fixed_path=safe_path(project,FIXED_CANDIDATE_PATH)
    candidate,_=read_json(fixed_path,'fixed modified candidate')
    require(digest(candidate)==MODIFIED_GRAPH_SHA,'fixed candidate graph SHA changed')
    provided=review.get('modified_candidate_path')
    if provided is not None:
        provided_path=Path(provided) if isinstance(provided,str) and Path(provided).is_absolute() else Path(project)/str(provided)
        require(isinstance(provided,str) and provided_path.resolve()==fixed_path.resolve(),'candidate path override refused')
    if 'modified_plan' in review:require(review['modified_plan']==candidate,'review modified plan differs from fixed candidate')
    if review.get('cases') is not None:require(review['cases']==cases,'review cases differ from Task')
    _sentence_changes(original,candidate)
    changed_cases=_changed_cases(cases);modified_requirements=_modified_requirements(requirements)
    backend=backend or RUNTIME_BACKEND
    raw_answers=review.get('topic_answers')
    require(isinstance(raw_answers,dict) and set(raw_answers)=={'original','modified'},'two-version topic answers required')
    original_answers=_validate_topic_answers(backend,task,original,requirements,raw_answers['original'],'original')
    modified_answers=_validate_topic_answers(backend,task,candidate,modified_requirements,raw_answers['modified'],'modified')
    topic_answers={'original':copy.deepcopy(original_answers),'modified':copy.deepcopy(modified_answers)}
    raw_fixture=review.get('fixture')
    fixture={'task_name':task.get('name'),'cases':copy.deepcopy(cases),'requirements':copy.deepcopy(requirements),'changed_no_hit_reply':NO_ANSWER_NEW,'inputs':{'no_hit_reply':NO_ANSWER_OLD},'topic_answers':topic_answers}
    if raw_fixture is not None:require(raw_fixture==fixture,'review fixture differs from Task')
    expectations=review.get('trace_expectations');require(isinstance(expectations,dict) and expectations,'trace expectations required')
    native,core=_compile_graph(backend,task,original);modified_native,modified_core=_compile_graph(backend,task,candidate)
    _validate_native(task,original,native,core);_validate_native(task,candidate,modified_native,modified_core)
    require(native['workflow'].get('conversation_variables')==modified_native['workflow'].get('conversation_variables'),'compiled state declarations changed')
    native_ids={node['id'] for node in native['workflow']['graph']['nodes']}
    require(native_ids=={node['id'] for node in modified_native['workflow']['graph']['nodes']},'compiled node ids changed')
    _validate_trace(expectations,cases,native_ids)
    contract={'owner_task_id':task.get('id'),'review_source':{'authority':'standing_delegated_content_review','actor':REVIEW_ACTOR,'human_signoff':False,'decision':'proceed'},'topic_answers':topic_answers,
              'original':{'plan':copy.deepcopy(original),'native':native,'core':core,'trace_expectations':expectations,'requirements':copy.deepcopy(requirements),'cases':copy.deepcopy(cases)},
              'modified':{'plan':copy.deepcopy(candidate),'native':modified_native,'core':modified_core,'trace_expectations':expectations,'requirements':modified_requirements,'cases':changed_cases}}
    if review.get('contract') is not None:require(review['contract']==contract,'review contract differs from compiled contract')
    return fixture,contract,candidate
def validate_contract(plan,reviewed,backend=None):
    backend=backend or RUNTIME_BACKEND
    contract=plan.get('contract');fixture=plan.get('fixture');compile_meta=plan.get('compile')
    require(isinstance(contract,dict) and set(contract)=={'owner_task_id','review_source','topic_answers','original','modified'},'contract shape changed')
    require(contract.get('review_source')=={'authority':'standing_delegated_content_review','actor':REVIEW_ACTOR,'human_signoff':False,'decision':'proceed'},'review source changed')
    for side in ('original','modified'):
        row=contract[side]
        require(isinstance(row,dict) and set(row)=={'plan','native','core','trace_expectations','requirements','cases'},'contract side shape changed')
        require(isinstance(row['plan'],dict) and isinstance(row['native'],dict) and isinstance(row['core'],dict),'contract graph missing')
        require(isinstance(row['requirements'],dict) and isinstance(row['cases'],list),'contract task inputs missing')
    original=contract['original'];modified=contract['modified']
    require(digest(original['plan'])==ORIGINAL_GRAPH_SHA and digest(modified['plan'])==MODIFIED_GRAPH_SHA,'contract graph SHA changed')
    require(plan.get('original_graph_sha256')==ORIGINAL_GRAPH_SHA and plan.get('modified_graph_sha256')==MODIFIED_GRAPH_SHA,'plan graph anchors changed')
    require(plan.get('original_plan_sha256')==ORIGINAL_GRAPH_SHA and plan.get('modified_plan_sha256')==MODIFIED_GRAPH_SHA,'plan graph digests changed')
    require(plan.get('original_native_sha256')==digest(original['native']) and plan.get('original_core_sha256')==digest(original['core']) and plan.get('modified_native_sha256')==digest(modified['native']) and plan.get('modified_core_sha256')==digest(modified['core']),'native/core digest changed')
    require(plan.get('fixture_sha256')==digest(fixture) and plan.get('contract_sha256')==digest(contract),'fixture/contract digest changed')
    require(isinstance(reviewed,dict) and reviewed.get('contract')==contract and reviewed.get('fixture')==fixture,'reviewed contract/fixture differs')
    require(reviewed.get('original_plan')==original['plan'] and reviewed.get('modified_plan')==modified['plan'],'reviewed plans differ')
    require(digest(reviewed.get('cases'))==digest(original['cases']),'reviewed cases differ')
    require(reviewed.get('trace_expectations')==original['trace_expectations']==modified['trace_expectations'],'trace expectations differ')
    require(plan.get('original_requirements_sha256')==digest(original['requirements']) and plan.get('original_cases_sha256')==digest(original['cases']),'task input binding changed')
    require(plan.get('trace_expectations_sha256')==digest(original['trace_expectations']),'trace digest changed')
    require(contract.get('owner_task_id')==plan.get('task_id'),'contract task id changed')
    require(isinstance(compile_meta,dict) and set(compile_meta)=={'task_id','task_name','app_type','configuration','messages'} and compile_meta.get('app_type')=='advanced-chat' and compile_meta.get('task_id')==plan.get('task_id'),'compile metadata changed')
    _sentence_changes(original['plan'],modified['plan'])
    require(_modified_requirements(original['requirements'])==modified['requirements'],'modified requirements differ')
    require(_changed_cases(original['cases'])==modified['cases'],'modified cases differ')
    require(isinstance(fixture,dict) and set(fixture)=={'task_name','cases','requirements','changed_no_hit_reply','inputs','topic_answers'} and fixture.get('task_name')==compile_meta['task_name'] and fixture.get('cases')==original['cases'] and fixture.get('requirements')==original['requirements'] and fixture.get('changed_no_hit_reply')==NO_ANSWER_NEW and fixture.get('inputs')=={'no_hit_reply':NO_ANSWER_OLD},'fixture differs from task')
    topic_answers=contract.get('topic_answers')
    require(isinstance(topic_answers,dict) and set(topic_answers)=={'original','modified'} and topic_answers==fixture.get('topic_answers'),'topic answers differ from fixture')
    require(plan.get('topic_answers_sha256')==digest(topic_answers),'topic answers digest changed')
    task_meta={'id':compile_meta['task_id'],'name':compile_meta['task_name'],'app_type':compile_meta['app_type'],'configuration':compile_meta['configuration'],'messages':compile_meta['messages']}
    _validate_topic_answers(backend,task_meta,original['plan'],original['requirements'],topic_answers['original'],'original')
    _validate_topic_answers(backend,task_meta,modified['plan'],modified['requirements'],topic_answers['modified'],'modified')
    _validate_native(task_meta,original['plan'],original['native'],original['core']);_validate_native(task_meta,modified['plan'],modified['native'],modified['core'])
    require(_derived_core(backend,original['native'])==original['core'],'core is not derived from native workflow')
    require(_derived_core(backend,modified['native'])==modified['core'],'core is not derived from native workflow')
    compile_task={'id':compile_meta['task_id'],'name':compile_meta['task_name'],'app_type':'advanced-chat','configuration':compile_meta['configuration']}
    compiled_native,compiled_core=_compile_graph(backend,compile_task,original['plan'])
    require(compiled_native==original['native'] and compiled_core==original['core'],'native/core is not actual compilation')
    compiled_native,compiled_core=_compile_graph(backend,compile_task,modified['plan'])
    require(compiled_native==modified['native'] and compiled_core==modified['core'],'native/core is not actual compilation')
    require(original['native']['workflow'].get('conversation_variables')==modified['native'].get('workflow',{}).get('conversation_variables'),'compiled state declarations changed')
    ids={node['id'] for node in original['native']['workflow']['graph']['nodes']}
    _validate_trace(original['trace_expectations'],original['cases'],ids)
    return True
def _canonical_root(project,must_exist=False):
    work=Path(project)/'work';require(work.is_dir() and not work.is_symlink(),'work directory missing')
    root=work/BATCH
    if must_exist:require(root.is_dir() and not root.is_symlink(),'canonical missing')
    else:require(not root.exists(),'canonical exists')
    return root
def _compare_existing(plan,facts):
    existing=plan['existing_source']
    require(facts['task_sha256']==plan['task_sha256'] and facts['budget_sha256']==plan['budget_sha256'] and facts['environment_sha256']==plan['environment_sha256'],'existing Task/budget/environment changed')
    require(facts['first_run_sha256']==existing['first_run_sha256'],'existing first run changed')
    require(facts['provider_sha256']==existing['provider_sha256'] and facts['key_cipher_sha256']==existing['key_cipher_sha256'],'existing provider key changed')
    require(facts['limits_sha256']==existing['execution_limits_sha256'],'existing execution policy changed')
    require(facts['provider_id']==existing['provider_id'],'existing provider id changed')
    require(EXISTING_APP_ID in facts['known_apps'],'existing App left frozen known set')
    return True
def prepare(project,source_commit,review_path):
    project=Path(project);require(project.resolve()==REAL_PROJECT.resolve(),'only fixed original project')
    data=project/'data';review,_=read_json(review_path,'review')
    require(review.get('schema_version')==1 and review.get('batch_id')==BATCH,'review identity')
    sources=verify_source(project,source_commit);fixed=verify_fixed_reuse(project);protected=verify_sealed(project)
    facts=inspect_existing(project)
    task=facts['task'];budget=facts['budget'];env=facts['env'];limits=facts['limits']
    require(review.get('task_sha256')==facts['task_sha256'] and review.get('budget_sha256')==facts['budget_sha256'] and review.get('environment_sha256')==facts['environment_sha256'],'review task/budget/environment digest changed')
    require(review.get('first_run_sha256')==facts['first_run_sha256'] and review.get('existing_app_id')==EXISTING_APP_ID,'review existing source changed')
    require(review.get('diagnostic_provider_sha256')==facts['provider_sha256'] and review.get('diagnostic_key_cipher_sha256')==facts['key_cipher_sha256'],'review provider metadata/cipher changed')
    fixture,contract,modified=reviewed_inputs(project,task,budget,env,review)
    cases=task['test_cases'];requirements=task['requirements'];expectations=review['trace_expectations']
    if 'protected' in review:
        require(isinstance(review['protected'],dict) and review['protected'].get('files')==protected['files'],'review 926 map mismatch')
    roots=capture_roots(project)
    final=_canonical_root(project);root=final.with_name(final.name+'.tmp-'+__import__('uuid').uuid4().hex);root.mkdir()
    try:
        old=capture(data)
        for name in SOURCE_FILES:(root/name).write_bytes(safe_path(project,'tools/'+BATCH+'/'+name).read_bytes())
        reviewed={'original_plan':task['workflow_plan'],'modified_plan':modified,'cases':cases,'trace_expectations':expectations,
                  'fixture':fixture,'contract':contract,
                  'original_native_sha256':digest(contract['original']['native']),'original_core_sha256':digest(contract['original']['core']),
                  'modified_native_sha256':digest(contract['modified']['native']),'modified_core_sha256':digest(contract['modified']['core']),
                  'source':'original=existing successful first-case r8 App reused without re-dispatch; modified=385 candidate + 388 manual save',
                  'task_sha256':review['task_sha256'],'budget_sha256':review['budget_sha256']}
        atomic_json(root/'reviewed.json',reviewed);atomic_json(root/'protected.json',protected)
        runtime={'build':RUNTIME_BUILD,'version':RUNTIME_VERSION,'file_count':RUNTIME_FILE_COUNT,'backend_path':str(RUNTIME_BACKEND),'manifest_sha256':review['runtime_manifest_sha256']}
        existing={'app_id':EXISTING_APP_ID,'import_run_id':EXISTING_IMPORT_RUN,'publish_run_id':EXISTING_PUBLISH_RUN,
                  'first_run_id':EXISTING_FIRST_RUN,'message_id':EXISTING_MESSAGE,'conversation_id':EXISTING_SESSION,
                  'first_run_sha256':facts['first_run_sha256'],'provider_id':facts['provider_id'],'provider_sha256':facts['provider_sha256'],
                  'key_cipher_sha256':facts['key_cipher_sha256'],'execution_limits_sha256':facts['limits_sha256'],'known_apps_contains':True}
        plan={'schema_version':1,'batch_id':BATCH,'source_commit':source_commit,'source_files':sources['files'],'fixed_reuse':fixed,
              'pins':PINS,'task_id':TASK_ID,'task_revision':8,'task_sha256':facts['task_sha256'],'budget_sha256':facts['budget_sha256'],
              'environment_id':ENVIRONMENT_ID,'workspace_id':WORKSPACE_ID,'environment_sha256':facts['environment_sha256'],
              'existing_source':existing,'diagnostic_scope':review['diagnostic_scope'],
              'diagnostic_provider_sha256':facts['provider_sha256'],'diagnostic_key_cipher_sha256':facts['key_cipher_sha256'],
              'original_plan_sha256':ORIGINAL_GRAPH_SHA,'modified_plan_sha256':MODIFIED_GRAPH_SHA,'artifact_sha256':task['artifact']['sha256'],
              'original_graph_sha256':ORIGINAL_GRAPH_SHA,'modified_graph_sha256':MODIFIED_GRAPH_SHA,
              'original_native_sha256':digest(contract['original']['native']),'original_core_sha256':digest(contract['original']['core']),
              'modified_native_sha256':digest(contract['modified']['native']),'modified_core_sha256':digest(contract['modified']['core']),
              'fixture_sha256':digest(fixture),'contract_sha256':digest(contract),
              'topic_answers_sha256':digest(contract['topic_answers']),
              'original_requirements_sha256':digest(requirements),'original_cases_sha256':digest(cases),
              'trace_expectations_sha256':digest(expectations),
              'compile':{'task_id':task.get('id'),'task_name':task.get('name'),'app_type':'advanced-chat','configuration':task.get('configuration'),'messages':copy.deepcopy(task.get('messages',[]))},
              'limits':LIMITS,'current_upper':CURRENT_UPPER,'proposed_upper':PROPOSED_UPPER,'model_estimate_book_upper_usd':MODEL_BOOK,
              'estimated_new_dify_usd':DIFY_ESTIMATE,'dify_is_billing_limit':False,'host_cost_known':False,'wall_seconds':WALL_SECONDS,
              'old_reservations_preserved':True,'new_model_calls':0,'new_tasks':0,'new_libraries':0,
              'execution_policy':EXECUTION_POLICY,'failure_policy':FAILURE_POLICY,'failure_exception':FAILURE_POLICY,
              'approval_phrase':APPROVAL_PHRASE,'old_refs':list(OLD_REFS),'protected':protected,'protected_sha256':digest(protected),
              'root_paths':dict(ROOT_PATHS),'roots':roots,'roots_sha256':digest({'paths':ROOT_PATHS,'roots':roots}),'runtime':runtime,'production_capture_sha256':digest(old),
              'reviewed_files':{'reviewed.json':sha(root/'reviewed.json'),'protected.json':sha(root/'protected.json')},
              'fixture':fixture,'contract':contract}
        atomic_json(root/'plan.json',plan)
        files={name:sha(root/name) for name in PACKAGE_FILES if (root/name).exists()}
        manifest={'schema_version':1,'batch_id':BATCH,'plan_sha256':sha(root/'plan.json'),'files':files}
        atomic_json(root/'manifest.json',manifest)
        validate_package(project,root);verify_runtime(project,plan,live=False);verify_roots_protected(project,plan)
        os.replace(root,final)
    except BaseException:
        import shutil;shutil.rmtree(root,ignore_errors=True);raise
    return plan
def approve(project,authorization_path):
    project=Path(project);require(project.resolve()==REAL_PROJECT.resolve(),'only fixed original project')
    root=_canonical_root(project,True);pkg=validate_package(project,root)
    require(verify_fixed_reuse(project)==pkg['plan'].get('fixed_reuse'),'fixed source reuse changed')
    verify_roots_protected(project,pkg['plan']);verify_runtime(project,pkg['plan'],live=False)
    facts=inspect_existing(project);_compare_existing(pkg['plan'],facts)
    auth,_=read_json(authorization_path,'authorization')
    validate_approval(root,auth,pkg['plan'],pkg['plan_sha256'],pkg['manifest_sha256'],stored=False)
    require(not (root/'approval.json').exists() and not (root/'attempt.json').exists() and not (root/'worker-started.json').exists() and not (root/'live-output').exists(),'already approved/consumed')
    approval={'schema_version':1,'batch_id':BATCH,'authorization_source':'direct_user_reply','scope':BATCH,
        'question_ref':auth['question_ref'],'literal':APPROVAL_PHRASE,'plan_sha256':pkg['plan_sha256'],'manifest_sha256':pkg['manifest_sha256'],
        'limits':LIMITS,'failure_policy':FAILURE_POLICY,'execution_policy':EXECUTION_POLICY,'wall_seconds':WALL_SECONDS,
        'dify_estimate':DIFY_ESTIMATE,'dify_is_billing_limit':False,'host_cost_known':False,
        'current_upper':CURRENT_UPPER,'proposed_upper':PROPOSED_UPPER,'old_reservations_preserved':True,
        'new_model_calls':0,'new_tasks':0,'new_libraries':0,'only_new_login':True,'failure_exception':FAILURE_POLICY,
        'single_use':True,'retry':False,
        'diagnostic_scope':pkg['plan']['diagnostic_scope'],'diagnostic_provider_sha256':pkg['plan']['diagnostic_provider_sha256'],
        'diagnostic_key_cipher_sha256':pkg['plan']['diagnostic_key_cipher_sha256'],'created_at':now()}
    exclusive_json(root/'approval.json',approval)
    return {'state':'approved'}
def _production(project,plan):
    project=Path(project);data=Path(project)/'data'
    facts=inspect_existing(project);_compare_existing(plan,facts)
    require(digest(capture(data))==plan['production_capture_sha256'],'production capture changed')
    verify_roots_protected(project,plan)
    return data,facts['task'],facts['budget'],facts['env'],facts['limits']
def verify_roots_protected(project,plan,production=True):
    project=Path(project);require(plan.get('root_paths')==ROOT_PATHS,'12 root paths changed')
    actual=capture_roots(project,include_data=production)
    expected={label:plan['roots'][label] for label in actual}
    require(actual==expected,'12 protected roots changed' if production else '11 old isolated roots changed')
    sealed=verify_sealed(project);require(sealed==plan['protected'],'926 sealed map changed')
    return {'roots':actual,'sealed_sha256':sealed['seal_index_sha256']}
def run(project):
    project=Path(project);require(project.resolve()==REAL_PROJECT.resolve(),'only fixed original project')
    root=_canonical_root(project,True);pkg=preflight_run(project,root);plan=pkg['plan']
    require(verify_fixed_reuse(project)==plan.get('fixed_reuse'),'fixed source reuse changed')
    verify_runtime(project,plan,live=True)
    data,task,budget,env,limits=_production(project,plan)
    output=root/'live-output';output.mkdir()
    exclusive_json(root/'attempt.json',{'schema_version':1,'batch_id':BATCH,'state':'admitted','approval_sha256':sha(root/'approval.json'),
        'plan_sha256':pkg['plan_sha256'],'manifest_sha256':pkg['manifest_sha256'],'created_at':now(),'automatic_retry':False})
    exclusive_json(root/'worker-started.json',{'pid':os.getpid(),'plan_sha256':pkg['plan_sha256'],'single_worker':True})
    record={'state':'running','stage':None,'physical_http':0,'automatic_retry':False,'model_http_started':0,'business_acceptance_complete':False}
    original_async=None;original_sync=None;original_model=None;original_budget_call=None;h=None;boundary=None;reads=[0];provider_reads=[0]
    try:
        import tempfile,httpx
        with tempfile.TemporaryDirectory(dir=output,prefix='bootstrap-') as bootstrap:
            os.environ['FLOWCRAFT_DATA_DIR']=bootstrap
            if plan['runtime']['backend_path'] not in sys.path:sys.path.insert(0,plan['runtime']['backend_path'])
            from app import main as h
            from app.storage import Store
            from fastapi.testclient import TestClient
            from boundary import Boundary
            from storage_guard import guarded,verify
            from journey import run as journey
            from reviewed_diagnostic_redaction import extend_guard
            source=Store(data);old=capture(data);diagnostics_seen={}
            boundary=Boundary(env,plan['fixture'],plan['contract'],record,known_apps(data));boundary.owner=task['id']
            boundary.save=lambda:atomic_json(output/'progress.json',record)
            provider_id=plan['existing_source']['provider_id']
            class CountingStore(Store):
                def secret(self,item,key):
                    if item==provider_id and key=='api_key':
                        require(provider_reads[0]<DIAGNOSTIC_MAX_READS,'diagnostic key read budget exceeded')
                        provider_reads[0]+=1
                    return super().secret(item,key)
            Guarded=guarded(CountingStore,env,plan['contract'],boundary,old,task,budget,initial_limits=limits,first_run_id=EXISTING_FIRST_RUN,diagnostics_seen=diagnostics_seen)
            Scoped=extend_guard(Guarded,CountingStore,boundary,task,plan['diagnostic_scope'])
            h.store=Scoped(data);h.DATA_ROOT=data
            def forbidden(*a,**kw):raise RuntimeError('Sierra model/synchronous HTTP forbidden')
            original_sync=httpx.HTTPTransport.handle_request;original_model=h.call_model;original_budget_call=h.budgets.call
            h.call_model=forbidden;h.budgets.call=forbidden;httpx.HTTPTransport.handle_request=forbidden
            original_async=httpx.AsyncHTTPTransport.handle_async_request
            async def intercepted(own,request):
                async def physical(req):
                    record['physical_http']+=1;boundary.save();return await original_async(own,req)
                return await boundary.dispatch(physical,request)
            httpx.AsyncHTTPTransport.handle_async_request=intercepted
            protection_error=None
            try:
                with TestClient(h.app) as api:journey(api,h,boundary,plan['fixture'],plan['contract'],output,scope=plan['diagnostic_scope'])
            finally:
                try:
                    record['protection']=verify(h.store,env,boundary,old,task,budget,first_run_id=EXISTING_FIRST_RUN,seen=diagnostics_seen)
                    verify_roots_protected(project,plan,production=False)
                except BaseException as protection_exc:
                    record['protection_error']=type(protection_exc).__name__;protection_error=protection_exc
                finally:
                    # Persist the protection evidence obtained so far; markers are never
                    # removed, so a failure stays consumed and nothing is replayed.
                    try:boundary.save()
                    except Exception:pass
                    if original_sync is not None:httpx.HTTPTransport.handle_request=original_sync
                    if original_async is not None:httpx.AsyncHTTPTransport.handle_async_request=original_async
                    if h is not None and original_model is not None:h.call_model=original_model
                    if h is not None and original_budget_call is not None:h.budgets.call=original_budget_call
            if protection_error is not None:raise RuntimeError('post-run protection failed') from protection_error
        record.update(state='passed',stage=_safe_stage(boundary),counts=dict(boundary.counts),provider_key_reads=provider_reads[0])
        atomic_json(output/'result.json',record);atomic_json(output/'progress.json',record)
        atomic_json(root/'attempt.json',{'schema_version':1,'batch_id':BATCH,'state':'passed','stage':record['stage'],
            'protection':record.get('protection'),'protection_error':record.get('protection_error'),
            'approval_sha256':sha(root/'approval.json'),
            'plan_sha256':pkg['plan_sha256'],'manifest_sha256':pkg['manifest_sha256'],'counts':dict(boundary.counts),'provider_key_reads':provider_reads[0],'completed_at':now()})
        return record
    except BaseException as exc:
        if original_sync is not None:
            try:httpx.HTTPTransport.handle_request=original_sync
            except Exception:pass
        if original_async is not None:
            try:httpx.AsyncHTTPTransport.handle_async_request=original_async
            except Exception:pass
        if h is not None and original_model is not None:
            try:h.call_model=original_model
            except Exception:pass
        if h is not None and original_budget_call is not None:
            try:h.budgets.call=original_budget_call
            except Exception:pass
        status=safe_failure_report(record,boundary,provider_reads[0],
            dict(boundary.counts) if boundary is not None else record.get('counts'),type(exc).__name__)
        status.update(approval_sha256=sha(root/'approval.json'),plan_sha256=pkg['plan_sha256'],manifest_sha256=pkg['manifest_sha256'])
        try:atomic_json(output/'progress.json',{**record,'state':'stopped','failure_type':status['failure_type'],
            'stage':status['stage'],'counts':status['counts'],'protection':status['protection'],'protection_error':status['protection_error']})
        except Exception:pass
        atomic_json(root/'attempt.json',status);atomic_json(output/'failure.json',status);raise
def main(argv=None):
    parser=argparse.ArgumentParser(description='reviewed-remaining394: no default side effect');parser.add_argument('--project',default=r'E:\workSpace\dify-agent')
    sub=parser.add_subparsers(dest='command');p=sub.add_parser('prepare');p.add_argument('--source-commit',required=True);p.add_argument('--review',required=True)
    a=sub.add_parser('approve');a.add_argument('--authorization',required=True);sub.add_parser('run')
    args=parser.parse_args(argv)
    if args.command is None:parser.print_help();return 0
    try:
        if args.command=='prepare':prepare(args.project,args.source_commit,args.review)
        elif args.command=='approve':approve(args.project,args.authorization)
        elif args.command=='run':run(args.project)
    except Exception as exc:print('stopped:',type(exc).__name__);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
