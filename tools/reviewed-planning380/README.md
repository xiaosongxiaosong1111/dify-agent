# reviewed-planning380：从固定 377 源派生的一次原规划批（仅本机准备）

本目录只新增本机跟踪源与公开检查。开发和公开检查阶段没有真实模型、Dify、登录、Task、资源或运行；不读取生产数据或凭据。原机pending由根在实现提交后执行，仅读精确保护摘要/密文哈希和封存，不读取明文Key或生成approval/attempt。

## 状态（精确区分）

- **已实现（本目录）**：从固定提交 `ec8d7b706fb12b98230eb1ec33e14933d5fcb2e9` 的
  五个 377 文件派生四个 `.py`；固定 SHA/替换计数/禁用串/门片段/编译；真实重算门；
  frozen 常量门；公开检查协议。
- **已公开观察**：此前固定 CLI 的前 9 组行为通过；README 曾被误当 Python `compile`
  的缺陷已修（五 blob 仍全部核 SHA，只对 `.py` 编译）；成功标签已改为实际 874。
- **未授权/未发生**：真实模型、Dify、登录、资源、原机 pending、canonical、approval、
  attempt 均未生成；真实新范围仍须 root 最终冻结后的新直接答复。
- **常量已冻结（本机修后实测）**：`DERIVED_SHA` 已填入修后 `derive.py` 实际计算
  的四个值；旧 v1 映射已失效，未沿用。公开检查尚未在本次修改后实际跑过，因此
  不声称 green。冻结映射：

```text
common.py  395c31937b730f3877779e192dd0bc7808940d5ff3d00d21cd181ed8ddf72387
worker.py  c4c80571b12b444021a394aaaaa480d3ca9201144100e7da4720a585eb1272f1
tool.py    251df52f4c6f8bdca5533673804c752d60eb6d460ffff2500b40338f16ae1fc4
checks.py  0fd7ce4a4feb815d90fb9c74c1e86bb2737caaef58e805bae04a358ea5e4ccf9
```

## 模板与派生

模板固定为提交 `ec8d7b7…` 的
`tools/preserved-planning377/{common,worker,tool,checks}.py` 与 `README.md`。
`derive.py` 只用 `git cat-file blob` 读取规范化 LF 字节，逐条精确 `count` 替换
（允许少量必要函数体区段替换），再断言禁用串、关键门片段、编译与最终 SHA。
README 是唯一的跟踪/包 README：人工源，不由派生覆盖，避免双来源矛盾。

根独立核的模板 normalized-LF SHA：

```text
common.py  3bbf5466b61a16f225a4cd55f192183907a8099b5c74d11c0e403a99a96bfcd1
worker.py  cf0ba4b289d6005dcf15f5487696f285c4578da49a3b91e7904a29ac69ec1a91
tool.py    084cbd011b9cf84129f08c57ebf6aa3c7ee9aa1dffa790041f2e8b223baa64d2
checks.py  5840b94b4780d09e5939abb214ad4490a586cd6b2074ccc4d35428e86a9d4cc7
README.md  2bdf8c05e1cb9d3afac4cb7f5b1e23420b064ed65f91cfbc00a0b79145cbabaf
```

来源门同时要求：blob SHA 等于上述常量；工作树文件存在、非链接、规范化 LF 等于
blob；仅 `.py` 执行 `compile`。缺文件、链接、工作树漂移均拒绝。

## 真实重算门（不靠名字/片段）

`tool.verify_derive` 的执行顺序：

1. `verified_derive` 用 `git cat-file` 证明 canonical 的
   `derive.py`/`run_checks.py`/`README.md` 等于 `derive_commit` 的 blob；
2. 用显式文件路径 `importlib.util.spec_from_file_location` 加载**刚被证实的**
   `derive.py`（唯一模块名，不插入 `sys.path`），并核 `module.__file__`、
   `DERIVED_FILES`、`ORIGIN_COMMIT/ORIGIN_DIR/ORIGIN_FILES/ORIGIN_SHA` 与
   `SOURCE_PINS`/`SOURCE_FILE_SHA` 一致；
3. 要求 `module.frozen()`；调用 `module.check(origin_project, root)` 从固定 origin
   blob 重算四个派生字节并比对固定 `DERIVED_SHA`；
4. 重算结果必须同时等于 plan 的 `derived_file_sha256`。

`pending` 在写 plan/manifest **之前**做同样重算与 frozen 检查；并且在任何消费标记/
数据读取之前先 frozen。`verify_package` 调用该门，因此
`approve`/`validate`/`live`/`authorize_worker`/`pre_dispatch` 每次都实际重算，
不是只查摘要或源码片段。空常量、常量被改、派生文件被改并同步伪造 plan 都会拒绝。

## 新源绑定

- `tool.py pending --derive-commit <完整40位>`；plan 持久 `derive_commit`、
  `derive_file_sha256`（3 跟踪源）、`derived_file_sha256`（4 派生输出）；
  manifest 覆盖 7 文件。
- 旧/缺失/篡改的新源提交、工作树漂移、缺文件、链接均失败；公开检查用临时纯合成
  Git 仓库验证 positive/negative，不触碰原 repo 或全局 Git 配置。

## 公开检查

```text
python tools/reviewed-planning380/run_checks.py            # 未冻结时非零退出
python tools/reviewed-planning380/run_checks.py --print-sha  # 只打印实际映射
python tools/reviewed-planning380/derive.py --print-sha      # 等价诊断
```

未冻结时 `run_checks.py` **不会**材料化或执行检查，而是打印当前实际计算映射并以
非零退出，供 root 一次回填 `DERIVED_SHA` 后提交。冻结后它只在 `PROJECT/work` 下
新建自己的临时包，执行派生 `checks.py`，并在结束时只清理该已核绝对路径目录。

公开检查覆盖：真实产品 API 成功/坏 JSON/needs_decision/unknown usage 停止、单次
HTTP、边界、Store/预算/旧前缀守卫、874 封存加载、runtime 绑定与进程身份、五源
blob/工作树校验、seal 加载与越界、receipt、旧 ref/退休 ref、manifest、新源提交
绑定、frozen 重算正例与常量/派生伪造反例。测试只使用临时合成 Git/目录，读数仅为
源码，不读真实 data/work。

## 原机包（7 文件）

`common.py`/`worker.py`/`tool.py`/`checks.py` 为派生；`README.md` 为本文件；
`derive.py`/`run_checks.py` 为跟踪工具。真实生命周期只在 root 提交并冻结后于原机执行。

## 已知限制

- 公开 green 不等于真实模型、Dify 平台或业务验收；完整模型主线仍未通过。
- 377 seal 的 14 个包内相对名、第四笔账本细分、旧审批 ref 只能在冻结现场从封存
  字节读取；任一不符即停。
- 运行 PID 34736 是观测值；实际要求唯一正确进程/源快照一致，查不到即停。
- 实现交付时未生成原机plan/manifest/approval/attempt，也未执行真实批；后续精确冻结与实际状态以docs/reviewed-planning380-plan-20261123.md及对应冻结/结果记录为准，本README不是直接批准。
