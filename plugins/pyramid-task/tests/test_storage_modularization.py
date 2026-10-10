"""P2 actual file/process/fault checks; legacy seams must trigger real code."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PLUGIN=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PLUGIN/'scripts'))
import pyramid_core as core
import pyramid_files as files
import pyramid_publication as publication
import pyramid_changes as changes
import pyramid_handoff as handoff
import pyramid_verification as verification

RACE = r'''
import json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import pyramid_core as core
root,guard,worker=Path(sys.argv[2]),sys.argv[3],sys.argv[4]
(root.parent/(worker+'.ready')).write_text(str(os.getpid()))
deadline=time.monotonic()+10
while not (root.parent/'go').exists():
    if time.monotonic()>deadline:raise TimeoutError('race rendezvous')
    time.sleep(.01)
try:
    core.take_task(root,worker,nid='RESEARCH-101',expected_guard=guard)
    print(json.dumps({'pid':os.getpid(),'status':'claimed'}))
except core.PyramidError as e:print(json.dumps({'pid':os.getpid(),'status':'rejected','error':str(e)}))
'''
CRASH = r'''
import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import pyramid_core as core
root=Path(sys.argv[2]);replace=os.replace
def interrupted(src,dst):
    if Path(dst).name=='state.json':
        (root.parent/'crash-hook').write_text(str(src))
        os._exit(73)
    return replace(src,dst)
os.replace=interrupted
core.take_task(root,'crashed-worker',nid='RESEARCH-101')
'''


class StorageModularizationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.parent=Path(self.temp.name);self.root=self.parent/'project'
        core.create_project(self.root,PLUGIN/'assets/example-plan.json','planner',mode='greenfield')

    def test_two_independent_processes_compete_on_one_guard(self):
        guard=core.inspect_project(self.root,nid='RESEARCH-101')['mutation_guards']['task']
        before=len(list((self.root/'.pyramid/events').glob('*.json')))
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYRAMID_USAGE='off')
        processes=[subprocess.Popen([sys.executable,'-B','-c',RACE,str(PLUGIN/'scripts'),str(self.root),guard,worker],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env) for worker in ['one','two']]
        try:
            deadline=time.monotonic()+10
            while not all((self.parent/(w+'.ready')).exists() for w in ['one','two']):
                self.assertLess(time.monotonic(),deadline);time.sleep(.01)
            (self.parent/'go').write_text('start both')
            outcomes=[]
            for process in processes:
                stdout,stderr=process.communicate(timeout=15);self.assertEqual(0,process.returncode,stderr);outcomes.append(json.loads(stdout))
        finally:
            for process in processes:
                if process.poll() is None:process.kill();process.wait()
        self.assertEqual(2,len({o['pid'] for o in outcomes}))
        self.assertEqual(['claimed','rejected'],sorted(o['status'] for o in outcomes))
        self.assertIn('Stale task guard',next(o['error'] for o in outcomes if o['status']=='rejected'))
        self.assertEqual(before+1,len(list((self.root/'.pyramid/events').glob('*.json'))))
        self.assertTrue(core.validate_project(self.root)['valid'])

    def test_atomic_replace_failure_preserves_old_bytes_and_cleans_temp(self):
        target=self.parent/'atomic.json';files.write_json(target,{'old':True});before=target.read_bytes();attempts=[]
        def interrupt(src,dst):
            attempts.append((Path(src),Path(dst)));self.assertIn('new',Path(src).read_text());raise OSError('actual replace fault')
        with mock.patch.object(files.os,'replace',side_effect=interrupt):
            with self.assertRaisesRegex(OSError,'actual replace fault'):core.write_json(target,{'new':True})
        self.assertEqual(1,len(attempts));self.assertEqual(before,target.read_bytes());self.assertFalse(attempts[0][0].exists())

    def test_real_process_exit_after_event_fails_closed_and_owned_backup_recovers(self):
        before={p.relative_to(self.root):p.read_bytes() for p in (self.root/'.pyramid').rglob('*') if p.is_file()}
        result=subprocess.run([sys.executable,'-B','-c',CRASH,str(PLUGIN/'scripts'),str(self.root)],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYRAMID_USAGE='off'),capture_output=True,text=True,timeout=15)
        self.assertEqual(73,result.returncode,result.stderr);self.assertTrue((self.parent/'crash-hook').exists())
        self.assertEqual(before[Path('.pyramid/head.json')],(self.root/'.pyramid/head.json').read_bytes())
        with self.assertRaisesRegex(core.PyramidError,'atomically published head'):core.load_project(self.root)
        # Explicit restore of this test's owned backup, not a new runtime repair API.
        for p in (self.root/'.pyramid').rglob('*'):
            if p.is_file() and p.relative_to(self.root) not in before:p.unlink()
        for p,data in before.items():(self.root/p).write_bytes(data)
        self.assertTrue(core.validate_project(self.root)['valid'])

    def test_event_state_head_fault_hooks_execute_real_atomic_writes(self):
        for target in ['event','state','head']:
            with self.subTest(target=target):
                root=self.parent/target;core.create_project(root,PLUGIN/'assets/example-plan.json','planner',mode='greenfield')
                before=(root/'.pyramid/head.json').read_bytes();replace=os.replace;hits=[]
                def interrupt(src,dst):
                    p=Path(dst)
                    if (target=='event' and p.parent.name=='events') or p.name==target+'.json':
                        hits.append(p);self.assertTrue(Path(src).is_file());raise OSError('actual '+target+' fault')
                    return replace(src,dst)
                with mock.patch.object(os,'replace',side_effect=interrupt):
                    with self.assertRaisesRegex(OSError,'actual '+target+' fault'):core.take_task(root,'worker',nid='RESEARCH-101')
                self.assertEqual(1,len(hits));self.assertEqual(before,(root/'.pyramid/head.json').read_bytes())
                if target=='event':self.assertTrue(core.validate_project(root)['valid'])
                else:
                    with self.assertRaisesRegex(core.PyramidError,'Project validation failed'):core.load_project(root)

    def test_ingestion_failure_removes_new_blob_but_preserves_shared_blob(self):
        artifacts=[]
        for name in ['shared','created','failed']:
            p=self.root/('proof-output/'+name);p.parent.mkdir(exist_ok=True);p.write_text(name)
            artifacts.append({'path':p.relative_to(self.root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
        storage=self.root/verification.ARTIFACT_DIR;storage.mkdir(parents=True)
        shared=storage/artifacts[0]['sha256'];shared.write_text('shared')
        payload={'proofs':[{'run':{'observations':[{'artifacts':copy.deepcopy(artifacts)}]}}]};original=Path.open;hits=[]
        def interrupt(path,*args,**kwargs):
            if path==storage/artifacts[2]['sha256'] and args and args[0]=='xb':
                hits.append(path);self.assertTrue((storage/artifacts[1]['sha256']).exists());raise OSError('actual blob fault')
            return original(path,*args,**kwargs)
        with mock.patch.object(Path,'open',new=interrupt):
            with self.assertRaisesRegex(OSError,'actual blob fault'):verification.publish_artifacts(self.root,payload)
        self.assertEqual(1,len(hits));self.assertEqual(b'shared',shared.read_bytes());self.assertEqual([shared],list(storage.iterdir()))

    def test_legacy_writer_fault_keeps_graph_bytes_and_mtime(self):
        graph=self.root/'.pyramid/graph.json';before=(graph.read_bytes(),graph.stat().st_mtime_ns);writer=core.write_projection_text;hits=[]
        def interrupt(path,text,*args,**kwargs):
            if path.name=='README.md' and path.parent.name=='tasks':hits.append(path);raise OSError('actual README fault')
            return writer(path,text,*args,**kwargs)
        with mock.patch.object(core,'write_projection_text',side_effect=interrupt):
            with self.assertRaisesRegex(OSError,'actual README fault'):core.compile_project(self.root)
        self.assertEqual(1,len(hits));self.assertEqual(before,(graph.read_bytes(),graph.stat().st_mtime_ns))

    def test_internal_publication_has_same_noop_bytes_and_mtimes(self):
        # History index has its own always-written timestamp protocol. Only the
        # ready/docs/graph projections use the byte-identical skip writer.
        paths=[self.root/'.pyramid/ready.json',self.root/'.pyramid/graph.json',
               *[p for p in (self.root/'docs/tasks').rglob('*') if p.is_file()]]
        before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in paths}
        generated_at=core.load_json(self.root/'.pyramid/graph.json')['generated_at']
        publication.compile_project(self.root,clock=lambda:generated_at)
        self.assertEqual(before,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in paths})

    def test_value_rules_do_not_read_files_or_clock(self):
        draft=core.load_json(PLUGIN/'assets/example-handoff-draft.json');_,plan,state=core.load_project(self.root)
        baseline=core.load_json(PLUGIN/'assets/example-baseline.json');assurance=core.load_json(PLUGIN/'assets/example-assurance.json')
        before=copy.deepcopy(assurance)
        with mock.patch.object(Path,'read_text',side_effect=AssertionError('read')), mock.patch.object(files,'utc_now',side_effect=AssertionError('clock')):
            self.assertEqual([],handoff._validate_handoff_draft(draft))
            self.assertEqual([{'path':'proof-output/check','class':'evidence'}],changes._classified_changes({'changed_files':['proof-output/check'],'change_effect':'evidence-only'},{'agent':{}}))
            records,_=changes.scope_drift_records(plan,state,'TASK-201',{'changed_files':['unknown']},baseline,assurance)
        self.assertEqual(before,assurance);self.assertEqual(1,len(records));self.assertIsNone(records[0]['detected_at'])


if __name__=='__main__':unittest.main()
