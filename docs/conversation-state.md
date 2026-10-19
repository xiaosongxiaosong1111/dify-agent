# Chatflow字符串持久状态与根赋值（0.106）

## 首批可生成范围

可选plan.conversation_variables为最多12项的数组，每项须完整name、var_type:string、initial_value（有效字符串，最多4000字，可明确为空）、description（最多255字）、persistence_policy:per_conversation、unwritten_policy:retain_current。名称唯一，ASCII字母开头，最多64字符，不用凭据／保留名称。Workflow／Agent不能采用非空声明，不能为实现状态擅自改变应用类型。

每个conversation独立保存，未执行赋值保留当前值，新会话使用声明初始值；不是聊天历史摘要、跨用户共享或会话保留期限保证。原生conversation_variables生成稳定UUID、name/value_type:string/value/description，现有凭据仍独立，不放这里。

根assigner config只含items（1—12），每项完整variable_selector:[conversation,已声明名]、input_type:constant或variable、operation:over-write、value。常量必须明确字符串（可空重置）；变量源必须明确两段selector、真实字符串类型且在全部路径上游；conversation.name是当前已声明状态，sys.query是本轮输入。节点原生version:2，没有节点输出，不生成虚构assigner.output。

一次图执行同状态只允许一个根写节点，同节点不能重复写目标或读正在更新的状态，不与根普通隐式并行分叉共存。显式条件的未赋值分支可保留旧值。容器内状态读取／赋值、对象／数组／数值／布尔／文件、追加／清除／算术、多写合并、跨用户或全局状态目前明确拒绝。

## 编辑与原文件保留

Chatflow流程页可以添加空白字符串声明，显式填入按会话保存／未写保留方案；改名或删除不偷偷改引用，需修正遗留目标／模板。赋值卡选择目标、来源方式与真正字符串候选，换模式不转换原value，无效JSON保持；覆盖操作属于待确认草稿。不会自动插赋值节点、改连线或确认业务。

原生保留只支持明确字符串CV及根v2 assigner，校验原UUID、selector、类型和赋值源，保持原ID／值／描述／布局；不删除未知状态类型、错误策略或重试设置后算完成。已适配循环的编译器私有v2状态更新保持原有保护，不能冒充根CV赋值。

## 建议数据与验收

验收建议的最终语义含原始声明／初始值及根assigner.items，排除运行中的conversation值。轻量数据范围升级scope12；旧11必须重新核对与主动确认，未确认不派发或换主模型。原始需求和默认值可能含业务信息，用户不要填写Key或密码。

须确认新会话初始值、同会话多轮保持与覆盖、不同会话隔离、未写分支和显式空字符串重置的样例；动态文字大小、持久执行、费用及完整业务质量仍需实际Dify验收。

已从本机Dify1.17.1安装包读取v2实体／枚举／支持规则及导入变量factory，确认原生type为assigner、字符串over-write和255字说明限制。当前编译／保留／路由／页面检查均隔离；没有创建Dify应用、更新真实CV或调用模型，不算实际持久质量通过。

声明改名或删除后，旧目标／模板引用保持待修正；同节点正在更新状态不会出现在来源候选中，需拆成明确串行根节点。同图普通根节点隐式并行分叉目前拒绝，条件分支仍可明确选择未写保留。

## 0.107数值与布尔

新增var_type:number/boolean。数值初始／常量必须真正有限JSON数值，绝对值<=10^12，不接受bool或文字数字；原生表示明确为float，非整数或Decimal金额精度保证。布尔须真正true/false，不接受0/1/文字真假。变量来源必须与目标的标量类型一致，不做解析／真假转换。

切换声明类型保留旧初始值和赋值value，用户须明确修正；不会转换已有Dify运行状态。原始保留支持string/float/boolean，native integer/number泛型或对象／数组／文件仍拒绝，不改成float冒充保留。同样保留单根写节点、无项间读后写依赖、无根隐式并行／容器读写限制。

验收建议范围升级scope13，新增数值／布尔声明类型与默认值；旧12必须重新确认，仍不发送运行中CV。已在本机目标Dify安装包中对三个隔离变量做factory／v2数据schema／输入支持验证，确认float0.0、booleanfalse及空字符串，不创建/更新Dify应用或执行赋值。真实多轮持久效果仍未验收。


0.108起单层容器可只读声明状态，0.109起根number支持明确常量加减乘除，覆盖规则仍适用。当前限制和动态范围边界见[会话计数](conversation-arithmetic.md)；上文0.106仅字符串／覆盖是历史切片范围。
