"""Evaluate visibility predicates before integrating a missing-target guard."""
import argparse,json,sys,statistics
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
from cu_s1.vlm import Vlm

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('model');p.add_argument('--url')
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    v=Vlm(args.model,base_url=args.url)
    cases=[]
    for manifest in ('audited.json','absent.json'):
        data=json.loads((ROOT/'bench/cases'/manifest).read_text())
        cases+=data if manifest=='absent.json' else data[::3]
    rows=[]
    for c in cases:
        with Image.open(ROOT/'bench/cases'/c['image']) as im:
            im=im.convert('RGB');im.thumbnail((1280,1280))
            statement=(f"The target requested by this command is actually visible in this screenshot: {c['instruction']} "
                       "The target must match the requested label or icon, not just be a nearby or similar control.")
            ok,ms=v.check(statement,im)
        row={'id':c['id'],'present':ok,'expected_present':not c.get('absent',False),'correct':ok != c.get('absent',False),'ms':ms}
        rows.append(row);print(json.dumps(row),flush=True)
    result={'model':args.model,'rows':rows,'accuracy':sum(r['correct'] for r in rows)/len(rows),
            'median_ms':statistics.median(r['ms'] for r in rows)}
    args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')

if __name__=='__main__':main()
