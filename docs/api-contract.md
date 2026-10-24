# Initial API contract

## 0.277：同版交付包

GET /api/tasks/{id}/delivery-bundle?revision=当前整数修订：只读打包当前有效静态成果及现有报告。须有本修订确认且计划未过期；旧修订409，缺成果404或准入不符422。返回application/zip、Cache-Control:no-store、X-Sierra-Revision，固定文件名sierra-{type}-r{revision}-delivery.zip。包内DSL、report、README和manifest.json；清单绑定任务/环境/App/类型/修订、目标Dify/DSL版本、时间及原始文件大小/SHA256。清单不签名，不证明平台状态或业务通过。

读取和报告生成持同一后台Store锁，若任务事实变化拒绝混合包。新build成果元数据增加sha256，按落盘字节计算；偏离构建摘要409。旧成果不迁移，明确legacy_export_bytes_only，只记录导出当时字节；无原始构建完整性保证。DSL限2MB、报告限8MB，路径须属于当前任务，不跟随文件符号链接；三种类型保持原选择。已识别明文凭据模式拒绝整包且不回显；不解密或复制环境凭据/材料原件，不发模型/Dify或写任务预算。页面未保存或作用域变化禁用/取消下载，响应类型和修订不匹配不下载。


Backend FastAPI on 127.0.0.1:8765; frontend Vite on 127.0.0.1:5173 proxies /api. Backend serves built frontend/dist on production startup.

JSON errors: HTTP status plus {detail: string}. No provider key values in responses. All endpoints below are prefixed /api.

## 模拟依赖逐项接入待办（0.272）

PATCH `/tasks/{id}` 的configuration可保存 `mock_dependency_bindings`（默认空列表）：

```json
{"configuration":{"mock_dependency_bindings":[{"dependency":"订单接口","node_id":"order-mock","replacement_todo":"补充真实服务与鉴权引用，替换后验证正常、缺少订单和接口故障。"}]}}
```

最多50项、每依赖一个位置；只接受上述三个字段。依赖/节点ID/待办须非空，分别最多2000/128/4000字；非法结构422且不写入。保存后原配置确认及成果失效。构建时dependency须精确对应当前mock_dependencies，node_id须对应本次编译后的实际节点；原生Agent仅接受agent.system_prompt。失效引用阻止新成果，未填写绑定的旧声明保持并附待补提示。DSL描述/Agent metadata及报告保留待办，检查不证明模拟实现或真实接入，没有可自行声明完成的字段。保留实际DSL路径会核对最终文件；缺当前待办说明时422，不写成果、不修改已确认文件/合并记录。

## 订单模拟模板只读预览（0.273）

POST `/tasks/{id}/mock-order-template`：`{revision,plan_text,node_id,input_selector,records_text,dependency,acknowledge_mock,request_nonce}`。revision为当前正整数，plan_text是保留精确原文的完整计划，input_selector是两个文字项，records_text是无重复订单号的合成JSON对象字符串，dependency须已明确保存到mock_dependencies，acknowledge_mock须true，request_nonce为新UUID。

只接受Workflow/Chatflow已有根代码节点和开始文字字段（Chatflow可选sys.query）；订单表1—10项、编号1—64位字母/数字/横线/下划线、固定说明1—500字。严格拒绝未知字段、重复键、疑似明文凭据、未接受/未声明范围、旧修订或不兼容下游引用；不回显坏输入。

返回完整plan_text、目标节点/依赖/selector、源原文/订单表原文/候选的SHA256、task_id/revision/request_nonce及verification=local_mock_order_template，only_selected_code_config_changed=true；task_changed/network_requested/code_executed/platform_checked/business_verified均false。建议不持久化，采用后须经既有计划保存/确认/构建接口，固定输出result与status；不是运行、接口接入或资源批准。

## 订单模板提取文字来源扩展（0.274）

`/tasks/{id}/mock-order-template`请求和响应字段保持兼容，input_selector新增接受原草稿中根parameter-extractor的已声明string业务参数。状态字段、非文字类型和不存在参数拒绝。完整计划校验要求成功分支保护及所有路径可用；失败/公共汇合路径不能读取默认提取值。只修改选中代码config，其余提取配置、保护节点、失败分支和连接保持，不执行模型或Dify。

## Chatflow首次发布（0.275）

既有`GET /tasks/{id}/workflow-publication`、`POST .../prepare {revision}`及`POST .../confirm {revision,proposal_id,review_token,confirm_publish:true}`新增支持advanced-chat，保留workflow。新提案/回执含app_type并绑定该类型，旧未含类型的就绪绑定不能直接确认；Workflow旧成功历史不迁移。

