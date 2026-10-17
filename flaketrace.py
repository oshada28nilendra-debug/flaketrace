"""Offline same-commit JUnit outcome comparison. Python standard library only."""
import argparse
from collections import Counter, defaultdict
import hashlib
import html
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def parse_xml(raw):
    if len(raw) > 5_000_000:
        raise ValueError('XML exceeds 5 MB limit')
    # UTF-8 only; reject DTDs/entities before parsing, including UTF-16 bypasses.
    text = raw.decode('utf-8-sig')
    if '\x00' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('DTD, entities and NUL bytes are unsupported')
    root = ET.fromstring(text)
    tag = lambda e: e.tag.rsplit('}', 1)[-1]
    if tag(root) not in ('testsuite', 'testsuites'):
        raise ValueError('expected testsuite or testsuites root')
    cases = {}
    for case in root.iter():
        if tag(case) != 'testcase':
            continue
        name, classname = case.get('name'), case.get('classname', '')
        if not name or not name.strip():
            raise ValueError('testcase name required')
        key = (classname, name)
        if key in cases:
            raise ValueError(f'duplicate testcase identity: {key!r}')
        outcomes = [c for c in case if tag(c) in ('failure', 'error', 'skipped')]
        kinds = {tag(c) for c in outcomes}
        if 'skipped' in kinds and kinds & {'failure', 'error'}:
            raise ValueError('conflicting skipped and failure outcomes')
        status = 'fail' if kinds & {'failure', 'error'} else 'skipped' if 'skipped' in kinds else 'pass'
        cases[key] = dict(status=status, details=[dict(kind=tag(c), message=c.get('message', ''), text=c.text or '') for c in outcomes])
    return cases


def load_runs(manifest):
    manifest = Path(manifest)
    rows = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(rows, list) or not rows:
        raise ValueError('manifest must be a nonempty list')
    runs, seen = [], set()
    base = manifest.parent.resolve()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'commit', 'run', 'file'}:
            raise ValueError('each entry needs exactly commit, run and file')
        if any(not isinstance(row[k], str) or not row[k].strip() for k in row):
            raise ValueError('manifest fields must be nonempty strings')
        if row['run'] in seen:
            raise ValueError('run identifiers must be globally unique')
        seen.add(row['run'])
        path = (base / row['file']).resolve()
        if Path(row['file']).is_absolute() or not path.is_relative_to(base):
            raise ValueError('XML paths must stay inside manifest directory')
        with path.open('rb') as stream:
            raw = stream.read(5_000_001)
        runs.append(dict(**row, sha256=hashlib.sha256(raw).hexdigest(), cases=parse_xml(raw)))
    return runs


def analyze(runs):
    groups = defaultdict(list)
    for r in runs:
        groups[r['commit']].append(r)
    records, evidence = [], []
    for commit, group in groups.items():
        keys = sorted(set().union(*(r['cases'] for r in group)))
        for classname, name in keys:
            outcomes = []
            for r in group:
                case = r['cases'].get((classname, name), dict(status='missing', details=[]))
                eid = f'e{len(evidence)}'
                evidence.append(dict(id=eid, commit=commit, run=r['run'], file=r['file'], sha256=r['sha256'], classname=classname, name=name, **case))
                outcomes.append(dict(run=r['run'], status=case['status'], evidence='evidence.html#'+eid))
            counts = Counter(o['status'] for o in outcomes)
            executed = counts['pass'] + counts['fail']
            records.append(dict(commit=commit, classname=classname, name=name,
                                counts={s:counts[s] for s in ('pass','fail','skipped','missing')},
                                observed_failure_rate=counts['fail']/executed if executed else None,
                                candidate=bool(counts['pass'] and counts['fail']), outcomes=outcomes))
    return dict(schema_version=1, run_count=len(runs), candidate_count=sum(r['candidate'] for r in records), tests=records, evidence=evidence,
                runs=[{k:v for k,v in r.items() if k!='cases'} for r in runs])


STYLE = '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{font:16px system-ui;background:#f5f2ea;color:#27342b;max-width:1200px;margin:30px auto;padding:20px}table{border-collapse:collapse;background:white;width:100%}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left}section{background:white;padding:20px;margin:20px 0;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.scroll{overflow:auto}a{color:#7d381f}</style>'


def render(report):
    esc = lambda s: html.escape(str(s), quote=True)
    page = ['<!doctype html><html lang="en">'+STYLE+'<title>FlakeTrace</title><h1>FlakeTrace</h1><p>Same-commit mixed-outcome candidates, not proof of a root cause.</p>', f'<p>{report["run_count"]} runs · {report["candidate_count"]} candidates</p>', '<div class="scroll"><table><tr><th>Commit / test</th><th>Pass / fail / skipped / missing</th><th>Observed failure rate</th><th>Candidate</th><th>Evidence by run</th></tr>']
    for r in report['tests']:
        rate = 'N/A' if r['observed_failure_rate'] is None else f'{r["observed_failure_rate"]:.1%}'
        links = ' · '.join(f'<a href="{o["evidence"]}">{esc(o["run"])}: {o["status"]}</a>' for o in r['outcomes'])
        page.append('<tr><td>'+esc(r['commit'])+'<br>'+esc(r['classname'])+' / '+esc(r['name'])+'</td><td>'+esc(list(r['counts'].values()))+'</td><td>'+rate+'</td><td>'+str(r['candidate'])+'</td><td>'+links+'</td></tr>')
    page.append('</table></div><p>Rate = fail / (pass + fail). Skipped and missing are excluded. Input order is not assumed chronological. Separate commits never share rates.</p></html>')
    evidence = ['<!doctype html><html lang="en">'+STYLE+'<title>FlakeTrace evidence</title><a href="index.html">Back to report</a><h1>Outcome evidence</h1>']
    for e in report['evidence']:
        evidence.append(f'<section id="{e["id"]}"><h2>{esc(e["run"])} · {esc(e["status"])}</h2><pre>{esc(json.dumps(e,indent=2))}</pre></section>')
    return ''.join(page), ''.join(evidence)+'</html>'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('--out', required=True, type=Path, help='new output directory')
    a = p.parse_args()
    try:
        report = analyze(load_runs(a.manifest))
        page, evidence = render(report)
        a.out.mkdir(parents=True, exist_ok=False)
        for name, content in [('report.json',json.dumps(report,indent=2)),('index.html',page),('evidence.html',evidence)]:
            (a.out/name).write_text(content,encoding='utf-8')
        print(f'{report["run_count"]} runs; {len(report["tests"])} commit/test groups; {report["candidate_count"]} candidates')
    except (ValueError, OSError, ET.ParseError) as e:
        p.exit(2, f'Error: {e}\n')


if __name__ == '__main__':
    main()
