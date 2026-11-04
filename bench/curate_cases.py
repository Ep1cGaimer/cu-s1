"""Preserve the historical manifest; create an audited subset plus absent-target probes."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
cases=json.loads((HERE/'cases/cases.json').read_text(encoding='utf-8'))
# Calculator MC and memory flyout have no saved memory and are disabled. Notepad has a blocking modal;
# only its OK control is actionable. "System" is an invisible app/system-menu control.
excluded={'real02','real03','real16','real18','real19','real20','real21','real22','real23'}
audited=[c for c in cases if c['id'] not in excluded]
(HERE/'cases/audited.json').write_text(json.dumps(audited,indent=2),encoding='utf-8')
absent=[{'id':f'absent{i:02d}','image':c['image'],'instruction':"Click the button labeled 'ZEBRA-9QX'.",
         'kind':'absent','absent':True} for i,c in enumerate(cases[:10])]
(HERE/'cases/absent.json').write_text(json.dumps(absent,indent=2),encoding='utf-8')
(HERE/'cases/audit.json').write_text(json.dumps({'excluded_ids':sorted(excluded),
    'reason':'Disabled memory-clear/flyout controls; Notepad controls blocked by modal or invisible system menu',
    'historical_count':len(cases),'audited_count':len(audited)},indent=2),encoding='utf-8')
print(f'Audited {len(audited)}/{len(cases)} historical cases; {len(absent)} absent-target cases')
