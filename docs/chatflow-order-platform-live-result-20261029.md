# 375人工售后Chatflow实际首例失败与停止

用户对call_e81418955baa45b6ab79e316294a1f8e question0直接答“允许这批完整新范围”，根代理绑定最终15文件plan97cad3a4/manifest98807f3d后，仅一次执行。批已永久消费并停止，不能重放或继续未派发阶段。

实际新增：0搭建模型、13管理读取、1次加密登录、Task1、App/首次发布/运行Key各1、Service1，共18次实际HTTP。导入、首次发布及Key绑定成功；首例faq-hit执行success，但声明规则failed，故立即停止。未追加消息映射/节点诊断读取，没有进入另外五样例、第二版或下载ZIP。

| 项 | 保存事实 |
|---|---|
| Task | 62bb060f-b7fa-4397-acb0-ba931c7dbfb2，r5/run_completed，确认保留，plan_stale=false |
| App | aa4a052e-c7b4-4b84-b4bf-4fe741afb22f |
| 发布工作流 | b4ef4a54-e19a-4c86-ae3b-9ac2b46accf3 |
| 本机运行 | f7576baa-61f4-43b2-80d9-4ad0609c897f |
| 消息/会话 | 091f7f7e-a0b8-46e2-8abd-d7db285ed11c / b4fbd90f-1b62-49f4-b90c-d55d725e1d0e |
| 原预期 | answer包含ZXRET715、七天、未拆封，未修改 |
| 实际回答 | 知识库暂无相关信息，请联系人工客服，并提供订单号。 |
| Dify返回用量 | 881输入/75输出/956总tokens；返回报价0 USD，不代表账单或免费 |

首例没有取得原生运行ID或节点轨迹，不能从固定回复断定具体是资料、检索、条件分支或回答问题。仅对照本机已保存配置和官方源码，未作修复、改期望或再运行。

离线检查了布尔条件假设：Dify1.17.1的[官方依赖](https://github.com/langgenius/dify/blob/1.17.1/api/pyproject.toml)固定graphon==0.7.0；[Graphon v0.7.0条件处理](https://github.com/langgenius/graphon/blob/v0.7.0/src/graphon/utils/condition/processor.py)的两个已审阅纯函数能正确处理True/False与expected=True。该假设没有复现，不能据此修改模板或归因本次真实失败；这不是完整引擎或真实节点复测。公开源码缓存及纯函数证明留work/condition-source376，所有Dify新请求0。

当前19Task，原18/旧对象、密文资产主Key、六settled模型费用及全部旧消费文件精确保持。专用连接已切新App的Key，原Key加密归档；原C1 r17/4次已满仍保持，不能派发第五次。模型26实际/30保守和账本0.755473652不变；保守读取701/登录38/资源各14/Service36保留，未使用的115读取、资源各1、13Service等不自动归还或借用。新Task本次1/12启动，物理Service1；两者不混为全局剩余授权。

最新授权后数据保护基线work/chatflow-order375/post-live-data-snapshot.json，旧374基线保留作原18历史，不能要求新19Task/新Key与旧全量相同。375的plan/manifest/approval/attempt/worker-started/progress及所有旧消费包均保留原字节，完整摘要在[安全JSON](chatflow-order-platform-live-result-20261029.json)。服务仍0.356.0-5476d30269eac2811387/289文件/PID35272，未改产品源码或重新部署。

下一步需要对这条已有失败消息取得只读原生诊断，才能定位实质问题；旧375因失败已停，不能拿未派发读取继续。应先完成独立、最多4管理GET、0登录/模型/资源/运行的新本机只读方案及源绑定，按明确改授规则请求新直接批准，不阶段重试375。当前原Chatflow订单链、模型自主访谈规划及全25业务仍未通过。
