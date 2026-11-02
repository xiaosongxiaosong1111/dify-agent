"""Persistent interview execution checkpoints; no prompt, raw delta or secrets."""
import copy,time
from fastapi import HTTPException
from .interview_text_preview import MessagePreview


class InterviewProgress:
    def __init__(self,host):self.h=host;self.counts={};self.previews={}

    def begin(self,task,provider,item_id,stream,mode="review",request_record=None):
        record={'id':item_id,'task_id':task['id'],'revision':task['revision'],'provider_id':provider['id'],'model':provider['model'],'protocol':provider.get('protocol','openai-compatible'),'stream_requested':stream,'status':'running','phase':'waiting_response','received_characters':0,'delta_count':0,'started_at':self.h.now(),'updated_at':self.h.now(),'note':'接收状态不是需求已确认；完整结构与修订校验后才可采用。'}
        record['mode']=mode
        if mode=='discussion':record['note']='只读讨论：完整回复仅保存到对话，不修改需求或确认，费用计入助手访谈预算。'
        task['updated_at']=self.h.now();self.h.store.put_many([('interview_operation',item_id,record),('task',task['id'],task)]+([('message_request',request_record['id'],request_record)] if request_record else []))
        self.counts[item_id]={'characters':0,'deltas':0,'last_saved':0}
        if stream:self.previews[item_id]=MessagePreview()

    def received(self,item_id,text):
        with self.h.store.lock:
            record=self.h.store.get('interview_operation',item_id)
            if not record or record['status']!='running':return
            counter=self.counts.setdefault(item_id,{'characters':record['received_characters'],'deltas':record['delta_count'],'last_saved':0})
            counter['characters']+=len(text);counter['deltas']+=1
            task=self.h.get_task(record['task_id'])
            if task.get('active_interview_id')!=item_id or task['revision']!=record['revision'] or task.get('status')!='interviewing':self.previews.pop(item_id,None)
            elif item_id in self.previews:self.previews[item_id].feed(text)
            if time.monotonic()-counter['last_saved']<.25:return
            counter['last_saved']=time.monotonic();self._update(record,'receiving_response');self.h.store.put('interview_operation',item_id,record)

    def context(self,item_id,summary,*,acceptance_cases=None):
        with self.h.store.lock:
            record=self.h.store.get('interview_operation',item_id)
            if record and record.get('status')=='running':
                record['context_summary']=copy.deepcopy(summary)
                if acceptance_cases is not None:record['acceptance_cases']=copy.deepcopy(acceptance_cases)
                self.h.store.put('interview_operation',item_id,record)

    def _update(self,record,phase):
        counter=self.counts.get(record['id'])
        if counter:record.update(received_characters=counter['characters'],delta_count=counter['deltas'])
        record.update(phase=phase,updated_at=self.h.now())

    def phase(self,item_id,phase):
        with self.h.store.lock:
            if phase not in {'waiting_response','receiving_response'}:self.previews.pop(item_id,None)
            record=self.h.store.get('interview_operation',item_id)
            if record and record['status']=='running':self._update(record,phase);self.h.store.put('interview_operation',item_id,record)

    def finish(self,task,item_id,status,note):
        with self.h.store.lock:
            record=self.h.store.get('interview_operation',item_id)
            if record:
                self._update(record,'completed');record.update(status=status,note=note,completed_at=self.h.now(),result_revision=task['revision'],applied=status=='applied')
                task['updated_at']=self.h.now();self.h.store.put_many([('interview_operation',item_id,record),('task',task['id'],task)])
            else:self.h.save_task(task)
            self.counts.pop(item_id,None)
            self.previews.pop(item_id,None)
            return task

    def recover(self):
        with self.h.store.lock:
            for record in self.h.store.list('interview_operation'):
                if record.get('status')=='running':
                    record.update(status='interrupted',phase='completed',applied=False,note='服务重启时访谈结果未确认，保留需求与费用预留，不重新派发。',completed_at=self.h.now());self.h.store.put('interview_operation',record['id'],record)
            self.counts.clear()
            self.previews.clear()

    def public(self,record,task):
        value=copy.deepcopy(record);value.pop('message_preview',None)
        if record.get('task_id')==task['id'] and record.get('revision')==task['revision'] and task.get('active_interview_id')==record['id'] and task.get('status')=='interviewing' and record.get('status')=='running' and record.get('stream_requested') and record.get('phase') in {'waiting_response','receiving_response'}:
            preview=self.previews.get(record['id']);text=preview.value() if preview else None
            if text is not None:value['message_preview']=text
        return value

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/interviews')
        def read(item_id:str):
            with h.store.lock:
                task=h.get_task(item_id)
                return {'task_id':item_id,'revision':task['revision'],'active_operation_id':task.get('active_interview_id'),'operations':[self.public(r,task) for r in h.store.list('interview_operation') if r['task_id']==item_id],'note':'只读执行检查点；字符数不是token数、费用或业务完成度。接收中的正文预览仅在进程内存，尚未校验，不进入正式需求；不展示原始JSON、思考、提示词或凭据。'}
        @h.app.get('/api/tasks/{item_id}/interviews/{operation_id}')
        def detail(item_id:str,operation_id:str):
            with h.store.lock:
                task=h.get_task(item_id);record=h.store.get('interview_operation',operation_id)
                if not record or record['task_id']!=item_id:raise HTTPException(404,'访谈记录不属于当前任务，未读取其他来源。')
                return self.public(record,task)
