"""Validate all statically read plan fields and three live identities before any actions."""
import ast,json,re
from pathlib import Path
KEYS=('intake_messages_sha256','plan_first_system_sha256','plan_changed_system_sha256')
def verify_identity_fields(root):
 root=Path(root)
 try:
  plan=json.loads((root/'plan.json').read_text('utf-8'));required=set(KEYS)
  for name in ('server.py','guards.py'):
   for node in ast.walk(ast.parse((root/name).read_text('utf-8'))):
    if isinstance(node,ast.Subscript) and isinstance(node.slice,ast.Constant) and isinstance(node.slice.value,str):
     value=node.value
     if isinstance(value,ast.Name) and value.id=='plan' or isinstance(value,ast.Attribute) and value.attr=='plan' and isinstance(value.value,ast.Name) and value.value.id=='self':required.add(node.slice.value)
  if not isinstance(plan,dict) or not required<=plan.keys():raise ValueError('missing required plan fields')
  if any(not isinstance(plan[k],str) or not re.fullmatch('[a-f0-9]{64}',plan[k]) for k in KEYS):raise ValueError('invalid message identity')
  return {k:plan[k] for k in KEYS}
 except (ValueError,TypeError,OSError,SyntaxError) as exc:raise SystemExit('Frozen plan identity preflight refused before Store, budget, receipt or network: '+str(exc)) from None
if __name__=='__main__':
 import sys
 verify_identity_fields(Path(sys.argv[1]).resolve() if len(sys.argv)==2 else Path(__file__).resolve().parent)
 print('Frozen plan identities and required fields valid; no Store/network')