Chatflow准备依次核对App身份/类型、草稿和未发布状态，确认时重核并最多POST一次，事后读发布图；planned_console_reads=7，Workflow仍5，认证可增加。已有发布或图/类型/环境变化拒绝，可能派发后异常unknown且不重发。报告/界面按当前App及匹配类型消费回执，pending/unknown尚无result也按未确认记录处理；入口不创建应用/Key或运行，不扩Agent及专用触发/人审范围。具体图与失败规则见docs/chatflow-publication.md。

## Task

Task object:
```json
{"id":"uuid","name":"客户售后问答","app_type":"advanced-chat","revision":1,"status":"requirements","requirements_confirmed":false,"configuration_confirmed":false,"environment_id":null,"requirements":{"goal":"","audience":"","input":"","output":"","rules":"","knowledge":"","exceptions":"","tests":""},"configuration":{"assistant_provider_id":null,"dify_model_provider":"","dify_model":"","temperature":0.2,"max_tokens":2048,"dataset_ids":[],"retrieval_top_k":3,"mock_dependencies":[],"resource_plan":"只创建新的应用，不覆盖已有资源。"},"messages":[],"materials":[],"versions":[],"runs":[],"created_at":"ISO","updated_at":"ISO"}
```

Types workflow / advanced-chat / agent. User chooses type. Native text Agent packages are supported; custom tools/advanced retrieval/files/skills/HITL remain unavailable and are never silently dropped. Never substitute another type.

- GET /meta -> {dify_version, dsl_version, app_types:[{value,label,supported,note}], capabilities:[{name,status,note}]}
- GET /tasks -> Task[]; POST /tasks {name,app_type,environment_id?} -> Task
- GET /tasks/{id} -> Task
- PATCH /tasks/{id} {name?,requirements?,configuration?,environment_id?} -> Task; partial changes merge and invalidate approvals, preserving history.
- POST /tasks/{id}/messages {content:string} -> Task. Real model response when configured. Missing model should clearly explain setup needs, not simulate a successful AI answer.
- POST /tasks/{id}/materials multipart file -> Task; actual extraction for supported formats; refs initially pending.
- PATCH /tasks/{id}/materials/{material_id} {reference_mode:"borrow"|"preserve"|"replicate",preserve_items?:string} -> Task
- DELETE /tasks/{id}/materials/{material_id} -> Task; removes reference, retains source file for version trace.
- POST /tasks/{id}/confirm {kind:"requirements"|"configuration",revision:number} -> Task; stale revision -> 409; configuration requires requirements approval.
- POST /tasks/{id}/build {revision:number} -> Task; requires approvals at same revision, calls compiler, persists artifact and real static results, status draft_ready. Not real import.
- GET /tasks/{id}/artifact -> YAML attachment (404 if none); GET /tasks/{id}/report -> Markdown attachment
- GET /tasks/{id}/dsl -> {content:string,revision:number,validation:object}
- POST /tasks/{id}/restore {version_id:string} -> Task; creates new draft revision and invalidates approvals.
- POST /tasks/{id}/pause -> Task. Safe interruption boundary; does not pretend canceling an already dispatched remote write.
- POST /tasks/{id}/import {revision:number} -> Task; only creates NEW app in selected Dify; requires current approved plan, compiler artifact and real console auth. Records actual result.
- POST /tasks/{id}/run {revision:number,input:object} -> Task; requires real imported app, published in Dify, and environment service_api_key plus service_app_id matching the task import. Workflow inputs pass through; Chatflow input contains query and optional conversation_id. Records response as run_completed, not full business verification.

## Providers

- GET /providers -> [{id,name,provider,base_url,model,role,has_api_key,protocol,capabilities}]
- POST /providers {name,provider,base_url,model,role,protocol:"openai-compatible"|"anthropic",api_key?} -> metadata
- PATCH /providers/{id} same optional fields (blank key preserves current) -> metadata
- DELETE /providers/{id} -> {ok:true}; selected references must be handled
- POST /providers/{id}/test -> {ok,latency_ms,message,capabilities}; actual API call, capabilities untested unless tested explicitly.

## Environments

- GET /environments -> [{id,name,base_url,version,has_console_token,has_service_api_key,has_dataset_api_key,capabilities}]
- POST /environments {name,base_url,version?,console_token?,csrf_token?,service_api_key?,service_app_id?,dataset_api_key?} -> metadata
- PATCH /environments/{id} optional same fields -> metadata; blank credentials preserve existing
- POST /environments/{id}/test -> {ok,message,capabilities}; credential classes remain distinct. Never claim console management works from a successful public health check.
- GET /environments/{id}/datasets -> {data:[],has_more:boolean}; actual dataset key request, list-all may be scope-limited.
- GET /settings -> {max_retries,max_minutes,max_cost_usd}; PATCH /settings same -> settings. Defaults are configurable development defaults, not user-approved product promises.

