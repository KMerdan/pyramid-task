"""Frozen-P4 loaded-record and ledger observations; no field normalization."""
import base64,copy,json
from pathlib import Path
from query_modularization_support import run_queries
from runtime_modularization_support import encoded

def run_history(api,root):
    import pyramid_history as history
    inherited=run_queries(api,root/'inherited')
    records=[];snapshot={};cases=[]
    meta=root/'inherited/inherited/inherited/legacy/.pyramid'
    actual=history._records(meta)
    if not actual:raise ValueError(('Missing independent history fixture',meta))
    for record in actual:
        cases.append(copy.deepcopy(record));bad=copy.deepcopy(record);bad['unknown']=True;cases.append(bad)
        for key in ['schema','record_id','record_type','recorded_at','recorded_by','plan_id']:
            bad=copy.deepcopy(record);bad.pop(key,None);cases.append(bad)
    cases += [None,[],{},dict(schema='invalid',record_type='code-binding')]
    for i,case in enumerate(cases):records.append(dict(label='history-contract-'+str(i),value_json=encoded(history._record_validation_errors(case)),error=None,expected_error=False))
    for i,case in enumerate([None,[],{},dict(schema='invalid'),dict(record=actual[0])]):records.append(dict(label='history-transaction-'+str(i),value_json=encoded(history._transaction_validation_errors(case)),error=None,expected_error=False))
    for i,case in enumerate([[],actual,list(reversed(actual)),actual+[actual[0]]]):records.append(dict(label='history-links-'+str(i),value_json=encoded(history._record_link_errors(case)),error=None,expected_error=False))
    for kwargs in [{},dict(path='source.txt'),dict(commit='missing'),dict(intent=actual[0]['plan_id']),dict(replay=actual[0]['plan_id']),dict(replay='missing')]:
        try:value=history.query_history(meta,**kwargs);records.append(dict(label='history-query-'+str(kwargs),value_json=encoded(value),error=None,expected_error=False))
        except Exception as e:records.append(dict(label='history-query-'+str(kwargs),value_json=None,error=dict(type=type(e).__name__,message=str(e)),expected_error=kwargs==dict(replay='missing')))
    for p in sorted(meta.rglob('*')):
        if p.is_file():snapshot[p.relative_to(meta).as_posix()]=base64.b64encode(p.read_bytes()).decode()
    return dict(inherited=inherited,rule_cases=cases,caller_observations=records,snapshots={'ledger':snapshot},core_clock_calls=0,datetime_calls=0,clock_trace=[])
