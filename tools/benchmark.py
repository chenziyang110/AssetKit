#!/usr/bin/env python3
"""Reproducible synthetic benchmark. Run separately from user's asset workspace."""
from __future__ import annotations
import argparse
import contextlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import uuid

SCRIPTS=Path(__file__).resolve().parents[1]/'skills/assetkit/scripts'
sys.path.insert(0,str(SCRIPTS))
sys.dont_write_bytecode=True
import ledger
import catalog


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=int,default=10000)
    parser.add_argument('--runs',type=int,default=10)
    parser.add_argument('--output')
    args=parser.parse_args()
    if not 1<=args.records<=100000 or not 3<=args.runs<=100: parser.error('records=1..100000; runs=3..100')
    with tempfile.TemporaryDirectory(prefix='assetkit-benchmark-') as temp:
        root=Path(temp)
        ledger.execute(ledger.parser().parse_args(['--root',str(root),'init']))
        (root/'fixture.md').write_text('synthetic benchmark, not a real project',encoding='utf-8')
        file=ledger.inspect_file(root,{'path':'fixture.md','role':'primary'})
        file['stat']=catalog.signature(root/'fixture.md')
        for i in range(args.records):
            ident='ast_'+uuid.uuid5(uuid.NAMESPACE_URL,f'assetkit-benchmark-{i}').hex
            card={'schema_version':1,'id':ident,'revision':1,'logical_key':f'benchmark/asset-{i:06}',
                  'content_mode':'live','content_version':0,'type':'document','domain':'benchmark',
                  'title':f'Asset {i}','summary':'首页 reusable hero fixture '+str(i),'use_when':['benchmark only'],
                  'status':'candidate','storage_policy':'in-place','files':[file],
                  'source':{'kind':'unknown','ref':'synthetic fixture'},'rights':{'status':'unknown','license':'unknown'},
                  'created_at':'2026-01-01T00:00:00Z','updated_at':'2026-01-01T00:00:00Z',
                  'request_key':str(i),'request_fingerprint':'synthetic'}
            ledger.card_path(root,ident).write_bytes(ledger.encoded(card))
        def run(script,parameters):
            start=time.perf_counter()
            proc=subprocess.run([sys.executable,'-B','-S',str(SCRIPTS/script),'--root',str(root),*parameters],
                                capture_output=True,check=True)
            return (time.perf_counter()-start)*1000,proc.stdout,json.loads(proc.stdout)
        cold,_,_=run('assetctl.py',['find','首页'])
        warm=[]; legacy=[]
        for _ in range(args.runs):
            duration,out,result=run('assetctl.py',['find','首页'])
            warm.append(duration)
            if result['index']['record_files_read']!=0: raise AssertionError('warm query read card files')
        for _ in range(3):
            duration,_,_=run('ledger.py',['search','首页','--status','all']); legacy.append(duration)
        percentile=lambda x:sorted(x)[max(0,__import__('math').ceil(len(x)*0.95)-1)]
        result={'fixture_records':args.records,'runs':args.runs,'python':platform.python_version(),'platform':platform.system(),
                'cold_find_ms':round(cold,2),'warm_find_p50_ms':round(statistics.median(warm),2),
                'warm_find_p95_ms':round(percentile(warm),2),'legacy_search_p50_ms':round(statistics.median(legacy),2),
                'warm_response_bytes':len(out),'warm_record_files_read':0,
                'scope':'Synthetic tiny records sharing one small file; includes interpreter startup. Not an engine benchmark, production SLA, or model-token benchmark.'}
        text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
        if args.output: Path(args.output).write_text(text,encoding='utf-8')
        print(text)

if __name__=='__main__': main()
