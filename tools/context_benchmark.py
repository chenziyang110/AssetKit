#!/usr/bin/env python3
"""Measure actual fixed CLI transcripts, not LLM behavior or provider billing.

Runtime has no tokenizer dependency. Development-only --tokenizers optionally
uses pinned tiktoken to count visible strings in multiple named encodings.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENCODINGS = ('cl100k_base', 'o200k_base')


def call(repo: Path, project: Path, script: str, *args: str) -> tuple[dict, str]:
    proc = subprocess.run([sys.executable, '-B', '-S', str(repo/'skills/assetkit/scripts'/script),
                           '--root', str(project), *args], capture_output=True, text=True, encoding='utf-8',
                          env={**os.environ, 'PYTHONUTF8': '1'})
    if proc.returncode:
        raise RuntimeError(proc.stdout + proc.stderr)
    return json.loads(proc.stdout), proc.stdout


def fixture(repo: Path, project: Path) -> list[dict]:
    project.mkdir()
    call(repo, project, 'assetctl.py', 'init')
    config = project/'.assets/config.json'
    data = json.loads(config.read_text(encoding='utf-8'))
    data['project_id'] = '12345678-1234-5678-1234-567812345678'
    config.write_text(json.dumps(data), encoding='utf-8')
    (project/'docs').mkdir()
    cards = []
    for i in range(3):
        path = f'docs/hero{i}.md'
        (project/path).write_text('Hero fixture '+str(i), encoding='utf-8')
        data, _ = call(repo, project, 'assetctl.py', 'capture', path, '--use', '首页 hero 主视觉方案 '+str(i))
        item = data['items'][0]
        changes = {'status':'ready', 'source':{'kind':'authored','ref':'benchmark fixture'},
                   'rights':{'status':'restricted','license':'internal-test'},
                   'reviewed_by':'fixture','review_evidence':'synthetic benchmark only',
                   'restrictions':['不可用于对外广告']}
        call(repo, project, 'assetctl.py', 'patch', item['id'], '--expect-revision','1', '--patch', json.dumps(changes))
        cards.append(item)
    call(repo, project, 'assetctl.py', 'find', 'hero')  # Warm both equally; setup excluded.
    return cards


def measure(events: list[tuple[str, str]], counters: dict) -> dict:
    inputs = [v[0] for v in events]; outputs = [v[1] for v in events]
    value = {'cli_calls':len(events), 'input_bytes':sum(len(v.encode()) for v in inputs),
             'output_bytes':sum(len(v.encode()) for v in outputs)}
    if counters:
        value['tokens'] = {name:{'input':sum(count(v) for v in inputs),
                                'output':sum(count(v) for v in outputs),
                                'visible_total':sum(count(v) for pair in events for v in pair)}
                           for name,count in counters.items()}
    return value


def static(repo: Path, counters: dict) -> dict:
    skill = (repo/'skills/assetkit/SKILL.md').read_text(encoding='utf-8')
    entry = (repo/'skills/assetkit/assets/project-entry.md').read_text(encoding='utf-8').replace('{{SKILL_PATH}}','.agents/skills/assetkit')
    description = re.search(r'^description: (.+)$',skill,re.M).group(1)
    return {key:{'bytes':len(text.encode()), **({'tokens':{name:count(text) for name,count in counters.items()}} if counters else {})}
            for key,text in [('routing_description',description),('skill_file',skill),('project_entry',entry)]}


def run(baseline: Path, counters: dict) -> dict:
    scenarios: dict = {}
    with tempfile.TemporaryDirectory(prefix='assetkit-cost-') as tmp:
        base = Path(tmp).resolve()
        for label, repo, modern in [('v1.0.0',baseline,False),('v1.1.0',ROOT,True)]:
            project = base/label
            cards = fixture(repo,project)
            script = 'agent.py' if modern else 'assetctl.py'
            command = 'python .assets/ak.py' if modern else 'python .agents/skills/assetkit/scripts/assetctl.py'
            traces: dict[str,list] = {}
            data,text = call(repo,project,script,'find','hero', '--limit','3')
            events = [(command+' find hero --limit 3',text)]
            if modern:
                assert len(data['items'])==3 and all(x['usable'] for x in data['items'])
                assert all(x['restrictions']==['不可用于对外广告'] for x in data['items'])
            else:
                for item in data['items']:
                    detail,text=call(repo,project,script,'resolve',item['id'])
                    assert detail['usable'] and detail['restrictions']==['不可用于对外广告']
                    events.append((command+' resolve '+item['id'],text))
            traces['compare_three_checked_candidates']=events
            ref='@'+cards[0]['id'][4:12] if modern else cards[0]['id']
            data,text=call(repo,project,script,'get' if modern else 'resolve',ref)
            assert data['usable']
            traces['known_asset']=[(command+(' get ' if modern else ' resolve ')+ref,text)]
            data,text=call(repo,project,script,'find','nonexistent-query')
            assert data['items']==[]
            traces['no_match']=[(command+' find nonexistent-query',text)]
            (project/'new.md').write_text('Retained new result',encoding='utf-8')
            data,text=call(repo,project,script,'put' if modern else 'capture','new.md','--use','产品说明')
            assert data['ok']
            traces['capture_one']=[(command+(' put ' if modern else ' capture ')+'new.md --use "产品说明"',text)]
            batch='\n'.join(json.dumps({'path':f'docs/note{i}.md','use':'可复用笔记'},ensure_ascii=False,separators=(',',':')) for i in range(20))+'\n'
            for i in range(20): (project/f'docs/note{i}.md').write_text(str(i),encoding='utf-8')
            request=project/'requests.jsonl';request.write_text(batch,encoding='utf-8')
            for task in ['capture_batch20','unchanged_batch20']:
                data,text=call(repo,project,script,'put' if modern else 'capture','--batch',str(request))
                assert data['ok']
                if modern:
                    assert data['created' if task=='capture_batch20' else 'unchanged']==20
                traces[task]=[(batch+command+(' put ' if modern else ' capture ')+'--batch requests.jsonl',text)]
            for task,events in traces.items():
                scenarios.setdefault(task,{})[label]=measure(events,counters)
        # Fail if the lean interface merely moved more text into normal replies.
        for task, metrics in scenarios.items():
            old=metrics['v1.0.0'];new=metrics['v1.1.0']
            assert new['output_bytes'] < old['output_bytes'], task
            metrics['output_byte_reduction_pct']=round(100*(1-new['output_bytes']/old['output_bytes']),2)
    return {'baseline':'v1.0.0 @ 29dc7a762e9cfca7cbb48bc2ed6b08f70c7ceae5',
            'version':(ROOT/'VERSION').read_text().strip(),
            'static':{'v1.0.0':static(baseline,counters),'v1.1.0':static(ROOT,counters)},
            'scenarios':scenarios,
            'scope':'Fixed CLI transcripts with synthetic assets, not live LLM tasks. Input includes command text and JSONL batch content; output is actual stdout. Static text is reported separately, not counted twice. Setup excluded. Counts exclude tool/chat wrappers, reasoning, model output, cache pricing and repeated history replay. CLI calls are not necessarily model turns; a host may group commands. Batch task requires acknowledgement, not every ID. Two tiktoken encodings are reference measurements, not Claude or a universal tokenizer.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--tokenizers',action='store_true')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    counters={}
    if args.tokenizers:
        import tiktoken
        for name in ENCODINGS:
            encoding=tiktoken.get_encoding(name)
            counters[name]=lambda text,enc=encoding:len(enc.encode(text,disallowed_special=()))
    result=run(args.baseline.resolve(),counters)
    if counters:
        for name,count in counters.items():
            skill=(ROOT/'skills/assetkit/SKILL.md').read_text(encoding='utf-8')
            assert count(skill)<=850, f'{name}: Skill file exceeded activation token budget'
            assert result['static']['v1.1.0']['routing_description']['tokens'][name]<=90
            assert result['static']['v1.1.0']['project_entry']['tokens'][name]<=90
    output=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(output,encoding='utf-8')
    print(output,end='')

if __name__=='__main__': main()
