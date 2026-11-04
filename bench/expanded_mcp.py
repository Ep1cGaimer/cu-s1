"""Evaluate the real MCP on disposable browser/WinForms fixtures, without ground-truth leakage."""
import argparse,asyncio,json,os,time,base64,hashlib,sys
from pathlib import Path
import httpx
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from cu_s1.window import foreground,list_windows
from cu_s1.vlm import Vlm
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent

def source_hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'src/cu_s1').glob('*.py'))}

def summary(result):
    for item in result.content:
        if item.type=='text':
            try:
                obj=json.loads(item.text)
                if isinstance(obj,dict) and 'completed' in obj:return obj
            except ValueError:pass
    raise RuntimeError('MCP returned no chain summary')

async def main(args):
    port,title=(8095,'CU-S1 Native Benchmark') if args.surface=='native' else (8094,'CU-S1 Browser Benchmark')
    candidates=[w for w in list_windows() if w['title']==title]
    if len(candidates)!=1:raise RuntimeError('Expected exactly one owned fixture')
    hwnd=candidates[0]['hwnd']
    data={'surface':args.surface,'model':'qwen3-vl:2b-instruct','python':sys.version,
          'source_sha256':source_hashes(),'warmup_ms':0,'runs':[],
          'timing_scope':'Actual stdio run_steps call; excludes fixture reset, activation, warmup, parent planning and delegation generation.'}
    start=time.perf_counter()
    v=Vlm('qwen3-vl:2b-instruct')
    with Image.open(ROOT/'bench/cases/case00.png') as im:v.decide('Click the camera icon.',im)
    v.client.close();data['warmup_ms']=(time.perf_counter()-start)*1000
    params=StdioServerParameters(command=str(ROOT/'.venv/Scripts/python.exe'),args=['-m','cu_s1.server'],cwd=str(ROOT),
                                env={**os.environ,'CU_S1_MODEL':'qwen3-vl:2b-instruct','PYTHONUTF8':'1'})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=15) as fixture:
                for repeat in range(args.rounds):
                    for sid in range(3):
                        fixture.post(f'/reset?scenario={sid}').raise_for_status()
                        await asyncio.sleep(.35)
                        setup=fixture.get('/state').json()
                        print(f'Waiting for {title} foreground, scenario={sid}',flush=True)
                        deadline=time.monotonic()+45
                        while foreground()!=hwnd and time.monotonic()<deadline:await asyncio.sleep(.1)
                        start=time.perf_counter()
                        response=await client.call_tool('run_steps',{'target_hwnd':hwnd,'mode':'turbo','steps':setup['steps']})
                        wall=(time.perf_counter()-start)*1000
                        s=summary(response);actual=fixture.get('/state').json()
                        for item in response.content:
                            if item.type=='image':
                                image_path=args.out.with_name(args.out.stem+f'-{repeat}-{sid}.png')
                                image_path.write_bytes(base64.b64decode(item.data))
                        row={'scenario':sid,'repeat':repeat,'wall_ms':wall,'actual_success':actual['completed'],
                             'claimed_success':s['ok'],'summary':s,'events':actual['events'],
                             'modal_open':actual.get('modal_open')}
                        data['runs'].append(row)
                        args.out.parent.mkdir(parents=True,exist_ok=True)
                        args.out.write_text(json.dumps(data,indent=2),encoding='utf-8')
                        print(json.dumps({k:v for k,v in row.items() if k not in ('summary','events')}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--surface',choices=['native','edge'],required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--rounds',type=int,default=1)
    asyncio.run(main(p.parse_args()))
