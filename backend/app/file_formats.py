"""Expected local extraction paths in pinned Dify 1.17.1 / graphon 0.7.0.

This module never reads file contents or executes Dify extractors. Expected
behavior is disclosed and frozen, not presented as an observed platform result.
"""
import copy
from pathlib import PurePosixPath

FORMATS={
 '.txt':{'label':'TXT','parser':'plain_text','behavior':'按文字解码；编码探测范围有限，解码会忽略部分无效字节，可能误判或丢失字符，不保证原字节、原编码或完整文字。'},
 '.md':{'label':'Markdown','parser':'plain_text','behavior':'按文字解码并保留Markdown标记，不渲染页面、不访问链接、不识别图片；编码探测或忽略无效字节可能改变文字。'},
 '.csv':{'label':'CSV','parser':'csv_to_markdown','behavior':'按CSV读取，第一行作为表头，输出Markdown表格文字；引号和换行表示会变化，单元格内竖线不转义，可能使表格歧义；不保证列数一致、原格式、数据类型或业务正确。'},
 '.json':{'label':'JSON','parser':'json_normalize','behavior':'解析后重新输出JSON文字；重复键可能只保留最后一个值，数字写法／精度、空白和转义可能改变，不等于原文保真或严格JSON／Schema验收。'},
 '.yaml':{'label':'YAML','parser':'yaml_normalize','behavior':'安全加载多文档后重新输出YAML文字；重复键可能丢失，隐式类型、数字、日期、别名、注释和排版可能改变，不保证原语义或Schema。'},
 '.yml':{'label':'YML','parser':'yaml_normalize','behavior':'安全加载多文档后重新输出YAML文字；重复键可能丢失，隐式类型、数字、日期、别名、注释和排版可能改变，不保证原语义或Schema。'},
}

def extensions(value):
 if not isinstance(value,list) or not value or len(value)>len(FORMATS) or any(not isinstance(x,str) or x not in FORMATS for x in value) or len(set(value))!=len(value):raise ValueError('请明确选择TXT、MD、CSV、JSON、YAML、YML中的非空无重复后缀范围；不放开其他格式、不转换或重命名。')
 return value.copy()

def descriptor(filename):
 if not isinstance(filename,str):raise ValueError('文件名不能完整核对，未猜文件格式。')
 ext=PurePosixPath(filename).suffix.lower()
 if ext not in FORMATS:raise ValueError('文件试跑仅适配TXT、MD、CSV、JSON、YAML、YML的固定解析路线；PDF／Word等保留上传能力，但本批不运行，不转格式、不改名或调用额外解析服务。')
 return {'extension':ext,**copy.deepcopy(FORMATS[ext]),'external_parser_in_pinned_route':False}

def extraction(files):
 return {'schema_version':1,'dify_version':'1.17.1','graphon_version':'0.7.0','verification':'pinned_source_behavior_only','live_parser_verified':False,'content_verified':False,
 'files':[{'position':i+1,'record_id':row['id'],**descriptor(row['filename'])} for i,row in enumerate(files)],
 'note':'这些是固定版本源码的预期行为，未读取上传正文或验证目标部署实际解析器。文件仍由Dify从原存储读取；这六种后缀的固定路线不调用Unstructured解析服务，但存储／平台策略和模型服务仍按实际环境核对。编码或格式转换可能改变内容；需要原文或精确数据保真时，应先调整方案，不把原文件哈希当作提取结果完整性的证明。'}