Compiler module root ownership contract: backend/app/dsl.py exporting TARGET_DIFY_VERSION, DSL_VERSION, compile_dsl(task:dict)->tuple[str,dict], validate_dsl(content:str)->dict. Validation returns {valid:bool,errors:string[],warnings:string[],nodes:int}. User-supplied model provider/name required, no fabricated resource IDs.

Frontend can gracefully handle an endpoint error. It must never show demo results as real API successes. Loading state is backend request progress, not a success animation.

Implementation notes: execution settings now constrain one model planning operation only; see planning-contract.md. They do not cover interview/probe calls or Dify execution, nor guarantee a supplier invoice ceiling. Single requests also have timeout limits. Changing only runtime Key / declared service App ID after import preserves the import binding; changing environment address/version invalidates it. Configuration-only task changes carry unchanged approved business requirements to the new revision and require new configuration confirmation. Material snippets sent to the model are explicitly marked when truncated. Strict-reference generation is not supported by the initial linear compiler and returns an explicit limitation.


## 0.4.0 additions

- GET /tasks/{id}/planning -> {revision,runs:[PlanningRun]}; persistent planning attempt ledger, stopped candidates explicitly unapplied. POST /tasks/{id}/plan/generate {revision} applies a valid candidate with a new revision requiring confirmation; stops preserve the previous plan.
- Provider metadata and POST/PATCH support pricing:{input_per_million_usd,output_per_million_usd,cached_input_per_million_usd?}|null and pricing_note:string. Rates are finite nonnegative USD per million tokens, not invoice guarantees. Changing provider/model/address clears outdated pricing unless explicitly supplied. Active planning blocks connection mutations.
- POST /providers/{id}/test-json -> {ok,latency_ms,message,capabilities,usage}; basic strict JSON object probe, independent of text/tools/vision.
- POST /environments/{id}/login application/json {email,password} -> {ok,environment,message}. Explicit user action only; existing Dify 1.17.1 email/password account required, no initialization/registration/automatic retry. Backend Base64-encodes UTF-8 password for official login, verifies authenticated apps list with CSRF header AND cookie, then atomically stores encrypted access/CSRF tokens. Password/email are not persisted or returned; errors do not reflect credential inputs. No refresh token stored or automatic renewal; expiry requires reconnect. Login does not grant application runtime/dataset access.
- Changing environment base URL clears credentials not explicitly replaced, resets capabilities and invalidates related task bindings. Login/test results are rejected if the connection changes during the request. No credentials are forwarded to redirect targets.
- GET /environments/{id}/datasets?page=1&limit=100; page positive, limit 1–100. Actual dataset key required.
- GET/PATCH /settings: max_retries 0–10 (repair rounds, zero disables), max_minutes and max_cost_usd finite positive. Constraints apply to each model planning operation only.


## Actual runtime diagnostics

An unsuccessful workflow result returned over HTTP 200 is persisted separately as run.result (including its workflow run ID); its body is not appended to public HTTP error text. Known terminal unsuccessful states are failed/stopped/partial-succeeded; nonterminal, absent or unrecognized states are unknown and block blind retries. None count as a passed check. Task reports use matching current revision/environment import records and declared case results, rather than labeling every built artifact as an entirely untested application.


## 0.5.0 resource/configuration additions

- GET /environments/{id}/models?model_type=llm -> {data:[allowlisted model metadata],source:"console",observed_at,environment_id,connection_revision}. Supported model types are explicitly constrained. Active chat models are selectable; availability is a directory declaration, not a successful inference guarantee.
- GET /environments/{id}/model-parameters?provider=...&model=... -> {data:[allowlisted parameter rules],provider,model,source,observed_at,environment_id,connection_revision}. Rechecks current model availability; unsafe provider paths and stale connection reads are rejected.
- Dataset directory accepts source=console|service (API default service); no silent fallback. Scoped dataset keys cannot list the global directory in Dify 1.17.1; 403 is explicit, no fake empty success or automatic scope widening.
- Task configuration adds model_parameters (flat primitives, excludes connection credentials/core fields), opening_statement (<=4000 chars), suggested_questions (<=6, each nonempty <=500). Both compilers retain these settings. UI recommendations enter drafts only; same-model current values are preserved, unknown old parameters require review.
- Full specification and limitations: resource-contract.md. Real fictional RAG evidence: rag-live-validation.md. No automatic dataset provisioning or publishing product endpoint is claimed.


