"""Protocol/UI regression with explicitly synthetic map updates, no camera access."""
import json
from pathlib import Path
import sys

import cv2
import numpy as np

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo));sys.path.insert(0,str(repo/'.cache/browser-qa'))
from playwright.sync_api import sync_playwright
from backend.store import SessionStore
from backend.protocol import packet


def main():
    store=SessionStore(repo/'.cache/dashboard-qa/sessions')
    saved=store.create('QA synthetic live map',{'source':'webcam','options':{'slam':True},'limitations':['Synthetic UI test; not measurement data']})
    _,image=cv2.imencode('.jpg',np.full((480,640,3),90,np.uint8))
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True,args=['--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':1440,'height':1100});sockets=[];errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def connect(ws):
            sockets.append(ws)
            ws.send(json.dumps(packet({'state':'idle','mode':None})[0]))
        page.route_web_socket('**/ws/live',connect)
        page.goto('http://127.0.0.1:8002/',wait_until='networkidle')
        page.get_by_text('Connected',exact=True).wait_for()
        page.locator('.session-info').filter(has_text='QA synthetic live map').first.click()
        def send(sequence,count,epoch=0,dense=False,window=False):
            values=np.tile(np.array([[.1,0,1,.3,.8,.5]],dtype='<f4'),(count,1))
            header,rgb,cloud=packet({'session_id':saved['id'],'mode':'live','state':'running',
                'sequence':sequence,'timestamp':sequence,'pose':[0,0,0,0,0,0,1] if count else None,
                'fusion':{'state':'keyframe_window' if window else 'local_dense_preview' if dense else 'sparse_only',
                    'reason':'Synthetic test rejection','heldout_abs_rel_mean':.05,'window_keyframes':[1,2],'window_limit':4},
                'slam_sequence':sequence,'cloud_semantics':'live_sparse_and_local_dense','map_epoch':epoch},image.tobytes(),values.tobytes(),count)
            sockets[0].send(json.dumps(header));sockets[0].send(rgb)
            if cloud:sockets[0].send(cloud)
        send(0,2);page.wait_for_function("document.querySelector('#points').textContent === '2'")
        assert page.locator('#map-kind').inner_text()=='LIVE SPARSE'
        send(1,7,dense=True);page.wait_for_function("document.querySelector('#points').textContent === '7'")
        assert page.locator('#map-kind').inner_text()=='LIVE + DENSE'
        assert 'Online SLAM' in page.locator('#pose-note').inner_text()
        send(2,9,window=True);page.wait_for_function("document.querySelector('#points').textContent === '9'")
        assert page.locator('#map-kind').inner_text()=='LIVE WINDOW'
        assert 'Validated dense window' in page.locator('#source-note').inner_text()
        send(3,0,1);page.wait_for_function("document.querySelector('#points').textContent === '0'")
        assert page.locator('#map-kind').inner_text()=='INITIALIZING'
        assert page.locator('#pose-status').inner_text()=='Unavailable'
        assert not errors,errors
        browser.close()
    print(json.dumps({'same_session_map_updates':True,'map_reset_clears_points':True,'page_errors':errors}))


if __name__=='__main__':main()
