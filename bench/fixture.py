"""Disposable native GUI with evaluator-only HTTP control on localhost:8093.

All actions affect this fixture only. /state is an answer key, never model input.
Run with the workspace Python. Reset using POST /reset?scenario=0.
"""
from __future__ import annotations
import json
import queue
import random
import threading
import time
import tkinter as tk
import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from PIL import Image, ImageDraw, ImageTk

TITLE = "CU-S1 Benchmark"
ctypes.windll.shcore.SetProcessDpiAwareness(2)
SCENARIOS = [
    {"name":"light", "bg":"#f3f5f8", "fg":"#182238", "target":"purple star", "text":"cedar-47", "finish":"Apply"},
    {"name":"dark", "bg":"#18222e", "fg":"#f1f4f9", "target":"green triangle", "text":"maple-83", "finish":"Continue"},
    {"name":"compact", "bg":"#fff4dc", "fg":"#2b2434", "target":"red circle", "text":"birch-26", "finish":"Confirm"},
]
SHAPES = [("purple star","#8b36d0"),("green triangle","#138d4c"),("red circle","#df343b"),
          ("blue diamond","#247ac6"),("orange plus","#d87719"),("gray square","#627080")]
root = tk.Tk()
root.title(TITLE)
root.geometry("1100x740+180+100")
root.resizable(False,False)
commands = queue.Queue()
events = []
images = []
selected = None
scenario_id = 0
completed = False
started = 0.0

def picture(name,color,size):
    im = Image.new("RGB",(size,size),"#ffffff")
    d = ImageDraw.Draw(im)
    p = int(size*.18); q = size-p; c = size/2
    if "circle" in name: d.ellipse((p,p,q,q),fill=color)
    elif "triangle" in name: d.polygon([(c,p),(q,q),(p,q)],fill=color)
    elif "diamond" in name: d.polygon([(c,p),(q,c),(c,q),(p,c)],fill=color)
    elif "plus" in name:
        d.rectangle((c-size*.1,p,c+size*.1,q),fill=color)
        d.rectangle((p,c-size*.1,q,c+size*.1),fill=color)
    elif "star" in name:
        import math
        pts = [(c+math.cos(-math.pi/2+k*math.pi/5)*(size*.35 if k%2==0 else size*.15),
                c+math.sin(-math.pi/2+k*math.pi/5)*(size*.35 if k%2==0 else size*.15)) for k in range(10)]
        d.polygon(pts,fill=color)
    else: d.rectangle((p,p,q,q),fill=color)
    return ImageTk.PhotoImage(im)

def choose(name):
    global selected
    selected = name
    events.append({"event":"select","value":name,"time":time.perf_counter()})
    status.config(text="Selected: "+name)

def finish():
    global completed
    s = SCENARIOS[scenario_id]
    completed = selected == s["target"] and entry.get() == s["text"]
    events.append({"event":"finish","success":completed,"text":entry.get(),"time":time.perf_counter()})
    status.config(text="COMPLETE" if completed else "Check your selection and note")

def reset(sid):
    global scenario_id, selected, completed, started, entry, status
    scenario_id = sid % len(SCENARIOS)
    selected = None; completed = False; started = time.perf_counter()
    events.clear(); images.clear()
    for child in root.winfo_children(): child.destroy()
    s = SCENARIOS[scenario_id]; bg=s["bg"]; fg=s["fg"]
    root.config(bg=bg)
    tk.Label(root,text="Visual task laboratory",font=("Segoe UI",25,"bold"),bg=bg,fg=fg).place(x=45,y=25)
    tk.Label(root,text="Choose an image, enter a note, then finish.",font=("Segoe UI",12),bg=bg,fg=fg).place(x=45,y=82)
    rng=random.Random(20261104+sid)
    shapes=SHAPES.copy(); rng.shuffle(shapes)
    small=scenario_id==2; size=62 if small else 90
    for i,(name,color) in enumerate(shapes):
        photo=picture(name,color,size); images.append(photo)
        x=70+(i%3)*(190 if small else 270); y=150+(i//3)*(115 if small else 155)
        tk.Button(root,image=photo,command=lambda n=name:choose(n),takefocus=False,
                  relief="flat",borderwidth=3).place(x=x,y=y)
    y=470 if scenario_id!=1 else 510
    tk.Label(root,text="Note",font=("Segoe UI",13,"bold"),bg=bg,fg=fg).place(x=70,y=y)
    entry=tk.Entry(root,font=("Segoe UI",16),width=36)
    entry.place(x=70,y=y+34,height=42)
    tk.Button(root,text=s["finish"],font=("Segoe UI",13),command=finish,takefocus=False).place(x=730,y=y+31,width=160,height=48)
    status=tk.Label(root,text="Ready",font=("Segoe UI",12),bg=bg,fg=fg)
    status.place(x=70,y=650)
    root.update_idletasks()
    root.lift(); root.focus_force()

def state():
    return {"scenario":scenario_id,"name":SCENARIOS[scenario_id]["name"],"selected":selected,
            "text":entry.get(),"completed":completed,"events":list(events),
            "elapsed_ms":(time.perf_counter()-started)*1000,
            "rect":[root.winfo_rootx(),root.winfo_rooty(),root.winfo_width(),root.winfo_height()],
            "steps":[{"do":f"Click the {SCENARIOS[scenario_id]['target']} image."},
                     {"do":"Click inside the Note text field."},
                     {"do":"Type: "+SCENARIOS[scenario_id]["text"]},
                     {"do":f"Click '{SCENARIOS[scenario_id]['finish']}'.","expect":"The status says COMPLETE."}]}

def drain():
    try:
        while True:
            operation,done,result=commands.get_nowait()
            try: result.append(operation())
            except Exception as exc: result.append({"error":str(exc)})
            finally: done.set()
    except queue.Empty: pass
    root.after(15,drain)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def handle_request(self):
        url=urlparse(self.path); query=parse_qs(url.query)
        if url.path=="/state": op=state
        elif url.path=="/reset" and self.command=="POST":
            sid=int(query.get("scenario",[0])[0]); op=lambda:(reset(sid),state())[1]
        else:
            self.send_error(404); return
        done=threading.Event(); result=[]; commands.put((op,done,result))
        if not done.wait(10): self.send_error(503); return
        payload=json.dumps(result[0]).encode()
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)

reset(0)
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1",8093),Handler).serve_forever,daemon=True).start()
root.after(15,drain)
root.mainloop()
