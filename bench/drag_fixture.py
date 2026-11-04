"""Disposable drag surface with independent press/move/release scoring on port 8097."""
from __future__ import annotations
import json
import queue
import random
import threading
import tkinter as tk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

root = tk.Tk()
root.title('CU-S1 Drag Benchmark')
root.geometry('940x600+100+100')
root.resizable(False, False)
canvas = tk.Canvas(root, highlightthickness=0)
canvas.pack(fill='both', expand=True)
commands = queue.Queue()
events = []
dragging = False
moved = False
completed = False
seed = 0
card = None
label = None
last = (0, 0)
zone = (0, 0, 0, 0)

def reset(value):
    global seed, dragging, moved, completed, card, label, zone
    seed = value
    rng = random.Random(value)
    dragging = moved = completed = False
    events.clear()
    canvas.delete('all')
    dark = bool(value % 2)
    bg, fg = ('#17212d', '#e9eff8') if dark else ('#edf3f7', '#182d3a')
    canvas.configure(bg=bg)
    canvas.create_text(40, 35, text='Move the project', anchor='nw', fill=fg, font=('Segoe UI', 24, 'bold'))
    canvas.create_text(40, 90, text='Drag the blue Project card into the outlined Archive area.', anchor='nw', fill=fg, font=('Segoe UI', 14))
    sx, sy = rng.randint(75, 220), rng.randint(190, 380)
    tx, ty = rng.randint(570, 695), rng.randint(180, 350)
    zone = (tx, ty, tx + 170, ty + 150)
    canvas.create_rectangle(*zone, outline='#69b99e' if dark else '#277f64', width=4, dash=(8, 5))
    canvas.create_text(tx + 85, ty + 75, text='Archive', fill=fg, font=('Segoe UI', 17, 'bold'))
    canvas.create_rectangle(365, 360, 485, 440, fill='#7e8795', outline='')
    canvas.create_text(425, 400, text='Notes', fill='white', font=('Segoe UI', 14))
    card = canvas.create_rectangle(sx, sy, sx + 120, sy + 80, fill='#2468c7', outline='#5b9aff', width=2)
    label = canvas.create_text(sx + 60, sy + 40, text='Project', fill='white', font=('Segoe UI', 16, 'bold'))
    canvas.create_text(40, 550, text='Ready', fill=fg, anchor='w', font=('Segoe UI', 16, 'bold'), tags='status')
    return {'seed': seed, 'steps': [{'do': 'Drag the blue Project card into the outlined Archive area.',
                                  'expect': 'The status says COMPLETE.'}]}

def press(event):
    global dragging, last
    x1, y1, x2, y2 = canvas.coords(card)
    dragging = x1 <= event.x <= x2 and y1 <= event.y <= y2
    last = (event.x, event.y)
    events.append({'event': 'press', 'on_card': dragging})

def move(event):
    global last, moved
    if dragging:
        dx, dy = event.x - last[0], event.y - last[1]
        canvas.move(card, dx, dy)
        canvas.move(label, dx, dy)
        moved |= abs(dx) + abs(dy) > 3
        last = (event.x, event.y)
        events.append({'event': 'move'})

def release(event):
    global dragging, completed
    if dragging:
        x1, y1, x2, y2 = canvas.coords(card)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        completed = moved and zone[0] < cx < zone[2] and zone[1] < cy < zone[3]
        if completed:
            canvas.itemconfigure('status', text='COMPLETE')
    events.append({'event': 'release', 'completed': completed})
    dragging = False

canvas.bind('<ButtonPress-1>', press)
canvas.bind('<B1-Motion>', move)
canvas.bind('<ButtonRelease-1>', release)

def state():
    return {'seed': seed, 'completed': completed, 'dragging': dragging, 'events': list(events)}

def drain():
    try:
        while True:
            operation, done, result = commands.get_nowait()
            try:
                result.append(operation())
            except Exception as exc:
                result.append({'error': str(exc)})
            finally:
                done.set()
    except queue.Empty:
        pass
    root.after(15, drain)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        self.handle_request()
    def do_POST(self):
        self.handle_request()
    def handle_request(self):
        url = urlsplit(self.path)
        if self.command == 'GET' and url.path == '/state':
            operation = state
        elif self.command == 'POST' and url.path == '/reset':
            try:
                value = int(parse_qs(url.query)['seed'][0])
                if not 0 <= value <= 999999:
                    raise ValueError()
            except (KeyError, ValueError, IndexError):
                self.send_error(400)
                return
            operation = lambda: reset(value)
        else:
            self.send_error(404)
            return
        done, result = threading.Event(), []
        commands.put((operation, done, result))
        if not done.wait(10):
            self.send_error(503)
            return
        body = json.dumps(result[0]).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == '__main__':
    reset(0)
    threading.Thread(target=ThreadingHTTPServer(('127.0.0.1', 8097), Handler).serve_forever, daemon=True).start()
    root.after(15, drain)
    root.mainloop()
