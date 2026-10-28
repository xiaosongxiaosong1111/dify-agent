"""Reuse actual saved sources only; neither a new model call nor live authorization."""
from guard import require,digest


def inherited(plan,task,project):
    from audit import audit
    require(task['id']==plan['target_task_id'] and task['revision']==13 and digest(task)==plan['protected_data']['objects']['task:'+task['id']],'Saved source changed before admission')
    proof=audit()
    return {'from_batch':'c1-planning365','original_sha256':proof['comparison']['original_sha256'],
            'candidate_sha256':proof['comparison']['candidate_sha256'],'two_literal_locations_only':True,
            'new_model_call':False,'human_signoff':False,'resource_authorized':False}
