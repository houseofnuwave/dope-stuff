"""Download the real validated ZIP and keep failures inside the test workspace."""
import io
from pathlib import Path
import zipfile
from unittest.mock import patch

from playwright.sync_api import expect
from app import backup, main, photo_storage


def run_backup_journey(page, api, device):
    page.evaluate("nav('account')")
    button = page.get_by_role('button', name='Download full backup', exact=True)
    expect(page.get_by_text('up to 10,000 items and 4,000 photos', exact=False)).to_have_count(2)
    downloads = []

    def on_download(download):
        downloads.append(download)

    page.on('download', on_download)
    try:
        with patch.object(photo_storage, 'read_photo', side_effect=FileNotFoundError('synthetic missing object')):
            button.click()
            expect(page.locator('.toast').filter(has_text='referenced photo is missing')).to_be_visible()
        expect(button).to_be_enabled()
        expect(page.locator('.shell')).to_be_visible()
        assert downloads == [], 'An error was incorrectly downloaded as a ZIP'
        page.evaluate('''()=>{window.backupTestFetch=window.fetch;
          window.fetch=(url,options)=>String(url)==='/api/account/export.zip'
            ?Promise.resolve(new Response('<html>Gateway error</html>',{status:200,
              headers:{'content-type':'text/html'}})):window.backupTestFetch(url,options);}''')
        button.click()
        expect(page.locator('.toast').filter(has_text='No file was downloaded')).to_be_visible()
        assert downloads == [], 'A gateway HTML response was downloaded as a ZIP'
        page.evaluate('()=>{window.fetch=window.backupTestFetch;}')
        with page.expect_download(timeout=20000) as event:
            button.click()
        download = event.value
        assert download.suggested_filename == 'form_account_backup.zip'
        assert download.failure() is None
        raw = Path(download.path()).read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert archive.testzip() is None
        email = api.get('/api/session').json()['user']['email']
        verified = backup.inspect_archive(raw, email, **main.portable_validators())
        assert verified.metadata['items'] > 500 and verified.metadata['sales'] > 500
        assert verified.metadata['photos'] > 0
        expect(button).to_be_enabled()
        print('CHECK', device, 'backup: inline missing-photo failure, no false download, real ZIP beyond 500 items PASS', flush=True)
    finally:
        page.remove_listener('download', on_download)
