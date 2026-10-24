import {Component,lazy,Suspense,type ReactNode,type ComponentProps} from 'react';
type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};
type Plan={nodes:Node[];edges:unknown[]};
type Props={plan:Plan|null;disabled:boolean;onChange:(plan:Plan)=>void};
const ScheduleEditor=lazy(()=>import('./ScheduleNodePanel'));
export function LazyScheduleNodePanel(props:Props&{appType:string}){return contains(props.plan,['trigger-schedule'])?boundary('schedule','定时触发编辑器',<ScheduleEditor {...props}/>):null}
const CodeEditor=lazy(()=>import('./CodeTemplatePanel'));
const HttpEditor=lazy(()=>import('./HttpNodePanel'));
const ConditionEditor=lazy(()=>import('./ConditionNodePanel'));
const PromptEditor=lazy(()=>import('./PromptNodePanel'));
const DraftPanel=lazy(()=>import('./PlanDraftPanel'));
const TerminalEditor=lazy(()=>import('./TerminalNodePanel'));
const RepairPanel=lazy(()=>import('./RuntimeRepairPanel'));
const LimitsPanel=lazy(()=>import('./ExecutionLimitsPanel'));
const ClassifierPanel=lazy(()=>import('./ClassifierNodePanel'));
const NodeModels=lazy(()=>import('./NodeModelPanel'));
const ExtractorPanel=lazy(()=>import('./ExtractorNodePanel'));
const ListPanel=lazy(()=>import('./ListOperatorPanel'));
const DocumentPanel=lazy(()=>import('./DocumentExtractorPanel'));
const StartPanel=lazy(()=>import('./StartInputPanel'));
const AggregationPanel=lazy(()=>import('./AggregationNodePanel'));
export function LazyAggregationNodePanel(props:Props&{appType:string}){return contains(props.plan,['variable-aggregator'])?boundary('aggregation','变量聚合编辑器',<AggregationPanel {...props}/>):null}
const LoopPanel=lazy(()=>import('./LoopNodePanel'));
export function LazyLoopNodePanel(props:Props){return contains(props.plan,['loop'])?boundary('loop','循环配置编辑器',<LoopPanel {...props}/>):null}
const IterationPanel=lazy(()=>import('./IterationNodePanel'));
const IterationOutcomes=lazy(()=>import('./IterationOutcomePanel'));
export function LazyIterationOutcomePanel(props:ComponentProps<typeof IterationOutcomes>){return contains(props.plan,['iteration'])?boundary('iteration-outcomes','逐项失败方案',<IterationOutcomes {...props}/>):null}
export function LazyIterationNodePanel(props:Props){return contains(props.plan,['iteration'])?boundary('iteration','迭代配置编辑器',<IterationPanel {...props}/>):null}
const ImageInterpretation=lazy(()=>import('./ImageInterpretationPanel'));
export function LazyImageInterpretationPanel(props:ComponentProps<typeof ImageInterpretation>){return props.material.status==='needs_input'&&/[.](png|jpe?g)$/i.test(props.material.name||'')||props.material.source_kind==='reviewed_model_image_text'?boundary('image-interpretation','图像读取面板',<ImageInterpretation {...props}/>):null}
const MaterialText=lazy(()=>import('./MaterialTextPanel'));
export function LazyMaterialTextPanel(props:ComponentProps<typeof MaterialText>){return props.material.status==='needs_input'||props.material.source_kind==='user_supplied_text'?boundary('material-text','材料文字替代编辑器',<MaterialText {...props}/>):null}
const Capabilities=lazy(()=>import('./CapabilityPanel'));
export function LazyCapabilityPanel(props:ComponentProps<typeof Capabilities>){return boundary('capability','能力范围说明',<Capabilities {...props}/>)}
const RunForm=lazy(()=>import('./RunInputForm'));
export function LazyRunInputForm(props:ComponentProps<typeof RunForm>){return boundary('run-input','试跑输入表单',<RunForm {...props}/>)}
export function LazyStartInputPanel(props:Props&{appType:string}){return ['workflow','advanced-chat'].includes(props.appType)&&contains(props.plan,['start'])?boundary('start-input','入口变量编辑器',<StartPanel {...props}/>):null}
export function LazyDocumentExtractorPanel(props:Props){return contains(props.plan,['document-extractor'])?boundary('document','文档文件编辑器',<DocumentPanel {...props}/>):null}
export function LazyListOperatorPanel(props:Props){return contains(props.plan,['list-operator'])?boundary('list','数组处理编辑器',<ListPanel {...props}/>):null}

