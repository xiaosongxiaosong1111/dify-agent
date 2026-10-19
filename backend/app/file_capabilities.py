"""Declared implemented file routes, independent of any selected task or resource."""
from .file_formats import FORMATS

SCENARIOS=[
 ('document_extraction','单文件／列表原生提取',3,'文字或文字数组',False,False,False,3),
 ('document_model','单文件总结／问答',4,'文字',True,False,False,3),
 ('document_model_object','单文件结构化提取',4,'JSON对象',True,False,False,5),
 ('document_list_model','列表规范拼接后模型处理',5,'文字',True,True,False,3),
 ('document_list_model_object','列表规范拼接后结构化提取',5,'JSON对象',True,True,False,7),
 ('document_model_guarded_object','单文件对象及工作流Schema检查',5,'JSON对象',True,False,True,6),
 ('document_list_model_guarded_object','列表拼接对象及工作流Schema检查',6,'JSON对象',True,True,True,8),
 ('document_optional_extraction','可选单文件存在／缺失分支',5,'提取文字或明确缺失说明',False,False,False,4),
]


def catalog():
 return {
  'schema_version':1,'verification':'implemented_file_flow_scope_only',
  'platform_business_verified':False,'network_requested':False,
  'formats':[{'extension':ext,'label':row['label'],'parser':row['parser'],'behavior':row['behavior']} for ext,row in FORMATS.items()],
  'scenarios':[{'id':sid,'label':label,'node_count':count,'output':output,'includes_model':model,'includes_join':join,'includes_guard':guard,'flow_schema_version':version,'single_run_available':True,'platform_business_verified':False} for sid,label,count,output,model,join,guard,version in SCENARIOS],
  'conditions':[
   '先保存并确认需求、模型及资源配置，生成并核对完整DSL；上传与单次运行分别准备具体方案并批准，不自动创建资源或派发。',
   '模型路线另确认内容出站及费用未知；拼接和Schema失败各自确认，不复用旧方案批准。实际权限、模型支持、平台及业务质量仍须验收。',
   '字段表只帮填写明确平面Schema；完整原文保存不舍入大整数。Schema声明与静态图检查不证明模型字段真实，失败不自动修复或重试。',
  ],
  'limits':[
   '这八类是独立的精确根节点图，不表示任意文件节点组合均可执行。',
   '文件逐项迭代可生成草稿；含容器、HTTP、自定义代码、多模型或其他分支的通用文件单次运行仍未适配，不删节点后试跑。',
   '仅列出六种上传／专用试跑格式；PDF、Word等其他格式上传、OCR和真实文件模型平台验收尚未完成。',
   '解析说明来自固定Dify源码，不是当前文件实测；转换可能改变编码、数字、重复键、表格或YAML语义。',
  ],
 }
