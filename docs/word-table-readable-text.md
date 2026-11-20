# Word表格的可读取文字判定

2026-11-20，BACKLOG343/交付清单05，FR05/06、AT06。DeepSeek查出两列全空/纯图片Word表格会拼接成“ | ”，被当作parsed正文；Codex用公开空表和单像素图片通过正常API独立复现后，给限定实现方案。

仅当表格行至少一个单元格实际提取到非空白文字，才生成该行的分隔文本。空单元格仍保留位置，真实文字/段落/嵌套与合并去重逻辑保持；不在全局正文删竖线或符号。空表、嵌套空表、纯图片表均保留needs_input、正文空和补文字入口，不能通过引用方式选择变成已读；原文件字节与SHA保持。不引入OCR或扩大格式支持。

根代理完整审产品和新检查差异；三种核心反例在旧material_documents.py真实3失败，逐字恢复新代码后运行`python -m pytest backend/tests/test_material_documents.py backend/tests/test_material_parsing.py backend/tests/test_material_text.py -q`，60 passed。正常前后段落顺序、三列表格中间空列位置、单元格实际“|”文字均保留。临时Store/公开合成文件、禁止真实HTTP/模型/Dify，无生产资料读取，未全量回归。

现有TXT/MD/JSON/YAML/YML/CSV UTF8文字、PDF页面文字和Word主正文提取功能保留；CSV未承诺结构化表格语义、Word非正文区域/图片与扫描PDF/OCR仍按原限制说明。测试通过不代表全部文档业务内容已理解，部署结果见当前交接。
