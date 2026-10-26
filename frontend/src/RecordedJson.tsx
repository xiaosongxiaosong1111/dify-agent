import {useMemo,useState} from 'react';
export default function RecordedJson({value,scope,label}:{value:unknown;scope:string;label:string}){
 const data=useMemo(()=>{try{const text=JSON.stringify(value,null,2);if(text===undefined)return {text:'未保存此值，未按null处理。',prefix:'未保存此值，未按null处理。',length:0};let prefix='',length=0;for(const ch of text){length++;if(length<=4000)prefix+=ch}return {text,prefix,length}}catch{return {text:'本页已读值无法完整格式化，未转换或显示部分成功。',prefix:'本页已读值无法完整格式化，未转换或显示部分成功。',length:0}}},[value]);
 const [disclosure,setDisclosure]=useState<{value:unknown;scope:string;open:boolean}|null>(null),open=!!disclosure&&disclosure.value===value&&disclosure.scope===scope&&disclosure.open;
 return <div className="recorded-json"><pre>{open?data.text:data.prefix}</pre>{data.length>4000&&<><p className="hint">{open?'已展开本页已读完整JSON':'仅显示前4000字符'}，共{data.length}字符；原记录未改变。</p><button className="secondary" onClick={()=>setDisclosure({value,scope,open:!open})}>{open?'收起':'展开'}{label}JSON</button></>}</div>;
}
