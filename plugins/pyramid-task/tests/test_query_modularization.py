"""Query boundary invariants and explicit scan opt-in."""
import sys,tempfile,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pyramid_core as core
import pyramid_queries as queries
import pyramid_project_queries as shared
import pyramid_dependencies
import pyramid

class QueryModularizationTests(unittest.TestCase):
    def test_lower_queries_do_not_read_facade_or_optional_extractor(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);core.create_project(root,Path(__file__).resolve().parents[1]/'assets/example-plan.json','owner',mode='greenfield')
            with mock.patch.object(core,'load_project',side_effect=AssertionError('facade')),mock.patch.object(pyramid_dependencies,'_provider',side_effect=AssertionError('extractor')),mock.patch.object(queries,'artifact_footprint',side_effect=AssertionError('walker')):
                self.assertEqual('pyramid-summary-v1',queries.inspect_project(root)['schema'])
                self.assertEqual('ready',queries.inspect_project(root,ready=True)['query'])
                self.assertTrue(shared.validate_project(root)['valid'])
                self.assertEqual(0,pyramid.run(pyramid.build_parser().parse_args(['inspect','--project',str(root),'--summary']))[1])
    def test_query_ports_are_immutable_and_construct_without_effects(self):
        with mock.patch.object(queries,'load_project',side_effect=AssertionError('read')):
            p=queries.default_ports()
        with self.assertRaises(AttributeError):p.read_project=lambda _:None
