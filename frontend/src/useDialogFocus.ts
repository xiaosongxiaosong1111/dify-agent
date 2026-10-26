import {useEffect,useLayoutEffect,useRef,type RefObject} from 'react';

const selector='button,input:not([type="hidden"]),select,textarea,a[href],summary,[tabindex],[contenteditable="true"]';
function available(element:HTMLElement){return element.tabIndex>=0&&!element.matches(':disabled')&&!element.closest('[inert]')&&element.getClientRects().length>0&&getComputedStyle(element).visibility!=='hidden'}
function controls(dialog:HTMLElement){return [...dialog.querySelectorAll<HTMLElement>(selector)].filter(available)}

/** Root dialog only. It controls keyboard focus; it never submits or cancels work. */
export default function useDialogFocus(dialog:RefObject<HTMLDivElement|null>,kind:string,onClose:()=>void){
 const outside=useRef<HTMLElement|null>(null),origin=useRef<HTMLElement|null>(null),open=!!kind,active=useRef(open),close=useRef(onClose);active.current=open;close.current=onClose;
 const focus=()=>{const root=dialog.current;if(!root)return;const list=controls(root),field=list.find(el=>el.matches('input,select,textarea,[contenteditable="true"]'));(field||list[0]||root).focus({preventScroll:true})};
 useEffect(()=>{
  const remember=(event:FocusEvent)=>{const target=event.target;if(!(target instanceof HTMLElement))return;if(target.closest('[data-root-dialog]'))return;if(!active.current)outside.current=target;else focus()};
  document.addEventListener('focusin',remember);return()=>document.removeEventListener('focusin',remember);
 },[dialog]);
 useLayoutEffect(()=>{
  if(!open||!dialog.current)return;
  const root=dialog.current,overlay=root.parentElement,parent=overlay?.parentElement;
  const previous=document.activeElement;origin.current=outside.current||(previous instanceof HTMLElement&&!root.contains(previous)?previous:null);
  const backgrounds=parent?[...parent.children].filter((el):el is HTMLElement=>el instanceof HTMLElement&&el!==overlay).map(el=>({el,inert:el.inert})):[];
  backgrounds.forEach(({el})=>{el.inert=true});
  const keydown=(event:KeyboardEvent)=>{
   const current=dialog.current;if(!current||event.defaultPrevented||event.isComposing)return;
   if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close.current();return}
   if(event.key!=='Tab')return;
   const list=controls(current),first=list[0],last=list.at(-1),focused=document.activeElement;
   if(!first){event.preventDefault();current.focus();return}
   if(!current.contains(focused)||!list.includes(focused as HTMLElement)){event.preventDefault();(event.shiftKey?last!:first).focus();return}
   if(event.shiftKey&&focused===first){event.preventDefault();last!.focus()}
   else if(!event.shiftKey&&focused===last){event.preventDefault();first.focus()}
  };
  document.addEventListener('keydown',keydown);
  return()=>{document.removeEventListener('keydown',keydown);backgrounds.forEach(({el,inert})=>{el.inert=inert});const target=origin.current;origin.current=null;if(target?.isConnected&&available(target))target.focus({preventScroll:true})};
 },[open,dialog]);
 useLayoutEffect(()=>{if(kind)focus()},[kind,dialog]);
}
