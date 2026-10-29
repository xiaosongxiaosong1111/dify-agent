# 修复上下文后的独立Chatflow双版平台核对（378）

375已失败消费，376已完成诊断消费，不能重放或借退旧槽。本批是新独立完整范围，仅本机准备、隔离及冻结；新直接批准前不执行。固定357-c038db013b5e96bc4d3e/原空间，原19Task、375及376和更旧304证据/旧unknown及全部费用保持。

使用357已修复的售后人工17节点模板，必须在grounded_answer提示中引用{{#context#}}且绑定retrieve.result；没有引用则合同拒绝，不能退回旧有缺口图。0搭建模型，不是模型自主访谈规划或全原§11/25质量；未来Dify内部仍调用分类/提取/回答模型。

新Task1、App/首次发布/Key各2；两版各6样例：FAQ政策命中、资料无答案、范围外、模拟订单有/无、缺号后同会话补号。共12启动/14Service，逐轮原生轨迹及双ZIP；第二版只在两处同一无答案文案增加商品型号。Task上限12启动/45分钟，整批60分钟；任何异常整批停止不重试。

拟全部新增128管理GET/1加密登录，资源各2/14Service，不改授或借用375余105读/资源1/Service13；旧预留及unknown不退。拟保守读取701→829、登录39→40、资源各14→16、Service36→50，Sierra模型30及账本0.755473652不增。Dify新估0.10 USD非账单硬限、宿主未知；专用连接切新Key、旧Key加密归档，不覆盖旧App，不建库。

入口为正常产品API。只读管理接口按1.17.1原App消息/会话映射实际run，核执行/发布/本地核心图，不证明不可变发布版本；无答案可为空检索或片段不足，分别记录。静态ZIP flags=false，不把替身升级真实质量。

本机命令：python tools/corrected-chatflow378/rehearse.py work/NEW-CORRECTED-REHEARSAL；python -m pytest backend/tests/test_corrected_chatflow_boundary.py -q --basetemp work/NEW-CORRECTED-GATES。生产数据不进入替身。

隔离证明源码哈希通过后freeze.py只写新的work/corrected-chatflow378，不生成approval/attempt；新直接答复绑定最终plan/manifest/完整范围后才可唯一execute.py live。非canonical/优化模式/来源或运行变化拒绝；本机Docker未就绪则不消费/登录。旧批准和常规委托不能扩大外部范围，任何异常终止，未派发槽/费用不自动归还。
