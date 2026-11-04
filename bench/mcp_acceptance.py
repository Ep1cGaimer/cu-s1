"""Exercise the real stdio MCP protocol and optionally the disposable fixture."""
import argparse,asyncio,json,os,time
from pathlib import Path
import httpx
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parent.parent

def summary(result):
    for content in result.content:
        if content.type=='text':
            try:
                parsed=json.loads(content.text)
                if isinstance(parsed,dict) and 'completed' in parsed: return parsed
            except ValueError: pass
    raise ValueError('No chain summary in MCP response')

async def run(exercise, out, protocol_only=False):
    params=StdioServerParameters(command=str(ROOT/'.venv/Scripts/python.exe'),args=['-m','cu_s1.server'],
        cwd=str(ROOT),env={**os.environ,'CU_S1_MODEL':'qwen3-vl:2b-instruct','PYTHONUTF8':'1'})
    results={'tools':[],'runs':[]}
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            results['tools']=[t.name for t in (await client.list_tools()).tools]
            assert set(results['tools'])=={'run_steps','windows','look','stop'}
            stopped=await client.call_tool('stop',{})
            stop_result=next(json.loads(c.text) for c in stopped.content if c.type=='text')
            assert stop_result=={'active':False,'stop_requested':False}
            results['idle_stop']=True
            if not protocol_only:
                risk=await client.call_tool('run_steps',{'steps':[{'do':'Do not execute this test step','risky':True}]})
                assert summary(risk)['steps'][0]['status']=='needs_confirmation'
                invalid=await client.call_tool('run_steps',{'steps':[{'do':'test','risky':True,'confirmed':'false'}]})
                assert invalid.isError
                results.update(risky_gate=True,strict_confirmation=True)
            if exercise:
                from cu_s1.window import foreground,list_windows
                candidates=[w for w in list_windows() if w['title']=='CU-S1 Benchmark']
                assert len(candidates)==1
                hwnd=candidates[0]['hwnd']
                with httpx.Client(base_url='http://127.0.0.1:8093') as fixture:
                    for sid in range(3):
                        setup=fixture.post(f'/reset?scenario={sid}').json()
                        print(f'Waiting for fixture foreground scenario={sid}',flush=True)
                        deadline=time.monotonic()+45
                        while foreground()!=hwnd and time.monotonic()<deadline: await asyncio.sleep(.1)
                        start=time.perf_counter()
                        result=await client.call_tool('run_steps',{'steps':setup['steps'],'mode':'turbo','target_hwnd':hwnd})
                        wall=(time.perf_counter()-start)*1000
                        s=summary(result);actual=fixture.get('/state').json()
                        row={'scenario':sid,'wall_ms':wall,'actual_success':actual['completed'],
                             'summary':s,'events':actual['events']}
                        results['runs'].append(row)
                        print(json.dumps({k:v for k,v in row.items() if k not in ('summary','events')}),flush=True)
                    fixture.post('/reset?scenario=12')
                    result=await client.call_tool('run_steps',{'steps':[{'do':"Click the button labeled 'ZEBRA-9QX'."}],
                                               'mode':'turbo','target_hwnd':hwnd})
                    absent=summary(result);actual=fixture.get('/state').json()
                    results['absent']={'summary':absent,'events':actual['events']}
                    assert not actual['events'] and absent['completed']==0 and not absent['ok']
            out.write_text(json.dumps(results,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in results.items() if k not in ('runs','absent')}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--exercise-fixture',action='store_true')
    p.add_argument('--out',type=Path,default=ROOT/'bench/runs/mcp-acceptance.json')
    p.add_argument('--protocol-only',action='store_true',help='List tools and call idle stop only; no window metadata, capture or input')
    args=p.parse_args()
    if args.protocol_only and args.exercise_fixture:p.error('--protocol-only cannot exercise a fixture')
    asyncio.run(run(args.exercise_fixture,args.out,args.protocol_only))
