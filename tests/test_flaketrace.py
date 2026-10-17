import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from flaketrace import parse_xml, load_runs, analyze, render
ROOT=Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
    def report(self):return analyze(load_runs(ROOT/'examples/runs.json'))
    def test_labelled_fixture(self):
        r=self.report();self.assertEqual(r['candidate_count'],1)
        c=next(x for x in r['tests'] if x['candidate'])
        self.assertEqual(c['name'],'mixed');self.assertEqual(c['commit'],'synthetic-a')
        self.assertEqual(c['counts'],{'pass':2,'fail':1,'skipped':0,'missing':0})
        self.assertAlmostEqual(c['observed_failure_rate'],1/3)
    def test_separate_commits_single_failure_not_candidate(self):
        row=next(x for x in self.report()['tests'] if x['commit']=='synthetic-b')
        self.assertFalse(row['candidate']);self.assertEqual(row['observed_failure_rate'],1)
    def test_missing_skipped_not_pass(self):
        rows={x['name']:x for x in self.report()['tests'] if x['commit']=='synthetic-a'}
        self.assertEqual(rows['sometimes_absent']['counts']['missing'],1)
        self.assertEqual(rows['sometimes_absent']['observed_failure_rate'],0)
        self.assertIsNone(rows['skipped']['observed_failure_rate'])
        self.assertFalse(rows['always_fails']['candidate'])
    def test_namespace_nested(self):
        c=parse_xml(b'<testsuites xmlns="urn:test"><testsuite><testcase name="x"/></testsuite></testsuites>')
        self.assertEqual(c[('', 'x')]['status'],'pass')
    def test_bad_xml(self):
        for raw in [b'<bad/>',b'<testsuite>',b'<testsuite><testcase/></testsuite>',b'<testsuite><testcase name="x"/><testcase name="x"/></testsuite>',b'<testsuite><testcase name="x"><failure/><skipped/></testcase></testsuite>',b'<!DOCTYPE x><testsuite/>',b'\x00',b'x'*5_000_001]:
            with self.subTest(raw=raw[:70]),self.assertRaises(Exception):parse_xml(raw)
    def test_empty_suite_missing(self):
        self.assertEqual(parse_xml(b'<testsuite/>'),{})
    def test_manifest_validation_and_traversal(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'runs.json'
            for data in [[],{},[{'commit':'a','run':'1','file':'../outside.xml'}],[{'commit':'a','run':'1','file':'/tmp/x.xml'}],[{'commit':'','run':'1','file':'x'}]]:
                p.write_text(json.dumps(data))
                with self.assertRaises(ValueError):load_runs(p)
    def test_duplicate_run(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'x.xml').write_text('<testsuite/>');entry=dict(commit='a',run='1',file='x.xml');(p/'m.json').write_text(json.dumps([entry,entry]))
            with self.assertRaises(ValueError):load_runs(p/'m.json')
    def test_evidence_and_escaping(self):
        r=self.report();r['evidence'][0]['details']=[{'message':'<script>alert(1)</script>'}]
        page,evidence=render(r);self.assertNotIn('<script>',evidence)
        for row in r['tests']:
            for o in row['outcomes']:self.assertIn('id="'+o['evidence'].split('#')[1]+'"',evidence)
        self.assertEqual(len(r['runs'][0]['sha256']),64)
    def test_cli(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'out';cmd=[sys.executable,str(ROOT/'flaketrace.py'),str(ROOT/'examples/runs.json'),'--out',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads((out/'report.json').read_text())['candidate_count'],1)
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)
if __name__=='__main__':unittest.main()
