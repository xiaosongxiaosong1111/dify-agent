"""Bounded, volatile first-field JSON message preview. Never a business result."""
import re

HEADER=re.compile(r'^[ \t\r\n]*\{[ \t\r\n]*"message"[ \t\r\n]*:[ \t\r\n]*"$')
HEX=set('0123456789abcdefABCDEF')
ESCAPES={'"':'"','\\':'\\','/':'/','n':'\n','r':'\r','t':'\t'}
MAX_PREVIEW=16000


class MessagePreview:
    def __init__(self):
        self.header='';self.state='header';self.characters=[];self.digits='';self.high=None;self.valid=True

    def reject(self):
        self.valid=False;self.state='rejected';self.header='';self.characters.clear();self.digits='';self.high=None

    def append(self,char):
        if len(self.characters)>=MAX_PREVIEW or ord(char)<32 and char not in '\n\r\t' or 0xD800<=ord(char)<=0xDFFF:self.reject();return
        self.characters.append(char)

    def feed(self,text):
        if not isinstance(text,str):self.reject();return
        for char in text:
            if self.state in {'rejected','done'}:return
            if self.state=='header':
                self.header+=char
                if len(self.header)>1024:self.reject()
                elif HEADER.fullmatch(self.header):self.state='text';self.header=''
            elif self.state=='text':
                if char=='"':self.state='done'
                elif char=='\\':self.state='escape'
                elif ord(char)<32:self.reject()
                else:self.append(char)
            elif self.state=='escape':
                if char=='u':self.state='unicode';self.digits=''
                elif char in ESCAPES:self.state='text';self.append(ESCAPES[char])
                else:self.reject()
            elif self.state=='low_slash':
                if char=='\\':self.state='low_u'
                else:self.reject()
            elif self.state=='low_u':
                if char=='u':self.state='unicode';self.digits=''
                else:self.reject()
            elif self.state=='unicode':
                if char not in HEX:self.reject();continue
                self.digits+=char
                if len(self.digits)!=4:continue
                value=int(self.digits,16);self.digits=''
                if self.high is not None:
                    if not 0xDC00<=value<=0xDFFF:self.reject();continue
                    result=chr(0x10000+((self.high-0xD800)<<10)+value-0xDC00);self.high=None;self.state='text';self.append(result)
                elif 0xD800<=value<=0xDBFF:self.high=value;self.state='low_slash'
                elif 0xDC00<=value<=0xDFFF:self.reject()
                else:self.state='text';self.append(chr(value))

    def value(self):return ''.join(self.characters) if self.valid and self.state!='header' else None
