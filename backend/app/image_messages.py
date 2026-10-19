"""Bounded embedded raster messages; no URL fetch, resize, OCR or image execution."""
import base64,binascii,copy,hashlib,re,struct

MAX_IMAGE_BYTES=1024*1024
MAX_IMAGE_EDGE=4096


def raster_info(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_IMAGE_BYTES:raise ValueError('首批图像须为1MB内的PNG／JPEG原文件；不会截断或自动压缩。')
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        if len(raw)<33 or raw[8:12]!=b'\x00\x00\x00\r' or raw[12:16]!=b'IHDR':raise ValueError('PNG图像头无效，未发送。')
        width,height=struct.unpack('>II',raw[16:24]);mime='image/png'
    elif raw.startswith(b'\xff\xd8'):
        pos=2;size=None
        while pos<len(raw):
            if raw[pos]!=255:break
            while pos<len(raw) and raw[pos]==255:pos+=1
            if pos>=len(raw):break
            marker=raw[pos];pos+=1
            if marker in {0xDA,0xD9}:break
            if marker==1 or 0xD0<=marker<=0xD7:continue
            if pos+2>len(raw):break
            length=int.from_bytes(raw[pos:pos+2],'big')
            if length<2 or pos+length>len(raw):break
            if marker in {0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF}:
                if length<8:break
                height,width=struct.unpack('>HH',raw[pos+3:pos+7]);size=(width,height);break
            pos+=length
        if size is None:raise ValueError('JPEG尺寸头无效或无法核对，未发送。')
        width,height=size;mime='image/jpeg'
    else:raise ValueError('首批只接收PNG／JPEG图像字节，不按扩展名假设格式，不支持SVG／GIF／WebP或PDF图像。')
    if not 1<=width<=MAX_IMAGE_EDGE or not 1<=height<=MAX_IMAGE_EDGE:raise ValueError('首批图像边长须为1—4096像素，请缩小或拆分；不会自动裁切。')
    return {'mime_type':mime,'width':width,'height':height,'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'verification':'raster_header_only_not_pixel_decode_or_ocr'}


def image_part(raw,detail='auto'):
    if detail not in {'auto','low','high','original'}:raise ValueError('图像detail未适配，不会切换为默认值。')
    info=raster_info(raw)
    return {'type':'image_url','image_url':{'url':'data:'+info['mime_type']+';base64,'+base64.b64encode(raw).decode('ascii'),'detail':detail}}


def embedded_image(value):
    if not isinstance(value,str) or len(value)>4*((MAX_IMAGE_BYTES+2)//3)+40:raise ValueError('图像引用不是受限内嵌数据，未发送。')
    matched=re.fullmatch(r'data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/]+={0,2})',value)
    if not matched:raise ValueError('图像须为PNG／JPEG内嵌base64；远程URL／file_id／任意文件来源尚未适配，不会抓取或悄悄删除图片。')
    try:raw=base64.b64decode(matched[2],validate=True)
    except (ValueError,binascii.Error):raise ValueError('图像base64无效，未发送。') from None
    info=raster_info(raw)
    if info['mime_type']!=matched[1]:raise ValueError('图像字节与声明格式不符，未发送。')
    return info,matched[2]


def prepare_messages(messages,protocol,*,allow_images=False):
    if all(isinstance(m,dict) and isinstance(m.get('content'),str) for m in messages):return copy.deepcopy(messages)
    if protocol not in {'openai-compatible','anthropic'}:raise ValueError('图像消息协议尚未适配，不退回文字调用。')
    result=[];images=0
    for message in messages:
        if not isinstance(message,dict) or set(message)!={'role','content'} or message['role'] not in {'system','user','assistant'}:raise ValueError('图文消息只支持明确system／user／assistant与content，不忽略额外字段。')
        value=message['content']
        if isinstance(value,str):result.append(copy.deepcopy(message));continue
        if message['role']!='user' or not isinstance(value,list) or not 1<=len(value)<=8:raise ValueError('图像只放在1—8段明确user内容中，不把系统规则当图像或忽略无效内容。')
        parts=[]
        for part in value:
            if not isinstance(part,dict):raise ValueError('图文内容段格式无效，未发送。')
            if part.get('type')=='text' and set(part)=={'type','text'} and isinstance(part['text'],str):parts.append(copy.deepcopy(part));continue
            if part.get('type')!='image_url' or set(part)!={'type','image_url'} or not isinstance(part['image_url'],dict):raise ValueError('仅支持text与内嵌image_url段，未知输入不转换或丢弃。')
            if allow_images is not True:raise ValueError('图像须经明确出站预览和确认入口派发，普通文字操作不会隐式发送图片。')
            image=part['image_url']
            if set(image)-{'url','detail'} or 'url' not in image:raise ValueError('图像引用含未适配字段，未发送。')
            detail=image.get('detail','auto')
            if detail not in {'auto','low','high','original'}:raise ValueError('图像detail未适配，未发送。')
            info,data=embedded_image(image['url']);images+=1
            if images>1:raise ValueError('首批一次只发送1张图像，不省略其余图像或合并任务。')
            if protocol=='anthropic':
                if detail!='auto':raise ValueError('Anthropic首批只支持原生自动图像处理，不能静默忽略OpenAI专用detail控制。')
                parts.append({'type':'image','source':{'type':'base64','media_type':info['mime_type'],'data':data}})
            else:parts.append(copy.deepcopy(part))
        result.append({'role':message['role'],'content':parts})
    return result
