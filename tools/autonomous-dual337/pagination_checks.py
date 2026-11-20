"""Public acceptance for the Dify 1.17.1 FAQ page protocols and safe failure location.

No product backend, Store, production data or network; both httpx transports are
patched to forbidden and counted so any physical attempt fails the check.
"""
import json
import sys
from pathlib import Path
from uuid import UUID

import httpx

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))

from common import require
from pagination import document_page,segment_page
from worker import SAFE_FRAMES,failure_location


def document_row(number):
    return {'id':str(UUID(int=number)),'indexing_status':'completed','name':'公开政策'}

def segment_row(number):
    return {'id':str(UUID(int=number)),'content':'公开资料','status':'completed','enabled':True}

def document(rows,has_more,total,page=1,limit=2):
    return {'data':rows,'has_more':has_more,'total':total,'page':page,'limit':limit}

def segments(rows,total,page=1,limit=20,total_pages=1):
    return {'data':rows,'total':total,'total_pages':total_pages,'page':page,'limit':limit}

def accepted(fn,count):
    rows=fn()
    require(isinstance(rows,list) and len(rows)==count,'parser did not return the complete rows')
    return rows

def rejected(fn,text):
    try:fn()
    except RuntimeError as exc:
        require(text in str(exc),'wrong rejection: '+str(exc));return exc
    raise AssertionError('expected RuntimeError: '+text)


def checks():
    passed=0
    # Real documents shape: a short complete page says false; an exactly full page may say true.
    accepted(lambda:document_page(document([document_row(1)],False,1)),1);passed+=1
    accepted(lambda:document_page(document([document_row(1),document_row(2)],True,2)),2);passed+=1
    rejected(lambda:document_page(document([document_row(1),document_row(2),document_row(3)],True,3)),'FAQ document rows exceed limit');passed+=1
    rejected(lambda:document_page(document([document_row(1),document_row(2)],False,2)),'FAQ document has_more inconsistent');passed+=1
    rejected(lambda:document_page(document([document_row(1)],True,1)),'FAQ document has_more inconsistent');passed+=1
    value=document([document_row(1)],False,1);del value['total']
    rejected(lambda:document_page(value),'FAQ document total invalid');passed+=1
    rejected(lambda:document_page(document([document_row(1)],False,2)),'FAQ document total inconsistent');passed+=1
    rejected(lambda:document_page(document([document_row(1)],False,True)),'FAQ document total invalid');passed+=1
    rejected(lambda:document_page(document([document_row(1)],False,-1)),'FAQ document total invalid');passed+=1
    rejected(lambda:document_page(document([document_row(1)],False,1.0)),'FAQ document total invalid');passed+=1
    rejected(lambda:document_page(document([document_row(1)],False,1,page=2)),'FAQ document page number invalid');passed+=1
    rejected(lambda:document_page(document([document_row(1)],False,1,page=True)),'FAQ document page number invalid');passed+=1
    rejected(lambda:document_page(document([document_row(1)],False,1,limit=1)),'FAQ document limit mismatch');passed+=1
    rejected(lambda:document_page(document([{'id':'not-a-uuid'}],False,1)),'FAQ document id invalid');passed+=1
    rejected(lambda:document_page(document([document_row(1),document_row(1)],True,2)),'FAQ document id duplicated');passed+=1
    rejected(lambda:document_page(document(['not-an-object'],False,1)),'FAQ document row malformed');passed+=1
    rejected(lambda:document_page(document([],False,0)),'FAQ document rows missing');passed+=1
    rejected(lambda:document_page([]),'FAQ document page is not an object');passed+=1
    rejected(lambda:document_page(document([document_row(1)],0,1)),'FAQ document has_more invalid');passed+=1
    # Real segments shape: no has_more, total_pages must be the single complete page.
    accepted(lambda:segment_page(segments([segment_row(1)],1)),1);passed+=1
    accepted(lambda:segment_page(segments([segment_row(i) for i in range(1,21)],20)),20);passed+=1
    rejected(lambda:segment_page(segments([segment_row(i) for i in range(1,22)],21)),'FAQ segment rows exceed limit');passed+=1
    rejected(lambda:segment_page(segments([segment_row(1),segment_row(2)],1)),'FAQ segment total inconsistent');passed+=1
    rejected(lambda:segment_page(segments([segment_row(1)],21)),'FAQ segment total inconsistent');passed+=1
    rejected(lambda:segment_page(segments([segment_row(1)],1,total_pages=2)),'FAQ segment total_pages invalid');passed+=1
    value=segments([segment_row(1)],1);del value['total_pages']
    rejected(lambda:segment_page(value),'FAQ segment total_pages invalid');passed+=1
    value=segments([segment_row(1)],1);value['has_more']=False
    rejected(lambda:segment_page(value),'FAQ segment protocol unknown');passed+=1
    rejected(lambda:segment_page(segments([segment_row(1),segment_row(1)],2)),'FAQ segment id duplicated');passed+=1
    rejected(lambda:segment_page(segments([{'id':'not-a-uuid'}],1)),'FAQ segment id invalid');passed+=1
    rejected(lambda:segment_page(segments([segment_row(1)],1,page=2)),'FAQ segment page number invalid');passed+=1
    rejected(lambda:segment_page(segments([segment_row(1)],1,limit=10)),'FAQ segment limit mismatch');passed+=1
    # Failure location may only carry whitelisted package frames and never the input or message.
    secret='SENSITIVE-PUBLIC-PROBE-7f3a9c'
    exc=rejected(lambda:document_page({'data':[{'id':secret}],'has_more':False,'total':1,'page':1,'limit':2}),'FAQ document id invalid')
    location=failure_location(exc,HERE)
    require(location,'package frame location missing')
    require(len(location)<=8,'too many failure frames')
    require(all(set(frame)=={'file','function','line'} and frame['file'] in SAFE_FRAMES and isinstance(frame['function'],str) and type(frame['line']) is int for frame in location),'unsafe failure frame')
    require(all(frame['file']!='pagination_checks.py' for frame in location),'non-package frame recorded')
    require(secret not in json.dumps(location) and 'SENSITIVE' not in json.dumps(location),'failure location echoed exception input')
    passed+=1
    def raised(message):
        try:raise RuntimeError(message)
        except RuntimeError as exc:return exc
    location=failure_location(raised(secret),HERE)
    require(location==[],'non-package frame must be excluded')
    require(secret not in json.dumps(location),'failure location echoed the exception message')
    passed+=1
    return passed


def main():
    physical=[0]
    def forbidden_request(self,request):
        physical[0]+=1;raise AssertionError('physical HTTP is forbidden in pagination checks')
    async def forbidden_async(self,request):
        physical[0]+=1;raise AssertionError('physical HTTP is forbidden in pagination checks')
    original=(httpx.HTTPTransport.handle_request,httpx.AsyncHTTPTransport.handle_async_request)
    httpx.HTTPTransport.handle_request=forbidden_request
    httpx.AsyncHTTPTransport.handle_async_request=forbidden_async
    try:
        passed=checks()
        require(physical[0]==0,'a physical transport was used')
        print('passed',passed);print('physical_http0')
    finally:
        httpx.HTTPTransport.handle_request,httpx.AsyncHTTPTransport.handle_async_request=original


if __name__=='__main__':main()
