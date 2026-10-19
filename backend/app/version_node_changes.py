"""Compare history node locations/field groups without exposing customer values."""
TYPE_LABELS = {
 'start':'开始','end':'结束','answer':'对话回答','llm':'大模型',
 'code':'代码','template-transform':'模板','if-else':'条件分支',
 'iteration':'迭代','loop':'循环','variable-aggregator':'变量聚合',
 'question-classifier':'问题分类','parameter-extractor':'参数提取',
 'knowledge-retrieval':'知识检索','http-request':'HTTP请求',
 'list-operator':'数组处理','document-extractor':'文档提取',
 'trigger-schedule':'定时触发','human-input':'人工审核','assigner':'状态赋值',
}
GROUPS = [
 ('代码或语言',{'code','code_language'}),
 ('提示词',{'system_prompt','user_prompt','prompt_template','system_instruction'}),
 ('输入／输出绑定',{'variables','variable_selector','value_selector','query_variable_selector','query_variable','iterator_selector','output_selector','input_variable_selector','input_selector','input_type','iterator_input_type'}),
 ('输出声明',{'outputs','output_type','output_schema','structured_output','structured_output_enabled'}),
 ('模型选择或参数',{'model','temperature','max_tokens','model_parameters','completion_params','provider','model_provider','model_name'}),
 ('知识检索',{'dataset_ids','retrieval_mode','retrieval_top_k','multiple_retrieval_config','retrieval_settings','score_threshold','reranking_enable','reranking_model','top_k','dataset_query_variable_selector'}),
 ('条件、分类或提取规则',{'cases','conditions','logical_operator','classes','instruction','parameters'}),
 ('HTTP配置',{'url','method','headers','params','body','authorization','timeout','ssl_verify'}),
 ('模板',{'template','template_source','template_variables'}),
 ('循环规则',{'loop_variables','updates','break_conditions','loop_count','no_progress_limit','progress_variables','progress_reason','failure_policy','limit_policy'}),
 ('迭代或并发规则',{'is_parallel','parallel_nums','error_handle_mode','flatten_output','independent_items','independence_reason'}),
 ('正文连接',{'edges','entry_node_id'}),
 ('记忆或状态',{'memory','conversation_memory','memory_turns','assignments','items'}),
 ('文件处理',{'file_selector','file_variable_selector','extractor_config'}),
]


def flatten(plan):
 if plan is None:return {}
 if not isinstance(plan,dict) or not isinstance(plan.get('nodes'),list):return None
 result={}
 def visit(nodes,identity=(),position=(),depth=0):
  if depth>20 and nodes:raise ValueError()
  for index,node in enumerate(nodes,1):
   if len(result)>=2000 or not isinstance(node,dict) or not isinstance(node.get('id'),str):raise ValueError()
   key=identity+(node['id'],)
   if key in result:raise ValueError()
   content={'top':{k:v for k,v in node.items() if k!='config'}};cfg=node.get('config')
   content['config']={k:v for k,v in cfg.items() if k!='nodes'} if isinstance(cfg,dict) else cfg
   location=position+(index,)
   result[key]={'content':content,'position':location}
   if isinstance(cfg,dict) and 'nodes' in cfg:
    children=cfg['nodes']
    if not isinstance(children,list):raise ValueError()
    content['child_order']=[n.get('id') if isinstance(n,dict) else None for n in children]
    visit(children,key,location,depth+1)
 try:visit(plan['nodes']);return result
 except (ValueError,RecursionError):return None


def type_label(content):
 value=content['top'].get('type')
 return TYPE_LABELS.get(value,'其它类型') if isinstance(value,str) else '未声明类型'


def changed_fields(a,b,equal):
 def differs(left,right,key):return (key in left)!=(key in right) or not equal(left.get(key),right.get(key))
 labels=[]
 at,bt=a['top'],b['top']
 for key,label in (('title','标题'),('type','节点类型')):
  if differs(at,bt,key):labels.append(label)
 if differs(a,b,'child_order'):labels.append('正文节点及顺序')
 other=(set(at)|set(bt))-{'id','title','type'}
 if any(differs(at,bt,k) for k in other):labels.append('其它节点字段')
 ac,bc=a.get('config'),b.get('config')
 if not isinstance(ac,dict) or not isinstance(bc,dict):
  if not equal(ac,bc):labels.append('配置结构')
 else:
  known=set()
  for label,keys in GROUPS:
   known.update(keys)
   if any(differs(ac,bc,k) for k in keys):labels.append(label)
  if any(differs(ac,bc,k) for k in (set(ac)|set(bc))-known):labels.append('其它配置字段')
 return labels


def compare(a,b,equal):
 left,right=flatten(a),flatten(b)
 if left is None or right is None:
  return {'available':False,'note':'节点结构无效、标识重复或超出2000节点／21层位置范围，不能逐项对应；仅确认整份变化，未列部分明细，恢复后须重新检查。'}
 rows=[];counts={'added':0,'removed':0,'changed':0,'moved':0}
 # Current positions first, then nodes only present in the restore destination.
 keys=sorted(left,key=lambda k:left[k]['position'])+sorted(right.keys()-left.keys(),key=lambda k:right[k]['position'])
 for key in keys:
  before,after=left.get(key),right.get(key)
  if before is None:change='added';fields=['整个节点']
  elif after is None:change='removed';fields=['整个节点']
  elif not equal(before['content'],after['content']):
   change='changed';fields=changed_fields(before['content'],after['content'],equal)
   if before['position']!=after['position']:fields.append('节点顺序')
  elif before['position']!=after['position']:change='moved';fields=['节点顺序']
  else:continue
  counts[change]+=1
  rows.append({'change':change,'current_path':list(before['position']) if before else None,
               'historical_path':list(after['position']) if after else None,
               'before_type':type_label(before['content']) if before else None,
               'after_type':type_label(after['content']) if after else None,
               'fields':fields or ['其它节点字段']})
 def edges(plan):return plan.get('edges') if isinstance(plan,dict) else None
 def order(plan):return [n['id'] for n in plan['nodes']] if isinstance(plan,dict) else []
 def other(plan):return {k:v for k,v in plan.items() if k not in {'nodes','edges'}} if isinstance(plan,dict) else None
 return {'available':True,**counts,'connections_changed':not equal(edges(a),edges(b)),
         'root_order_changed':not equal(order(a),order(b)),
         'other_plan_fields_changed':not equal(other(a),other(b)),
         'details':{'scope':'node_identity_and_fields_only','items':rows[:30],
                    'total':len(rows),'omitted':max(0,len(rows)-30),'limit':30},
         'note':'按节点标识与容器身份匹配，只展示1基位置、类型和字段类别；改标识按移除／新增计。位置、字段及连线变化不证明业务影响、静态有效或运行通过。'}