## 0.6.0 knowledge provisioning

Persistent, explicitly confirmed knowledge jobs support economy and conditional high_quality indexes, complete extracted text snapshots, independent scoped encrypted keys, actual indexing readiness, pause/restart/unknown-result recovery and atomic application to a task revision. Endpoints, confirmation fields and limitations are defined in knowledge-provisioning-contract.md. Economic product flow has real evidence; high-quality conditions only have controlled coverage so far. No destructive cleanup or blind write retry is implied.

## Chatflow 连续自由试跑

运行请求可包含 `conversation_from_run_id`，不能与 `case_id` 或另一个 `input.conversation_id` 混用。来源限定为同任务当前修订／环境的成功 Chatflow 自由试跑；固定样例记录不可作为来源。结果保留 `conversation_context`。配置新增 `conversation_memory`（默认 false）、`memory_turns`（1—50，默认 5）。详见 [对话记忆契约](conversation-memory-contract.md)。

## 0.7.0 Native Agent

`GET/POST /api/tasks/{id}/plan` chooses the native `agent_plan` field for app type `agent`, independently of `workflow_plan`. The strict shape is `{schema_version:1,scope:"text",system_prompt:string}`. Model generation uses the Agent contract. PATCH may clear only the matching plan with null. Configuration approval requires a valid saved plan and native model identity; build emits `app.mode=agent` and `agent_packages`. Unsupported fields/resources block approval/build.

Native runtime accepts `{query:string}` and uses upstream SSE. Since 0.9.0, free runs may use a saved successful source via top-level conversation_from_run_id; literal input.conversation_id and fixed-case sources are rejected. The resolved ID is sent as a top-level Dify parameter. The returned record is terminal only after authoritative final `message` and `message_end`; `agent_message` previews are not concatenated with the final answer. A disconnect, unknown event or limit stores an unknown result and blocks blind repeat. Pause/limit attempts stop if a remote task ID is known. The frontend receives the completed local HTTP result, not every upstream delta. Details: [Agent contract](agent-plan-contract.md), [live evidence](agent-live-validation.md).

Agent `scope=knowledge` adds strict `knowledge_sets`; each set has name, description, dataset_ids, query_mode=generated_query, top_k. The union of IDs must exactly match selected configuration.dataset_ids. Native sets use multiple retrieval, disabled reranking/threshold/metadata filters. Text scope with selected datasets is rejected rather than dropping them. Tool-name summaries are retained without copying observations or parameters. See the Agent contract for bounds; only two fictional retrieval scenarios are verified, and the model chooses when to retrieve.

Provider failures now carry allowlisted reported token usage and recognized finish_reason. Planning pauses without retry on provider errors; reported usage is estimated when usable, otherwise the previous unknown-usage reservation remains. Previously lost usage is not fabricated or retroactively changed to zero.

## 0.8.0 Provider presets

GET `/api/provider-presets` returns a reviewed local catalog (`account_unverified`). POST/PATCH providers accept `preset_id` plus API Key; server supplies official identity and reference pricing. `preset_id:null` clears the binding for custom mode. Same-origin editing can retain encrypted Key; a changed origin requires a new Key. Model changes get model-specific pricing; same identity preserves user pricing. Identity/preset changes reset capability evidence. Save does not call a model. Native request mapping and verification bounds are documented in [provider-presets.md](provider-presets.md).

## 0.9.0 模型反馈与原生会话

模型探测 API 未改变；前端分别展示 text／JSON 的实际返回或 HTTP 错误，配置状态刷新失败单独说明，不自动重试。临时结果只保留在当前页面内存。

`conversation_from_run_id` 现在同时适用于 Chatflow 和原生 Agent 自由试跑；来源必须是同任务当前修订／环境成功自由记录，具有有效实际会话标识。原生 Agent 首轮仅 query，追问仍提交 query 与顶层来源记录 ID，不支持应用变量／文件。实际会话与请求不一致标为未知并保留结果、禁止重复派发。该版本正式连续验收链尚未实现；0.10.0 已新增，见下节。见 [原生会话契约](agent-conversation-contract.md)。

## 0.10.0 正式多轮验收

