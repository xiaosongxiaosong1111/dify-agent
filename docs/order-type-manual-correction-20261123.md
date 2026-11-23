# 单节点纠正已保存为manual，原模型图保留

第383项，2026-11-23。依据用户既有常规可逆本机修正委托，由DeepSeek实施片段、根独立验收及正常本机API集成；这是代理决定，不是新的直接人类答复。没有扩展产品模型或Dify资源/费用授权，不重放380。

## 纠正与实际检查

DeepSeek同会话1ca3bd90-16f2-47c5-9787-d8a7f0456402的do正常退出0，固定py_compile由ds CLI实际执行通过；模型自身说明没有shell工具不等于CLI没检查，分别记录。仅生成work/order-type383-code.py，无产品后端/前端改动；不是新增永久工具框架。新公开片段（非供应商原代码）：

```python
def main(order_no) -> dict:
    if not isinstance(order_no, str):
        raise ValueError("订单号输入须为文字，不转换类型。")
    normalized = order_no.strip()
    return {"nonblank": bool(normalized), "normalized": normalized}
```

片段SHA48ba3980c972fc9376650d50ca57b81ea83ab43f032e50ddf7690c150cea479f。根核完整函数，仅函数/类型检查/明确ValueError/strip/返回，无IO、网络、import、try/except或状态。9种非文字输入均抛明确ValueError；8种文字输入覆盖空/空白/普通编号/首尾空白/未知编号/中文/长文字，保持只做非空检查而不擅自加格式限制。

完整稿只替换nodes[order_no_blank_check].config.code；所有其它节点/边/模型配置/状态/文案完全相同。隔离正常POST change-preview只报1个代码节点变化、连接/其它字段0，原任务未写；POST plan正常保存manual/r8、快照保留r7/model/完整原图；需求/配置/样例/历史规划与预算保持、旧revision返回409。外部HTTP/模型/Dify/凭据读取均0，生产27Task/十二根/892旧文件和密文资产前后保持。证据work/order-type383-local-v3/report.json。

根验收壳先误用固定874旧helper验证892新增范围、再误将隔离首次Store插入序号当原序号，均失败且目录/log保留；修为旧874门+892实际每SHA和独立隔离插入基线后通过，没有改产品/候选业务期望或运行任何新模型。

## 原机正常采用与来源

隔离通过后，根按同一正常接口先POST预览、再POST plan，共2次本机Sierra请求，0模型/Dify/登录/资源/构建/运行。原目标由r7到r8，plan_source=manual、配置仍未确认；23节点/24边，纠正图SHAdd71f629c0d6a1e82d8e88aa424341fbe751369fbe0cedf19a9f1b5f44198c69。原r7/model图以完整历史版本保留，旧380包及其root-review和封存一字未改。不能称为模型自主原样通过。

独立核另外26任务/总27对象集合、11旧隔离根、892旧封存、所有密文和资产保持；目标原需求/配置/样例/intake_review/三规划记录与全部五笔费用保持，仅正常plan/manual版本/系统说明/需求确认继承变化。没有配置确认、App或artifact。当前Task SHA91cdafcc9a22a643e901753bfbe48757fe84325620fc6ce4f0772a14ecc21bbb；budget SHAb2472f1c98a48418bded9a9a73c776a14cc0b56bf0a6f04c21d87b2fea94bad0。私有order-type383-before-apply.json、work/order-type383-applied/agent-decision.json/preview.json/report.json保留实际决定和结果。

服务仍0.412.0-4b3c27aad0a80a616364，无产品代码重建/重启。模型/Dify参数均未改。下一步先用此纠正稿做正常本机静态构建/交付并核真实改版余链最小复用方案；静态包不是平台运行或自主双版验收，新的真实范围仍需明确批准。
