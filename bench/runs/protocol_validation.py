"""Real MCP transport, synthetic worker only. Never captures or controls the desktop."""
import argparse,asyncio,json,os,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

if '--server' in sys.argv:
    from cu_s1 import server
    from cu_s1.runner import ChainResult
    class SyntheticTarget:
        def __init__(self,*args):pass
        def guard(self):return True
        def capture(self):raise AssertionError('Synthetic test must never capture')
    def synthetic_runner(steps,vlm,mode,**kw):
        if steps[0].do=='fast':return ChainResult(ok=True,completed=1,total=1)
        deadline=time.monotonic()+5
        while kw['input_guard']() and time.monotonic()<deadline:time.sleep(.01)
        if kw['input_guard']():raise RuntimeError('No stop received')
        try:kw['capture_fn']()
        except RuntimeError as e:
            if 'stopped before capture' not in str(e):raise
        else:raise AssertionError('Capture guard failed')
        return ChainResult(ok=False,completed=0,total=1,handback='synthetic worker stopped before capture/input')
    server.WindowTarget=SyntheticTarget
    server.run_steps=synthetic_runner
    server.main()
else:
    from mcp import ClientSession,StdioServerParameters,types
    from mcp.client.stdio import stdio_client
    def value(r):return next(json.loads(c.text) for c in r.content if c.type=='text')
    async def main():
        params=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).resolve()),'--server'],cwd=str(ROOT),env={**os.environ,'PYTHONUTF8':'1'})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                first=asyncio.create_task(client.call_tool('run_steps',{'steps':[{'do':'wait for stop'}],'target_hwnd':123}))
                await asyncio.sleep(.3)
                busy=await client.call_tool('run_steps',{'steps':[{'do':'fast'}],'target_hwnd':123})
                assert busy.isError
                stopped=value(await client.call_tool('stop',{}));assert stopped['active'] and stopped['stop_requested']
                outcome=value(await asyncio.wait_for(first,2));assert not outcome['ok'] and 'stopped before capture' in outcome['handback']
                canceled=asyncio.create_task(client.call_tool('run_steps',{'steps':[{'do':'wait for host cancellation'}],'target_hwnd':123}))
                await asyncio.sleep(.3)
                # A local Python task cancellation does not emit a protocol
                # cancellation in MCP1.30. Exercise the host notification itself.
                request_id=next(iter(client._response_streams))
                await client.send_notification(types.ClientNotification(types.CancelledNotification(
                    params=types.CancelledNotificationParams(requestId=request_id,reason='synthetic host cancellation'))))
                try:await canceled
                except Exception:pass  # The protocol sends a Request cancelled error.
                await asyncio.sleep(.25)
                idle=value(await client.call_tool('stop',{}))
                assert not idle['active'], 'Host cancellation did not release synthetic worker'
                next_result=value(await client.call_tool('run_steps',{'steps':[{'do':'fast'}],'target_hwnd':123}))
                assert next_result['ok']
        data={'scope':'Actual stdio transport with synthetic target and runner; no desktop metadata/capture/input or model requests',
              'concurrent_chain_rejected':True,'stop_processed_during_running_chain':True,
              'new_capture_blocked_after_stop':True,'host_cancellation_signaled_worker':True,
              'worker_cleanup_allows_next_chain':True}
        (ROOT/'bench/runs/mcp-cancellation-v7.json').write_text(json.dumps(data,indent=2));print(json.dumps(data))
    asyncio.run(main())
