# Sierra AT-06 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 14 项「核对 AT-06『只有原始知识资料』现状并补隔离检查」。基线：`docs/requirements-v1.0.md` 的 AT-06「检查、提出整理与建库方案，确认后执行可用操作」。

结论：**本项本地隔离检查通过；真实资料整理、Dify 建库与索引、成本和客户知识命中仍未全面验收。** 本次仅补测试与记录，未修改产品实现、未部署；只做第 14 项。

## 现状核对

- `backend/app/main.py` 的资料上传接口读取支持格式的全文；不可读、空白、超限资料保存为 `needs_input` 并返回中文原因，不截取部分正文充当可用资料。
- `backend/app/knowledge.py` 检查资料属于当前任务、已解析且非空，限制份数、单份长度与总字节数；建库方案保存用途、名称、索引方式、完整资料快照与 SHA256、任务修订、目标连接和工作空间身份。当前流程不执行语义清洗、重写、去重或自动解决事实冲突，不能据此声称完成自动资料整理。
- 生成方案仅读取适配层的工作空间及必要模型目录，不写外部资源；确认方案后仍须单独启动执行。经济索引不调用 Embedding；高质量索引要求精确可用模型及明确接受未知模型费用，不自动降级。时间上限不能取消已提交的索引，也不是供应商账单硬上限。
- 执行依次创建资料库、单库 Key、上传完整文本；索引状态核对通过后才进入 `ready`，加入配置前重新读取状态。`ready` 不代表知识检索效果已验收；加入配置增加修订、使配置确认失效，不代做应用构建、导入、运行或业务验收。
- 作业和任务持久化在本地后端；任务修订或连接修订变化使旧方案不能执行。原有隔离用例还覆盖工作空间切换、写入结果未知、暂停与恢复、时间限制、Key 隔离与脱敏。

## 新增隔离检查

在指定 `backend/tests/test_knowledge.py` 新增 12 例，并为整个文件设置自动 fixture，阻断同步／异步真实 HTTP transport 及默认模型调用；Dify 适配方法只返回固定测试数据。沿用临时数据库与临时资料目录，不接触真实 Dify 资源或付费模型。

1. Workflow、Chatflow（接口标识 `advanced-chat`）、Agent 各一例：从正常新建任务和真实本机文本上传开始，保留准入门禁；核对完整原文及摘要、用途与费用说明、草稿／确认阶段无写入且任务不变、临时数据库重开后作业与确认保持。模拟索引等待时不得加入配置；状态完成后显式加入，原类型与资料保留、修订增加、确认失效，且没有成果、Dify 应用绑定或运行记录。再次重开数据库核对任务与应用修订持久化。
2. 不支持的图片、空白文本、超限文本各一例：实际上传返回解析限制，建库方案拒绝，不保存作业、不修改任务或写入适配资源。
3. 其他任务的有效素材 ID 不得用于当前任务，不能越过资料范围限制。
4. 高质量方案确认后模型失效，执行暂停、无资源派发，保留精确模型和索引方式，不自动降级。
5. 任务修订、连接凭据修订变化各一例：旧已确认方案执行被拒绝，无资源写入、任务不变。
6. 作业曾为 `ready`，加入配置时索引变为错误，重新核对阻止采纳，配置不变。
7. 两份资料一份完成、一份等待时不标记就绪；全部固定状态完成后才进入 `ready`，刷新不重复上传。

## 指定命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge.py -q
```

首轮退出码 1：`1 failed, 36 passed, 1 warning, 2 errors in 12.70s`。新增测试使用了过长的自动参数 ID，产生夹具错误；另将 Chatflow 接口类型误写为 `chatflow`。先增加短参数 ID 后第二轮退出码 1：`1 failed, 37 passed, 1 warning in 12.95s`，剩余失败为上述类型标识错误。将测试类型改成真实接口标识 `advanced-chat` 后，同一指定命令退出码 0，完整输出：

```text
......................................                                   [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
38 passed, 1 warning in 13.03s
```

唯一警告来自现有 FastAPI／Starlette TestClient 依赖，未修改依赖。

## 修订与未关闭边界

产品代码基线：`daa8c1f2a29eff4dfd8d13e5d9c3b5baacdea8a7`。验收时 `backend/tests/test_knowledge.py` SHA256：`41d587bb3eae7d60e4314ca4cc7437c46ffe5111ffc10154d0b3a814c7aec971`。相关实现或测试变更后须重新验收。

本记录登记为 acceptance-mapping 的 `final_acceptance_record`，只记录此次本地结论。固定适配响应不是实际索引、授权或模型调用回执，语义资料整理、真实高质量索引与费用、客户资料检索命中、前端操作体验和真实 Dify 业务链路仍待验收，不代表 AT-06 最终业务通过或整个 136 项计划完成。

未运行全量测试、重建、Docker、真实资源操作或真实模型调用；未修改 `.venv`、`.gitignore` 或仓库设置，未删除目录或推送。
