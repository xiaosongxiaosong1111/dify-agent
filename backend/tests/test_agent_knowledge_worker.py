import copy
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from app.agent_knowledge_preservation import project

PROMPT = '请基于已选知识生成检索计划'
DID = re.compile(r'[A-Za-z0-9_-]{1,128}')
KEYS = {'name', 'description', 'dataset_ids', 'query_mode', 'top_k'}
O = object()


def ds(i, name=O, desc=O, **kw):
    d = {'id': i}
    if name is not O:
        d['name'] = name
    if desc is not O:
        d['description'] = desc
    d.update(kw)
    return d


def st(sid='set_a', name='政策', desc='公开政策知识', ids=None, datasets=None,
       top_k=3, query=None, retrieval=None, meta=O):
    if datasets is None:
        datasets = [ds(x) for x in (ids or ['kb_a'])]
    if query is None:
        query = {'mode': 'generated_query', 'value': None}
    if retrieval is None:
        retrieval = {'mode': 'multiple', 'top_k': top_k,
                     'reranking_enable': False,
                     'reranking_mode': 'reranking_model',
                     'score_threshold': None}
    s = {'id': sid, 'name': name, 'description': desc,
         'datasets': copy.deepcopy(datasets), 'query': copy.deepcopy(query),
         'retrieval': copy.deepcopy(retrieval)}
    if meta is not O:
        s['metadata_filtering'] = copy.deepcopy(meta)
    return s


def case(*sets):
    return {'sets': [copy.deepcopy(s) for s in sets]}


def check(plan, union=None):
    assert isinstance(plan, list) and 1 <= len(plan) <= 5
    names, got = set(), set()
    for e in plan:
        assert isinstance(e, dict) and set(e) == KEYS
        n = e['name']
        assert isinstance(n, str) and 1 <= len(n) <= 100
        k = n.casefold()
        assert k not in names
        names.add(k)
        d = e['description']
        assert isinstance(d, str) and 1 <= len(d) <= 2000
        ids = e['dataset_ids']
        assert isinstance(ids, list) and 1 <= len(ids) <= 20
        assert len(set(ids)) == len(ids)
        for i in ids:
            assert isinstance(i, str) and DID.fullmatch(i)
            got.add(i)
        assert e['query_mode'] == 'generated_query'
        t = e['top_k']
        assert isinstance(t, int) and not isinstance(t, bool)
        assert 1 <= t <= 20
    if union is not None:
        assert got == set(union)


def test_both_empty_returns_empty_plan():
    assert project({'sets': []}, {'sets': []}, PROMPT) == []


def test_selected_empty_but_knowledge_not_empty_rejected():
    with pytest.raises(ValueError):
        project(case(st()), {'sets': []}, PROMPT)


def test_selected_not_empty_but_knowledge_empty_rejected():
    with pytest.raises(ValueError):
        project({'sets': []}, case(st(sid='sel', name='已选政策')), PROMPT)


def test_extra_current_resource_rejected_without_filtering():
    knowledge = case(st(name='全量政策', ids=['kb_a', 'kb_b', 'kb_c']))
    selected = case(st(sid='sel', name='已选政策', ids=['kb_b', 'kb_c']))
    with pytest.raises(ValueError):
        project(knowledge, selected, PROMPT)


def test_missing_current_resource_rejected_without_insertion():
    knowledge = case(st(name='已有知识', ids=['kb_a']))
    selected = case(st(sid='sel', name='新增选择', ids=['kb_a', 'kb_new']))
    with pytest.raises(ValueError):
        project(knowledge, selected, PROMPT)


def test_same_dataset_name_does_not_authorize_other_id():
    picked = [ds('kb_dup_1', name='同名库'), ds('kb_dup_2', name='同名库')]
    knowledge = case(st(name='全量知识', datasets=picked + [ds('kb_x', name='同名库')]))
    selected = case(st(sid='sel', name='已选知识', datasets=picked))
    with pytest.raises(ValueError):
        project(knowledge, selected, PROMPT)


def test_dataset_may_span_groups_and_union_dedups():
    a = st(sid='set_a', name='政策', datasets=[ds('kb_shared'), ds('kb_a')])
    b = st(sid='set_b', name='法规', datasets=[ds('kb_shared'), ds('kb_b')])
    check(project(case(a, b), case(a, b), PROMPT), {'kb_shared', 'kb_a', 'kb_b'})


def test_unicode_names_and_null_dataset_metadata():
    picked = [ds('kb_u1', name='公共政策📚', desc=None),
              ds('kb_u2', name=None, desc='公开说明')]
    selected = case(st(sid='sel', name='政策与法规🌐',
                       desc='中文、Ελληνικά、emoji 😀', datasets=picked))
    knowledge = copy.deepcopy(selected)
    check(project(knowledge, selected, PROMPT), {'kb_u1', 'kb_u2'})


