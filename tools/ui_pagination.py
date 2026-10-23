"""Real DOM pagination journey using the isolated UI-smoke test account."""
from playwright.sync_api import expect
from pathlib import Path

from tools.pagination_checks import seed_records


def run_pagination_journey(page, api, device):
    uid = api.get('/api/session').json()['user']['id']
    ids = seed_records(uid, 201, 'inventory')
    target = api.get(f'/api/items/{ids[0]}').json()
    page.evaluate("async()=>{resetLists();await reloadData();nav('inventory');}")
    inventory = page.get_by_role('navigation', name='inventory pages', exact=True)
    total = api.get('/api/items').json()['total']
    expect(inventory.get_by_role('status')).to_contain_text(f'1–50 of {total}')
    for index in range(4):
        inventory.get_by_role('button', name='Next', exact=True).click()
        expect(inventory.get_by_role('status')).to_contain_text(f'Page {index + 2} of')
    # An older record outside both original 200-item fetches must be editable.
    page.locator(f'[data-action="edit"][data-id="{target["id"]}"]').filter(visible=True).click()
    expect(page.locator('#field-sku')).to_have_value(target['sku'])
    page.get_by_role('button', name='Close', exact=True).click()
    page.locator(f'[data-action="prepare"][data-id="{target["id"]}"]').filter(visible=True).click()
    expect(page.locator('#publish-item')).to_have_value(str(target['id']))
    publisher = page.get_by_role('navigation', name='publish pages', exact=True)
    publisher.get_by_role('button', name='Next', exact=True).click()
    expect(publisher.get_by_role('status')).to_contain_text('Page 2 of')
    page.locator('#publish-search').fill(target['sku'])
    expect(publisher.get_by_role('status')).to_contain_text('1–1 of 1 · Page 1 of 1')
    expect(page.locator('#publish-item')).to_have_value(str(target['id']))

    page.evaluate("nav('inventory')")
    page.locator('#inventory-search').fill(target['sku'])
    expect(inventory.get_by_role('status')).to_contain_text('1–1 of 1 · Page 1 of 1')
    # Delay an older search response until after a new search completes.
    page.evaluate('''()=>{
      window.testFetch=window.fetch;window.releaseOldSearch=null;
      window.fetch=async(url,options)=>{
        const response=await window.testFetch(url,options);
        if(String(url).includes('q=DELAYED-OLD-SEARCH&')){
          await new Promise(resolve=>{window.releaseOldSearch=resolve;});
        }
        return response;
      };
    }''')
    page.locator('#inventory-search').fill('DELAYED-OLD-SEARCH')
    page.wait_for_function('window.releaseOldSearch !== null')
    page.locator('#inventory-search').fill(target['sku'])
    expect(inventory.get_by_role('status')).to_contain_text('1–1 of 1 · Page 1 of 1')
    page.evaluate('''async()=>{window.releaseOldSearch();window.fetch=window.testFetch;
      await new Promise(resolve=>setTimeout(resolve,100));}''')
    expect(page.locator('#inventory-search')).to_have_value(target['sku'])
    expect(inventory.get_by_role('status')).to_contain_text('1–1 of 1 · Page 1 of 1')
    page.locator('#inventory-search').fill('')
    expect(inventory.get_by_role('status')).to_contain_text(f'1–50 of {total}')

    # A failed page request must leave the last good page and controls intact.
    page.evaluate('''()=>{
      window.testFetch=window.fetch;
      window.fetch=(url,options)=>String(url).includes('/api/items?status=all&q=&limit=50&offset=50')
        ?Promise.resolve(new Response(JSON.stringify({detail:'Synthetic page outage'}),
          {status:503,headers:{'content-type':'application/json'}}))
        :window.testFetch(url,options);
    }''')
    inventory.get_by_role('button', name='Next', exact=True).click()
    expect(page.locator('.toast').filter(has_text='Synthetic page outage')).to_be_visible()
    expect(inventory.get_by_role('status')).to_contain_text(f'1–50 of {total}')
    expect(inventory.get_by_role('button', name='Next', exact=True)).to_be_enabled()
    page.evaluate('()=>{window.fetch=window.testFetch;}')
    page.locator('button[data-filter="sold"]').click()
    expect(inventory.get_by_role('status')).to_contain_text('Page 1 of 1')
    page.locator('button[data-filter="all"]').click()
    expect(inventory.get_by_role('status')).to_contain_text(f'1–50 of {total}')

    seed_records(uid, 201, 'actions')
    page.evaluate("async()=>{await reloadData();nav('actions');}")
    actions = page.get_by_role('navigation', name='actions pages', exact=True)
    expect(actions.get_by_role('status')).to_contain_text('1–50 of 201')
    for index in range(4):
        actions.get_by_role('button', name='Next', exact=True).click()
        expect(actions.get_by_role('status')).to_contain_text(f'Page {index + 2} of')
    expect(actions.get_by_role('status')).to_contain_text('201–201 of 201')
    page.locator('[data-action="clear-delist"]').click()
    # Deleting the sole record on the last page must clamp to the previous page.
    expect(actions.get_by_role('status')).to_contain_text('151–200 of 200 · Page 4 of 4')
    expect(page.get_by_text('Your removal queue is clear', exact=True)).to_have_count(0)

    seed_records(uid, 501, 'sales')
    page.evaluate("async()=>{await reloadData();nav('sales');}")
    sales = page.get_by_role('navigation', name='sales pages', exact=True)
    sales_total = api.get('/api/sales').json()['total']
    expect(sales.get_by_role('status')).to_contain_text(f'1–50 of {sales_total}')
    expect(page.locator('.metric').filter(has_text='Total sales').locator('.value')).to_have_text(str(sales_total))
    for index in range((sales_total - 1) // 50):
        sales.get_by_role('button', name='Next', exact=True).click()
        expect(sales.get_by_role('status')).to_contain_text(f'Page {index + 2} of')
    expect(sales.get_by_role('button', name='Next', exact=True)).to_be_disabled()
    expect(page.locator('.metric').filter(has_text='Total sales').locator('.value')).to_have_text(str(sales_total))
    assert not page.evaluate('document.documentElement.scrollWidth>window.innerWidth'), device + ' pagination overflow'
    page.screenshot(path=str(Path(__file__).resolve().parents[1] / 'docs' / f'v1-{device}-pagination.png'), full_page=True)
    print('CHECK', device, 'pagination: old caps, editing/publishing, search races, failure, queue clamp, full sales totals PASS', flush=True)
