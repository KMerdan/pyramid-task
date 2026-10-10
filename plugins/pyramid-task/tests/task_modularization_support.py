"""Independent frozen-P2 task journeys with exact inputs and real compile faults.

Synthetic result/audit records test the format and protocol; actual acceptance
evidence is the old/new execution comparison and assertions in stage tests.
"""
from __future__ import annotations
import base64
import copy
import json
import uuid
from datetime import datetime,timezone
from pathlib import Path
from unittest import mock
from runtime_modularization_support import encoded,run_case
FIXED='2026-10-10T00:00:00Z'

def result_fixture(api,project,nid='RESEARCH-101'):
    plan=api.load_project(project)[1];node=next(n for n in plan['nodes'] if n['id']==nid)
    return {'schema':'agent-result-v1','task':nid,'outcome':'implemented','changed_files':[],
        'checks':[{'command':'owned format fixture','result':'passed'}],
        'acceptance_evidence':[{'criterion':c['id'],'result':'passed','reference':'owned format fixture'} for c in node['acceptance_criteria']],
        'discovered_risks':[],'suggested_graph_changes':[]}

def audit_fixture(nid='RESEARCH-101',result='pass'):
    return {'schema':'audit-result-v1','target':nid,'result':result,'affected_claims':[],
        'recommended_action':'advance' if result=='pass' else 'repair',
        'checks':[{'id':'FIXTURE','result':'passed' if result=='pass' else 'failed','evidence':['owned format fixture']}]}

def proposal_fixture():
    return {'schema':'pyramid-amendment-v1','task':'RESEARCH-101','reason':'Existing context owner discovered',
        'boundary_review':'Same outcome, criteria, authority and dependencies','add_write_paths':['extra/context.py'],'add_context_paths':[]}

