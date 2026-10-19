export default function AgentPreservationNote({appType}:{appType?:string}) {
 if(appType!=='agent') return null;
 return <p className="hint agent-preservation-note" role="note">原生 Agent 可保留单个文本或已选知识集包的系统指令、名称说明、开场白和建议问题；知识集名称、用途、top_k 与分组按最终文件保留，知识库 ID 并集须与本次选择一致，采用自主生成词及无重排多库检索。模型须与本次已选配置一致；自定义工具、文件、Skills、环境变量、复杂检索与非默认沙箱／记忆配置暂不合并，不会删除这些功能后通过。合并仍需逐项确认，不代表已导入或试跑。</p>;
}
