"""Frozen-P3B query/CLI fixtures; exact values, errors and bytes."""
from __future__ import annotations
import base64,contextlib,io,json,uuid
from datetime import datetime,timezone
from pathlib import Path
from unittest import mock
from plan_modularization_support import run_plans,FIXED
from runtime_modularization_support import encoded

def run_queries(api,root):
    import pyramid
    import pyramid_assurance as assurance
    import pyramid_history as history
    inherited=run_plans(api,root/'inherited')
    records=[];snapshots={};trace=[]
    class FixedDate(datetime):
        @classmethod
        def now(cls,tz=None):trace.append('datetime');return datetime(2026,10,10,tzinfo=timezone.utc)
    def clock():trace.append('utc_now');return FIXED
    def files(project):return {p.relative_to(project).as_posix():p.read_bytes() for folder in [project/'.pyramid',project/'docs/tasks'] for p in sorted(folder.rglob('*')) if p.is_file()}
    def observe(label,fn,error=False):
        try:value=fn();records.append(dict(label=label,value_json=encoded(value),error=None,expected_error=error));return value
        except Exception as e:records.append(dict(label=label,value_json=None,error=dict(type=type(e).__name__,message=str(e)),expected_error=error));return None
    ids=iter(range(30000,40000))
    with mock.patch.object(api,'datetime',FixedDate),mock.patch.object(api,'utc_now',side_effect=clock),mock.patch.object(assurance,'utc_now',return_value=FIXED),mock.patch.object(history,'_now',return_value=FIXED),mock.patch.object(uuid,'uuid4',side_effect=lambda:uuid.UUID(int=next(ids)<<96)):
        for name in ['topology','brown-legacy','brown-bound']:
            project=root/'inherited'/name;paths,plan,state=api.load_project(project);node=next(n['id'] for n in plan['nodes'] if n['kind']=='implementation' and n['selection']=='primary')
            modes=[{},dict(summary=True),dict(ready=True),dict(blocked=True),dict(pending_audits=True),dict(paused=True),dict(assurance_view=True),dict(assurance_summary_view=True),dict(assurance_detail=True),dict(parallel_ready=True),dict(audit_readiness=node),dict(harness=node),dict(nid=node),dict(footprint=True,footprint_detail=True)]
            for index,mode in enumerate(modes):
                before=files(project);observe(f'{name}-query-{index}',lambda mode=mode:api.inspect_project(project,**mode));records.append(dict(label=f'{name}-query-{index}-readonly',unchanged=before==files(project)))
            observe(name+'-bad-node',lambda:api.inspect_project(project,nid='unknown'),True)
            observe(name+'-bad-footprint',lambda:api.inspect_project(project,footprint_detail=True),True)
            observe(name+'-bad-parallel',lambda:api.inspect_project(project,parallel_ready=True,max_agents=0),True)
            for detail in [False,True]:observe(name+'-diff-'+str(detail),lambda detail=detail:api.inspect_changes(project,0,detail=detail))
            observe(name+'-bad-diff',lambda:api.inspect_changes(project,-1),True)
            observe(name+'-history',lambda:api.inspect_history(project))
            observe(name+'-health',lambda:api.inspect_history_health(project))
            observe(name+'-repair-healthy',lambda:api.repair_history(project))
            observe(name+'-bad-binding',lambda:api.bind_history_commit(project,'unknown',''),True)
            snapshots[name]={p:base64.b64encode(b).decode() for p,b in files(project).items()}
    parser=pyramid.build_parser();sub=next(a for a in parser._actions if getattr(a,'choices',None));catalog=parser.get_default('command_catalog')
    records.append(dict(label='cli-help',help=parser.format_help(),commands=list(catalog),children={name:p.format_help() for name,p in sub.choices.items()}))
    # Parse every command with both output policies, then execute all ordinary
    # query modes through the actual CLI adapter. Mutation journeys remain the
    # independent API oracle above and the real CLI regression fixtures.
    samples={'create':['--plan','fixture.json','--actor','owner'],'new-intent':['--plan','fixture.json','--actor','owner','--reason','fixture','--preview'],'assess':['--baseline','fixture.json','--actor','owner','--preview'],'impact':['--assurance','fixture.json','--actor','owner','--preview'],'diff':['--from-version','0'],'take':['--next','--actor','owner'],'pause':['--node','TASK-201','--actor','owner','--reason','fixture','--handoff','fixture.json'],'resume':['--node','TASK-201','--actor','owner'],'update':['--node','TASK-201','--actor','owner','--status','release'],'audit':['--node','TASK-201','--actor','owner','--result','pass','--evidence','fixture.json'],'amend':['--proposal','fixture.json','--actor','owner','--preview'],'replan':['--plan','fixture.json','--actor','owner','--reason','fixture','--preview'],'expand':['--proposal','fixture.json','--actor','owner','--preview'],'reopen':['--node','TASK-201','--actor','owner','--reason','fixture'],'close':['--actor','owner'],'archive':['--actor','owner','--reason','fixture'],'reset':['--plan','fixture.json','--actor','owner','--reason','fixture'],'restore':['--archive','fixture','--actor','owner','--reason','fixture']}
    project=root/'inherited/topology'
    for command in catalog:
        for policy in ['--compact','--full']:
            args=parser.parse_args([command,'--project',str(project),*samples.get(command,[]),policy]);records.append(dict(label='cli-parse-'+command+'-'+policy,args=vars(args)))
    for mode in [[],['--summary'],['--ready'],['--blocked'],['--pending-audits'],['--paused'],['--assurance'],['--assurance-summary'],['--assurance-detail'],['--parallel-ready']]:
        observe('cli-inspect-'+str(mode),lambda mode=mode:pyramid.run(parser.parse_args(['inspect','--project',str(project),*mode])))
    for args in [[],['inspect'],['inspect','--usage','--project',str(project)]]:
        stdout,stderr=io.StringIO(),io.StringIO()
        with mock.patch('sys.argv',['pyramid',*args]),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            try:code=pyramid.main()
            except SystemExit as e:code=e.code
        records.append(dict(label='cli-process-args-'+str(args),code=code,stdout=stdout.getvalue(),stderr=stderr.getvalue()))
    return dict(inherited=inherited,rule_cases=inherited['rule_cases'],caller_observations=records,snapshots=snapshots,core_clock_calls=trace.count('utc_now'),datetime_calls=trace.count('datetime'),clock_trace=trace)