`test-cases` 样例可添加 followups（1—9 项，每项 input／expectation），仅 Chatflow／Agent，保存使版本与确认失效。每次固定链从新会话首轮执行，不混入自由来源；实际每轮输入、预期、输出、规则与源会话保存在 result.turns。自动规则失败停止后续，链整体计一个样例；manual 轮次在全部自动规则通过后由现有 review 接口整体复核，不覆盖自动失败。结果不一致、超时和中断为未知，保留 pending_turn 与已完成轮次。运行页轮询后台检查点并可调用 pause。启动恢复把 run/import 的 pending 改为 unknown，不重发。详见 [多轮契约](conversation-cases-contract.md)。

## 0.11.0 DSL 实际版本与保留

新增 dsl-reference、dsl-merge、dsl-merge/preview、dsl-merge/apply 与 dsl-reference/discard 接口。读取源编辑草稿（不含秘密）或上传文件后新修订／确认失效；基于对应生成建议比较三方，冲突须明确选择，预览绑定修订／来源与文件摘要。确认后最终 DSL 独立保存，任务计划仍是生成建议；导入只新建，先核对源草稿未变和成果未被修改。后续改动使保护审批失效，成功导入保留生成建议基线以继续保护既有手改。原生 Agent 仅读取保存，不支持包合并。完整契约及限制见 [保留契约](dsl-roundtrip-contract.md)。


## 0.186／0.187：进度导航与只读讨论

GET /api/tasks/{id}/next-step?revision=当前整数修订：只读保存状态与准入，旧修订409。schema_version=1、task_id／revision／app_type、snapshot_token、state、target_page、固定title／reason／checklist及verification=saved_local_navigation_advice_only；task_changed／network_requested／automatic_execution／business_verified均false。不执行模型、Dify或资源，不是全套预检；前端只导航，未保存编辑时停止读取与导航。各专用运行入口仍独立。

0.276新增state=publication／publication_review／runtime_key，Workflow/Chatflow按当前修订、环境、App及类型的已保存发布回执和专属运行Key配对建议；未知或回执不匹配优先原记录，已有当前普通运行则复核结果。仅调用has_secret查存在，不解密、不访问Dify；snapshot_token包含发布事实及Key配对布尔值，同修订变化也失效。本机配对不证明Key有效，建议不是执行许可。

POST /api/tasks/{id}/messages：content为非空、最多16000字符、UTF8完整文字，stream_response为严格布尔（默认false），mode为review或discussion（默认review）。未知字段和无效模式拒绝，错误不回显输入；默认review维持原需求与准入更新行为。discussion仍使用配置模型及同一助手访谈预算，保存对话和实际用量，但不写需求、配置、流程、确认、版本或成果；暂停／超限仍可能改变执行状态。只读讨论不代表免费或取消已派发请求。

discussion使用独立系统协议与当前类型公共能力目录，并附无身份ID的最小本机进度描述。模型响应仅完整JSON对象message一个非空字段（最多16000字符；整个回复UTF8最多128000字节），重复键、非有限值、额外修改字段、围栏及不完整回复整份拒绝，不部分采用，不自动重试。revision变化或暂停保留迟到候选与用量，不修改原业务。

服务器为讨论用户与模型回复设置purpose=discussion；该用户文字不参与需求主题、来源、准入摘要或配置建议需求依据，后续模型历史明确标为未批准讨论。用户要采用时切换review并明确更新／复核。旧消息无purpose保持原行为。执行检查点新增可选mode，旧记录无该字段仍兼容；applied只表示完整回复已保存，discussion不表示需求已修改或业务验证。

0.187已部署并完成完整3944项回归；真实模型语义与业务验收仍未新增。以development-status.md实际运行版本和检查证据为准。


## 0.188：历史比较与恢复确认

GET /api/tasks/{id}/versions/{version_id}/restore-preview?revision=当前整数修订：只读比较当前保存内容与本任务唯一历史UUID。返回schema_version=1、任务／类型／当前及历史修订、version_id、review_token、15类sections、changed_sections及5项固定impacts；verification=local_history_restore_preview_only，task_changed／network_requested／business_verified均false。仅字段标签、计数和节点结构变更数量，不返回需求正文、代码、文件名、模型／知识库标识或凭据。缺字段、重复目标、坏结构、非有限数、坏编码或完整决策JSON超过8MB不返回可确认的部分比较；节点不能逐项对应时明确只有整份变化，不推断无改动。

POST /api/tasks/{id}/restore现在必须包含严格整数revision、UUID version_id、64位小写SHA256 review_token和严格布尔acknowledge_restore=true，拒绝未知字段。**旧的仅version_id请求返回422**；不保留可绕过预览的恢复入口。错误不回显输入，旧修订、预览后当前内容／确认／成果或目标快照变化返回409。token绑定本机完整恢复决策，不是资源或模型授权。读取预览不要求任务空闲；恢复仍执行原空闲检查。恢复前先存当前快照，再恢复为新修订，相关确认／成果／应用绑定失效；保留原运行、对话、费用账本及历史，不还原Dify资源或凭据。旧快照缺materials按原语义保留当前材料，intake_required不弱化；历史分歧确认不复活。原历史不改写，前端有未保存编辑时阻止比较和恢复，取消或失败不自动重试。


