"""P3A lower-module independence, immutable ports and pure contract boundaries."""
from __future__ import annotations
import copy
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock
PLUGIN=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PLUGIN/'scripts'))
import pyramid_core as core
import pyramid_task_commands as commands
import pyramid_results as results
from task_modularization_support import result_fixture,audit_fixture


class TaskModularizationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'project'
        core.create_project(self.root,PLUGIN/'assets/example-plan.json','planner',mode='greenfield')

    def test_concrete_lower_command_needs_no_facade_reader_or_clock(self):
        with mock.patch.object(core,'load_project',side_effect=AssertionError('facade reader')),mock.patch.object(core,'utc_now',side_effect=AssertionError('facade clock')),mock.patch.object(core,'compile_project',side_effect=AssertionError('facade compile')):
            taken=commands.take_task(self.root,'worker',nid='RESEARCH-101')
            self.assertEqual('worker',taken['packet']['owner'])
            released=commands.update_task(self.root,'RESEARCH-101','worker','release')
            self.assertEqual('planned',released['packet']['execution'])
        self.assertTrue(core.validate_project(self.root)['valid'])

    def test_port_construction_has_no_effects_and_bindings_are_immutable(self):
        with mock.patch.object(Path,'read_text',side_effect=AssertionError('read')),mock.patch.object(commands,'utc_now',side_effect=AssertionError('clock')),mock.patch.object(subprocess,'run',side_effect=AssertionError('process')):
            ports=commands.default_ports()
            self.assertIs(ports.read_project,commands.load_project)
            with self.assertRaises(FrozenInstanceError):ports.clock=lambda:'changed'

    def test_result_contracts_are_pure_and_preserve_inputs(self):
        _,plan,state=core.load_project(self.root);node=next(n for n in plan['nodes'] if n['id']=='RESEARCH-101')
        result=result_fixture(core,self.root);audit=audit_fixture();before=copy.deepcopy([result,audit,plan,state,node])
        with mock.patch.object(Path,'read_text',side_effect=AssertionError('read')),mock.patch.object(subprocess,'run',side_effect=AssertionError('process')),mock.patch.object(core,'utc_now',side_effect=AssertionError('clock')):
            self.assertEqual([],results._validate_agent_result(result,node))
            self.assertEqual([],results._validate_audit_result(audit,'RESEARCH-101','pass'))
            self.assertEqual(['RESEARCH-101 must be implemented before audit pass'],results._audit_prerequisite_errors(plan,state,node))
        self.assertEqual(before,[result,audit,plan,state,node])


if __name__=='__main__':unittest.main()
