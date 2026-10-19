/** Display saved decimal money exactly; never round a nonzero charge to zero. */
export function usdText(value:unknown):string{
 if(value===null||value===undefined)return '未知';
 if(typeof value==='number'){
  if(!Number.isFinite(value)||value<0)return '金额格式待核对';
  value=String(value);
 }
 if(typeof value!=='string'||value.length>100)return '金额格式待核对';
 const match=/^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/.exec(value);
 if(!match)return '金额格式待核对';
 const exponent=match[5]??'0';
 if(exponent.replace(/^[+-]/,'').length>3||Math.abs(Number(exponent))>100)return '金额格式待核对';
 const whole=match[2]??'0',fraction=match[3]??match[4]??'',digits=whole+fraction;
 if(match[1]==='-'&&/[1-9]/.test(digits))return '金额格式待核对';
 if(!/[1-9]/.test(digits))return '$0';
 const point=whole.length+Number(exponent);
 const expanded=point<=0?'0.'+'0'.repeat(-point)+digits:point>=digits.length?digits+'0'.repeat(point-digits.length):digits.slice(0,point)+'.'+digits.slice(point);
 const [integer,decimal='']=expanded.split('.'),tail=decimal.replace(/0+$/,'');
 const result=integer.replace(/^0+(?=\d)/,'')+(tail?'.'+tail:'');
 return result.length<=128?'$'+result:'金额格式待核对';
}