## 0.190：运行前节点规模

POST /api/tasks/{id}/execution-scale：revision、完整plan_text和request_nonce必填，item_counts可省略，为当前根迭代ID到0—100000严格整数的字典。仅读当前保存任务校验原文并计算声明节点的保守次数，不执行代码或联网。source_kind=editor_plan_only、final_dsl_checked／actual_api_calls_known／cost_estimate_available均false，cost_usd=null，verification=local_declared_node_visits_only。未知项数导致总次数及相应资源次数null；原限制、预算、确认和运行保持。完整范围见execution-scale.md。


## 0.191：历史节点明细

restore-preview中可比较的nodes摘要增加moved、connections_changed、root_order_changed、other_plan_fields_changed和details。details.scope=node_identity_and_fields_only、limit=30；items为change、current_path／historical_path（1基位置数组或null）、before_type／after_type（固定类型标签或null）、fields（固定字段类别）；total覆盖全部，omitted=total-items.length，最多4000差异、30明细。结构失败available=false且不返回部分details。仅位置变化与内容修改不重复计数；根连线／元数据变化不假造节点行。原restore请求和token规范保持，不构成静态或业务通过。


## 0.192：对象逐项计算合同

POST /iteration-outcomes严格请求新增result_schema_text?:string|null（最多64000字符，实际UTF-8字节也限64000），根单计算result=object时必填完整根object Schema；string／number不得附非空对象合同。Schema原文重复键、非法编码、非有限数、超安全整数、未适配规则及疑似凭据拒绝，不回显原文；Schema子集和执行边界见iteration-outcomes.md。接口仍为本机无状态草稿，不执行／持久化／联网。响应value_type可为object，result_schema_sha256为64位哈希（标量为null）；其它归属、nonce和未验证字段保持。POST /iteration-summary不增加请求字段，从完整对象规范代码严格重建Schema并复核原方案，同样返回value_type与Schema哈希。旧标量生成规范保持。


## 0.194：只读对象Schema检查

POST /api/tasks/{id}/object-schema-check，严格revision>=1、schema_text（最多64000字符且UTF8字节也限64000）、UUID request_nonce，不接收未知字段。当前Workflow修订才接受，旧409、结构错误422且不回显原文；合法请求的规则问题返回200/valid=false，不代表通过。返回task_id／revision／nonce、source_text_sha256、schema_sha256（无效null）、diagnostics（最多20，含固定code、受限schema属性位置path或null、JSON行列或null），verification=local_object_schema_rules_only。task_changed／network_requested／code_executed／platform_checked／business_verified均false。不存在客户键名或原始错误正文；问题多于20项用too_many整份粗略提示，不静默截取或采用规则。结构通过不是计算输出检查、实际平台或业务结论，不代替结果合同确认，不改计划／预算／需求／批准或运行记录。


## 0.195：顺序多代码计算链

POST /api/tasks/{id}/iteration-chain-outcomes：revision>=1、完整plan_text（2MB）、node_id、acknowledge_chain_contract严格布尔、request_nonce必填。include_summary与acknowledge_summary_outputs均默认false，必须一致；operation为wrap（默认）或append_summary（必须确认汇总）。只为有效Workflow四根图/2—8步顺序文字数值链准备草稿，旧修订409，无效结构／确认422，不回显原文，不写任务或派发资源。

响应verification=local_calculation_chain_draft_only，task_changed／network_requested／platform_checked／business_verified均false；operation、include_summary、stages（position、input_type、value_type、original_code_sha256、code_sha256）、value_type、summary_node_id|null、added_nodes、added_end_fields、五record_fields及六caught_error_classes、native_error_handle_mode=terminated和output_type=array[object]。输入输出检查在计算捕获外、后继只传失败不调用原计算，详细边界见iteration-chain.md。标识不证明运行，采用仍未保存，保存后需求与配置重新复核。


## 0.196：计算链准备诊断

