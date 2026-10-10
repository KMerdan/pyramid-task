"""P3B lower default bindings and preserved legacy post-commit fault seam."""
import sys,tempfile,unittest
from pathlib import Path
from unittest import mock
PLUGIN=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PLUGIN/'scripts'))
import pyramid_core as core
import pyramid_plan_commands as plans
import pyramid_plan_lifecycle as lifecycle

class PlanModularizationTests(unittest.TestCase):
    def test_lower_plan_operations_do_not_call_facade(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'owned'
            with mock.patch.object(core,'load_project',side_effect=AssertionError('facade read')),mock.patch.object(core,'compile_project',side_effect=AssertionError('facade compile')):
                plans.create_project(root,PLUGIN/'assets/example-plan.json','planner',mode='greenfield')
                result=lifecycle.clean_project(root)
                self.assertTrue(result['canonical_preserved'])
            self.assertTrue(core.validate_project(root)['valid'])

    def test_create_compile_fault_executes_after_canonical_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'owned';hits=[]
            def interrupt(*args,**kwargs):hits.append('compile');raise OSError('owned create compile fault')
            with mock.patch.object(core,'compile_project',side_effect=interrupt):
                with self.assertRaisesRegex(OSError,'owned create compile fault'):core.create_project(root,PLUGIN/'assets/example-plan.json','planner',mode='greenfield')
            self.assertEqual(['compile'],hits);self.assertTrue(core.validate_project(root)['valid'])
            self.assertEqual(1,core.load_project(root)[2]['graph_version'])

if __name__=='__main__':unittest.main()
