"""Frozen-P3A plan/assurance caller fixtures; exact bytes, no normalization."""
from __future__ import annotations
import base64,copy,json,uuid
from datetime import datetime,timezone
from pathlib import Path
from unittest import mock
from runtime_modularization_support import encoded
from storage_modularization_support import run_oracle
FIXED='2026-10-10T00:00:00Z'

def run_plans(api,root):
    import pyramid_assurance as assurance
    import pyramid_history as history
    from test_runtime import PyramidRuntimeTests
    inherited=run_oracle(api,root/'inherited')
    records=[];snapshots={};trace=[];assets=Path(api.__file__).resolve().parents[1]/'assets'
    class FixedDate(datetime):
        @classmethod
        def now(cls,tz=None):trace.append('datetime');return datetime(2026,10,10,tzinfo=timezone.utc)
    def clock():trace.append('utc_now');return FIXED
    def write(path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value)+'\n');return path
    def files(project):return {p.relative_to(project).as_posix():p.read_bytes() for folder in [project/'.pyramid',project/'docs/tasks'] for p in sorted(folder.rglob('*')) if p.is_file()}
    def snap(label,project):snapshots[label]={p:base64.b64encode(b).decode() for p,b in files(project).items()}
    def observe(label,fn,error=False,status=None):
        try:
            value=fn();records.append({'label':label,'value_json':encoded(value),'error':None,'expected_error':error,'expected_status':status,'actual_status':value.get('status') if isinstance(value,dict) else None});return value
        except Exception as e:
            records.append({'label':label,'value_json':None,'error':{'type':type(e).__name__,'message':str(e)},'expected_error':error,'expected_status':status,'actual_status':None});return None
    def readonly(label,project,fn,error=False,status=None):
        before=files(project);value=observe(label,fn,error,status);records.append({'label':label+'-readonly','unchanged':before==files(project)});return value
    ids=iter(range(10000,20000))
    with mock.patch.object(api,'datetime',FixedDate),mock.patch.object(api,'utc_now',side_effect=clock),mock.patch.object(assurance,'utc_now',return_value=FIXED),mock.patch.object(history,'_now',return_value=FIXED),mock.patch.object(uuid,'uuid4',side_effect=lambda:uuid.UUID(int=next(ids)<<96)):
        for name in ['legacy','bound']:
            project=root/'inherited'/name;archive=api.list_archives(project)[-1]['archive_id']
            observe(name+'-restore',lambda:api.restore_project(project,archive,'owner','owned restoration'),status='restored')
            observe(name+'-clean',lambda:api.clean_project(project),error=name=='bound',status='clean' if name=='legacy' else None)
            # Bound clean has a pre-existing directory-hash failure for proof blobs.
            # Preserve and disclose it; it must not become a silent refactor fix.
            candidate=api.load_json(assets/'example-harness-plan.json' if name=='bound' else assets/'example-plan.json');candidate['plan_id']='NEXT-'+name.upper();next_path=write(root/(name+'-next.json'),candidate)
            preview=readonly(name+'-new-intent-preview',project,lambda:api.new_intent_project(project,next_path,'planner','owned next intent'),status='preview')
            readonly(name+'-bad-new-intent-approval',project,lambda:api.new_intent_project(project,next_path,'planner','owned next intent',apply=True,approved_by='owner',approval_reference='fixture',approved_new_intent_sha256='wrong'),error=True)
            observe(name+'-new-intent-apply',lambda:api.new_intent_project(project,next_path,'planner','owned next intent',apply=True,approved_by='owner',approval_reference='fixture',approved_new_intent_sha256=preview['new_intent_sha256']),status='started')
            candidate['plan_id']='RESET-'+name.upper();reset_path=write(root/(name+'-reset.json'),candidate)
            before_history=api.inspect_history(project)
            reset=observe(name+'-reset',lambda:api.reset_project(project,reset_path,'planner','owned reset'),status='reset')
            observe(name+'-restore-reset',lambda:api.restore_project(project,reset['previous_archive'],'owner','return owned snapshot'),status='restored')
            records.append({'label':name+'-history-retained','before_json':encoded(before_history),'after_json':encoded(api.inspect_history(project))})
            snap(name+'-lifecycle',project)
        project=root/'topology';api.create_project(project,assets/'example-plan.json','planner',mode='greenfield')
        plan=api.load_project(project)[1];candidate=copy.deepcopy(plan);candidate['revision']+=1;candidate['title']='Owned replan fixture';path=write(root/'replan.json',candidate)
        readonly('replan-preview',project,lambda:api.replan_project(project,path,'planner','owned replan',False),status='preview')
        readonly('replan-stale',project,lambda:api.replan_project(project,path,'planner','owned replan',True,expected_version=0),error=True)
        observe('replan-apply',lambda:api.replan_project(project,path,'planner','owned replan',True),status='applied')
        proxy=PyramidRuntimeTests();proxy.root=project;proposal=write(root/'expansion.json',proxy.proposal_for('TASK-201','21'))
        preview=readonly('expand-preview',project,lambda:api.expand_project(project,proposal,'planner',apply=False),status='preview')
        readonly('expand-bad-approval',project,lambda:api.expand_project(project,proposal,'planner',apply=True,approved_by='owner',approval_reference='fixture',approved_proposal_sha256='wrong'),error=True)
        observe('expand-apply',lambda:api.expand_project(project,proposal,'planner',apply=True,approved_by='owner',approval_reference='fixture',approved_proposal_sha256=preview['proposal_sha256']),status='applied')
        readonly('close-unverified',project,lambda:api.close_project(project,'owner'),error=True)
        snap('topology',project)
        for bound in [False,True]:
            name='brown-bound' if bound else 'brown-legacy';project=root/name
            api.create_project(project,assets/('example-harness-plan.json' if bound else 'example-plan.json'),'planner',mode='brownfield',baseline_path=assets/'example-baseline.json',assurance_path=assets/'example-assurance.json')
            paths,plan,state=api.load_project(project);baseline=api.load_json(paths['baseline']);baseline['revision']+=1;baseline['captured_at']=FIXED;path=write(root/(name+'-baseline.json'),baseline)
            readonly(name+'-assess-preview',project,lambda:api.assess_project(project,path,'reviewer'),status='preview')
            readonly(name+'-assess-stale',project,lambda:api.assess_project(project,path,'reviewer',apply=True,expected_version=0),error=True)
            observe(name+'-assess-apply',lambda:api.assess_project(project,path,'reviewer',apply=True),status='applied')
            candidate=api.load_json(paths['assurance']);path=write(root/(name+'-assurance.json'),candidate)
            readonly(name+'-impact-preview',project,lambda:api.impact_project(project,path,'reviewer'),status='preview')
            observe(name+'-impact-apply',lambda:api.impact_project(project,path,'reviewer',apply=True),status='applied')
            snap(name,project)
        project=root/'fresh'
        observe('fresh-new-intent-preview',lambda:api.new_intent_project(project,assets/'example-plan.json','planner','owned fresh'),status='preview')
        observe('fresh-new-intent-apply',lambda:api.new_intent_project(project,assets/'example-plan.json','planner','owned fresh',apply=True),status='started')
        snap('fresh',project)
    return {'rule_cases':inherited['rule_cases'],'caller_observations':records,'snapshots':snapshots,'core_clock_calls':trace.count('utc_now'),'clock_trace':trace,'inherited':inherited}
