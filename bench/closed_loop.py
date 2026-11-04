"""Run the real pixel/input executor against the disposable benchmark fixture.

Fixture ground truth is used ONLY for reset, capture bounds and scoring.
The decision model receives screenshots and step instructions, never event state.
"""
import argparse
import ctypes
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
import httpx
import mss
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"src"))
from cu_s1.runner import Step,run_steps
from cu_s1.screen import Frame
from cu_s1.verify import changed_fraction
from cu_s1.vlm import Vlm

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("model"); p.add_argument("--url"); p.add_argument("--out",type=Path,required=True)
    p.add_argument("--rounds",type=int,default=1)
    args=p.parse_args()
    c=httpx.Client(base_url="http://127.0.0.1:8093",timeout=15)
    vlm=Vlm(args.model,base_url=args.url,timeout=90)
    user32=ctypes.windll.user32
    user32.FindWindowW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p]
    user32.FindWindowW.restype=ctypes.c_void_p
    user32.GetForegroundWindow.restype=ctypes.c_void_p
    user32.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]
    user32.GetAncestor.restype=ctypes.c_void_p
    runs=[]
    for repeat in range(args.rounds):
        for sid in range(3):
            seed_sid=sid+3*repeat
            fixture=c.post(f"/reset?scenario={seed_sid}").json()
            x,y,w,h=fixture["rect"]
            hwnd=ctypes.windll.user32.FindWindowW(None,"CU-S1 Benchmark")
            def guard():
                active=ctypes.windll.user32.GetForegroundWindow()
                return ctypes.windll.user32.GetAncestor(active,2)==ctypes.windll.user32.GetAncestor(hwnd,2)
            def capture():
                if not guard(): raise RuntimeError("Fixture is not foreground; refusing to capture another app")
                with mss.mss() as sct:
                    shot=sct.grab({"left":x,"top":y,"width":w,"height":h})
                return Frame(Image.frombytes("RGB",shot.size,shot.bgra,"raw","BGRX"),x,y)
            print(f"Waiting for fixture foreground (scenario {sid})",flush=True)
            deadline=time.monotonic()+45
            while not guard() and time.monotonic()<deadline:
                time.sleep(.1)
            def stable(before):
                last=before; start=time.perf_counter()
                while time.perf_counter()-start<1.5:
                    time.sleep(.08); cur=capture()
                    if changed_fraction(last.image,cur.image)<.0002 and time.perf_counter()-start>.2:
                        return cur
                    last=cur
                return last
            r=run_steps([Step(**s) for s in fixture["steps"]],vlm,"turbo",capture_fn=capture,stable_fn=stable,input_guard=guard)
            actual=c.get("/state").json()
            row={"scenario":sid,"seed":seed_sid,"repeat":repeat,"actual_success":actual["completed"],
                 "claimed_success":r.ok,"total_ms":r.total_ms,"completed":r.completed,"handback":r.handback,
                 "steps":[asdict(s) for s in r.steps],"events":actual["events"]}
            runs.append(row); print(json.dumps(row),flush=True)
            args.out.parent.mkdir(parents=True,exist_ok=True)
            args.out.write_text(json.dumps({"model":args.model,"runs":runs},indent=2),encoding="utf-8")

if __name__=="__main__": main()
