"""Frozen-P4 assurance/ordered-plan corpus and explicit I/O observations."""
import base64,copy,json
from pathlib import Path
from unittest import mock
from history_modularization_support import run_history
from plan_validation_support import validation_cases
from runtime_modularization_support import encoded

def run_assurance(api,root):
    import pyramid_assurance as assurance
    inherited=run_history(api,root/'inherited');records=[];cases=[];trace=[]
    assets=Path(api.__file__).resolve().parents[1]/'assets';plan=json.loads((assets/'example-plan.json').read_text());baseline=json.loads((assets/'example-baseline.json').read_text());bundle=json.loads((assets/'example-assurance.json').read_text())
    def observe(label,fn,error=False):
        try:records.append(dict(label=label,value_json=encoded(fn()),error=None,expected_error=error))
        except Exception as e:records.append(dict(label=label,value_json=None,error=dict(type=type(e).__name__,message=str(e)),expected_error=error))
    for label,value in validation_cases().items():
        cases.append(label);observe('plan-'+label,lambda value=value:api.validate_plan(copy.deepcopy(value)),error=label=='malformed-edge-exception')
    for name,base,fn in [('baseline',baseline,assurance.validate_baseline),('assurance',bundle,lambda value:assurance.validate_assurance(value,plan=plan,baseline=baseline))]:
        observe(name+'-valid',lambda base=base,fn=fn:fn(copy.deepcopy(base)))
        for key in base:
            value=copy.deepcopy(base);value.pop(key);cases.append(name+'-missing-'+key);observe(cases[-1],lambda value=value,fn=fn:fn(value))
        for key in ['assets','relations','history'] if name=='baseline' else ['impacts','inspections','findings','scope_drift','controls','legacy_bridge']:
            for replacement in [None,[],{},'invalid']:
                value=copy.deepcopy(base);value[key]=replacement;cases.append(name+'-'+key+'-'+encoded(replacement));observe(cases[-1],lambda value=value,fn=fn:fn(value))
        if name=='baseline':
            for field in ['id','kind','locators','confidence','criticality']:
                value=copy.deepcopy(base);value['assets'][0][field]=None;cases.append(name+'-asset-'+field);observe(cases[-1],lambda value=value,fn=fn:fn(value))
        else:
            for field in ['id','status','result','sufficiency','refresh_policy','invalidated_by','asset_ids','task_ids']:
                value=copy.deepcopy(base);value['inspections'][0][field]=None;cases.append(name+'-inspection-'+field);observe(cases[-1],lambda value=value,fn=fn:fn(value))
    def clock():trace.append('clock');return '2026-10-10T00:00:00Z'
    with mock.patch.object(assurance,'utc_now',side_effect=clock):
        observe('default-manifest',lambda:assurance.default_project_manifest(plan_id='OWNED',mode='greenfield',actor='owner'))
        observe('default-manifest-explicit',lambda:assurance.default_project_manifest(plan_id='OWNED',mode='greenfield',actor='owner',created_at='explicit'))
        observe('default-baseline',lambda:assurance.default_baseline(actor='owner'))
        observe('default-assurance',lambda:assurance.default_assurance(plan_id='OWNED',baseline=baseline,actor='owner'))
        observe('default-missing-baseline',lambda:assurance.default_assurance(plan_id='OWNED',baseline={},actor='owner'),True)
        changed=copy.deepcopy(bundle);assurance.mark_assurance_stale(changed,'owned','owner');records.append(dict(label='stale-result',value_json=encoded(changed),error=None,expected_error=False))
    changed=copy.deepcopy(bundle)
    def fail_clock():trace.append(encoded(changed));raise OSError('owned clock fault')
    with mock.patch.object(assurance,'utc_now',side_effect=fail_clock):observe('stale-clock-failure',lambda:assurance.mark_assurance_stale(changed,'owned','owner'),True)
    records.append(dict(label='stale-after-failure',value_json=encoded(changed),error=None,expected_error=False))
    project=root/'footprint';project.mkdir();(project/'source.txt').write_text('owned');(project/'nested').mkdir();(project/'nested/result.json').write_text('{}');(project/'link').symlink_to(project/'nested',target_is_directory=True)
    for limit in [1,10000]:observe('footprint-'+str(limit),lambda limit=limit:assurance.artifact_footprint(project,plan,{'nodes':{}},baseline,detail=True,limit=limit))
    return dict(inherited=inherited,rule_cases=cases,caller_observations=records,snapshots={'footprint':{p.relative_to(project).as_posix():base64.b64encode(p.read_bytes()).decode() for p in sorted(project.rglob('*')) if p.is_file() and not p.is_symlink()}},core_clock_calls=len(trace),datetime_calls=0,clock_trace=trace)
