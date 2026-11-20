"""Pure parsers for the Dify 1.17.1 dataset page protocols.

Only a complete page one is accepted. Nothing is fetched here, a missing field is
never treated as completeness, and every rejection is a fixed ASCII reason that
never echoes page content.
"""
from common import uuid


def _page(value,limit,label):
    if not isinstance(value,dict):raise RuntimeError(label+' page is not an object')
    if type(value.get('page')) is not int or value['page']!=1:raise RuntimeError(label+' page number invalid')
    if type(value.get('limit')) is not int or value['limit']!=limit:raise RuntimeError(label+' limit mismatch')
    rows=value.get('data')
    if not isinstance(rows,list) or not rows:raise RuntimeError(label+' rows missing')
    for row in rows:
        if not isinstance(row,dict):raise RuntimeError(label+' row malformed')
        if not uuid(row.get('id')):raise RuntimeError(label+' id invalid')
    ids=[row['id'] for row in rows]
    if len(set(ids))!=len(ids):raise RuntimeError(label+' id duplicated')
    if len(rows)>limit:raise RuntimeError(label+' rows exceed limit')
    total=value.get('total')
    if type(total) is not int or total<=0:raise RuntimeError(label+' total invalid')
    if total!=len(rows):raise RuntimeError(label+' total inconsistent')
    return rows


def document_page(value,limit=2):
    """Return every row of a complete document page one, else a fixed RuntimeError."""
    rows=_page(value,limit,'FAQ document')
    more=value.get('has_more')
    if type(more) is not bool:raise RuntimeError('FAQ document has_more invalid')
    if more!=(len(rows)==limit):raise RuntimeError('FAQ document has_more inconsistent')
    return rows


def segment_page(value,limit=20):
    """Return every row of a complete segment page one, else a fixed RuntimeError."""
    if isinstance(value,dict) and 'has_more' in value:raise RuntimeError('FAQ segment protocol unknown')
    rows=_page(value,limit,'FAQ segment')
    pages=value.get('total_pages')
    if type(pages) is not int or pages!=1:raise RuntimeError('FAQ segment total_pages invalid')
    return rows
