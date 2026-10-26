import MaterialStoredTextPanel from './MaterialStoredTextPanel';
import type {TextMaterial} from './materialStoredTextTransport';

export default function MaterialExtraction({taskId,revision,material}:{taskId:string;revision:number;material:TextMaterial}){
 const note=material.extraction_coverage?.scope_note;
 return <div className="material-extraction">{note&&<p className="hint">{note}</p>}<MaterialStoredTextPanel taskId={taskId} revision={revision} material={material}/></div>;
}
