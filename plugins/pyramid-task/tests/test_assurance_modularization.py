"""Explicit assurance clock/scan boundaries and value-only validators."""
import copy,sys,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pyramid_assurance as adapter
import pyramid_assurance_contracts as contracts
import pyramid_assurance_defaults as defaults
import pyramid_assurance_rules as rules
import pyramid_validation as validation

class AssuranceModularizationTests(unittest.TestCase):
    def test_value_contracts_and_defaults_need_no_file_clock_or_scan(self):
        with mock.patch.object(Path,'open',side_effect=AssertionError('file')),mock.patch.object(adapter,'utc_now',side_effect=AssertionError('clock')),mock.patch.object(adapter,'artifact_footprint',side_effect=AssertionError('walker')):
            baseline=defaults.default_baseline(actor='owner',timestamp='explicit')
            assurance=defaults.default_assurance(plan_id='OWNED',baseline_id=baseline['baseline_id'],baseline_revision=1,actor='owner',timestamp='explicit')
            self.assertFalse(contracts.validate_baseline(baseline))
            self.assertIsInstance(contracts.validate_assurance(assurance,plan={'plan_id':'OWNED','nodes':[]},baseline=baseline),list)
            self.assertTrue(validation.validate_plan({}))
            self.assertEqual([],rules.inspection_freshness_blockers(assurance,impacted_assets=set(),task_ids=set(),implementation_frontier={}))
    def test_stale_clock_failure_preserves_pre_clock_mutation_order(self):
        value={'status':'ready','stale_reasons':[],'updated_at':'old','updated_by':'old'}
        observed=[]
        def fail():observed.append(copy.deepcopy(value));raise OSError('owned clock')
        with mock.patch.object(adapter,'utc_now',side_effect=fail):
            with self.assertRaisesRegex(OSError,'owned clock'):adapter.mark_assurance_stale(value,'reason','owner')
        self.assertEqual([{'status':'stale','stale_reasons':['reason'],'updated_at':'old','updated_by':'old'}],observed)
        with mock.patch.object(adapter,'utc_now',side_effect=AssertionError('unexpected clock')):
            with self.assertRaises(KeyError):adapter.default_assurance(plan_id='OWNED',baseline={},actor='owner')
