"""Real HTTP check ONLY inside an explicitly disposable, network-isolated container."""
import http.cookiejar
import io
import json
import os
import secrets
import time
import urllib.error
import urllib.request
import zipfile

from PIL import Image


def main():
    if (os.getenv('FORM_CONTAINER_SMOKE_ALLOW_SYNTHETIC') != 'YES_DISPOSABLE_CONTAINER'
            or os.getenv('FORM_ENV', 'development') not in ('test', 'development')
            or os.getenv('FORM_DATABASE_URL', '').strip()
            or os.getenv('FORM_PHOTO_STORAGE', 'local') != 'local'):
        raise RuntimeError('Refusing synthetic HTTP smoke outside the disposable local container')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path, data=None, csrf=None, content_type='application/json'):
        headers = {'Content-Type': content_type}
        if csrf: headers['x-csrf-token'] = csrf
        payload = (json.dumps(data).encode() if isinstance(data, dict) else data)
        with opener.open(urllib.request.Request('http://127.0.0.1:8000' + path,
                         data=payload, headers=headers), timeout=5) as response:
            return response.read()

    deadline = time.monotonic() + 30
    while True:
        try:
            assert json.loads(request('/readyz')) == {'status': 'ready'}
            break
        except (urllib.error.URLError, AssertionError):
            if time.monotonic() >= deadline: raise
            time.sleep(0.25)
    password = 'SyntheticContainerPassword456'
    request('/api/auth/register', {'name': 'Container fixture',
        'email': 'container-' + secrets.token_hex(6) + '@example.com', 'password': password})
    session = json.loads(request('/api/session'))
    assert session['authenticated']
    token = session['csrf']
    item = json.loads(request('/api/items', {'title': 'Synthetic container garment',
        'condition': 'Good', 'price_cents': 1000}, token))
    output = io.BytesIO()
    Image.new('RGB', (24, 24), 'blue').save(output, 'PNG')
    boundary = 'fixture-' + secrets.token_hex(12)
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="photos"; filename="sample.png"\r\n'
            'Content-Type: image/png\r\n\r\n').encode() + output.getvalue() + f'\r\n--{boundary}--\r\n'.encode()
    uploaded = json.loads(request(f"/api/items/{item['id']}/photos", body, token,
                                 'multipart/form-data; boundary=' + boundary))
    assert uploaded['item']['photo_count'] == 1
    assert request(f"/api/items/{item['id']}/photo")[:4] == b'RIFF'
    assert json.loads(request('/api/items?limit=1'))['total'] == 1
    with zipfile.ZipFile(io.BytesIO(request('/api/account/export.zip'))) as archive:
        metadata = json.loads(archive.read('form_backup.json'))
        assert len(metadata['items']) == 1 and len(metadata['item_photos']) == 1
    request('/api/account/delete', {'password': password, 'confirmation': 'DELETE MY ACCOUNT'}, token)
    assert not json.loads(request('/api/session'))['authenticated']
    print('CONTAINER HTTP SMOKE PASSED: schema revisions, real HTTP/cookies/CSRF, photo upload, private export and account deletion')


if __name__ == '__main__':
    main()
