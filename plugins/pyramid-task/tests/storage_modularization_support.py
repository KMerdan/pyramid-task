"""Owned caller/fault fixtures for independent frozen P1 and candidate processes.

Both executions use the same disposable absolute root, deterministic clock/UUID,
and exact canonical/projection bytes. Synthetic task proof is a format fixture;
the stage's actual observations are the executed comparison and fault outcomes.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from runtime_modularization_support import encoded, run_case

FIXED = '2026-10-10T00:00:00Z'


def rule_cases(assets):
    draft = json.loads((assets/'example-handoff-draft.json').read_text())
    cases = []
    def add(function,*args):
        cases.append({'name':f'{function}-{len(cases)}','function':function,'args':list(args)})
    add('_validate_handoff_draft',draft)
    for key in draft:
        invalid = copy.deepcopy(draft);invalid[key]=None;add('_validate_handoff_draft',invalid)
    invalid = copy.deepcopy(draft);invalid['unexpected']=1;add('_validate_handoff_draft',invalid)
    record = dict(draft,schema='pyramid-handoff-v1',id='HANDOFF-TASK-201-FIXTURE',plan_id='PLAN-001',task='TASK-201',actor='worker',pause_mode='handoff',reason='fixture',created_at=FIXED,resume_deadline=None,graph_version=1,fingerprint={'plan_sha256':'hash','baseline_sha256':None,'assurance_sha256':None,'worktree':{'kind':'not-git'}})
    add('_handoff_record_errors',record);add('_handoff_markdown',record)
    for key in record:
        invalid=copy.deepcopy(record);invalid[key]=None;add('_handoff_record_errors',invalid)
    for value in ['HANDOFF-TASK-201-FIXTURE','../../outside','bad','']:
        add('_handoff_path',{'handoffs':Path('/owned/handoffs')},value)
    for path in ['src/file.py','./src/file.py','src','generated/a.json','outside.py']:
        for patterns in [['src/**'],['src/*'],['generated/*.json'],[]]:add('_path_matches',path,patterns)
    node={'agent':{'evidence_outputs':['proof-output/**'],'generated_outputs':[{'pattern':'generated/**','asset_ids':['ASSET-GEN']}]}}
    for path in ['src/file.py','generated/a.json','proof-output/test.log']:
        add('_generated_assets_for_path',node,path)
        for effect in [None,'source-change','evidence-only']:
            result={'changed_files':[path,'',None],'change_effect':effect};add('_classified_changes',result,node)
    return cases


def run_oracle(api, root):
    import pyramid_assurance as assurance_module
    import pyramid_history as history_module
    assets=Path(api.__file__).resolve().parents[1]/'assets'
    class FixedDate(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,10,10,tzinfo=timezone.utc)
    calls=[]
    def clock():calls.append('core');return FIXED
    ids=iter(range(1,10000))
    records=[]
    snapshots={}
    def write(path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False)+'\n');return path
    def snapshot(label, project):
        snapshots[label]={p.relative_to(project).as_posix():base64.b64encode(p.read_bytes()).decode()
            for folder in [project/'.pyramid',project/'docs/tasks'] for p in sorted(folder.rglob('*')) if p.is_file()}
    def observe(label,fn):
        try:value=fn();records.append({'label':label,'value_json':encoded(value),'error':None});return value
        except Exception as e:
            records.append({'label':label,'value_json':None,'error':{'type':type(e).__name__,'message':str(e)}});return None
    with mock.patch.object(api,'datetime',FixedDate), mock.patch.object(api,'utc_now',side_effect=clock), \
         mock.patch.object(assurance_module,'utc_now',return_value=FIXED), mock.patch.object(history_module,'_now',return_value=FIXED), \
         mock.patch.object(uuid,'uuid4',side_effect=lambda:uuid.UUID(int=next(ids)<<96)):
        values=[run_case(api,c) for c in rule_cases(assets)]
        for bound in [False,True]:
            project=root/('bound' if bound else 'legacy');plan=api.load_json(assets/'example-plan.json')
            if bound:
                plan['schema_version']=2
                for n in plan['nodes']:
                    n['agent']['evidence_outputs']=['proof-output/**']
                    for e in n['required_evidence']:
                        e['verification']={'criteria':[c['id'] for c in n['acceptance_criteria']],'method':'review','procedure':'Compare owned fixture values','inputs':['inputs/source.txt'],'observations':['internal'],'not_applicable':{'external':'Unit proof-format fixture','visual':'No rendered fixture'},'environment':'Owned deterministic fixture'}
                for n in plan['nodes']:
                    if n['id'] in ['GATE-290','OUTCOME-010','INTENT-001']:
                        e=n['required_evidence'][0];e['verification']={'criteria':e['verification']['criteria'],'reuse':'TASK-201/EVREQ-201-01'}
            plan_path=write(root/(project.name+'-plan.json'),plan)
            observe(project.name+'-create',lambda:api.create_project(project,plan_path,'planner',mode='greenfield'))
            write(project/'inputs/source.txt',{'fixture':1});write(project/'proof-output/check.json',{'observed':True})
            packet=api.inspect_project(project,nid='RESEARCH-101');guard=packet['mutation_guards']['task']
            observe(project.name+'-claim',lambda:api.take_task(project,'worker',nid='RESEARCH-101',expected_guard=guard))
            observe(project.name+'-stale-guard',lambda:api.take_task(project,'other',nid='RESEARCH-101',expected_guard=guard))
            observe(project.name+'-pause',lambda:api.pause_task(project,'RESEARCH-101','worker','fixture pause',assets/'example-handoff-draft.json',mode='hold'))
            observe(project.name+'-resume',lambda:api.resume_task(project,'RESEARCH-101','worker'))
            for nid in ['RESEARCH-101','CONTRACT-102','TASK-201','GATE-290']:
                if nid!='RESEARCH-101':observe(project.name+'-claim-'+nid,lambda:api.take_task(project,'worker',nid=nid))
                n=next(n for n in plan['nodes'] if n['id']==nid)
                result={'schema':'agent-result-v1','task':nid,'outcome':'implemented','changed_files':[],'discovered_risks':[],'suggested_graph_changes':[]}
                if bound:
                    harness=api.inspect_project(project,harness=nid)
                    if harness['reusable_proofs']:proof=harness['reusable_proofs'][0]
                    else:
                        proof=harness['proof_templates'][0]
                        for obs in proof['run']['observations']:
                            p=project/'proof-output/check.json';obs.update(result='passed',summary='Synthetic proof-format fixture',reviewer='oracle-fixture',artifacts=[{'path':p.relative_to(project).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}])
                    result['proofs']=[proof]
                else:
                    result['checks']=[{'command':'owned proof-format fixture','result':'passed'}]
                    result['acceptance_evidence']=[{'criterion':c['id'],'result':'passed','reference':'owned fixture'} for c in n['acceptance_criteria']]
                observe(project.name+'-update-'+nid,lambda:api.update_task(project,nid,'worker','implemented',result_path=write(root/'result.json',result)))
                audit={'schema':'audit-result-v1','target':nid,'result':'pass','affected_claims':[],'recommended_action':'advance','checks':[{'id':'FIXTURE','result':'passed','evidence':['owned fixture']}]}
                observe(project.name+'-audit-'+nid,lambda:api.audit_node(project,nid,'reviewer','pass',write(root/'audit.json',audit)))
            for nid in ['OUTCOME-010','INTENT-001']:
                audit={'schema':'audit-result-v1','target':nid,'result':'pass','affected_claims':[],'recommended_action':'advance','checks':[{'id':'FIXTURE','result':'passed','evidence':['owned fixture']}]}
                if bound:audit['proofs']=api.inspect_project(project,harness=nid)['reusable_proofs'][:1]
                observe(project.name+'-audit-'+nid,lambda:api.audit_node(project,nid,'reviewer','pass',write(root/'audit.json',audit)))
            observe(project.name+'-compile-read',lambda:api.compile_and_load_graph(project))
            observe(project.name+'-validate',lambda:api.validate_project(project))
            snapshot(project.name+'-completed-work',project)
            observe(project.name+'-close',lambda:api.close_project(project,'owner'))
            observe(project.name+'-archive',lambda:api.archive_project(project,'owner','oracle archive'))
            snapshot(project.name+'-archived',project)
        project=root/'brownfield'
        observe('brown-create',lambda:api.create_project(project,assets/'example-plan.json','planner',mode='brownfield',baseline_path=assets/'example-baseline.json',assurance_path=assets/'example-assurance.json'))
        paths,plan,state=api.load_project(project);node=next(n for n in plan['nodes'] if n['id']=='TASK-201')
        assertion={'assurance':{'impact_ids':['IMPACT-001'],'inspection_ids':['INSPECTION-001'],'finding_ids':[],'scope_review':'complete'}}
        observe('brown-audit-assertion',lambda:api._assurance_audit_errors(paths,plan,state,node,assertion))
        for effect,path in [('evidence-only','proof-output/evidence.log'),('source-change','src/executor/main.py')]:
            result={'changed_files':[path],'change_effect':effect}
            observe('brown-invalidate-'+effect,lambda:api._invalidate_inspections_for_actual_change(paths,plan,'TASK-201',result,'worker'))
        observe('brown-scope-drift',lambda:api._record_scope_drift(paths,plan,state,'TASK-201',{'changed_files':['unpredicted.py','unpredicted.py']},'worker'))
        observe('brown-task-invalidation',lambda:api._invalidate_assurance_for_change(paths,plan,{'TASK-201'},'worker','fixture change'))
        snapshot('brown-effects',project)
        project=root/'faults';observe('fault-create',lambda:api.create_project(project,assets/'example-plan.json','planner',mode='greenfield'))
        before=(project/'.pyramid/graph.json').read_bytes();writer=api.write_projection_text;touched=[]
        def fail_readme(path,data,*args,**kwargs):
            touched.append(str(path))
            if path.name=='README.md' and path.parent.name=='tasks':raise OSError('oracle projection fault')
            return writer(path,data,*args,**kwargs)
        with mock.patch.object(api,'write_projection_text',side_effect=fail_readme):observe('fault-graph-last',lambda:api.compile_project(project))
        records.append({'label':'fault-graph-seam','called':len(touched),'graph_preserved':before==(project/'.pyramid/graph.json').read_bytes()})
        for target in ['event','state','head']:
            project=root/('fault-'+target);api.create_project(project,assets/'example-plan.json','planner',mode='greenfield');replace=os.replace;hits=[]
            def interrupt(src,dst):
                p=Path(dst)
                if (target=='event' and p.parent.name=='events') or p.name==target+'.json':
                    hits.append(str(p));raise OSError('oracle '+target+' interruption')
                return replace(src,dst)
            with mock.patch.object(os,'replace',side_effect=interrupt):observe('fault-'+target,lambda:api.take_task(project,'worker',nid='RESEARCH-101'))
            observe('fault-'+target+'-verified-read',lambda:api.load_project(project))
            records.append({'label':'fault-'+target+'-seam','hits':len(hits)})
            snapshot('fault-'+target,project)
    return {'rule_cases':values,'caller_observations':records,'snapshots':snapshots,'core_clock_calls':len(calls)}
