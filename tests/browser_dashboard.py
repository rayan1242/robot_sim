"""Local browser QA using installed Chrome and an isolated backend session directory."""
import json
from pathlib import Path
import sys
import time
import shutil
import numpy as np

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo))
sys.path.insert(0,str(repo/".cache/browser-qa"))
from playwright.sync_api import sync_playwright
from backend.store import SessionStore


def depth_fixture():
    store=SessionStore(repo/".cache/dashboard-qa/sessions")
    source=next(s for s in store.list() if s["metadata"]["source"]=="offline_import")
    result=store.create("QA recorded depth",{"source":"webcam","frames":5,"image_size_wh":[640,480],"options":{"duration":5,"depth":True},"limitations":["Synthetic browser-test timing and depth fixture; not measurement data"]})
    root=store.path(result["id"]);(root/"rgb").mkdir()
    states=[]
    for index in range(5):
        shutil.copyfile(store.path(source["id"])/"rgb/000000.png",root/f"rgb/{index:06d}.png")
        np.save(root/f"depth_{index:06d}.npy",np.tile(np.arange(320,dtype=np.float32),(240,1)))
        states.append({"timestamp":index,"sequence":index,"rgb_path":f"rgb/{index:06d}.png","pose":None,"depth_kind":"relative_inverse","latency_ms":{"capture_to_state":34,"preprocess_ms":2,"inference_ms":30,"postprocess_ms":2},"fps":15,"device":"test"})
    (root/"states.jsonl").write_text("".join(json.dumps(s)+"\n" for s in states))
    return result


def main():
    artifacts=Path(".cache/dashboard-qa")
    artifacts.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel="chrome",headless=True,args=["--enable-unsafe-swiftshader"])
        page=browser.new_page(viewport={"width":1440,"height":1100},device_scale_factor=1)
        errors=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto("http://127.0.0.1:8002/",wait_until="networkidle")
        page.get_by_text("Connected",exact=True).wait_for()
        page.locator('.session-info').filter(has_text='TUM spatial replay').click()
        page.wait_for_function("document.querySelector('#points').textContent === '5,000'")
        page.wait_for_function("document.querySelector('#camera-image').naturalWidth > 0")
        page.screenshot(path=str(artifacts/"desktop.png"),full_page=True)
        assert page.locator("#viewport canvas").count()==1,"3D canvas not created"
        assert page.locator("#quick-replay").bounding_box()["y"] < 768
        page.locator("#quick-replay").click()
        page.wait_for_function("document.querySelector('#pose-status').textContent === 'Available'")
        page.wait_for_function("document.querySelector('#frame-label').textContent !== 'FRAME —'")
        page.screenshot(path=str(artifacts/"replay.png"),full_page=True)
        page.locator("#stop").click()
        page.wait_for_function("document.querySelector('#play').disabled === false")
        page.locator("#toggle-grid").click()
        assert page.locator("#toggle-grid").get_attribute("aria-pressed")=="false"
        page.locator("#fit-map").click()
        page.locator("#new-recording").click()
        assert page.locator("#record-dialog").is_visible()
        page.locator("#record-dialog .close-dialog").first.click()
        # Verify a record request without opening the physical camera during UI QA.
        captured=[]
        def intercept_record(route):
            captured.append(route.request.post_data_json)
            route.fulfill(status=409,content_type="application/json",body=json.dumps({"detail":"QA recording request verified"}))
        page.route("**/sessions/start",intercept_record)
        page.locator("#new-recording").click()
        page.locator("#record-form input[name=depth]").check()
        page.locator('#record-form input[name=keyframe_map]').check()
        page.locator('#record-form select[name=depth_size]').select_option('160,120')
        page.locator("#record-submit").click()
        page.get_by_text("QA recording request verified",exact=True).wait_for()
        assert captured[0]["backend"]=="dshow"
        assert captured[0]["depth"] is True
        assert captured[0]['depth_width']==160 and captured[0]['depth_height']==120
        assert captured[0]['auto_exposure'] is True
        assert captured[0]['keyframe_map'] is True and captured[0]['slam'] is True
        page.locator("#record-dialog .close-dialog").first.click()
        page.unroute("**/sessions/start",intercept_record)
        fixture=depth_fixture()
        page.locator("#refresh-sessions").click()
        page.get_by_text("QA recorded depth",exact=True).wait_for()
        row=page.locator(".session-row").filter(has=page.get_by_text("QA recorded depth",exact=True))
        row.locator("[data-play]").click()
        page.wait_for_function("document.querySelector('#depth-mode').disabled === false")
        page.locator("#depth-mode").click()
        page.wait_for_function("document.querySelector('#depth-image').naturalWidth === 320 && !document.querySelector('#depth-image').hidden")
        assert page.locator("#p50").inner_text().startswith("34")
        page.locator("#stop").click()
        page.wait_for_function("document.querySelector('#new-recording').disabled === false")
        row=page.locator(".session-row").filter(has=page.get_by_text("QA recorded depth",exact=True))
        row.locator("[data-delete]").click()
        page.locator("#confirm-delete").click()
        page.wait_for_function("!document.querySelector('#delete-dialog').open")
        page.locator(".session-row h3").filter(has_text="QA recorded depth").wait_for(state="detached")
        page.locator("#connection-button").click()
        assert page.locator("#endpoint").inner_text()=="http://127.0.0.1:8002"
        page.locator("#connection-dialog .close-dialog").click()
        page.locator("#connection-button").click()
        page.locator("#reconnect").click()
        page.get_by_text("Connected",exact=True).wait_for()
        page.set_viewport_size({"width":390,"height":844})
        page.screenshot(path=str(artifacts/"mobile.png"),full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"),"Mobile horizontal overflow"
        assert not errors,errors
        fallback=browser.new_page(viewport={"width":1100,"height":800})
        fallback.add_init_script("const original=HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext=function(type,...args){if(type.startsWith('webgl'))return null;return original.call(this,type,...args);}")
        fallback.goto("http://127.0.0.1:8002/",wait_until="networkidle")
        fallback.get_by_text("3D view unavailable",exact=True).wait_for()
        assert fallback.locator("#map-empty").is_visible()
        assert fallback.locator("#play").is_enabled()
        fallback.close()
        print(json.dumps({"page_errors":errors,"desktop_and_mobile":True,"replay_pose_and_rgb":True,"snapshot_points":5000,"record_request_dshow":True,"saved_depth_overlay":True,"delete_session":True}))
        browser.close()


if __name__=="__main__":
    main()
