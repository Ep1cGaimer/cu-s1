"""Disposable seeded holdout GUI. Evaluator routes are not model observations.

Start separately: python bench/holdout_fixture.py. POST /reset?scenario=0..2&seed=N;
GET /state returns independent scoring. Seeds 0,1 are development; 8,19,31 are holdout.
"""
from __future__ import annotations
import ctypes
import json
import math
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from PIL import Image, ImageDraw, ImageTk

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

TITLE = 'CU-S1 Holdout Benchmark'
root = tk.Tk()
root.title(TITLE)
root.resizable(False, False)
commands = queue.Queue()
events = []
images = []
scenario = seed = 0
completed = False
started = 0.0
steps = []
selected = None
entry = None
status = None


def event(name, value=None):
    events.append({'event': name, 'value': value, 'time': time.time()})


def finish(success):
    global completed
    completed = bool(success)
    event('submit', completed)
    status.config(text='COMPLETE' if completed else 'Please review the selection')


def button(parent, text, command, **kw):
    return tk.Button(parent, text=text, command=command, takefocus=False, **kw)


def reset(sid, seed_value):
    global scenario, seed, completed, started, selected, steps, entry, status
    scenario, seed = sid, seed_value
    completed, selected, entry = False, None, None
    started = time.perf_counter()
    events.clear()
    images.clear()
    for child in root.winfo_children():
        child.destroy()
    rng = random.Random(seed_value * 997 + sid * 71 + 42013)
    width, height = rng.choice([(960, 620), (990, 640), (940, 630)])
    root.geometry(f'{width}x{height}+{rng.choice([35, 55, 75])}+{rng.choice([25, 45, 65])}')
    bg, fg, accent = rng.choice([('#edf3f5', '#132732', '#d1e2eb'),
                                 ('#f7f2e9', '#302820', '#eadac7'),
                                 ('#f1eff8', '#292337', '#ddd8ef')])
    family = rng.choice(['Segoe UI', 'Arial', 'Calibri'])
    size = rng.choice([11, 12, 13])
    root.configure(bg=bg)
    title = tk.Label(root, text=['Record archive', 'Delivery settings', 'Symbol registration'][sid],
                     bg=bg, fg=fg, font=(family, size + 9, 'bold'))
    title.place(x=35, y=20)
    status = tk.Label(root, text='Ready', bg=bg, fg=fg, font=(family, size + 1, 'bold'))
    status.place(x=40, y=height - 48)
    if sid == 0:
        build_records(rng, bg, fg, accent, family, size)
    elif sid == 1:
        build_tabs(rng, bg, fg, family, size)
    else:
        build_symbols(rng, bg, fg, accent, family, size)
    root.update_idletasks()
    return state()


def build_records(rng, bg, fg, accent, family, size):
    global steps
    labels = ['LARK-51', 'LARK-15', 'LARK-57', 'LARK-75', 'LARK-35', 'LARK-53',
              'LARK-58', 'LARK-85', 'LARK-25', 'LARK-52', 'LARK-37', 'LARK-73']
    rng.shuffle(labels)
    # The desired record is always visible after scrolling to the bottom.
    target = rng.choice(labels[-3:])
    tk.Label(root, text='Choose one record from the archive, then save.', bg=bg, fg=fg,
             font=(family, size)).place(x=40, y=75)
    canvas = tk.Canvas(root, width=650, height=320, bg=accent, highlightthickness=1)
    canvas.place(x=40, y=120)
    scroll = tk.Scrollbar(root, orient='vertical', command=canvas.yview)
    scroll.place(x=690, y=120, height=322)
    canvas.configure(yscrollcommand=scroll.set)
    inside = tk.Frame(canvas, bg=accent)
    canvas.create_window((0, 0), window=inside, anchor='nw', width=645)
    def wheel(e):
        canvas.yview_scroll(-int(e.delta / 120), 'units')
        event('scroll')
        return 'break'
    canvas.bind('<MouseWheel>', wheel)
    inside.bind('<MouseWheel>', wheel)
    def select(label):
        global selected
        selected = label
        event('select_record', label)
        selection.config(text='Record selected')
    for label in labels:
        row = tk.Frame(inside, bg=accent, height=58)
        row.pack(fill='x', padx=8, pady=2)
        row.pack_propagate(False)
        name = tk.Label(row, text=label, bg=accent, fg=fg, font=(family, size, 'bold'))
        name.pack(side='left', padx=18)
        b = button(row, 'Select ' + label, lambda value=label: select(value), font=(family, size))
        b.pack(side='right', padx=20)
        for widget in (row, name, b): widget.bind('<MouseWheel>', wheel)
    inside.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox('all'))
    selection = tk.Label(root, text='No record selected', bg=bg, fg=fg, font=(family, size))
    selection.place(x=40, y=462)
    button(root, 'Save record', lambda: finish(selected == target), font=(family, size)).place(x=520, y=460, width=170, height=45)
    steps = [{'do': 'Scroll to the bottom of the archive records pane.'},
             {'do': f'Click Select {target}.'},
             {'do': 'Click Save record.', 'expect': 'The status says COMPLETE.'}]