上述接口已知步骤错误返回422/detail对象，恰好code（stage_configuration／calculation_scope／wrapper_contract／stage_order）、stage_position（严格1—stage_count）、stage_count（2—8）、kind=chain_stage_preparation、task_id、revision、request_nonce、node_id、operation、include_summary、source_text_sha256（原始plan_text UTF8字节SHA256）、verification=local_chain_preparation_only及task_changed／network_requested／platform_checked／business_verified=false。封装／次序两码只用于追加汇总重建。没有代码、标题、原输入或原异常正文；不提供部分候选。原全图／准入／汇总冲突等拒绝仍可能为字符串detail，不能猜步骤；旧修订409及成功响应完全保持。诊断不是运行中的failed_stage，不写任务或联网。


## 0.197：计算链保留上游图

iteration-chain-outcomes请求和响应字段不变，旧四根成功响应SHA保持。允许完整有效Workflow中所选链的全部根祖先，不按根节点数量或首个code位置猜输入；由iterator_selector明确items解析代码。链仍直连唯一End和唯一完整结果，全部其它根节点须为其祖先；其它结束、链后处理和旁路消费者拒绝。原上游节点、参数、代码和连接保持，不执行其副作用或批准费用；追加汇总重建比较涵盖整图。单步逐项接口范围不变，应用、确认、保存和执行门禁保持。


## 0.198：逐步对象Schema计算链

iteration-chain-outcomes增加可选stage_schema_texts（默认{}）：最多8项，键为当前对象输出步骤ID（1—256字符），值为最多64000字符且实际64000UTF8字节内的完整Schema原文。wrap含对象步骤时须精确对应每个对象步骤，不得缺少、附加或为标量步骤传规则；append_summary必须空映射，只提取原规范封装。原纯标量请求和成功响应完全保持。JSON重复键、未知规则、坏编码、非有限数、超安全整数及疑似凭据拒绝；规则错误只返回安全步骤配置码，不附客户字段或原规则。

含对象步骤的成功响应增加stage_schema_sha256（所有对象输出步骤的规范Schema摘要）、stage_schema_text_sha256（wrap为原文UTF8摘要，append为{}）、result_schema_sha256（最终对象对应最后一步摘要，最终标量为null）；stages输入／输出类型允许object，value_type也允许object，五字段与未验证标志不变。客户端严格核对步骤集合、当前原文、最终合同和原nonce；明确Schema不证明实际计算或平台运行。原输入／输出安全边界、独立typed标识和汇总重建见workflow-plan-contract及iteration-chain.md。


## 0.199：规划模型能力上下文

plan/generate的用户请求字段和保存／预算门禁不变。实际内部规划消息增加capability_catalog，由当前task.app_type和运行版本生成，内容与GET /api/capabilities相同；用户需求或材料不能替换该对象。系统提示限定其为编译范围，不代表环境可用或资源批准。Workflow人审／文件／定时受限支持与Chatflow、原生Agent分开，契约早期全面禁止说明按后续明确扩展校正，不能从局部适配推导通用组合。实际模型质量仍需新的明确供应商调用许可，不把受控API检查当真实生成成功。


## 0.200：规划澄清清单（已部署）

plan/generate用户请求不变。模型明确返回error时暂停，不进入计划校验或自动修复；planning run新增可选decision_report，严格字段schema_version=1、verification=model_clarification_only、message、questions、incomplete、format_valid。问题最多20项，每条只含question/recommendation/reason/experience/cost/manual_work六个文字字段；缺少的可选说明为空串，不编造建议，不将模型id当资源或确认id。错误/问题文字各最多2000字符。未知字段、超限或坏格式显式标记不完整；安全检查失败不展开内容。原响应有界预览、费用与调用记录保留，不自动追加模型调用、采用计划或确认配置。旧error-only记录兼容，问题按run.revision显示；客户端严格识别标志和字段，历史修订不得当当前确认。

内部coverage_scope增加enabled/stale/blockers，保留confirmed/items；未启用可选覆盖清单不等于没有草稿规划权限，不能据此省略需求；真正启用后的阻塞和需求准入保持。Agent与Workflow规划共享澄清格式，但计划与原生编译各自独立。0.199八个已批准的真实响应及纠错见work/semantic-acceptance-plan/summary.md；该证据不能证明0.200修复后模型稳定性。

客户端可主动将一个当前修订问题预填入只读讨论框，不发送、不调用模型；已有文字不覆盖，旧修订禁用。完整模型回复建议仍待用户核实和需求／配置独立确认。


## 0.201：交付报告中的澄清历史

GET /tasks/{id}/report新增白名单规划澄清历史。最多50份、合计256000 UTF8字节、最多检查5000规划记录，超限或坏元数据不返部分；固定未核实标志、问题/可选建议及输入修订，旧记录不由raw响应推测。无新请求字段、确认、写入或模型调用；不是用户回答或平台验收。


