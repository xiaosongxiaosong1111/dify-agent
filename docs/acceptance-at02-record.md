# Sierra AT-02 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 10 项「核对 AT-02『用户不知道分类规则』现状并补隔离检查」。基线：`docs/requirements-v1.0.md` 的 AT-02「提出规则与例子，确认后采用」。

结论：**本项本地隔离检查通过；AT-02 真实模型建议质量及最终业务验收仍未完成。** 本次仅修改测试和记录，未修改产品实现或部署。

## 现状核对

- `backend/app/assistant_scope_prompt.py` 的 `BASE_PROMPT` 要求用户不懂规则时提供明确草案供确认，拟议规则标为建议，不用默认值填未知项；没有强制结构化的分类例子字段。
- `backend/app/intake.py` 保存规则追问、推荐、理由及体验／费用／人工影响；空白或以“待确认”“建议：”等开头的规则，以及检查中的 `needs_input`，阻止需求确认。证据只能引用已保存需求、用户需求消息、已解析材料或人工复核决定，助手消息不是用户依据。
- `backend/app/main.py` 的需求检查访谈会校验补丁和来源后整理需求，并使旧确认失效；模型回复不会自动完成需求确认。用户需对当前修订另行调用确认接口。来源校验验证引文存在，不判定语义正确或用户同意；不能据此宣称所有未经同意的建议都被确定性阻断。
- 原有测试覆盖一般规则缺口、人工复核和模型不能自证补丁，但缺少分类规则与例子从建议到用户裁定的专门链路。

## 新增隔离检查

`backend/tests/test_intake.py` 新增 5 例，使用固定模型替身，不验证真实模型的分类质量：

1. 三种用户所选类型 Workflow／Chatflow／Agent 各一例：先建议退款类、物流类、其他类及重叠时退款优先，并提供正常、重叠、未命中共四个例子；建议和影响从 API 读回。用户暂不采用时，规则和例子不写入需求、修订不变、规则缺口保留；需求确认和构建拒绝，拒绝操作不改变任务或预算。
2. 上述三例继续使用用户明确复述接受规则和例子的消息作为证据，允许整理 `rules/tests`，但需求仍未确认；旧修订确认返回 409，当前修订单独确认才生效。类型保持不变，无流程、成果、Dify 绑定或运行。再次修改规则后，准入检查过期、确认失效并阻止重新确认。每例恰好三次替身调用，无自动重试。
3. 另两例分别以模型未落库的规则补丁、已保存的助手建议消息作为“已接受”依据，均因来源引文不存在而拒绝候选；保留原需求、修订及原检查记录，记录失败且不能确认。每例恰好两次替身调用，无自动重试。

沿用临时 Store、进程内 TestClient；文件级自动 fixture 阻断真实同步／异步 HTTP 传输和默认 `main.call_model`，需要响应的用例显式安装固定替身。测试用量仅为固定模拟账本，不是供应商账单。不接触真实任务、Dify 资源或付费模型。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_intake.py -q
```

最终退出码 `0`。同一次执行的分段输出合并如下（执行前仅设置进程环境 `PYTHONIOENCODING=utf-8` 以正确显示中文）：

```text
.......................................                                  [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
39 passed, 1 warning in 11.06s
```

首次指定命令输出 `2 failed, 37 passed, 1 warning in 10.95s`。失败原因：测试通用 `review` 助手为 Chatflow／Agent 专项证据引用了本轮尚未保存的新规则，产品正确拒绝。补充固定需求中的对话／工具边界，并让专项检查引用已保存边界后重跑通过，未放宽产品校验。唯一警告来自现有 FastAPI／Starlette TestClient 依赖，未改依赖。

## 修订与未关闭边界

产品代码基线：`9f831931837691021076ad1c452a782973333e4d`。最终验收时 `backend/tests/test_intake.py` SHA256：`e5114fdbc8551ed330caf95f93e4a50c83378966ecaf8ad601c6a89cafcaef04`。相关实现或测试变化后须重新验收。测试、本文、映射、队列第 10 项及开发进度同次提交；队列其他任务不变。

固定响应证明这些响应下的持久化、来源和修订门禁行为，不证明真实模型会持续提出合理分类规则、完整例子、正确识别拒绝／接受，也不证明合法引文在语义上授权新规则。未做前端体验、真实模型、Dify 导入／试跑或最终业务验收。不把本次 39 个本地通过计作 AT-02 最终业务通过或 136 项计划完成。未跑全量测试、重建、Docker 操作、修改 `.venv`／`.gitignore`／仓库设置、删除目录或推送。
