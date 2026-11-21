"""Exercise the real offline replay artifacts against the isolated QA server."""
import json
import re
from pathlib import Path
import shutil
import sys

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo));sys.path.insert(0,str(repo/'.cache/browser-qa'))
from playwright.sync_api import sync_playwright
from backend.store import SessionStore


def main():
    source_store=SessionStore(repo/'data/sessions')
    source=next(s for s in source_store.list() if s['name']=='Room reconstruction - experimental replay' and s['status']=='ready')
    store=SessionStore(repo/'.cache/dashboard-qa/sessions')
    initial_metadata=dict(source['metadata'])
    initial_metadata.pop('image_size_wh',None);initial_metadata.pop('depth_device',None)
    saved=store.create('QA room replay evidence',initial_metadata)
    src=source_store.path(source['id']);dst=store.path(saved['id']);(dst/'rgb').mkdir()
    states=[json.loads(s) for s in (src/'states.jsonl').read_text().splitlines()][:12]
    for state in states:
        shutil.copyfile(src/state['rgb_path'],dst/state['rgb_path'])
        name=f"depth_{state['sequence']:06d}.npy";shutil.copyfile(src/name,dst/name)
    for name in ['map.npz','analysis.json']:shutil.copyfile(src/name,dst/name)
    (dst/'states.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in states))
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True,args=['--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':1440,'height':1250})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8002/',wait_until='networkidle')
        page.get_by_text('Connected',exact=True).wait_for()
        page.locator('.session-info').filter(has_text='QA room replay evidence').first.click()
        page.wait_for_function("document.querySelector('#tracking-summary').textContent.includes('299/449')")
        assert '19' in page.locator('#fusion-summary').inner_text()
        assert '66.6%' in page.locator('#tracking-summary').inner_text()
        store.update(saved['id'],'ready',source['metadata'])
        page.wait_for_function("document.querySelector('#run-info').textContent.includes('640 x 480') && document.querySelector('#run-info').textContent.includes('cpu')")
        assert 'Original recording rate' in page.locator('#fps-note').inner_text()
        page.locator('#speed').select_option('0.5');page.locator('#quick-replay').click()
        page.wait_for_function("!document.querySelector('#depth-mode').disabled")
        page.locator('#depth-mode').click()
        page.wait_for_function("!document.querySelector('#depth-image').hidden && document.querySelector('#depth-image').naturalWidth === 320")
        page.wait_for_function("document.querySelector('#offline-timing').textContent.includes('Offline depth: p50')")
        assert 'unavailable' not in page.locator('#offline-timing').inner_text().lower()
        assert page.locator('#timing-title').inner_text()=='Offline depth timing'
        assert page.locator('#infer-p50').inner_text()!='—'
        assert page.locator('#p50').inner_text()!='— ms'
        assert 'Offline depth only' in page.locator('#latency-note').inner_text()
        page.screenshot(path=str(repo/'docs/replay_dashboard.png'),full_page=True)
        page.wait_for_function("document.querySelector('#stream-state').textContent === 'COMPLETED'")
        response=page.request.post(f"http://127.0.0.1:8002/sessions/{saved['id']}/replay",data={'speed':1})
        assert response.ok
        page.wait_for_function("document.querySelector('#stream-state').textContent === 'RUNNING'")
        page.wait_for_function("document.querySelector('#stream-state').textContent === 'COMPLETED'")
        count=int(re.search(r'\((\d+) samples\)',page.locator('#offline-timing').inner_text()).group(1))
        assert count<=12, 'Depth timings accumulated across externally started replays'
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
        assert not errors,errors
        browser.close()
    print(json.dumps({'analysis_panels':True,'real_saved_depth':True,'offline_timings':True,'mobile':True,'page_errors':errors}))


if __name__=='__main__':main()
