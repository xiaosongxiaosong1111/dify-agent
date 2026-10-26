import MaterialStoredTextPanel from './MaterialStoredTextPanel';
import type {TextMaterial} from './materialStoredTextTransport';

export default function MaterialExtraction({taskId,revision,material,blocked,onQuote}:{taskId:string;revision:number;material:TextMaterial;blocked?:boolean;onQuote?:(text:string)=>boolean}){
 const note=material.extraction_coverage?.scope_note;
 return <div className="material-extraction">{note&&<p className="hint">{note}</p>}<MaterialStoredTextPanel taskId={taskId} revision={revision} material={material} blocked={blocked} onQuote={onQuote}/></div>;
}
