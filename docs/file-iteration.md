# HTTP文件数组逐文件处理（0.105）

根原生HTTP.files文件数组可作为单层迭代的array[file]输入，不必逐项重复下载同一数组。要求HTTP在所有路径上游；代码声明的文件对象、未知文件来源、用户上传和跨容器文件都不猜测。并行仍须实际独立性依据与2—10并发数声明，按输入索引汇总，失败模式仍terminated。

本项item为受保护文件段。内部document-extractor需明确variable_selector:[迭代ID,"item"]、input_type:"file"、empty_policy:"fail_if_missing"；生成is_array_file:false，输出text是字符串，可交给本项LLM/模板/文字问题或作为共同标量终点，汇总成array[string]。数组提取仍是is_array_file:true与array[string]text，不能混用标记、空输入政策或猜来源类型。

可信来源证明只通过编译器内部作用域传递，不接受IR中自行声明“文件已验证”。保留路径反解本文件迭代结构并重新证明HTTP数组、单文件item及输出形状一致；保留parentId、selector、标记、原代码与布局。根单文件、其他容器item、index/URL/普通对象或伪造file声明仍拒绝。

文档卡显式选择输入类型及来源，切换类型不会替换selector或空政策；单文件失败方案按钮只写当前子配置，未完成JSON保持。迭代输入候选只列必经原生HTTP.files，输出不提供文件数组作为本项标量输出。解析服务、数据出站、格式、扫描件、缺失/空内容/坏文件、限流和费用仍须明确；不提供OCR、不跳过坏文件或保证立即取消已发并发。解析费用不计入Sierra助手预算。

已核对Dify1.17.1 tag的test_document_extractor_node.py：单FileSegment成功返回字符串，提取异常失败。当前编译/保留与页面验证是隔离结果，没有HTTP下载、解析真实文件、付费模型或Dify新建/运行；实际质量与运行仍需具体资源方案获批后验收。
