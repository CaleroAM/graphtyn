"""Real Chromium topic UI smoke. Requires GRAPHTYN_CHROMIUM when not installed."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def main():
    from playwright.sync_api import sync_playwright
    from graphtyn.core.shared_memory import SharedMemoryStore
    root = Path(tempfile.mkdtemp(prefix='topics-browser-'))
    project = root / 'project'; project.mkdir()
    os.environ['GRAPHTYN_HOME'] = str(root / 'state')
    store = SharedMemoryStore(project)
    store.ingest_turn('codex','browser','Texturas', [{'role':'user','content':'Texturas del podio'}, {'role':'assistant','content':'Se corrigió el material; falta verificar'}],consent=True,provider='deterministic')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    server=subprocess.Popen([sys.executable,'-m','uvicorn','graphtyn.api.main:app','--host','127.0.0.1','--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        base=f'http://127.0.0.1:{port}'
        for _ in range(100):
            try: urllib.request.urlopen(base+'/health',timeout=1); break
            except OSError: time.sleep(.1)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=os.environ.get('GRAPHTYN_CHROMIUM'),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            page=browser.new_page()
            page.goto(base)
            page.evaluate('''async path => { const {state}=await import('/js/state.js'); state.activePath=path; const memory=await import('/js/memory.js'); memory.openMemoryPanel(); }''',str(project))
            page.locator('#memory-topic-list summary').wait_for()
            welcome = page.locator('#modal-welcome')
            if welcome.is_visible():
                close = welcome.locator('button').last
                if close.is_visible(): close.click()
            assert 'Texturas del podio' in page.locator('#memory-topic-list').inner_text()
            page.locator('#memory-topic-list summary').click()
            page.get_by_role('button',name='Ver conversación',exact=True).click()
            page.locator('#memory-conversation-panel').get_by_text('Cerrar conversación').wait_for()
            assert 'codex' in page.locator('#memory-conversation-panel').inner_text()
            page.get_by_role('button',name='Cerrar conversación').click()
            page.select_option('#memory-topic-state','resuelto')
            page.click('#memory-topic-filter')
            page.get_by_text('Sin temas para estos filtros.').wait_for()
            page.select_option('#memory-topic-state','')
            failed=[False]
            def intercept(route):
                if not failed[0]:
                    failed[0]=True; route.fulfill(status=503,content_type='application/json',body=json.dumps({'ok':False,'error':'fallo temporal'}))
                else: route.continue_()
            page.route('**/api/memory/topics?*',intercept)
            page.click('#memory-topic-filter')
            page.locator('#memory-topic-list').get_by_role('button',name='Reintentar').click()
            page.locator('#memory-topic-list summary').wait_for()
            page.screenshot(path=str(root/'topics.png'),full_page=True)
            browser.close()
        print(json.dumps({'ok':True,'checks':['titles','episodes','conversation','state_filter','recoverable_error_retry'],'artifact':str(root/'topics.png')}))
    finally:
        server.terminate(); server.wait(timeout=10)

if __name__ == '__main__': main()
