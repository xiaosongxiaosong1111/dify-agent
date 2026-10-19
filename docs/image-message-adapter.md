# 受限内嵌图像消息底座（0.93）

OpenAI兼容入口保留user content中的text／image_url，Anthropic转换为image+source(type=base64,media_type,data)，文字和图像顺序保持。只接收一张PNG／JPEG内嵌数据，Sierra首批单图1MB／边长1—4096，不抓取远程URL、不上传FilesAPI、不支持GIF／WebP／SVG／PDF、不自动缩小／裁切。头部及MIME／SHA核对仅静态元数据，不解码像素，不证明完整文件或OCR质量。

默认call_model.allow_images=false，普通文字操作不能隐式发送图像。未来图像派发必须来自具体出站预览／确认入口且显式允许；尚未提供该产品入口，不能把协议底座当成自动识图已经可用。未知段／额外字段／多图／错误base64／MIME／尺寸／系统图像会拒绝，不丢图后继续。Anthropic不能使用OpenAI专用low/high/original细节设置，明确auto原生处理；否则拒绝，不忽略用户选择。纯文字历史请求不改变。

协议依据已实际读取的官方 [OpenAI Chat内容类型](https://developers.openai.com/api/reference/resources/chat)与[图像输入指南](https://developers.openai.com/api/docs/guides/images-vision)、[Anthropic图像base64](https://platform.claude.com/docs/en/build-with-claude/vision)。官方协议不证明所有兼容服务、用户账号或型号支持识图，图像计费随模型／尺寸与处理设置变化，不按base64字符数宣称准确费用。本阶段没有建议或更换模型，也没有真实供应商调用。

11新增，91相关通过6.03秒（既有Starlette提示1），受控HTTP检查两种实际payload及usage、坏输入不会发请求；首次独立测试缺backend sys.path已修正。前端未变沿用0.92主493.90kB／材料lazy8.45kB；完整 **1993通过**（124.61秒／既有Starlette提示1），不重复无理由UI／build。没有真实图像／模型／OCR、业务HTTP或Dify操作。
