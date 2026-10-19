import asyncio,base64,copy,json,struct,zlib,sys
from pathlib import Path
import httpx,pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.image_messages import raster_info,image_part,prepare_messages,embedded_image
from app import providers


def png(width=1,height=1):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\0\1\2'))+chunk(b'IEND',b'')


def messages(detail='auto'):
    return [{'role':'system','content':'仅提取可见内容，不编造缺失信息。'},{'role':'user','content':[image_part(png(),detail),{'type':'text','text':'这是本机隔离图像样例。'}]}]


def test_embedded_raster_header_binding_and_input_unchanged():
    value=messages();before=copy.deepcopy(value);info,data=embedded_image(value[1]['content'][0]['image_url']['url'])
    assert info['mime_type']=='image/png' and info['width']==1 and info['height']==1
    assert info['verification']=='raster_header_only_not_pixel_decode_or_ocr'
    assert base64.b64decode(data)==png()
    assert prepare_messages(value,'openai-compatible',allow_images=True)==before and value==before


def test_anthropic_uses_base64_source_and_keeps_text_order_without_precision_coercion():
    value=messages();result=prepare_messages(value,'anthropic',allow_images=True)
    assert result[0]==value[0] and result[1]['content'][0]['type']=='image'
    source=result[1]['content'][0]['source'];assert source['type']=='base64' and source['media_type']=='image/png'
    assert base64.b64decode(source['data'])==png() and result[1]['content'][1]==value[1]['content'][1]
    with pytest.raises(ValueError,match='不能静默忽略'):prepare_messages(messages('high'),'anthropic',allow_images=True)


@pytest.mark.parametrize('uri',['https://private.example/picture.png','file:///E:/private.png','data:image/svg+xml;base64,AAAA','data:image/png;base64,broken','data:image/jpeg;base64,'+base64.b64encode(png()).decode()])
def test_remote_file_or_invalid_image_is_rejected_without_fetch_or_drop(uri):
    value=messages();value[1]['content'][0]['image_url']['url']=uri
    with pytest.raises(ValueError):prepare_messages(value,'openai-compatible',allow_images=True)


def test_size_dimensions_multiple_images_and_system_images_are_explicitly_rejected():
    with pytest.raises(ValueError,match='边长'):image_part(png(4097,1))
    with pytest.raises(ValueError,match='1MB'):raster_info(b'x'*(1024*1024+1))
    with pytest.raises(ValueError,match='PNG／JPEG'):raster_info(b'<svg/>')
    value=messages();value[1]['content'].append(image_part(png()))
    with pytest.raises(ValueError,match='1张'):prepare_messages(value,'openai-compatible',allow_images=True)
    value=messages();value[1]['role']='system'
    with pytest.raises(ValueError,match='user'):prepare_messages(value,'openai-compatible',allow_images=True)


def test_unknown_fields_and_no_explicit_image_dispatch_cannot_be_silently_normalized():
    with pytest.raises(ValueError,match='出站预览'):prepare_messages(messages(),'openai-compatible')
    value=messages();value[1]['content'][0]['image_url']['unknown']=True
    with pytest.raises(ValueError,match='未适配字段'):prepare_messages(value,'openai-compatible',allow_images=True)
    legacy=[{'role':'system','content':'原文字规则'},{'role':'user','content':'原文字'}]
    assert prepare_messages(legacy,'anthropic')==legacy


@pytest.mark.parametrize('protocol',['openai-compatible','anthropic'])
def test_provider_transport_preserves_actual_image_and_usage_with_controlled_http(protocol,monkeypatch):
    captured=[]
    class Controlled:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,headers,json):
            captured.append(json)
            body={'content':[{'type':'text','text':'隔离响应'}],'usage':{'input_tokens':10,'output_tokens':4}} if protocol=='anthropic' else {'choices':[{'message':{'content':'隔离响应'},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':4}}
            return httpx.Response(200,json=body,request=httpx.Request('POST',url))
    monkeypatch.setattr(providers.httpx,'AsyncClient',Controlled)
    provider={'model':'fixture-model','provider':'custom','protocol':protocol,'base_url':'https://example.test/v1'}
    text,usage=asyncio.run(providers.call_model(provider,'test-only',messages(),allow_images=True))
    assert text=='隔离响应' and usage and len(captured)==1
    part=captured[0]['messages'][-1]['content'][0]
    assert part['type']==('image' if protocol=='anthropic' else 'image_url')
    captured.clear()
    with pytest.raises(providers.ProviderError,match='出站预览'):
        asyncio.run(providers.call_model(provider,'test-only',messages()))
    assert captured==[]