def build_tabs(rng, bg, fg, family, size):
    global steps
    modes = ['Economy', 'Express', 'Standard']
    rng.shuffle(modes)
    target = rng.choice(modes)
    names = ['Overview', 'Delivery', 'Account']
    rng.shuffle(names)
    notebook = ttk.Notebook(root)
    notebook.place(x=40, y=105, width=690, height=330)
    variable = tk.StringVar(value='')
    for name in names:
        pane = tk.Frame(notebook, bg=bg)
        notebook.add(pane, text=name)
        if name == 'Delivery':
            tk.Label(pane, text='Choose a delivery mode', bg=bg, fg=fg, font=(family, size + 1, 'bold')).pack(anchor='w', padx=25, pady=20)
            for mode in modes:
                radio = tk.Radiobutton(pane, text=mode, value=mode, variable=variable, bg=bg, fg=fg,
                    selectcolor='white', font=(family, size), command=lambda m=mode: event('choose_mode', m))
                radio.pack(anchor='w', padx=35, pady=8)
        else:
            tk.Label(pane, text=name + ' settings', bg=bg, fg=fg, font=(family, size)).pack(padx=25, pady=25)
    notebook.select(names.index('Overview'))
    notebook.bind('<<NotebookTabChanged>>', lambda e: event('tab', notebook.tab(notebook.select(), 'text')))
    button(root, 'Apply settings', lambda: finish(variable.get() == target), font=(family, size)).place(x=530, y=465, width=190, height=45)
    steps = [{'do': 'Click the Delivery tab.'}, {'do': f'Select the {target} radio option.'},
             {'do': 'Click Apply settings.', 'expect': 'The status says COMPLETE.'}]


def shape_picture(shape, color, bg, size):
    im = Image.new('RGB', (size, size), bg)
    draw = ImageDraw.Draw(im)
    a, b, mid = size * .2, size * .8, size * .5
    if shape == 'circle': draw.ellipse((a, a, b, b), fill=color)
    elif shape == 'square': draw.rectangle((a, a, b, b), fill=color)
    elif shape == 'diamond': draw.polygon([(mid, a), (b, mid), (mid, b), (a, mid)], fill=color)
    else: draw.polygon([(mid, a), (b, b), (a, b)], fill=color)
    return ImageTk.PhotoImage(im)


def build_symbols(rng, bg, fg, accent, family, size):
    global steps, entry
    shapes = ['circle', 'square', 'diamond', 'triangle']
    rng.shuffle(shapes)
    target = rng.choice(shapes)
    color_name, color = rng.choice([('blue', '#165aa1'), ('purple', '#713cac'), ('green', '#16804d')])
    code = rng.choice(['orbit-64', 'harbor-29', 'cobalt-71', 'quartz-48'])
    tk.Label(root, text='Select one symbol and enter its registration code.', bg=bg, fg=fg,
             font=(family, size)).place(x=40, y=75)
    def select(shape):
        global selected
        selected = shape
        event('select_symbol', shape)
        selection.config(text='Symbol selected')
    side = rng.choice([80, 90, 100])
    for index, shape in enumerate(shapes):
        photo = shape_picture(shape, color, 'white', side)
        images.append(photo)
        button(root, '', lambda s=shape: select(s), image=photo, bg='white').place(x=55 + index * 150, y=135)
    selection = tk.Label(root, text='No symbol selected', bg=bg, fg=fg, font=(family, size))
    selection.place(x=50, y=270)
    tk.Label(root, text='Registration code', bg=bg, fg=fg, font=(family, size)).place(x=50, y=330)
    entry = tk.Entry(root, font=(family, size + 2), width=28)
    entry.place(x=50, y=365, height=40)
    button(root, 'Submit registration', lambda: finish(selected == target and entry.get() == code), font=(family, size)).place(x=500, y=365, width=210, height=45)
    steps = [{'do': f'Click the {color_name} {target} image.'}, {'do': 'Click the Registration code text field.'},
             {'do': f'Type: {code}'}, {'do': 'Click Submit registration.', 'expect': 'The status says COMPLETE.'}]


def state():
    return {'scenario': scenario, 'seed': seed, 'completed': completed, 'events': list(events),
            'steps': steps, 'selected': selected, 'text': entry.get() if entry is not None else None,
            'elapsed_ms': (time.perf_counter() - started) * 1000}


def drain():
    try:
        while True:
            op, done, result = commands.get_nowait()
            try: result.append(op())
            except Exception as exc: result.append({'error': str(exc)})
            finally: done.set()
    except queue.Empty:
        pass
    root.after(15, drain)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def handle_request(self):
        url = urlparse(self.path)
        if self.command == 'GET' and url.path == '/state':
            op = state
        elif self.command == 'POST' and url.path == '/reset':
            try:
                query = parse_qs(url.query)
                sid, value = int(query['scenario'][0]), int(query['seed'][0])
                if sid not in (0, 1, 2) or not 0 <= value <= 999999: raise ValueError()
            except (KeyError, ValueError, IndexError):
                self.send_error(400, 'scenario 0..2 and seed 0..999999 required'); return
            op = lambda: reset(sid, value)
        else:
            self.send_error(404); return
        done, result = threading.Event(), []
        commands.put((op, done, result))
        if not done.wait(10): self.send_error(503); return
        payload = json.dumps(result[0]).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == '__main__':
    reset(0, 0)
    threading.Thread(target=ThreadingHTTPServer(('127.0.0.1', 8096), Handler).serve_forever, daemon=True).start()
    root.after(15, drain)
    root.mainloop()
