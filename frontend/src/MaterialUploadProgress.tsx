import type {UploadProgress} from './materialUploadQueue';
const labels={waiting:'未派发',uploading:'本份正在上传／核对回执',parsed:'已保存并提取文字',needs_input:'已保存，待补充可读文字',unknown:'结果需核对，不自动重传'};
export default function MaterialUploadProgress({value,onStop,onClear}:{value:UploadProgress;onStop:()=>void;onClear:()=>void}){
 return <div className="material-upload-progress callout"><b>材料逐份上传 · {value.items.length}份</b><p role="status">{value.note}</p><p className="hint">停止不取消已派发文件或删除已保存原件；上传解析不调用模型，也不表示理解或业务验证通过。刷新关闭后请从原任务材料区核对，不自动恢复队列。</p><ol>{value.items.map((item,index)=><li key={index}>{item.name} · {labels[item.state]}{item.revision!==undefined&&` · 保存于v${item.revision}`}{item.materialId&&<small> · 材料{item.materialId}</small>}</li>)}</ol>{value.running?<button className="secondary" disabled={value.stopping} onClick={onStop}>{value.stopping?'已请求停止后续上传':'停止后续上传'}</button>:<button className="secondary" onClick={onClear}>收起本次上传记录</button>}</div>;
}
