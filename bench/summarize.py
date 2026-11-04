"""Regenerate scored summaries from immutable predictions and the final audited manifest."""
import json,math,statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
RUNS=HERE/'runs'

def load(name): return json.loads((RUNS/name).read_text(encoding='utf-8'))

def main():
    ids={c['id'] for c in json.loads((HERE/'cases/audited.json').read_text())}
    candidates=[('Qwen3-VL 2B instruct / Ollama','qwen-audited-json.json'),
                ('GUI-Owl 1.5 2B Q4_K_M / llama.cpp CUDA','guiowl-audited-json-1024.json'),
                ('UI-Venus 1.5 2B Q4_K_M / llama.cpp CUDA','uivenus-audited-json-1024.json')]
    summary={'grounding':[]}
    for name,file in candidates:
        d=load(file);rows=[r for r in d['cases'] if r['id'] in ids]
        assert len(rows)==len(ids)
        lat=sorted(r['latency_ms'] for r in rows)
        row={'name':name,'source':file,'correct':sum(r['hit'] for r in rows),'count':len(rows),
             'median_ms':statistics.median(lat),'p90_ms':lat[math.ceil(.9*len(lat))-1],
             'failures':[r['id'] for r in rows if not r['hit']]}
        row['hit_rate']=row['correct']/row['count'];summary['grounding'].append(row)
    for key,file,field in [('builtin','builtin-sky-baseline.json','wall_ms'),
                           ('local_mcp','mcp-acceptance.json','wall_ms'),
                           ('local_heldout','qwen-guarded-heldout.json','total_ms')]:
        runs=load(file)['runs'];values=[r[field] for r in runs]
        summary[key]={'count':len(runs),'successes':sum(r.get('actual_success',r.get('success',False)) for r in runs),
                      'median_ms':statistics.median(values),'min_ms':min(values),'max_ms':max(values)}
    summary['observed_speedup']=summary['builtin']['median_ms']/summary['local_mcp']['median_ms']
    summary['scope']='Three four-action native fixture tasks. Parent planning/prompt and setup time excluded for both; built-in wall includes parent model reasoning and tool orchestration. Not a universal computer-use ranking.'
    (RUNS/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
