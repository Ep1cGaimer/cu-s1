"""Local browser benchmark. Event state is evaluator-only, never supplied to the VLM."""
import json,threading
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs

lock=threading.Lock()
current={'scenario':0,'generation':0,'events':[],'completed':False}
TASKS=[
 [{'do':'Click the image of a blue line rising from left to right.'},{'do':'Click inside the Label text field.'},
  {'do':'Type: OAK-19'},{'do':"Click 'Apply label'.",'expect':'The page says COMPLETE.'}],
 [{'do':'Scroll down to the bottom of this page.'},{'do':"Click 'Open ticket Q7'.",'expect':'The page says COMPLETE.'}],
 [{'do':"Click 'Review settings'."},{'do':"Click the checkbox 'Enable image previews'."},
  {'do':"Click 'Confirm settings'.",'expect':'The page says COMPLETE.'}]
]

HTML=r'''<!doctype html><html><meta charset="utf-8"><title>CU-S1 Browser Benchmark</title>
<style>*{box-sizing:border-box}body{margin:0;font:18px Segoe UI;background:#eef2ed;color:#24312a}main{max-width:980px;margin:25px auto;padding:28px;background:white;border:1px solid #bdc7bd}h1{font-size:30px;margin:0 0 8px}button{font:inherit;padding:12px 22px;cursor:pointer}#charts{display:flex;gap:22px;margin:35px 0}svg{background:#fafbfc;display:block}label{display:block;margin:24px 0}input[type=text]{font:inherit;padding:12px;width:380px}#status{margin-top:28px;font-weight:bold;color:#19633a}#shade{position:fixed;inset:0;background:#0008;display:flex;align-items:center;justify-content:center}#dialog{width:500px;background:white;padding:32px;box-shadow:0 8px 45px #0006}.ticket{padding:25px;margin:22px 0;border:1px solid #aab2b6;background:#f6f7f9}</style>
<main id="app"></main><script>
let generation=-1,scenario=0,selected='',last='';
async function recordEvent(name,extra={}){await fetch('/event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({generation,event:name,...extra})});}
function chart(color,points,label,key){return `<button aria-label="${label}" onclick="selected='${key}';recordEvent('select',{value:selected});document.querySelector('#status').textContent='Selected image'"><svg width="160" height="110" role="img" aria-label="${label}"><path d="M18 12V90H148" fill="none" stroke="#89939c"/><polyline points="${points}" fill="none" stroke="${color}" stroke-width="6"/></svg></button>`;}
function render(s){scenario=s.scenario;generation=s.generation;selected='';document.querySelector('#shade')?.remove();window.scrollTo(0,0);
let intro='<h1>Visual workspace</h1><p>Temporary local benchmark — no real records.</p>';
if(scenario===0){document.querySelector('#app').innerHTML=intro+'<div id="charts">'+chart('#2268ce','20,78 55,65 90,41 142,20','blue rising line chart','rise')+chart('#e57d20','20,22 55,40 90,50 142,80','orange falling line chart','fall')+chart('#7d3bb5','20,52 55,52 90,52 142,52','purple flat line chart','flat')+'</div><label>Label <input id="label" type="text" aria-label="Label"></label><button id="apply">Apply label</button><p id="status">Ready</p>';document.querySelector('#apply').onclick=async()=>{let value=document.querySelector('#label').value;await recordEvent('apply',{selected,text:value});document.querySelector('#status').textContent=(selected==='rise'&&value==='OAK-19')?'COMPLETE':'Check image and label';};}
if(scenario===1){document.querySelector('#app').innerHTML=intro+'<h2>Ticket archive</h2><p>Find the requested ticket below the fold.</p>'+Array.from({length:10},(_,i)=>`<div class="ticket">Archived ticket ${i+1} — read-only preview</div>`).join('')+'<button style="font-size:13px;padding:5px 10px" id="ticket">Open ticket Q7</button><p id="status">Ready</p>';document.querySelector('#ticket').onclick=async()=>{await recordEvent('open_ticket');document.querySelector('#status').textContent='COMPLETE';};}
if(scenario===2){document.querySelector('#app').innerHTML=intro+'<h2>Preview preferences</h2><p>Settings apply only to this temporary page.</p><button id="review">Review settings</button><p id="status">Ready</p>';document.querySelector('#review').onclick=()=>{recordEvent('open_dialog');let shade=document.createElement('div');shade.id='shade';shade.innerHTML='<div id="dialog" role="dialog" aria-label="Preview settings"><h2>Preview settings</h2><label><input id="check" type="checkbox"> Enable image previews</label><button id="confirm">Confirm settings</button></div>';document.body.append(shade);document.querySelector('#confirm').onclick=async()=>{let checked=document.querySelector('#check').checked;await recordEvent('confirm',{checked});if(checked){shade.remove();document.querySelector('#status').textContent='COMPLETE';}};};}}
async function poll(){try{let s=await(await fetch('/state')).json();if(s.generation!==generation)render(s);}catch{}setTimeout(poll,150);}poll();
</script></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/':self.reply(HTML.encode(),'text/html; charset=utf-8')
        elif path=='/state':
            with lock:s={**current,'events':list(current['events']),'steps':TASKS[current['scenario']]}
            self.reply(json.dumps(s).encode())
        else:self.send_error(404)
    def do_POST(self):
        u=urlparse(self.path)
        with lock:
            if u.path=='/reset':
                current.update(scenario=int(parse_qs(u.query).get('scenario',[0])[0])%3,generation=current['generation']+1,events=[],completed=False)
            elif u.path=='/event':
                data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
                if data.get('generation')==current['generation']:
                    current['events'].append(data)
                    if current['scenario']==0:current['completed']=data.get('event')=='apply' and data.get('selected')=='rise' and data.get('text')=='OAK-19'
                    if current['scenario']==1:current['completed']=data.get('event')=='open_ticket'
                    if current['scenario']==2:current['completed']=data.get('event')=='confirm' and data.get('checked') is True
            else:self.send_error(404);return
        self.reply(b'{"ok":true}')
    def reply(self,payload,kind='application/json'):
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)

if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',8094),Handler).serve_forever()