def run_commands(api,root):
    import pyramid_assurance as assurance
    import pyramid_history as history
    assets=Path(api.__file__).resolve().parents[1]/'assets';records=[];snapshots={};clock_calls=[];date_calls=[];clock_trace=[]
    class FixedDate(datetime):
        @classmethod
        def now(cls,tz=None):date_calls.append('date');clock_trace.append('datetime');return datetime(2026,10,10,tzinfo=timezone.utc)
    def clock():clock_calls.append('clock');clock_trace.append('utc_now');return FIXED
    def write(path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value)+'\n');return path
    def snapshot(label,project):
        snapshots[label]={p.relative_to(project).as_posix():base64.b64encode(p.read_bytes()).decode()
            for folder in [project/'.pyramid',project/'docs/tasks'] for p in sorted(folder.rglob('*')) if p.is_file()}
    def observe(label,fn,error=False,status=None):
        try:
            value=fn();records.append({'label':label,'value_json':encoded(value),'error':None,'expected_error':error,'expected_status':status,'actual_status':value.get('status') if isinstance(value,dict) else None});return value
        except Exception as e:
            records.append({'label':label,'value_json':None,'error':{'type':type(e).__name__,'message':str(e)},'expected_error':error,'expected_status':status,'actual_status':None});return None
    ids=iter(range(1,10000))
    with mock.patch.object(api,'datetime',FixedDate),mock.patch.object(api,'utc_now',side_effect=clock),mock.patch.object(assurance,'utc_now',return_value=FIXED),mock.patch.object(history,'_now',return_value=FIXED),mock.patch.object(uuid,'uuid4',side_effect=lambda:uuid.UUID(int=next(ids)<<96)):
        project=root/'journey';api.create_project(project,assets/'example-plan.json','planner',mode='greenfield')
        result=result_fixture(api,project);node=next(n for n in api.load_project(project)[1]['nodes'] if n['id']=='RESEARCH-101')
        cases=[{'name':'result-valid','function':'_validate_agent_result','args':[result,node]},
            {'name':'audit-prerequisites','function':'_audit_prerequisite_errors','args':[api.load_project(project)[1],api.load_project(project)[2],node]}]
        for key in result:
            bad=copy.deepcopy(result);bad[key]=None;cases.append({'name':'result-'+key,'function':'_validate_agent_result','args':[bad,node]})
        audit=audit_fixture()
        for value in [audit,{},dict(audit,checks=[{'id':'x','result':'failed','evidence':[]}]),dict(audit,assurance={})]:cases.append({'name':'audit-'+str(len(cases)),'function':'_validate_audit_result','args':[value,'RESEARCH-101','pass']})
        values=[run_case(api,c) for c in cases]
        observe('claim',lambda:api.take_task(project,'worker',nid='RESEARCH-101'),status='taken')
        write(project/'extra/context.py',{'fixture':True});proposal=write(root/'proposal.json',proposal_fixture())
        preview=observe('amend-preview',lambda:api.amend_task(project,proposal,'worker'),status='preview')
        observe('amend-missing-token',lambda:api.amend_task(project,proposal,'worker',apply=True),error=True)
        observe('amend-apply',lambda:api.amend_task(project,proposal,'worker',apply=True,expected_amendment=preview['amendment_id']),status='applied')
        observe('wrong-owner',lambda:api.update_task(project,'RESEARCH-101','other','clear'),error=True)
        for status in ['at-risk','clear','blocked']:
            observe('update-'+status,lambda:api.update_task(project,'RESEARCH-101','worker',status,reason='owned fixture reason'),status=status)
        paused=observe('pause-blocked',lambda:api.pause_task(project,'RESEARCH-101','worker','fixture handoff',assets/'example-handoff-draft.json',mode='handoff'),status='paused')
        observe('resume-without-recovery',lambda:api.resume_task(project,'RESEARCH-101','next'),error=True)
        observe('reopen-contract',lambda:api.reopen_node(project,'CONTRACT-102','reviewer','fixture rework'),status='reopened')
        observe('stale-handoff',lambda:api.resume_task(project,'RESEARCH-101','next',for_recovery=True),status='stale-handoff')
        snapshot('stale-handoff-preserved',project)
        observe('recover',lambda:api.resume_task(project,'RESEARCH-101','next',for_recovery=True,accept_stale=True),status='resumed')
        observe('recovery-clear',lambda:api.update_task(project,'RESEARCH-101','next','clear'),status='clear')
        observe('release',lambda:api.update_task(project,'RESEARCH-101','next','release'),status='release')
        observe('reclaim',lambda:api.take_task(project,'next',nid='RESEARCH-101'),status='taken')
        result_path=write(root/'result.json',result)
        observe('implement',lambda:api.update_task(project,'RESEARCH-101','next','implemented',result_path=result_path),status='implemented')
        observe('audit-fail',lambda:api.audit_node(project,'RESEARCH-101','reviewer','fail',write(root/'audit-fail.json',audit_fixture(result='fail'))),status='fail')
        snapshot('failed-audit',project)
        observe('take-rework',lambda:api.take_task(project,'next',nid='RESEARCH-101'),status='taken')
        observe('implement-rework',lambda:api.update_task(project,'RESEARCH-101','next','implemented',result_path=result_path),status='implemented')
        observe('audit-pass',lambda:api.audit_node(project,'RESEARCH-101','reviewer','pass',write(root/'audit-pass.json',audit_fixture())),status='pass')
        observe('reopen',lambda:api.reopen_node(project,'RESEARCH-101','reviewer','fixture regression'),status='reopened')
        snapshot('journey',project)
        for operation in ['take_task','pause_task','resume_task','update_task','audit_node','amend_task','reopen_node']:
            project=root/('fault-'+operation);api.create_project(project,assets/'example-plan.json','planner',mode='greenfield')
            if operation not in ['take_task','reopen_node']:api.take_task(project,'worker',nid='RESEARCH-101')
            if operation=='resume_task':api.pause_task(project,'RESEARCH-101','worker','fault setup',assets/'example-handoff-draft.json')
            result_path=write(root/('result-'+operation+'.json'),result_fixture(api,project))
            if operation=='audit_node':api.update_task(project,'RESEARCH-101','worker','implemented',result_path=result_path)
            if operation=='amend_task':
                write(project/'extra/context.py',{'fixture':True});proposal=write(root/('proposal-'+operation+'.json'),proposal_fixture());token=api.amend_task(project,proposal,'worker')['amendment_id']
            invoke={
                'take_task':lambda:api.take_task(project,'worker',nid='RESEARCH-101'),
                'pause_task':lambda:api.pause_task(project,'RESEARCH-101','worker','fault pause',assets/'example-handoff-draft.json'),
                'resume_task':lambda:api.resume_task(project,'RESEARCH-101','worker'),
                'update_task':lambda:api.update_task(project,'RESEARCH-101','worker','implemented',result_path=result_path),
                'audit_node':lambda:api.audit_node(project,'RESEARCH-101','reviewer','pass',write(root/('audit-'+operation+'.json'),audit_fixture())),
                'amend_task':lambda:api.amend_task(project,proposal,'worker',apply=True,expected_amendment=token),
                'reopen_node':lambda:api.reopen_node(project,'RESEARCH-101','reviewer','fault reopen'),
            }[operation]
            seam='_compile_project_locked' if operation=='amend_task' else 'compile_project';hits=[]
            def interrupt(*args,**kwargs):hits.append('compile');raise OSError('actual '+operation+' compile fault')
            before=api.load_project(project)[2]['graph_version']
            with mock.patch.object(api,seam,side_effect=interrupt):observe('fault-'+operation,invoke,error=True)
            after=api.load_project(project)[2]['graph_version'];records.append({'label':'seam-'+operation,'hits':len(hits),'committed_versions':after-before})
            snapshot('fault-'+operation,project)
    return {'rule_cases':values,'caller_observations':records,'snapshots':snapshots,'clock_calls':len(clock_calls),'datetime_calls':len(date_calls),'clock_trace':clock_trace}