## 0.202：读取保留流程候选

GET /tasks/{task_id}/planning/{run_id}/candidate为本机只读接口。仅kind省略或plan且已paused/interrupted的唯一记录，last_candidate须为非空完整对象；不从last_response_excerpt推测。后台将已存对象序列化为JSON，保留已存整数，限2MB UTF8，拒绝坏编码/非有限数/凭据；不声称恢复原模型小数词法或响应字节。404表示记录不存在或不唯一，409为活动/已成功状态，422为无可读对象/非流程种类/修订或安全结构不符。

成功字段精确为task_id,planning_run_id,input_revision,current_revision,is_current_revision,app_type,plan_text,source_sha256,byte_count,verification=retained_candidate_unverified,formal_plan_changed=false,network_requested=false,platform_checked=false,business_verified=false。network_requested=false指未请求供应商或Dify，浏览器仍有本机GET。不存在保存/确认/试跑副作用。历史记录仍可只读读取，但UI禁止载入当前草稿；来源任务、记录、原输入修订、当前修订、类型、原文摘要及字节数必须完整匹配。主动载入只调用已有本地编辑状态，不能覆盖任何未保存修改；后续留存草稿或正式保存仍由原接口与校验处理。


## 0.204：不保存的计划草稿检查

POST /tasks/{id}/plan-check仅本机静态检查：revision严格正整数、plan_text最多2000000字符且实际2MB UTF8、request_nonce为UUID，不接受额外字段或请求外层重复键，错误不回显请求。按当前已保存任务配置，用与手动保存相同的JSON/明确LLM字段文字解析和三应用校验器；不调用编译器，不存任务/草稿/版本/确认，不检查实际资源可达，不执行生成代码。异步检查前后均核对修订，变化409，不返旧结果。

成功HTTP200结果字段：valid、errors、warnings、nodes、json_location(null或正整数line/column)、source_text_sha256(原文UTF8，坏编码null)、verification=local_plan_structure_only，以及task_changed/network_requested/code_executed/platform_checked/business_verified全false，附task_id/revision/request_nonce。语法/结构/范围问题也以valid=false返回，不代表业务运行失败；消息合计最多200条，每条4000字符、总256000UTF8字节，超范围固定说明不返回部分诊断。客户端核对完整字段/归属/原文摘要，编辑或禁用即失效，无自动重试；正式保存仍重新校验。


## 0.205：明确补充单个缺失文档提取节点

POST /tasks/{id}/missing-document-extractor接revision严格正整数、plan_text实际2MB内、missing_node_id(1—256文字)、input_variable(1—64文字)、acknowledge_extraction严格true、request_nonce UUID；外层禁止重复/额外字段。仅用户选定Workflow的两现有start/end、两边经过唯一不存在ID、结束唯一missing.text、唯一必填file输入。来源/ID必须与原稿明确匹配；file-list、可选或多文件、额外节点/边、不同输出和坏配置拒绝，不部分删除或默认替换。

新增标准document-extractor(input_type=file,empty_policy=fail_if_missing)后完整validate_plan，移去新增节点应与原计划对象完全相等，原节点/边次序保留，纯JSON文字保留已存整数。无持久化、模型、编译、上传、Dify或代码执行；检查前后绑定当前修订，变化409。用户确认表示本次节点建议的类型/来源/政策，不是资源运行批准。

返回plan_text,source_text_sha256,proposal_sha256,added_node_id,file_selector,failure_policy，以及verification=local_missing_extractor_proposal_only、original_nodes_preserved/original_edges_preserved=true、task_changed/network_requested/code_executed/platform_checked/business_verified=false和task_id/revision/request_nonce。客户端按原文/归属/摘要/新增节点类型和配置严格检查，明确预览后仅更新当前未保存稿；原文/确认/任务变化清除，正式采用仍独立校验保存和确认。


## 0.211：试跑请求线格式

POST `/api/tasks/{id}/run`、`run-input-check`、`run-case-input-check`在进入处理函数前拒绝重复JSON键（含转义后同名）、非法JSON／UTF8、不合对象根、非有限数字以及浮点词法转换后数值意义改变。请求线格式最多8MB、结构至多10万个值，更小的各接口输入／Schema限制仍有效；不会截断或回显键值。整数按Python整数保留不强转float，业务Schema仍独立校验。RunRequest仅接收正整数revision、input对象、可选case_id与conversation_from_run_id；revision不接受bool／字符串／float，未知字段422。返回422的detail为固定中文说明，不含原输入；GET以及实际处理函数原资源／预算／任务修订门禁保持。