@pytest.mark.parametrize('query,meta', [
    ({'mode': 'generated_query'}, O),
    ({'mode': 'generated_query', 'value': None}, {'mode': 'disabled'}),
    ({'mode': 'generated_query'}, {'conditions': None}),
    ({'mode': 'generated_query', 'value': None},
     {'mode': 'disabled', 'model_config': None,
      'metadata_model_config': None, 'conditions': None}),
], ids=['omit_all', 'null_and_disabled', 'mode_omitted', 'disabled_nulls'])
def test_query_and_metadata_defaults(query, meta):
    selected = case(st(sid='sel', name='已选政策', query=query, meta=meta))
    check(project(selected, case(st(name='全量知识')), PROMPT), {'kb_a'})


@pytest.mark.parametrize('bad', [
    {'mode': 'semantic_search', 'value': None},
    {'mode': 'generated_query', 'value': '关键词'},
    {'mode': 'generated_query', 'value': []},
    {'mode': 'generated_query', 'value': False},
    {'mode': 'generated_query', 'value': None, 'extra': 1},
], ids=['wrong_mode', 'text', 'list', 'bool', 'unknown'])
def test_invalid_query_rejected(bad):
    with pytest.raises(ValueError):
        project(case(st(sid='sel', name='已选政策', query=bad)), case(st()), PROMPT)


@pytest.mark.parametrize('kind', [
    'mode_single', 'mode_missing', 'enable_true', 'enable_none',
    'enable_missing', 'rerank_weighted', 'rerank_empty', 'unknown',
], ids=['single', 'no_mode', 'true', 'none', 'enable_absent',
        'weighted', 'rerank_blank', 'extra_field'])
def test_invalid_retrieval_rejected(kind):
    s = st(sid='sel', name='已选政策')
    r = s['retrieval']
    if kind == 'mode_single':
        r['mode'] = 'single'
    elif kind == 'mode_missing':
        del r['mode']
    elif kind == 'enable_true':
        r['reranking_enable'] = True
    elif kind == 'enable_none':
        r['reranking_enable'] = None
    elif kind == 'enable_missing':
        del r['reranking_enable']
    elif kind == 'rerank_weighted':
        r['reranking_mode'] = 'weighted_score'
    elif kind == 'rerank_empty':
        r['reranking_mode'] = ''
    else:
        r['unknown'] = 'x'
    with pytest.raises(ValueError):
        project(case(s), case(st()), PROMPT)


@pytest.mark.parametrize('meta', [
    {'mode': 'enabled'},
    {'mode': None},
    {'unknown': 1},
    {'conditions': []},
    {'mode': 'disabled', 'conditions': {'k': 1}},
], ids=['enabled', 'mode_null', 'unknown', 'list_conditions', 'nonnull_cond'])
def test_invalid_metadata_filtering_rejected(meta):
    with pytest.raises(ValueError):
        project(case(st(sid='sel', name='已选政策', meta=meta)), case(st()), PROMPT)


@pytest.mark.parametrize('where', ['dataset', 'set'], ids=['dataset', 'set'])
def test_unknown_fields_rejected(where):
    s = st(sid='sel', name='已选政策')
    if where == 'dataset':
        s['datasets'] = [ds('kb_a', extra=1)]
    else:
        s['extra'] = 1
    with pytest.raises(ValueError):
        project(case(s), case(st()), PROMPT)


@pytest.mark.parametrize('bad_k', [True, False, 0, 21, '3', 3.0],
                         ids=['true', 'false', 'zero', 'too_big', 'str', 'float'])
def test_invalid_top_k_rejected(bad_k):
    with pytest.raises(ValueError):
        project(case(st(sid='sel', name='已选政策', top_k=bad_k)), case(st()), PROMPT)


@pytest.mark.parametrize('k', [1, 20], ids=['min', 'max'])
def test_top_k_bounds_accepted(k):
    check(project(case(st(sid='sel', name='已选政策', top_k=k)), case(st()), PROMPT),
          {'kb_a'})


def test_inputs_are_not_mutated():
    knowledge = case(st(name='全量知识', ids=['kb_b']))
    selected = case(st(sid='sel', name='已选政策', ids=['kb_b']))
    k_before, s_before = copy.deepcopy(knowledge), copy.deepcopy(selected)
    check(project(knowledge, selected, PROMPT), {'kb_b'})
    assert knowledge == k_before
    assert selected == s_before
