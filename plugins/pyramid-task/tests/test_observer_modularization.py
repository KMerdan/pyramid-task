"""Pure observer isolation and complete-package resource/escaping regression."""
import json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pyramid_core as core
import pyramid_observer as observer
import pyramid_visualizer as viewer

class ObserverModularizationTests(unittest.TestCase):
    def test_loaded_graph_projection_does_not_read_files_or_renderer(self):
        with tempfile.TemporaryDirectory() as d:
            core.create_project(d,Path(__file__).resolve().parents[1]/'assets/example-plan.json','owner',mode='greenfield')
            core.compile_project(d)
            graph=json.loads((Path(d)/'.pyramid/graph.json').read_text())
            with mock.patch('builtins.open',side_effect=AssertionError('read')),mock.patch.object(viewer,'load_visualization_graph',side_effect=AssertionError('renderer')),mock.patch.object(core,'utc_now',side_effect=AssertionError('clock')):
                value=observer.visualization_snapshot(graph)
            self.assertEqual('pyramid-visualization-v3',value['schema'])
            self.assertEqual(graph['graph_version'],value['graph_version'])
            self.assertIn('observer',value)
    def test_copied_package_resources_and_closing_tags_from_unrelated_cwd(self):
        plugin=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);package=root/'package';shutil.copytree(plugin,package,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            other=root/'other';other.mkdir()
            probe="import json,sys;sys.path.insert(0,sys.argv[1]);import pyramid_visualizer as v;print(json.dumps({'static':v.build_visualization_html({'title':'</script> 中文'}),'live':v.build_visualization_html({},live=True),'asset':str(v._ASSETS)}))"
            result=subprocess.run([sys.executable,'-B','-c',probe,str(package/'scripts')],cwd=other,text=True,capture_output=True,check=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYRAMID_USAGE='off'))
            value=json.loads(result.stdout)
            self.assertEqual(str((package/'assets').resolve()),value['asset'])
            self.assertIn('<\\/script>',value['static'])
            self.assertNotIn('src="observer.html"',value['static'])
            self.assertIn("new EventSource('/events')",value['live'])
            self.assertNotIn('__GRAPH_DATA__',value['static'])
            self.assertNotIn('__LIVE_SCRIPT__',value['live'])
