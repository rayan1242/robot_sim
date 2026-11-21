"""Explicit hardware smoke: eight seconds of local webcam/depth recording."""
import json
import argparse
from pathlib import Path
import sys

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo));sys.path.insert(0,str(repo/'.cache/browser-qa'))
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--depth-width',type=int,choices=[160,224,320],default=320)
    parser.add_argument('--slam',action='store_true')
    args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True,args=['--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':1440,'height':1250})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8002/',wait_until='networkidle')
        page.get_by_text('Connected',exact=True).wait_for()
        response=page.request.post('http://127.0.0.1:8002/sessions/start',data={
            'name':'QA live freshness hardware smoke','backend':'dshow','auto_exposure':True,
            'width':640,'height':480,'fps':15,'duration':8,'depth':True,'device':'cpu','slam':args.slam,
            'depth_width':args.depth_width,'depth_height':args.depth_width*3//4})
        assert response.ok,response.text()
        saved=response.json()
        page.wait_for_function("document.querySelector('#freshness').textContent.includes('Output jitter p95')",timeout=120000)
        page.wait_for_function("!document.querySelector('#depth-mode').disabled")
        page.locator('#depth-mode').click()
        page.wait_for_function("!document.querySelector('#depth-image').hidden",timeout=30000)
        page.wait_for_function("document.querySelector('#stream-state').textContent === 'COMPLETED'",timeout=60000)
        root=repo/'.cache/dashboard-qa/sessions'/saved['id']
        report=json.loads((root/'timing_summary.json').read_text())
        assert report['capture_receipt_to_packet']['samples']>1
        if args.slam:
            states=[json.loads(s) for s in (root/'states.jsonl').read_text().splitlines()]
            assert all(s['slam_sequence']==s['capture_sequence'] and abs(s['slam_timestamp']-s['timestamp'])<1e-7 for s in states)
        assert not errors,errors
        page.screenshot(path=str(repo/f'.cache/dashboard-qa/live_freshness_{args.depth_width}.png'),full_page=True)
        print(json.dumps({'session_id':saved['id'],'depth_width':args.depth_width,'slam':args.slam,'timing_summary':report,'page_errors':errors},indent=2))
        browser.close()


if __name__=='__main__':main()