class EditorBoundary extends Component<{editor:string;label:string;children:ReactNode;failureHint?:string},{failed:boolean}>{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true}}
 render(){return this.state.failed?<div className="callout amber" role="alert" data-node-editor-failed={this.props.editor}>{this.props.failureHint||`${this.props.label}载入失败，当前草稿保持。仍可在高级 JSON 中核对和编辑；不会自动重跑、删除节点或改配置。`}</div>:this.props.children}
}
function contains(plan:Plan|null,types:string[]){
 return plan?.nodes.some(node=>types.includes(node.type)||['iteration','loop'].includes(node.type)&&Array.isArray(node.config?.nodes)&&(node.config.nodes as Node[]).slice(0,12).some(child=>types.includes(child.type)));
}
function boundary(editor:string,label:string,child:ReactNode){return <EditorBoundary editor={editor} label={label}><Suspense fallback={<p className="hint" role="status" data-node-editor-loading={editor}>正在载入{label}，草稿保持...</p>}>{child}</Suspense></EditorBoundary>}
const MockOrder=lazy(()=>import('./MockOrderTemplatePanel'));
export function LazyMockOrderPanel(props:ComponentProps<typeof MockOrder>){return ['workflow','advanced-chat'].includes(props.appType)&&props.plan?.nodes.some(node=>node.type==='code')?boundary('mock-order','订单模拟模板',<MockOrder {...props}/>):null}
export function LazyCodeTemplatePanel(props:Props&{appType:string}){return contains(props.plan,['code','template-transform'])?boundary('code','代码与模板编辑器',<CodeEditor {...props}/>):null}
export function LazyConditionNodePanel(props:Props&{appType:string}){return contains(props.plan,['if-else'])?boundary('condition','条件编辑器',<ConditionEditor {...props}/>):null}
export function LazyPromptNodePanel(props:Props&{scope?:string}){return contains(props.plan,['llm'])?boundary('prompt','提示词编辑器',<PromptEditor {...props}/>):null}
export function LazyPlanDraftPanel(props:ComponentProps<typeof DraftPanel>){return boundary('draft','流程草稿面板',<DraftPanel {...props}/>)}
export function LazyTerminalNodePanel(props:ComponentProps<typeof TerminalEditor>){return contains(props.plan,['end','answer'])?boundary('terminal','终点编辑器',<TerminalEditor {...props}/>):null}
export function LazyRuntimeRepairPanel(props:ComponentProps<typeof RepairPanel>){return boundary('repair','本机运行修复面板',<RepairPanel {...props}/>)}
export function LazyClassifierNodePanel(props:Props){return contains(props.plan,['question-classifier'])?boundary('classification','问题分类编辑器',<ClassifierPanel {...props}/>):null}
export function LazyNodeModelPanel(props:ComponentProps<typeof NodeModels>){return contains(props.plan,['llm','question-classifier','parameter-extractor'])?boundary('model','逐节点模型编辑器',<NodeModels {...props}/>):null}
export function LazyExtractorNodePanel(props:Props){return contains(props.plan,['parameter-extractor'])?boundary('extraction','参数提取编辑器',<ExtractorPanel {...props}/>):null}
export function LazyExecutionLimitsPanel(props:ComponentProps<typeof LimitsPanel>){return <EditorBoundary editor="execution-limits" label="Dify执行上限面板" failureHint="执行上限面板载入失败，后端已保存策略仍生效；请刷新页面，不会取消限制或派发试跑。"><Suspense fallback={<p role="status">正在载入执行上限面板...</p>}><LimitsPanel {...props}/></Suspense></EditorBoundary>}

export function LazyHttpNodePanel(props:Props){return contains(props.plan,['http-request'])?boundary('http','HTTP编辑器',<HttpEditor {...props}/>):null}

const InterviewProgress=lazy(()=>import('./InterviewProgressPanel'));
export function LazyInterviewProgressPanel(props:ComponentProps<typeof InterviewProgress>){return boundary('interview-progress','访谈进度面板',<InterviewProgress {...props}/>)}

const ConversationState=lazy(()=>import('./ConversationStatePanel'));
export function LazyConversationStatePanel(props:ComponentProps<typeof ConversationState>){return props.appType==='advanced-chat'||props.plan?.conversation_variables?boundary('conversation-state','对话状态编辑器',<ConversationState {...props}/>):null}

const ScheduleObservation=lazy(()=>import('./ScheduleObservationPanel'));
export function LazyScheduleObservationPanel(props:ComponentProps<typeof ScheduleObservation>){return boundary('schedule-observation','调度只读核对',<ScheduleObservation {...props}/>)}

