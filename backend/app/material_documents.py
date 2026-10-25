"""Text extraction with explicit scope; no OCR, password handling or execution."""


class DocumentInputError(ValueError):pass


class PartialDocument(DocumentInputError):
    def __init__(self,message,partial_text,coverage):
        super().__init__(message);self.partial_text=partial_text;self.coverage=coverage


def bounded(text):
    if len(text)>100000:raise DocumentInputError('文本超过当前10万字处理上限，请拆分；本次没有静默截断原文。')
    return text


def extract_pdf(path):
    from pypdf import PdfReader
    try:
        reader=PdfReader(path)
        if reader.is_encrypted:raise DocumentInputError('加密PDF暂不能解析，请在本机解除保护后重新上传；此处不索取或保存文件密码。')
        count=len(reader.pages)
        if count>100:raise DocumentInputError('当前PDF超过100页，请拆分。')
        if not count:raise DocumentInputError('PDF没有可读取页面，请核对原文件。')
        parts=[];unread=[];characters=0
        for number,page in enumerate(reader.pages,1):
            try:text=page.extract_text()
            except Exception:text=None
            if not isinstance(text,str) or not text.strip():unread.append(number);continue
            part=f'[第 {number} 页]\n{text}';characters+=len(part)+(1 if parts else 0)
            if characters>100000:raise DocumentInputError('文本超过当前10万字处理上限，请拆分；本次没有静默截断原文。')
            parts.append(part)
        text=bounded('\n'.join(parts))
        note=f'共{count}页，{count-len(unread)}页提取到文字。仅页面文字提取，不代表布局、图片、OCR或全部业务含义已读取。'
        coverage={'format':'pdf','total_pages':count,'unread_pages':unread,'scope_note':note,'verification':'page_text_extraction_only'}
        if unread:
            pages='、'.join(map(str,unread))
            message=f'PDF第{pages}页未提取到可读取文字，可能为空白、扫描页或提取失败。未接入OCR；请核对原页并补充文字或重新上传可读文件，不能把部分文字当完整材料。'
            coverage['scope_note']=note+f'第{pages}页未提取到文字，覆盖尚未确认。'
            raise PartialDocument(message,text,coverage)
        return text,coverage
    except DocumentInputError:raise
    except Exception:raise DocumentInputError('PDF文件解析失败，请检查损坏情况或重新导出可读取文本；未展示文件内部内容。') from None


def blocks(container):
    from docx.text.paragraph import Paragraph
    for block in container.iter_inner_content():
        if isinstance(block,Paragraph):yield block.text
        else:
            seen=set()
            for row in block.rows:
                cells=[]
                for cell in row.cells:
                    if cell._tc in seen:continue
                    seen.add(cell._tc);cells.append(bounded('\n'.join(blocks(cell))))
                if cells:yield bounded(' | '.join(cells))


def extract_docx(path):
    from docx import Document
    try:
        text=bounded('\n'.join(blocks(Document(path))))
        coverage={'format':'docx','scope_note':'仅提取Word主正文的段落及表格（含嵌套），按正文和单元格顺序；未读取页眉、页脚、脚注、文本框和图片，不保证布局、OCR或全部业务含义。','verification':'body_text_extraction_only'}
        return text,coverage
    except DocumentInputError:raise
    except Exception:raise DocumentInputError('Word文件解析失败，请检查损坏情况或转换为可读取文本；未展示文件内部内容。') from None
