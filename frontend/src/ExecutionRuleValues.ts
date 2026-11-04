import {modelNumber} from './ModelParameterValues';

export const executionRuleFields = ['max_retries','max_minutes','max_cost_usd'] as const;
export type ExecutionRuleKey = typeof executionRuleFields[number];
export type ExecutionRuleValues = Record<ExecutionRuleKey,number>;
export const executionRuleLabels:Record<ExecutionRuleKey,string> = {
  max_retries:'最大自动修复次数',max_minutes:'时间上限',max_cost_usd:'费用估算上限',
};
export function executionRuleText(values:ExecutionRuleValues):Record<ExecutionRuleKey,string>{
  return {max_retries:String(values.max_retries),max_minutes:String(values.max_minutes),max_cost_usd:String(values.max_cost_usd)};
}
export function executionRuleNumber(field:ExecutionRuleKey,raw:string):number{
  const value=modelNumber(raw,executionRuleLabels[field]);
  if(field==='max_retries'){
    if(!Number.isInteger(value)||value<0||value>10)throw Error('最大自动修复次数须为0—10的整数；空白不表示关闭。');
  }else if(value<=0)throw Error(`${executionRuleLabels[field]}须为正数；空白不使用默认值。`);
  return value;
}