const ScheduleStop=lazy(()=>import('./ScheduleStopPanel'));
export function LazyScheduleStopPanel(props:ComponentProps<typeof ScheduleStop>){return boundary('schedule-stop','具体停用方案',<ScheduleStop {...props}/>)}

const ScheduleEnable=lazy(()=>import('./ScheduleEnablePanel'));
export function LazyScheduleEnablePanel(props:ComponentProps<typeof ScheduleEnable>){return boundary('schedule-enable','具体启用方案',<ScheduleEnable {...props}/>)}

const HumanReview=lazy(()=>import('./HumanReviewNodePanel'));
export function LazyHumanReviewNodePanel(props:ComponentProps<typeof HumanReview>){return boundary('human-review','人工审核配置',<HumanReview {...props}/>)}

const WaitingRun=lazy(()=>import('./WaitingRunPanel'));
export function LazyWaitingRunPanel(props:ComponentProps<typeof WaitingRun>){return boundary('workflow-waiting','原运行状态核对',<WaitingRun {...props}/>)}

const HumanRuntimePlan=lazy(()=>import('./HumanRuntimePlanPanel'));
const ResourceProgress=lazy(()=>import('./ResourceProgressPanel'));
export function LazyResourceProgressPanel(props:ComponentProps<typeof ResourceProgress>){return boundary('resource-progress','独立资源进度',<ResourceProgress {...props}/>)}
const SchedulePublication=lazy(()=>import('./SchedulePublicationPanel'));
export function LazySchedulePublicationPanel(props:ComponentProps<typeof SchedulePublication>){return boundary('schedule-publication','新定时应用发布',<SchedulePublication {...props}/>)}
const HumanDecision=lazy(()=>import('./HumanDecisionPanel'));
export function LazyHumanDecisionPanel(props:ComponentProps<typeof HumanDecision>){return boundary('human-decision','人工决定',<HumanDecision {...props}/>)}
export function LazyHumanRuntimePlanPanel(props:ComponentProps<typeof HumanRuntimePlan>){return boundary('human-runtime-plan','人工运行资源方案',<HumanRuntimePlan {...props}/>)}

const ScheduleRuns=lazy(()=>import('./ScheduleRunsPanel'));
export function LazyScheduleRunsPanel(props:ComponentProps<typeof ScheduleRuns>){return boundary('schedule-runs','调度证据读取',<ScheduleRuns {...props}/>)}

const StructuredGuardEditor=lazy(()=>import('./StructuredGuardPanel'));
export function LazyStructuredGuardPanel(props:ComponentProps<typeof StructuredGuardEditor>){return props.appType==='workflow'&&props.plan?.nodes.some(n=>n.type==='llm'&&n.config?.structured_output_enabled===true)?boundary('structured-guard','严格Schema校验方案',<StructuredGuardEditor {...props}/>):null}

const CaseInputCheck=lazy(()=>import('./RunCaseInputCheck'));
export function LazyRunCaseInputCheck(props:ComponentProps<typeof CaseInputCheck>){return boundary('case-input-check','固定样例入口检查',<CaseInputCheck {...props}/>)}

const ConversationCopy=lazy(()=>import('./ConversationInputCopy'));
export function LazyConversationInputCopy(props:ComponentProps<typeof ConversationCopy>){return boundary('conversation-input-copy','原会话参数准备',<ConversationCopy {...props}/>)}

const PolicyAudit=lazy(()=>import('./NodePolicyAudit'));
export function LazyNodePolicyAudit(props:ComponentProps<typeof PolicyAudit>){return boundary('node-policy-audit','最终节点设置读取',<PolicyAudit {...props}/>)}

const SchemaTemplates=lazy(()=>import('./SchemaCaseTemplates'));
export function LazySchemaCaseTemplates(props:ComponentProps<typeof SchemaTemplates>){return boundary('schema-case-templates','Schema验收草稿读取',<SchemaTemplates {...props}/>)}

const RuntimeFiles=lazy(()=>import('./RuntimeFilePanel'));
export function LazyRuntimeFilePanel(props:ComponentProps<typeof RuntimeFiles>){return boundary('runtime-files','文件上传方案',<RuntimeFiles {...props}/>)}

const FileRun=lazy(()=>import('./FileRunPanel'));
export function LazyFileRunPanel(props:ComponentProps<typeof FileRun>){return boundary('file-run','文件单次试跑',<FileRun {...props}/>)}

const FileStarter=lazy(()=>import('./FileWorkflowStarter'));
export function LazyFileWorkflowStarter(props:ComponentProps<typeof FileStarter>){return props.appType==='workflow'?boundary('file-workflow-starter','文件流程起步',<FileStarter {...props}/>):null}

