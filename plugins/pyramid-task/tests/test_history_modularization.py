"""Pure history boundary and original ledger fault seam."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pyramid_history as ledger
import pyramid_history_contracts as contracts
import pyramid_history_model as model
import pyramid_core as core

class HistoryModularizationTests(unittest.TestCase):
    def test_contracts_and_loaded_record_models_need_no_io_or_clock(self):
        with mock.patch.object(Path,'open',side_effect=AssertionError('file')),mock.patch.object(ledger,'_write_json',side_effect=AssertionError('write')),mock.patch.object(ledger,'_now',side_effect=AssertionError('clock')),mock.patch.object(ledger,'_git',side_effect=AssertionError('git')):
            self.assertTrue(contracts._record_validation_errors({}))
            self.assertTrue(contracts._transaction_validation_errors({}))
            self.assertEqual([],contracts._record_link_errors([]))
            chronicles=model.chronicles_from_records([])
            summary=model.summary_from_chronicles(chronicles)
            self.assertEqual(0,model.query_from_chronicles(chronicles,[],summary)['count'])
            self.assertEqual({},model.index_from_records([],'explicit')['files'])
            self.assertEqual('pyramid_history',ledger.HistoryError.__module__)
    def test_ledger_write_fault_seam_keeps_recoverable_pending_transaction(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);core.create_project(root,Path(__file__).resolve().parents[1]/'assets/example-plan.json','owner',mode='greenfield');meta=root/'.pyramid'
            start=ledger._records(meta)[0];record=copy.deepcopy(start);record.update(record_id='START-OWNED-2',plan_id='OWNED-2')
            real=ledger._write_json;hits=[]
            def fail_record(path,value):
                hits.append(path)
                if path.parent.name=='records':raise OSError('owned record fault')
                return real(path,value)
            with mock.patch.object(ledger,'_write_json',side_effect=fail_record):
                with self.assertRaisesRegex(ledger.HistoryError,'History append was interrupted') as failure:ledger._append_record(meta,record)
            self.assertIsInstance(failure.exception.__cause__,OSError)
            self.assertEqual(2,len(hits));self.assertTrue(ledger.history_paths(meta)['transaction'].exists())
            recovered=ledger.repair_history_transaction(meta)
            self.assertEqual('valid',recovered['status'])
            self.assertEqual('completed',recovered['repair'])
            self.assertEqual(record['record_id'],recovered['repaired_record_id'])
            self.assertFalse(ledger.history_paths(meta)['transaction'].exists())
            self.assertFalse(ledger.history_validation_errors(meta))
