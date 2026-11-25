"""Prints a results file from run.sh as one line per scenario window."""
import json,sys
for line in open(sys.argv[1]):
    if not line.startswith('{'): continue
    d=json.loads(line); w=d['result']['windows']
    print('==',d['scenario'])
    for win in ('before','fault','after'):
        x=w[win]; parts=[]
        for k in ('victim:async','victim:thread','victim:click','victim:token','health','attack'):
            if k in x:
                v=x[k]; st=','.join(f'{s}:{n}' for s,n in sorted(v['status'].items()))
                parts.append(f"{k.split(':')[-1]} p50={v['p50']} p95={v['p95']} max={v['max']} [{st}]")
        print(f"  {win:6} thr={x['threads_max']}  " + " | ".join(parts))