const FileJoinPolicy=lazy(()=>import('./FileJoinPolicyPanel'));
export function LazyFileJoinPolicyPanel(props:ComponentProps<typeof FileJoinPolicy>){return contains(props.plan,['code'])?boundary('file-join-policy','文件拼接政策编辑器',<FileJoinPolicy {...props}/>):null}

const IterationSummary=lazy(()=>import("./IterationSummaryPanel"));
export function LazyIterationSummaryPanel(props:ComponentProps<typeof IterationSummary>){return contains(props.plan,["iteration"])?boundary("iteration-summary","批量结果汇总",<IterationSummary {...props}/>):null}

const VersionHistory=lazy(()=>import('./VersionHistoryPanel'));
export function LazyVersionHistoryPanel(props:ComponentProps<typeof VersionHistory>){return boundary('version-history','历史比较与恢复',<VersionHistory {...props}/>)}

const ExecutionScale=lazy(()=>import('./ExecutionScalePanel'));
export function LazyExecutionScalePanel(props:ComponentProps<typeof ExecutionScale>){return props.plan?boundary('execution-scale','节点执行规模预览',<ExecutionScale {...props}/>):null}

const IterationChain=lazy(()=>import('./IterationChainPanel'));
export function LazyIterationChainPanel(props:ComponentProps<typeof IterationChain>){return contains(props.plan,['iteration'])?boundary('iteration-chain','多步计算链',<IterationChain {...props}/>):null}

const CheckPanel=lazy(()=>import('./PlanCheckPanel'));
export function LazyPlanCheckPanel(props:ComponentProps<typeof CheckPanel>){return boundary('plan-check','草稿静态检查',<CheckPanel {...props}/>)}

const MissingExtractor=lazy(()=>import('./MissingExtractorPanel'));
export function LazyMissingExtractorPanel(props:ComponentProps<typeof MissingExtractor>){return props.appType==='workflow'?boundary('missing-extractor','缺失文档提取节点建议',<MissingExtractor {...props}/>):null}

const MappingPanel=lazy(()=>import('./EnvironmentMappingPanel'));
export function LazyEnvironmentMappingPanel(props:ComponentProps<typeof MappingPanel>){return <EditorBoundary key={props.taskId} editor="environment-mapping" label="目标映射面板" failureHint="目标映射面板载入失败。后台已存映射与来源任务保持；请先保存其他编辑，再刷新页面重试。"><Suspense fallback={<p className="hint" role="status" data-node-editor-loading="environment-mapping">正在载入目标映射工具，尚未改动来源或目标任务…</p>}><MappingPanel {...props}/></Suspense></EditorBoundary>}
const MappingHistory=lazy(()=>import('./MappingCopiesPanel'));
const WorkflowMapping=lazy(()=>import('./WorkflowEnvironmentMapping'));
export function LazyWorkflowEnvironmentMapping(props:ComponentProps<typeof WorkflowMapping>){return <EditorBoundary key={props.taskId} editor="workflow-mapping" label="流程逐节点目标映射" failureHint="流程映射面板载入失败，来源任务保持；请先保存其他编辑后刷新，不会自动生成或导入。"><Suspense fallback={<p className="hint" role="status">正在载入流程逐节点目标映射…</p>}><WorkflowMapping {...props}/></Suspense></EditorBoundary>}
export function LazyMappingCopiesPanel(props:ComponentProps<typeof MappingHistory>){return <EditorBoundary key={props.taskId} editor="mapping-history" label="本机映射创建历史" failureHint="本机映射历史面板载入失败，后台创建回执仍保留；不会自动重新创建目标任务。请先保存其他编辑，再刷新页面重读。"><Suspense fallback={<p className="hint" role="status">正在载入本机映射历史工具…</p>}><MappingHistory {...props}/></Suspense></EditorBoundary>}

const LinearStarter=lazy(()=>import('./LinearPlanStarter'));
export function LazyLinearPlanStarter(props:ComponentProps<typeof LinearStarter>){return ['workflow','advanced-chat'].includes(props.appType)?boundary('linear-starter','基础线性流程草稿',<LinearStarter {...props}/>):null}
const AfterSalesStarter=lazy(()=>import('./AfterSalesStarter'));
export function LazyAfterSalesStarter(props:ComponentProps<typeof AfterSalesStarter>){return props.appType==='advanced-chat'?boundary('after-sales-starter','售后分支草稿',<AfterSalesStarter {...props}/>):null}
