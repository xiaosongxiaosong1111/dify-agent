export function taskNameText(raw:string):{value:string;count:number;error:string}{
  const value=raw.trim(),count=Array.from(value).length;
  const error=!value?'请填写任务名称。':/[\uD800-\uDFFF]/u.test(value)?'任务名称含无法保存的文字，请明确修正。':count>100?'任务名称最多100个字符，当前输入未截断。':'';
  return {value,count,error};
}
