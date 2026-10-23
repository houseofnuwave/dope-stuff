"""Real Chromium DOM + actual FastAPI TestClient bridge (including binary multipart).

Tests browser validation, photo upload, listing readiness, backup preview, secure
restore, desktop/mobile layout and JavaScript errors. The API is reached in-process,
not through HTTPS: this does not replace live deployment/device QA.

  FORM_CHROMIUM_PATH=/usr/bin/chromium python tools/ui_smoke.py
"""
from __future__ import annotations
import base64
import io
import os
from pathlib import Path
import sys
import tempfile
from PIL import Image
from playwright.sync_api import sync_playwright
from fastapi.testclient import TestClient

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from app import main, db


def picture(path: Path):
    image=Image.new('RGB',(150,170),(96,119,93))
    image.save(path,format='PNG')


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.environ.get('FORM_CHROMIUM_PATH') or None,
            headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        for device,vp in [('desktop',{'width':1440,'height':900}),('mobile',{'width':390,'height':844})]:
            db.DATA_DIR=Path(tempfile.mkdtemp(prefix='form-v10-ui-'))
            db.DB_PATH=db.DATA_DIR/'form.db'
            main.DATA_DIR=db.DATA_DIR
            with TestClient(main.app) as api:
                page=browser.new_page(viewport=vp)
                errors=[]
                page.on('pageerror',lambda err: errors.append(str(err)))

                def bridge(url,method='GET',payload=None,csrf=''):
                    headers={'x-csrf-token':csrf} if csrf else {}
                    if isinstance(payload,dict) and payload.get('kind')=='form':
                        fields={};files=[]
                        for field in payload['entries']:
                            if 'b64' in field:
                                files.append((field['key'],(field['name'],io.BytesIO(base64.b64decode(field['b64'])),field['mime'])))
                            else:
                                fields[field['key']]=field['value']
                        resp=api.request(method,url,headers=headers,data=fields,files=files)
                    else:
                        body=payload.get('value') if isinstance(payload,dict) else None
                        if body is not None:
                            headers['content-type']='application/json'
                        resp=api.request(method,url,headers=headers,data=body)
                    return {'status':resp.status_code,'body':resp.text,
                            'type':resp.headers.get('content-type','application/json')}

                page.expose_function('formBridge',bridge)
                html=(root/'app/static/index.html').read_text().replace(
                    '<link rel="stylesheet" href="/static/styles.css">','').replace(
                    '<script src="/static/app.js" defer></script>','')
                page.set_content(html)
                page.add_style_tag(content=(root/'app/static/styles.css').read_text())
                page.evaluate('''(()=>{window.fetch=async function(url,options={}) {
                  let payload={kind:'raw',value:options.body??null};
                  if(options.body instanceof FormData){
                    const entries=[];
                    for(const [key,value] of options.body.entries()){
                      if(value instanceof File){
                        const bytes=new Uint8Array(await value.arrayBuffer());let binary='';
                        for(let i=0;i<bytes.length;i+=32768) binary+=String.fromCharCode(...bytes.slice(i,i+32768));
                        entries.push({key,name:value.name,mime:value.type,b64:btoa(binary)});
                      }else entries.push({key,value:String(value)});
                    }
                    payload={kind:'form',entries};
                  }
                  const d=await window.formBridge(url,options.method||'GET',payload,options.headers?.['x-csrf-token']||'');
                  return new Response(d.body,{status:d.status,headers:{'content-type':d.type}});
                };return true;})()''')
                page.add_script_tag(content=(root/'app/static/app.js').read_text())
                email=f'browser-{device}@example.com'

                def signup():
                    page.locator('button[data-action="register"]').first.click()
                    page.locator('#auth-form input[name="name"]').fill('Browser Tester')
                    page.locator('#auth-form input[name="email"]').fill(email)
                    page.locator('#auth-form input[name="password"]').fill('LongSecurePassword123')
                    page.locator('#auth-form button').last.click()
                    page.locator('.shell').wait_for(timeout=12000)

                print('CHECK',device,'signed up',flush=True)
                signup()
                page.locator('[data-action="new"]').first.click()
                page.locator('#field-title').fill('Vintage leather moto jacket')
                page.locator('#field-brand').fill('Test Studio')
                page.locator('#field-size').fill('Medium')
                page.locator('#field-price').fill('120.00')
                page.locator('#item-description').fill('Heavy leather moto jacket. Inspect the real jacket for visible wear and disclose all observed flaws.')
                # A real seller must choose condition; the button cannot silently assume "New".
                assert not page.locator('#item-form').evaluate('(form)=>form.checkValidity()')
                page.locator('#item-condition').select_option(label='Good')
                photos=[]
                for n in range(3):
                    path=db.DATA_DIR/f'garment-{n}.png'
                    picture(path)
                    photos.append(str(path))
                page.locator('#item-photos').set_input_files(photos)
                print('CHECK',device,'saving item',flush=True)
                page.locator('#item-form button[type="submit"]').click()
                page.locator('.mobile-item .table-title' if device=='mobile' else '.desktop-item-table .table-title').first.wait_for(timeout=12000)
                assert api.get('/api/items').json()['items'][0]['photo_count']==3
                assert api.get('/api/items').json()['items'][0]['readiness']['complete']==7
                print('CHECK',device,'first screen',flush=True)
                page.locator('#toast-root').evaluate('(el)=>el.innerHTML=""')
                page.screenshot(path=str(root/'docs'/f'v10-{device}-overview.png'),full_page=True)
                (page.locator('[data-nav="publish"]').last if device=='mobile' else page.locator('[data-nav="publish"]').first).click()
                page.locator('[data-action="kit"]').first.click()
                page.locator('.readiness-review').wait_for(timeout=8000)
                assert '7/7 checks' in page.locator('.readiness-review').inner_text()
                page.locator('button[data-action="close"]').click()
                page.locator('[data-nav="account"]').last.click() if device=='mobile' else page.locator('[data-nav="account"]').first.click()
                page.get_by_text('Your records. Always yours.').first.wait_for(timeout=8000)
                page.locator('#toast-root').evaluate('(el)=>el.innerHTML=""')
                page.screenshot(path=str(root/'docs'/f'v10-{device}-account.png'),full_page=True)
                backup=db.DATA_DIR/'pilot-backup.zip'
                backup.write_bytes(api.get('/api/account/export.zip').content)
                assert backup.stat().st_size>0

                print('CHECK',device,'starting reset',flush=True)
                # Delete then recreate same email to exercise blank-account restore.
                page.locator('button[data-action="delete-account"]').click()
                page.locator('#delete-confirm').fill('DELETE MY ACCOUNT')
                page.locator('#delete-password').fill('LongSecurePassword123')
                print('CHECK',device,'deleting',flush=True)
                page.locator('#delete-account-form button[type="submit"]').click()
                page.locator('button[data-action="register"]').first.wait_for(timeout=10000)
                signup()
                page.locator('[data-nav="account"]').last.click() if device=='mobile' else page.locator('[data-nav="account"]').first.click()
                page.locator('button[data-action="restore-account"]').click()
                page.locator('#restore-file').set_input_files(str(backup))
                print('CHECK',device,'previewing',flush=True)
                page.locator('#restore-form button[type="submit"]').click()
                page.get_by_text('Archive verified').wait_for(timeout=12000)
                assert '3 photos' in page.locator('#restore-results').inner_text()
                page.locator('#toast-root').evaluate('(el)=>el.innerHTML=""')
                page.screenshot(path=str(root/'docs'/f'v10-{device}-restore-review.png'),full_page=True)
                page.locator('#restore-confirm').fill('RESTORE MY DATA')
                page.locator('#restore-password').fill('LongSecurePassword123')
                print('CHECK',device,'restoring',flush=True)
                page.locator('button[data-action="confirm-restore"]').click()
                try:
                    page.locator('#restore-form').wait_for(state='detached',timeout=12000)
                except Exception:
                    print('RESTORE UI ERROR',page.locator('#toast-root').inner_text(),page.locator('#restore-results').inner_text())
                    raise
                assert api.get('/api/items').json()['total']==1
                assert api.get('/api/items').json()['items'][0]['photo_count']==3
                assert api.get('/api/items').json()['items'][0]['readiness']['complete']==7
                # v1.0: action-center journey after a real recorded sale.
                csrf=api.get('/api/session').json()['csrf'];headers={'x-csrf-token':csrf}
                restored=api.get('/api/items').json()['items'][0]
                ident=restored['id']
                assert api.put(f'/api/items/{ident}/channels/grailed',headers=headers,
                    json={'status':'manually_published','listing_url':''}).status_code==200
                assert api.put(f'/api/items/{ident}/channels/depop',headers=headers,
                    json={'status':'manually_published','listing_url':''}).status_code==200
                assert api.post(f'/api/items/{ident}/sale',headers=headers,
                    json={'channel':'grailed','sold_cents':15000,'fee_cents':900,'ship_cents':500}).status_code==200
                assert api.get('/api/actions').json()['total']==1
                page.evaluate('refresh()')
                # On mobile the Action Center is reached by the urgent dashboard alert.
                (page.locator('[data-nav="overview"]').last if device=='mobile' else
                    page.locator('[data-nav="overview"]').first).click()
                page.locator('.alert [data-nav="actions"]').click()
                page.locator('.action-item').first.wait_for(timeout=10000)
                assert 'DEPOP' in page.locator('.action-item').first.inner_text().upper()
                page.locator('#toast-root').evaluate('(el)=>el.innerHTML=""')
                page.screenshot(path=str(root/'docs'/f'v10-{device}-action-center.png'),full_page=True)
                page.on('dialog',lambda dialog: dialog.accept())
                page.locator('button[data-action="clear-delist"]').click()
                page.get_by_text('Your removal queue is clear').wait_for(timeout=10000)
                assert api.get('/api/actions').json()['total']==0
                print('CHECK',device,'seller removal queue',flush=True)

                # v1.0: duplicate a sold garment as an independent new draft.
                (page.locator('[data-nav="inventory"]').last if device=='mobile' else
                    page.locator('[data-nav="inventory"]').first).click()
                page.locator('.mobile-item-list button[data-action="duplicate"]').first.click() if device=='mobile' else page.locator('.desktop-item-table button[data-action="duplicate"]').first.click()
                page.locator('#item-form').wait_for(timeout=10000)
                assert api.get('/api/items').json()['total']==2
                page.locator('.modal button[data-action="close"]').first.click()
                assert len(api.get('/api/items').json()['items'])==2
                print('CHECK',device,'duplicate draft',flush=True)

                # v1.0: password change must be usable, and rotate session CSRF.
                (page.locator('[data-nav="account"]').last if device=='mobile' else
                    page.locator('[data-nav="account"]').first).click()
                page.locator('button[data-action="change-password"]').click()
                page.locator('#pw-current').fill('LongSecurePassword123')
                page.locator('#pw-new').fill('EvenMoreSecurePassword456')
                page.locator('#password-form button[type="submit"]').click()
                page.locator('#password-form').wait_for(state='detached',timeout=12000)
                assert api.get('/api/session').json()['authenticated'] is True
                page.screenshot(path=str(root/'docs'/f'v10-{device}-account.png'),full_page=True)
                print('CHECK',device,'password change',flush=True)

                # v0.7: public password recovery from signed-out login to single-use email link.
                page.evaluate("async()=>{await api('/api/auth/logout',{method:'POST'});S.session=await api('/api/session');authLanding();}")
                page.locator('button[data-action="login"]').first.click()
                page.locator('button[data-action="forgot-password"]').click()
                page.locator('#recovery-email').fill(email)
                page.locator('#recovery-request-form button[type="submit"]').click()
                page.locator('#recovery-request-form').wait_for(state='detached',timeout=10000)
                inbox=list((db.DATA_DIR/'local-recovery-mail').glob('*.txt'))
                assert len(inbox)==1
                import re
                token=re.search(r'#reset=([A-Za-z0-9_-]{40,200})',inbox[0].read_text()).group(1)
                page.evaluate("async token=>{location.hash='reset='+token;await init();}",token)
                page.locator('#recovery-new').wait_for(timeout=10000)
                assert 'reset=' not in page.evaluate('location.hash')
                page.locator('#recovery-new').fill('BrandNewSecurePassword789')
                page.locator('#recovery-again').fill('BrandNewSecurePassword789')
                page.screenshot(path=str(root/'docs'/f'v07-{device}-reset-password.png'),full_page=True)
                page.locator('#recovery-confirm-form button[type="submit"]').click()
                page.locator('#recovery-confirm-form').wait_for(state='detached',timeout=10000)
                page.locator('button[data-action="login"]').first.click()
                page.locator('#auth-email').fill(email)
                page.locator('#auth-password').fill('BrandNewSecurePassword789')
                page.locator('#auth-form button').last.click()
                page.locator('.shell').wait_for(timeout=10000)
                assert api.get('/api/session').json()['authenticated'] is True
                print('CHECK',device,'email recovery',flush=True)

                from tools.ui_pagination import run_pagination_journey
                run_pagination_journey(page, api, device)

                overflow=page.evaluate('document.documentElement.scrollWidth>window.innerWidth')
                print(device,'UI + backup restore', 'PASS' if not errors else 'ERROR',
                    'js_errors',errors,'horizontal_overflow',overflow)
                assert not errors,errors
                assert not overflow,device+' overflow'
                page.close()
        browser.close()

if __name__=='__main__': run()
