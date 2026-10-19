/** Translate Python JSON line/code-point column to a browser textarea range. */
export type ErrorLocation={line:number;column:number};
export type EditorRange={start:number;end:number};
export function textareaText(text:string){return text.replace(/\r\n?/g,'\n')}
export function jsonErrorRange(text:string,location:ErrorLocation):EditorRange|null{
 if(typeof text!=='string'||text.length>2000000||!location||!Number.isSafeInteger(location.line)||!Number.isSafeInteger(location.column)||location.line<1||location.column<1||location.line>2000001||location.column>2000001)return null;
 let offset=0;
 for(let line=1;line<location.line;line++){const newline=text.indexOf('\n',offset);if(newline<0)return null;offset=newline+1}
 const found=text.indexOf('\n',offset),lineEnd=found<0?text.length:found;
 for(let column=1;column<location.column;column++){
  if(offset>=lineEnd)return null;
  offset+=text.codePointAt(offset)!>0xffff?2:1;
 }
 if(offset>lineEnd)return null;
 const end=offset<text.length?offset+(text.codePointAt(offset)!>0xffff?2:1):offset;
 return {start:textareaText(text.slice(0,offset)).length,end:textareaText(text.slice(0,end)).length};
}
