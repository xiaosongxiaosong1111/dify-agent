"""Consume real unread HTTPX body before observation; no retry."""
async def dispatch(boundary,forward,request):
 response=None
 try:
  entry=boundary.admit(request);boundary.persist()
  response=await forward(request)
  # Native transports return an unread response before AsyncClient attaches its request.
  # Observation needs both the full JSON body and request context for Cookie parsing.
  response.request=request;entry['status']=response.status_code;entry['response_body_read']=False;boundary.persist()
  await response.aread();entry['response_body_read']=True
  return boundary.observed(entry,response)
 except BaseException:
  boundary.halted=True
  if response is not None:
   try:await response.aclose()
   except Exception:pass
  raise
 finally:boundary.persist()

