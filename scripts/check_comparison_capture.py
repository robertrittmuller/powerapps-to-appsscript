"""Exercise the comparison runner in Chromium against independent local fixtures.

This checks capture tooling, not real Power Apps/Google behavioral equivalence.
Run: ./pfx2gas browser scripts/check_comparison_capture.py
"""
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright
from compare_workflow import capture
from pfx2gas.comparison import compare_captures


HTML = b'''<!doctype html><label>Name <input id="name"></label><button id="save">Save</button>
<p id="saved"></p><script>
saved.textContent=localStorage.getItem('saved')||'Empty';
document.querySelector('#save').onclick=()=>{let value=document.querySelector('#name').value;
localStorage.setItem('saved',value);saved.textContent=value;};</script>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers()
        self.wfile.write(b'<iframe id="frame" src="/inner"></iframe>' if self.path=='/target' else HTML)

    def log_message(self,*args):
        pass


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    output=Path('.artifacts/comparison-selftest'); output.mkdir(parents=True,exist_ok=True)
    def step(id,action,selector=None,**kwargs):
        result=dict(id=id,action=action,actor='member',journey='save-reload',**kwargs)
        if selector:
            result['locators']={'source':selector,'target':{'frames':['#frame'],'selector':selector}}
        return result
    plan={'sourceUrl':url+'/source','targetUrl':url+'/target','inputSha256':hashlib.sha256(HTML).hexdigest(),
          'capturePlanSha256':'selftest','context':{'locale':'en-US','timezone':'UTC',
          'viewport':{'width':1000,'height':700},'dataSnapshotSha256':'empty-fixture','launchParameters':{},
          'roles':['member','manager']},'actors':[{'id':'member','role':'member'},{'id':'manager','role':'manager'}],
          'steps':[step('initial','observe','#saved',expected='Empty'),step('fill','fill','#name',value='Ada'),
              step('save','click','#save'),step('saved','observe','#saved',expected='Ada'),step('reload','reload'),
              step('persistence','observe','#saved',expected='Ada'),step('checkpoint','screenshot')]}
    isolation=step('isolated-actor','observe','#saved',expected='Empty'); isolation['actor']='manager'
    plan['steps'].append(isolation)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            try:
                source=capture(browser,plan,'source',output)
                target=capture(browser,plan,'target',output)
                proof=compare_captures(source,target)
                assert proof['status']=='pass',proof
                assert len(source['steps'])==len(target['steps'])==8
                broken=copy.deepcopy(plan); broken['steps']=[step('wrong-value','observe','#saved',expected='Never written')]
                failed=capture(browser,broken,'target',output)
                assert failed['status']=='fail' and failed['steps'][0]['status']=='fail',failed
                assert compare_captures(source,failed)['status']=='fail'
            finally: browser.close()
    finally: server.shutdown(); server.server_close(); thread.join()
    (output/'result.json').write_text(json.dumps({'status':'pass','scope':'local capture-tool fixtures',
        'comparison':proof,'expectedFailure':failed},indent=2)+'\n')
    print('PASS: separate actors, nested target frame, save/reload, screenshots, and failed assertion rejection')


if __name__=='__main__': main()
