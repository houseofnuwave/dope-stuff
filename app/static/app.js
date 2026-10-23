/* Dope Stuff Seller OS — zero-build, progressively-enhanced pilot client.
 * Deliberately no browser automation or simulated marketplace integrations.
 */
const $=q=>document.querySelector(q);
const money=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format((Number(n)||0)/100);
const escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const attr=escapeHtml;
const slug=s=>String(s||'').replace(/[^a-z0-9_-]/gi,'');
const icons={
 grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
 box:'<path d="M3 7 12 2l9 5v10l-9 5-9-5V7Z"/><path d="m3 7 9 5 9-5M12 12v10"/>',
 send:'<path d="m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13"/>',
 chart:'<path d="M3 3v18h18M7 15v3M12 9v9M17 5v13"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 search:'<circle cx="11" cy="11" r="8"/><path d="m21 21-4.4-4.4"/>',
 arrow:'<path d="M7 17 17 7M7 7h10v10"/>',
 tick:'<path d="m5 12 4 4L19 6"/>',
 close:'<path d="M18 6 6 18M6 6l12 12"/>',
 edit:'<path d="m4 17 1 3 3-1L20 7l-4-4L4 15v2ZM14 5l4 4"/>',
 checkcircle:'<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
 alert:'<path d="M12 2 2 21h20L12 2ZM12 9v5M12 18h.01"/>',
 upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
 download:'<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
 shield:'<path d="m12 2 9 4v6c0 6-4 9-9 10-5-1-9-4-9-10V6l9-4ZM9 12l2 2 4-4"/>',
 heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0l-1 1-1-1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
 settings:'<path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"/><path d="M4 10V7l3-1 2-2h6l2 2 3 1v3l2 2-2 2v3l-3 1-2 2H9l-2-2-3-1v-3l-2-2 2-2Z"/>',
 photo:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-6-6L4 20"/>',
 chevron:'<path d="m9 18 6-6-6-6"/>',
 users:'<circle cx="9" cy="8" r="4"/><path d="M2 21v-2a7 7 0 0 1 14 0v2M18 12a4 4 0 0 0 0-8M18 15a6 6 0 0 1 4 6"/>',
 spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
 logout:'<path d="M10 3H4v18h6M14 7l5 5-5 5m5-5H8"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
 filter:'<path d="M3 5h18M7 12h10M10 19h4"/>',
 ellipsis:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'
};
const icon=(name,size=18)=>`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.box}</svg>`;
const PAGE_SIZE=50;
const S={session:null,items:[],overview:null,sales:[],channels:{},nav:'overview',filter:'all',q:'',catalog:[],activeId:null,selectedItem:null,publishQ:'',pages:{inventory:0,publish:0,actions:0,sales:0},totals:{inventory:0,publish:0,actions:0,sales:0},pendingImport:null,pendingRestore:null,insights:null,actions:[]};
let reloadGeneration=0;
const APP=$('#app');
const toast=(msg,error=false)=>{const el=document.createElement('div');el.className='toast'+(error?' error':'');el.textContent=msg;$('#toast-root').append(el);setTimeout(()=>el.remove(),4500);};
async function api(url,{method='GET',body,form=false}={}){
  const options={method,credentials:'same-origin',headers:{}};
  if(method!=='GET'&&S.session?.csrf) options.headers['x-csrf-token']=S.session.csrf;
  if(body!==undefined){options.body=form?body:JSON.stringify(body);if(!form)options.headers['Content-Type']='application/json';}
  let r;
  try{r=await fetch(url,options);}catch{throw Error('Unable to reach the app. Check your connection.');}
  if(!r.ok){let detail=`Request failed (${r.status})`;try{const j=await r.json();detail=Array.isArray(j.detail)?j.detail.map(e=>e.msg).join('; '):j.detail||detail;}catch{};const error=Error(detail);error.status=r.status;throw error;}
  const ct=r.headers.get('content-type')||'';
  return ct.includes('json')?r.json():r;
}
const head=(title,subtitle,action='')=>`<div class="page-title between wrap"><div><div class="eyebrow">SELLER WORKSPACE / ${escapeHtml(S.nav)}</div><h1>${escapeHtml(title)}</h1><div class="section-sub">${escapeHtml(subtitle)}</div></div>${action}</div>`;
const status=(s)=>({draft:'Draft',active:'Live (seller reported)',sold:'Sold',archived:'Archived',not_started:'Not prepared',ready:'Ready to publish',manually_published:'Published (manual)',delist_required:'Remove listing now',delisted:'Marked removed'})[s]||s;
const statusPill=(s)=>`<span class="pill ${s==='active'||s==='manually_published'||s==='delisted'?'green':s==='sold'?'dark':s==='delist_required'?'red':s==='ready'?'amber':''}">${['manually_published','active'].includes(s)?'<span class="dot"></span>':''}${escapeHtml(status(s))}</span>`;
const thumbnail=(it)=>it.has_photo?`<img class="item-thumb" loading="lazy" src="/api/items/${it.id}/photo" alt="Photo of ${attr(it.title)}">`:`<div class="item-thumb">${icon('photo')}</div>`;
const itemLine=(it)=>`<div class="item-cell">${thumbnail(it)}<div><div class="table-title" title="${attr(it.title)}">${escapeHtml(it.title)}</div><div class="tiny muted">${escapeHtml(it.brand||'Unbranded')} · ${escapeHtml(it.sku)}</div></div></div>`;
const countLive=it=>Object.values(it.channels||{}).filter(x=>x.status==='manually_published').length;
const countAction=it=>Object.values(it.channels||{}).filter(x=>x.status==='delist_required').length;
function empty(iconName,title,body,action=''){return `<div class="empty"><div class="empty-icon">${icon(iconName)}</div><h3>${title}</h3><p>${body}</p>${action}</div>`;}
function pageControls(section){
 const total=S.totals[section],page=S.pages[section],pages=Math.max(1,Math.ceil(total/PAGE_SIZE));
 const start=total?page*PAGE_SIZE+1:0,end=Math.min((page+1)*PAGE_SIZE,total);
 return `<nav class="pagination row wrap between" aria-label="${section} pages"><button class="btn secondary small" data-action="page" data-section="${section}" data-page="${page-1}" ${page===0?'disabled':''}>Previous</button><span class="small muted" role="status" tabindex="-1" aria-live="polite">${start}–${end} of ${total} · Page ${page+1} of ${pages}</span><button class="btn secondary small" data-action="page" data-section="${section}" data-page="${page+1}" ${page+1>=pages?'disabled':''}>Next</button></nav>`;
}
function resetLists(){
 clearTimeout(searchTimeout);
 reloadGeneration++;S.pages={inventory:0,publish:0,actions:0,sales:0};S.totals={inventory:0,publish:0,actions:0,sales:0};
 S.items=[];S.catalog=[];S.sales=[];S.actions=[];S.overview=null;S.insights=null;
 S.activeId=null;S.selectedItem=null;S.q='';S.publishQ='';S.filter='all';
}
function authLanding(){
  APP.innerHTML=`<div class="landing">
    <header class="land-nav"><div class="brand">Dope Stuff<span>SELLER OS</span></div><div class="row"><button class="btn secondary small" data-action="login">Log in</button><button class="btn small" data-action="register">Get started ${icon('arrow',15)}</button></div></header>
    <section class="land-hero"><div><div class="eyebrow">A smarter way to sell what you own</div><h1>Your inventory.<br><em>Under control.</em></h1><p>An organized workspace for resellers who sell on more than one marketplace. Create listings, prepare channel-specific copy, track where you published, and see what you actually earn.</p><div class="hero-buttons"><button class="btn" data-action="register">Create free workspace ${icon('arrow')}</button><button class="btn secondary" data-action="login">I have an account</button></div><p class="mini-note">Early pilot · Assisted publishing, not automated posting · No credit card required</p></div>
    <div class="mockapp"><div class="mockapp-inner"><div class="between"><div class="brand" style="font-size:23px">Dope Stuff</div><span class="pill green">Workspace preview</span></div><div class="mock-bars"><i></i><i></i><i></i></div><div class="eyebrow">INVENTORY OVERVIEW</div><div class="mock-big">A clearer picture.</div><div class="mock-grid"><div class="mock-tile"><b>42</b><small>Items</small></div><div class="mock-tile"><b>18</b><small>Active</small></div><div class="mock-tile"><b>9</b><small>Sold</small></div></div><div class="tiny muted strong" style="margin-bottom:8px">RECENT INVENTORY · SAMPLE DATA</div><div class="mock-list"><div class="mock-product"></div><div style="flex:1"><div class="strong small">Leather ankle boots</div><div class="tiny muted">Grailed, Depop, eBay</div></div><span class="pill green">Prepared</span></div><div class="mock-list"><div class="mock-product alt"></div><div style="flex:1"><div class="strong small">Vintage suede jacket</div><div class="tiny muted">Needs publishing review</div></div><span class="pill amber">Action needed</span></div></div></div></section>
    <div class="feature-strip"><span>ONE INVENTORY</span> · <span>BETTER LISTINGS</span> · <span>HONEST PROFIT TRACKING</span></div>
    <section class="land-section"><div class="eyebrow">THE WORKFLOW</div><h2>Every piece, one place.</h2><div class="land-features"><div class="card land-feature"><div class="feature-icon">${icon('box',22)}</div><h3>Catalog once.</h3><p>Build a reusable record with SKU, photos, cost, condition and notes. No scattered spreadsheets.</p></div><div class="card land-feature"><div class="feature-icon">${icon('send',22)}</div><h3>Prepare everywhere.</h3><p>Generate clear channel-ready drafts and finish publishing on the marketplace yourself.</p></div><div class="card land-feature"><div class="feature-icon">${icon('shield',22)}</div><h3>Keep stock honest.</h3><p>Record a sale and immediately see where you must remove remaining listings manually.</p></div></div></section>
    <section class="land-pricing"><div class="land-pricing-inner"><div><div class="eyebrow">FOUNDING SELLER PILOT</div><h2>Help shape the tools you actually need.</h2><p>We're testing a lean product with working sellers before launching subscriptions. Pilot access is free while we validate the core workflow. Future pricing is illustrative.</p></div><div class="price-card"><div class="eyebrow">FUTURE PRO PLAN · TARGET PRICE</div><div class="row" style="margin:12px 0"><strong>$39.99</strong><span class="muted">/ month</span></div><p>Inventory, listing preparation, manual publishing ledger, sales and profit. Marketplace automation and AI features require separate development and permissions.</p><form id="pilot-form" class="row"><input name="email" type="email" required autocomplete="email" placeholder="Email for pilot updates"><button class="btn">Join list</button></form><p class="fineprint" style="margin-top:10px">Interest only. No payment collected or guaranteed enrollment.</p></div></div></section><div class="footer">Dope Stuff. Independent pilot; not affiliated with any resale marketplace.</div>
   </div>`;
}
function shell(){
 const nav=[['overview','grid','Overview'],['inventory','box','Inventory'],['publish','send','Publish studio'],['actions','alert','Action center'],['sales','chart','Sales & profit'],['plans','spark','Pricing'],['feedback','heart','Feedback'],['account','settings','Account']];
 const current=nav.find(n=>n[0]===S.nav)?.[2]||'Workspace';
 const links=nav.map(([key,ic,name])=>`<button class="nav-btn ${S.nav===key?'active':''}" data-nav="${key}">${icon(ic)} ${name}</button>`).join('');
 APP.innerHTML=`<div class="shell"><aside class="sidebar"><a href="#overview" class="brand">Dope Stuff<span>SELLER OS</span></a><div class="nav-group-label">WORKSPACE</div>${links}<div class="sidebar-bottom"><div class="alert small">${icon('shield')} <b>Assisted-only pilot</b><br>No marketplace is automatically connected or synced.</div><div class="sidebar-profile"><div class="avatar">${escapeHtml((S.session.user.name||'U')[0].toUpperCase())}</div><div style="flex:1;min-width:0"><div class="strong small" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(S.session.user.name)}</div><div class="tiny muted">Founding seller</div></div><button class="icon-btn" data-action="logout" title="Sign out" aria-label="Sign out">${icon('logout')}</button></div></div></aside><main class="main-area"><header class="topbar"><div class="row"><span class="brand" style="font-size:21px;display:none" id="mobile-brand">Dope Stuff</span><span class="small muted">Workspace</span><span class="muted">/</span><span class="small strong">${current}</span></div><div class="row"><span class="pill green">${icon('checkcircle',12)} Pilot workspace</span><button class="btn small" data-action="new">${icon('plus',15)} New listing</button></div></header><section id="screen" class="content"></section></main></div><div class="mobile-nav">${nav.filter(([key])=>['overview','inventory','publish','actions','sales'].includes(key)).map(([key,ic,name])=>`<button data-nav="${key}" class="${S.nav===key?'active':''}">${icon(ic)}${name==='Action center'?'Action':name==='Sales & profit'?'Sales':name.split(' ')[0]}</button>`).join('')}<button data-nav="account" class="${S.nav==='account'?'active':''}">${icon('settings')}More</button></div>`;

 const css=document.createElement('style');css.textContent='@media(max-width:850px){#mobile-brand{display:block!important}}';APP.append(css);
}
function recentTable(items,full=false){
 if(!items.length)return empty('box','No listings yet','Create your first item to begin organizing your resale business.',`<button class="btn" data-action="new">${icon('plus')} New listing</button>`);
 return `<div class="table-scroll desktop-item-table"><table class="data-table"><thead><tr><th>Item</th><th>Price</th><th>Status</th><th>Channels</th><th>Actions</th></tr></thead><tbody>${items.map(it=>`<tr><td>${itemLine(it)}</td><td><span class="strong">${money(it.price_cents)}</span><div class="tiny muted">Cost ${money(it.cost_cents)}</div></td><td>${statusPill(it.status)}</td><td><div class="tiny strong">${countLive(it)} reported live</div>${countAction(it)?'<span class="pill red">'+countAction(it)+' delist now</span>':'<div class="tiny muted">'+Object.values(it.channels).filter(c=>c.status==='ready').length+' ready</div>'}</td><td><div class="action-dots"><button class="btn small secondary" data-action="prepare" data-id="${it.id}">Prepare</button>${it.status==='sold'?`<button class="btn small pale" data-action="delist" data-id="${it.id}">Review</button><button class="btn small secondary" data-action="duplicate" data-id="${it.id}">Duplicate</button>`:`<button class="btn small pale" data-action="sold" data-id="${it.id}">Sold</button><button class="btn small secondary" data-action="edit" data-id="${it.id}">${icon('edit',14)}</button><button class="btn small pale" data-action="duplicate" data-id="${it.id}" title="Duplicate this listing as a fresh draft">Duplicate</button><button class="icon-btn" aria-label="Archive item" title="Archive item" data-action="archive" data-id="${it.id}">${icon('close',14)}</button>`}</div></td></tr>`).join('')}</tbody></table></div><div class="mobile-item-list">${items.map(it=>`<div class="mobile-item"><div class="between">${itemLine(it)}<b class="small">${money(it.price_cents)}</b></div><div class="between" style="margin:12px 0">${statusPill(it.status)}<span class="tiny muted">${countLive(it)} live · ${countAction(it)} delist tasks</span></div><div class="row wrap"><button class="btn small secondary" data-action="prepare" data-id="${it.id}">Prepare</button>${it.status==='sold'?`<button class="btn small pale" data-action="delist" data-id="${it.id}">Review</button><button class="btn small secondary" data-action="duplicate" data-id="${it.id}">Duplicate</button>`:`<button class="btn small pale" data-action="sold" data-id="${it.id}">Mark sold</button><button class="btn small secondary" data-action="edit" data-id="${it.id}">Edit</button><button class="btn small pale" data-action="duplicate" data-id="${it.id}">Duplicate</button><button class="icon-btn" title="Archive" aria-label="Archive item" data-action="archive" data-id="${it.id}">${icon('close',14)}</button>`}</div></div>`).join('')}</div>`;
}
function overviewView(){
 const o=S.overview||{stats:{inventory:0,available:0,active:0,inventory_value:0},finance:{gross:0,profit:0,sales:0},action_required:0,latest:[]};
 const stats=[["Inventory",o.stats.inventory,'Items in your catalog'],['Reported live',o.stats.active,'Seller-confirmed only'],['Gross sales',money(o.finance.gross),'Manually recorded'],['Net profit',money(o.finance.profit),'After costs + fees']];
 return `${head('A clearer picture.','One place for your listings, publishing work and actual proceeds.',`<button class="btn" data-action="new">${icon('plus')} Add inventory</button>`)}
 ${!o.stats.inventory?`<div class="notice welcome-card"><div><div class="eyebrow">YOUR FIRST 10 PIECES</div><h3>Start with what you already own.</h3><p class="small">Add your first item with up to 8 photos, or review a spreadsheet before importing your inventory. Nothing is posted to marketplaces automatically.</p></div><div class="row wrap"><button class="btn" data-action="new">${icon('plus')} Add first item</button><button class="btn secondary" data-action="import">${icon('upload')} Import inventory</button></div></div>`:''}
 ${o.action_required?`<div class="alert between wrap"><div>${icon('alert')} <b>${o.action_required} live listing(s) need manual removal.</b> This software has not removed them from marketplaces.</div><button class="btn small secondary" data-nav="actions">Review removal tasks</button></div>`:''}
 <div class="stats">${stats.map(([label,value,foot])=>`<div class="card metric"><div class="metric-label">${label}</div><div class="value">${value}</div><div class="metric-foot">${foot}</div></div>`).join('')}</div>
 <div class="two-col"><div class="card"><div class="between" style="padding:22px 22px 12px"><div><h3 style="margin-bottom:3px">Recent inventory</h3><div class="small muted">Your latest saved pieces</div></div><button class="link small" data-nav="inventory">View all ${icon('arrow',13)}</button></div>${recentTable(o.latest)}</div><div class="stack"><div class="card card-pad"><div class="eyebrow">NEXT BEST ACTION</div><h3 style="margin:15px 0 10px">Prepare your next listing.</h3><p class="small">Create a consistent product record once, then copy tailored details to the platforms you choose.</p><button class="btn full" data-action="new">Create listing ${icon('arrow')}</button></div><div class="card card-pad"><h3>Inventory value</h3><div class="serif" style="font-size:39px">${money(o.stats.inventory_value)}</div><p class="tiny muted">Asking prices for unsold items. This is not cash or realized revenue.</p><div class="divider"></div><div class="feature-row">${icon('shield')}<div><b class="small">No false synchronization</b><div class="tiny muted">Every channel status reflects your confirmation, not an API connection.</div></div></div></div></div></div>`;
}
function inventoryView(){
 const actions=`<div class="row wrap"><button class="btn secondary small" data-action="import">${icon('upload',15)} Import CSV</button><button class="btn secondary small" data-action="export">${icon('download',15)} Export</button><button class="btn" data-action="new">${icon('plus')} New listing</button></div>`;
 return `${head('Your inventory.','Every item has one canonical record and SKU.',actions)}
 <div class="card"><div style="padding:20px"><div class="toolbar"><div class="filters">${['all','draft','active','sold','archived'].map(x=>`<button class="filter ${S.filter===x?'active':''}" data-filter="${x}">${x==='all'?'All':status(x)}</button>`).join('')}</div><div class="row"><input id="inventory-search" value="${attr(S.q)}" placeholder="Search title, brand or SKU" aria-label="Search inventory"></div></div><div class="tiny muted">${S.items.length} of ${S.totals.inventory} matching items shown · Active statuses are seller-reported</div></div>${!S.items.length&&(S.q||S.filter!=='all')?empty('search','No matching inventory','Try another search or filter.'):recentTable(S.items,true)}${pageControls('inventory')}</div><p class="fineprint" style="margin-top:14px">Archiving an item here will not remove any listing from an external website.</p>`;
}
function publishView(){
 const channels=Object.entries(S.channels);
 const current=S.selectedItem||S.catalog.find(x=>x.id===S.activeId)||S.catalog.find(x=>x.status!=='sold')||S.catalog[0];
 const select=`<select id="publish-item" aria-label="Select inventory item"><option value="">Choose an item</option>${(current&&!S.catalog.some(it=>it.id===current.id)?[current,...S.catalog]:S.catalog).map(it=>`<option value="${it.id}" ${current?.id===it.id?'selected':''}>${escapeHtml(it.title)} (${escapeHtml(it.sku)})</option>`).join('')}</select>`;
 return `${head('Publish studio.','Prepare channel-ready drafts, then complete publishing yourself.',`<button class="btn" data-action="new">${icon('plus')} New listing</button>`)}<div class="notice small" style="margin-bottom:18px">${icon('shield')} All marketplace workflows are currently manual-assisted. Nothing on this screen automatically posts, edits, or deletes an external listing.</div><div class="card card-pad" style="margin-bottom:18px"><div class="eyebrow">STEP 01</div><div class="between wrap"><div><h3 style="margin:8px 0 5px">Select an inventory item</h3><p class="small" style="margin:0">Only items you own can be prepared for listing.</p></div><div style="width:min(100%,390px)"><label class="small" for="publish-search">Search title, brand or SKU</label><input id="publish-search" value="${attr(S.publishQ)}" placeholder="Search all your inventory">${select}</div></div>${pageControls('publish')}</div><div class="between" style="margin:20px 0 14px"><h3 style="margin:0">Marketplace workflows</h3><span class="pill">${channels.length} supported manual workspaces</span></div>
 ${current?`<div class="readiness-overview card card-pad"><div><div class="eyebrow">LISTING QUALITY CONTROL</div><h3 style="margin:7px 0 5px">${current.readiness.complete} of ${current.readiness.total} details prepared.</h3><p class="small">${current.readiness.complete===current.readiness.total?'The record is documented. Verify accuracy before publishing.':'Fill the missing details to help buyers assess the actual item.'} This is not an authenticity or condition guarantee.</p></div><button class="btn secondary small" data-action="edit" data-id="${current.id}" ${current.status==='sold'?'disabled':''}>Review item ${icon('arrow',14)}</button></div>`:''}
 <div class="channel-grid">${channels.map(([key,c])=>{const entry=current?.channels?.[key];const st=entry?.status||'not_started';return `<div class="card channel-card"><div><div class="between"><div class="channel-badge">${c.name[0]}</div>${statusPill(st)}</div><h3 style="font-size:21px;margin:15px 0 5px">${escapeHtml(c.name)}</h3><p>Generate draft and open marketplace. Mark the listing published after confirming yourself.</p></div><button class="btn small ${st==='delist_required'?'danger':'secondary'}" data-action="${st==='delist_required'?'delist':'kit'}" data-id="${current?.id||''}" data-channel="${key}" ${!current||(['sold','archived'].includes(current.status)&&st!=='delist_required')?'disabled':''}>${st==='delist_required'?'Review removal':current?.status==='sold'?'Sold item':'Prepare listing'} ${icon('arrow',14)}</button></div>`;}).join('')}</div>`;
}
function actionsView(){
 const actions=S.actions||[];
 const count=S.totals.actions;
 return `${head('Action center.','Prevent double sales by removing sold items from other marketplaces yourself.')}
 <div class="alert" style="margin:0 0 20px">${icon('alert')} <strong>${count} external listing${count===1?'':'s'} awaiting manual removal.</strong> Dope Stuff never remotely deletes listings. Mark each task done only after verifying removal on the marketplace.</div>
 ${actions.length?`<div class="card">${pageControls('actions')}<div class="card-pad"><div class="eyebrow">MANUAL REMOVAL QUEUE</div><h3>Protect the next buyer.</h3><p class="small">Oldest seller-reported listing first. A sold item can still be visible on another platform until you personally remove it.</p></div>${actions.map(a=>`<div class="seller-check action-item"><div style="flex:1;min-width:0"><div class="eyebrow">${escapeHtml(a.display_name)}</div><h3 style="font-size:17px;margin:6px 0">${escapeHtml(a.title)}</h3><div class="tiny muted">SKU ${escapeHtml(a.sku)} · Needs manual removal</div>${a.listing_url?`<a href="${attr(a.listing_url)}" target="_blank" rel="noopener noreferrer" class="inline-link">Open listing on marketplace ${icon('arrow',13)}</a>`:'<p class="tiny muted" style="margin-top:7px">No listing link saved — locate this item in your marketplace account.</p>'}</div><button class="btn small secondary" data-action="clear-delist" data-id="${a.item_id}" data-channel="${attr(a.channel)}">I removed it ${icon('checkcircle',14)}</button></div>`).join('')}</div>`:S.totals.actions?empty('alert','This page changed','Reload the queue to see remaining tasks.',`<button class="btn secondary" data-action="reload-lists">Reload queue</button>`):empty('checkcircle','Your removal queue is clear','No listings currently require manual delisting. This reflects only the marketplace statuses you have recorded in Dope Stuff.')}
 <p class="fineprint" style="margin-top:16px">The queue is based entirely on seller-entered information. Dope Stuff cannot detect outside sales or confirm live listings.</p>`;
}
function salesView(){
 const sales=S.sales;const gross=S.insights?.totals?.gross_cents||0,profit=S.insights?.totals?.profit_cents||0;
 const by={};for(const channel of S.insights?.channels||[])by[channel.channel]=channel.gross_cents;
 const rows=Object.entries(by).sort((a,b)=>b[1]-a[1]);const max=Math.max(...rows.map(x=>x[1]),1);
 return `${head('Sales & profit.','Track actual transactions, fees, shipping and cost of goods.',`<a href="/api/sales-export.csv" download class="btn secondary">${icon('download',15)} Export sales CSV</a>`)}
 <div class="stats" style="grid-template-columns:repeat(3,1fr)"><div class="card metric"><div class="metric-label">Total sales</div><div class="value">${S.totals.sales}</div><div class="metric-foot">Manually recorded</div></div><div class="card metric"><div class="metric-label">Gross sales</div><div class="value">${money(gross)}</div><div class="metric-foot">Before fees & costs</div></div><div class="card metric"><div class="metric-label">Net profit</div><div class="value">${money(profit)}</div><div class="metric-foot">Not tax-adjusted</div></div></div>
 <div class="card card-pad" style="margin:0 0 18px"><div class="eyebrow">REALIZED PERFORMANCE BY CHANNEL</div><div class="table-scroll"><table class="data-table"><thead><tr><th>Marketplace</th><th>Sales</th><th>Gross</th><th>Net profit</th><th>Margin</th></tr></thead><tbody>${(S.insights?.channels||[]).length?(S.insights?.channels||[]).map(c=>`<tr><td><b>${escapeHtml(c.display_name)}</b></td><td>${c.sales}</td><td>${money(c.gross_cents)}</td><td><b>${money(c.profit_cents)}</b></td><td>${c.gross_cents?(100*c.profit_cents/c.gross_cents).toFixed(1)+'%':'—'}</td></tr>`).join(''):'<tr><td colspan="5" class="muted">Record your first sale to compare marketplaces.</td></tr>'}</tbody></table></div><p class="fineprint" style="margin-top:12px">${escapeHtml(S.insights?.disclaimer||'Seller-reported transactions only.')}</p></div>
 <div class="two-col"><div class="card"><div class="card-pad"><h3>Transactions</h3><p class="small">Use the Sold button on inventory items to record sales.</p>${pageControls('sales')}</div>${sales.length?`<div class="table-scroll"><table class="data-table"><thead><tr><th>Item</th><th>Channel</th><th>Sale</th><th>Profit</th></tr></thead><tbody>${sales.map(s=>`<tr><td><b class="small">${escapeHtml(s.title)}</b><div class="tiny muted">${escapeHtml(s.sku)}</div></td><td>${escapeHtml(S.channels[s.channel]?.name||s.channel)}</td><td>${money(s.sold_cents)}</td><td class="strong">${money(s.sold_cents-s.fee_cents-s.ship_cents-s.cost_cents)}</td></tr>`).join('')}</tbody></table></div>`:empty('chart','No sales recorded','Record your first sale from an inventory item.')}</div><div class="card card-pad"><h3>Revenue by marketplace</h3><p class="small">Based on the channel selected when recording a sale.</p>${rows.length?rows.map(([c,v])=>`<div style="margin:22px 0"><div class="between small" style="margin-bottom:7px"><b>${escapeHtml(S.channels[c]?.name||c)}</b><span>${money(v)}</span></div><div class="progress-track"><div class="progress-fill" style="width:${Math.round(100*v/max)}%"></div></div></div>`).join(''):empty('chart','No channel data','Your channel breakdown will appear after a recorded sale.')}</div></div>`;
}
function plansView(){
 const tiers=[['Starter','$14.99','For casual sellers',['100 new items monthly','Unlimited stored inventory','Assisted publishing','Basic sales tracking']],['Pro','$39.99','For working resellers',['500 new items monthly','Bulk preparation','Advanced profit analytics','Priority marketplace workflows']],['Studio','$89.99','For resale operations',['2,000 new items monthly','Team access (future)','Advanced reporting','Priority support (future)']]];
 return `${head('Simple pricing.','Proposed public plans. Billing is not enabled in this pilot.')}
 <div class="alert" style="margin-bottom:18px">There is no checkout, subscription activation, or automatic billing in this MVP. These are target prices for customer validation—not features already delivered.</div><div class="price-grid">${tiers.map(([name,price,desc,features])=>`<div class="card tier ${name==='Pro'?'featured':''}"><div class="eyebrow">${name==='Pro'?'RECOMMENDED':'FUTURE PLAN'}</div><h3 style="margin:0">${name}</h3><div><span class="tier-price">${price}</span><span class="muted"> / month</span></div><p>${desc}</p><ul>${features.map(f=>`<li>${f}</li>`).join('')}</ul><button class="btn ${name==='Pro'?'':'secondary'} full" data-action="pilot">Request pilot access</button></div>`).join('')}</div><p class="fineprint" style="margin-top:20px">An actual paid launch must include a payment processor, terms, privacy notice, support commitments and onboarding. Do not accept customer payments before these are implemented.</p>`;
}
function feedbackView(){return `${head('Help shape Dope Stuff.','We want evidence from working resellers, not feature wishlists alone.')}
 <div class="card card-pad feedbackbox"><div class="eyebrow">PRODUCT RESEARCH</div><h3 style="margin:12px 0">What was difficult today?</h3><p class="small">Tell us about the real workflow you attempted, the marketplace involved, and how much time you expected to save.</p><form id="feedback-form"><div class="form-block"><label for="rating">Overall usefulness</label><select name="rating" id="rating"><option value="5">5 — Extremely useful</option><option value="4">4 — Useful</option><option value="3">3 — Somewhat useful</option><option value="2">2 — Limited value</option><option value="1">1 — Not useful</option></select></div><div class="form-block"><label for="feedback-text">Your feedback</label><textarea id="feedback-text" name="message" required minlength="5" placeholder="I was trying to ... and couldn't ..."></textarea></div><button class="btn">Submit feedback ${icon('arrow')}</button></form></div><div class="card card-pad feedbackbox" style="margin-top:18px"><h3>Three questions we are testing</h3><div class="seller-check">${icon('checkcircle')} Can sellers prepare a quality listing faster than they do today?</div><div class="seller-check">${icon('checkcircle')} Can sellers avoid forgetting to remove sold items?</div><div class="seller-check">${icon('checkcircle')} Will sellers pay for one clear inventory system?</div></div>`;}
function accountView(){return `${head('Your account.','Own your catalog, keep a complete backup, and recover it when necessary.')}
 <div class="two-col"><div class="card card-pad"><div class="eyebrow">DATA PORTABILITY</div><h3 style="margin-top:12px">Your records. Always yours.</h3><p class="small">Download a private ZIP of your inventory, photos, sales, historical feedback, and self-reported marketplace statuses. Store it securely — it includes financial details and personal notes.</p><a class="btn" href="/api/account/export.zip" download>${icon('download')} Download full backup</a><p class="fineprint" style="margin-top:13px">This archive is not encrypted. Store it in a private location.</p></div>
 <div class="card card-pad"><div class="eyebrow">RECOVERY</div><h3 style="margin-top:12px">Restore your inventory.</h3><p class="small">Preview an original Dope Stuff backup, then restore it into a <strong>blank</strong> account using the same email. A restore never publishes or changes external listings.</p><button class="btn secondary" data-action="restore-account">Preview a backup ${icon('arrow',14)}</button><p class="fineprint" style="margin-top:13px">Pilot limit: 128 MB ZIP, 500 items. Existing records cannot be overwritten or merged.</p></div></div>
 <div class="card card-pad" style="margin-top:18px"><div class="eyebrow">SECURITY</div><h3 style="margin-top:12px">Protect your workspace.</h3><p class="small">Change your password. Other signed-in sessions will be revoked; this browser remains signed in.</p><button class="btn secondary" data-action="change-password">Change password ${icon('shield',14)}</button></div>
 <div class="card card-pad" style="margin-top:18px"><div class="eyebrow">ACCOUNT CONTROL</div><h3 style="margin-top:12px">Delete your workspace.</h3><p class="small">Permanently remove your Dope Stuff account, local inventory, photographs and sales. Download your backup first. External marketplace listings remain unchanged.</p><button class="btn secondary" data-action="delete-account">Review account deletion</button></div>
 <div class="notice small" style="margin-top:20px">This is a local pilot, not a hosted cloud account. Export regularly. Confirm marketplace listings yourself after restoring older records.</div>`;}
function passwordModal(){modal('Change your password',`<p class="small">Choose a new password with at least 12 characters. This will sign out other devices and protect your inventory.</p><form id="password-form" class="stack" style="margin-top:18px"><div class="form-block"><label for="pw-current">Current password</label><input id="pw-current" name="current_password" type="password" minlength="10" autocomplete="current-password" required></div><div class="form-block"><label for="pw-new">New password (12+ characters)</label><input id="pw-new" name="new_password" type="password" minlength="12" autocomplete="new-password" required></div><div class="row wrap"><button type="button" class="btn secondary" data-action="close">Cancel</button><button type="submit" class="btn">Update password ${icon('shield',14)}</button></div></form>`);}
function restoreAccountModal(){S.pendingRestore=null;modal('Restore a Dope Stuff backup',`<div class="notice small">${icon('shield')} Restore only into a blank account with the same email as the archive. We check photos, statuses, sales, and the integrity of the archive before importing. External listings are never changed.</div>
 <form id="restore-form" class="stack" style="margin-top:18px"><div class="form-block"><label for="restore-file">Original Dope Stuff backup ZIP</label><input id="restore-file" name="file" type="file" accept=".zip,application/zip" required><div class="hint">Pilot limit: 128 MB ZIP, 500 items.</div></div><button class="btn secondary" type="submit">Inspect backup first ${icon('search',15)}</button><div id="restore-results" aria-live="polite"></div></form>`, '', false);}
function deleteAccountModal(){modal('Permanently delete Dope Stuff account',`<div class="alert small">${icon('alert')} This action cannot be undone. Download your backup first. Any published marketplace listings stay live until you remove them yourself.</div>
 <form id="delete-account-form" style="margin-top:20px" class="stack"><div class="form-block"><label for="delete-confirm">Type DELETE MY ACCOUNT to confirm</label><input id="delete-confirm" name="confirmation" autocomplete="off" required pattern="DELETE MY ACCOUNT" placeholder="DELETE MY ACCOUNT"></div><div class="form-block"><label for="delete-password">Current password</label><input id="delete-password" type="password" name="password" autocomplete="current-password" required minlength="10"></div><button class="btn danger full" type="submit">Permanently delete my data</button></form>`, '', false);}
function render(){if(!S.session?.authenticated){authLanding();return;}shell();let html={overview:overviewView,inventory:inventoryView,publish:publishView,sales:salesView,plans:plansView,feedback:feedbackView,account:accountView,actions:actionsView}[S.nav]?.()||overviewView();$('#screen').innerHTML=html;}
async function fetchListPage(path,key,page){
 const query=path.includes('?')?'&':'?';
 let data=await api(`${path}${query}limit=${PAGE_SIZE}&offset=${page*PAGE_SIZE}`);
 const last=Math.max(0,Math.ceil(data.total/PAGE_SIZE)-1);
 if(page>last){page=last;data=await api(`${path}${query}limit=${PAGE_SIZE}&offset=${page*PAGE_SIZE}`);}
 return {rows:data[key],total:data.total,page};
}
async function reloadData(options={}){
 if(!S.session?.authenticated)return false;
 const generation=++reloadGeneration,owner=S.session.user.id,pages={...(options.pages||S.pages)},activeId=options.clearSelection?null:S.activeId;
 const [a,b,c,d,e,f,g]=await Promise.all([api('/api/overview'),
  fetchListPage(`/api/items?status=${encodeURIComponent(S.filter)}&q=${encodeURIComponent(S.q)}`,'items',pages.inventory),
  api('/api/channels'),fetchListPage('/api/sales','sales',pages.sales),
  fetchListPage(`/api/items?status=all&q=${encodeURIComponent(S.publishQ)}`,'items',pages.publish),
  api('/api/insights'),fetchListPage('/api/actions','actions',pages.actions)]);
 let selected=e.rows.find(item=>item.id===activeId)||b.rows.find(item=>item.id===activeId)||null;
 if(activeId&&!selected){try{selected=await api(`/api/items/${activeId}`);}catch(error){if(error.status!==404)throw error;}}
 if(generation!==reloadGeneration||!S.session?.authenticated||S.session.user.id!==owner)return false;
 S.overview=a;S.items=b.rows;S.channels=c.channels;S.sales=d.rows;S.catalog=e.rows;S.insights=f;S.actions=g.rows;S.selectedItem=selected;
 if(options.clearSelection)S.activeId=null;
 for(const [section,data] of Object.entries({inventory:b,sales:d,publish:e,actions:g})){S.pages[section]=data.page;S.totals[section]=data.total;}
 return true;
}
async function refresh(){if(await reloadData())render();}
async function init(){const hash=location.hash.slice(1);let token='';if(hash.startsWith('reset=')){try{token=decodeURIComponent(hash.slice(6));}catch(e){}try{history.replaceState(null,'',location.pathname+location.search);}catch(e){location.hash='';}}try{S.session=await api('/api/session');if(S.session.authenticated){await reloadData();}}catch(e){toast(e.message,true);}if(['overview','inventory','publish','sales','plans','feedback','account','actions'].includes(hash))S.nav=hash;render();if(token){S.resetToken=token;resetPasswordModal();}}
function nav(n){S.nav=n;location.hash=n;render();window.scrollTo({top:0,behavior:'instant'});}
let modalReturnFocus=null;
function modal(title,body,footer='',wide=false){modalReturnFocus=document.activeElement;$('#modal-root').innerHTML=`<div class="modal-backdrop" data-action="dismiss"><section class="modal ${wide?'wide':''}" role="dialog" aria-modal="true" aria-label="${attr(title)}"><div class="modal-head"><div><div class="eyebrow">Dope Stuff / WORKSPACE</div><h2>${escapeHtml(title)}</h2></div><button class="icon-btn" data-action="close" title="Close" aria-label="Close">${icon('close')}</button></div><div class="modal-body">${body}</div>${footer?`<div class="modal-foot">${footer}</div>`:''}</section></div>`;const focus=$('.modal input:not([type=hidden]),.modal textarea,.modal select');focus?.focus();}
function closeModal(){$('#modal-root').innerHTML='';if(modalReturnFocus?.isConnected)modalReturnFocus.focus();modalReturnFocus=null;}
function authModal(mode='register'){
 const register=mode==='register';
 modal(register?'Create your workspace':'Welcome back',`<p class="small muted">${register?'Your private pilot workspace stores your inventory and sales. Access is limited during testing.':'Continue managing your inventory.'}</p><form id="auth-form" data-mode="${mode}" class="stack">${register?'<div><label for="auth-name">Name</label><input id="auth-name" name="name" minlength="2" maxlength="60" autocomplete="name" required placeholder="Your name"></div>':''}<div><label for="auth-email">Email</label><input id="auth-email" name="email" type="email" autocomplete="email" required placeholder="you@example.com"></div><div><label for="auth-password">Password</label><input id="auth-password" name="password" type="password" minlength="10" autocomplete="${register?'new-password':'current-password'}" required placeholder="At least 10 characters"></div>${register&&S.session?.invite_required?'<div><label for="auth-invite">Pilot invitation code</label><input id="auth-invite" name="invite_code" type="text" autocomplete="off" minlength="16" required placeholder="Provided with your invitation"></div>':''}<button class="btn full">${register?'Create free account':'Sign in'} ${icon('arrow')}</button></form><p class="small" style="margin:20px 0 0">${register?'Already have an account?':'New here?'} <button class="link" data-action="${register?'login':'register'}">${register?'Log in':'Create an account'}</button></p>${!register&&S.session?.recovery_available?'<p class="small" style="margin-top:12px"><button class="link" data-action="forgot-password">Forgot your password?</button></p>':''}`);
}
function forgotPasswordModal(){modal('Recover your workspace',`<p class="small muted">Enter your account email. If a matching account exists, Dope Stuff will send a single-use link valid for 30 minutes. We never reveal whether an email is registered.</p><form id="recovery-request-form" class="stack" style="margin-top:18px"><div class="form-block"><label for="recovery-email">Email address</label><input id="recovery-email" name="email" type="email" autocomplete="email" required placeholder="you@example.com"></div><button type="submit" class="btn full">Send recovery instructions</button></form>${S.session?.recovery_local?'<p class="small muted" style="margin-top:12px">For local testing, recovery emails appear in the private data/local-recovery-mail directory.</p>':''}`);}
function resetPasswordModal(){modal('Set a new password',`<p class="small muted">Create a new password with at least 12 characters. All existing sessions will be signed out.</p><form id="recovery-confirm-form" class="stack" style="margin-top:18px"><div class="form-block"><label for="recovery-new">New password</label><input id="recovery-new" name="new_password" type="password" minlength="12" autocomplete="new-password" required></div><div class="form-block"><label for="recovery-again">Repeat new password</label><input id="recovery-again" name="confirm_password" type="password" minlength="12" autocomplete="new-password" required></div><button class="btn full" type="submit">Reset password</button></form>`);}
function field(name,label,value='',type='text',placeholder='',extra=''){return `<div class="form-block"><label for="field-${attr(name)}">${escapeHtml(label)}</label><input id="field-${attr(name)}" type="${type}" name="${name}" value="${attr(value)}" placeholder="${attr(placeholder)}" ${extra}></div>`;}
function galleryHtml(it){return it?.photos?.length?`<div class="photo-gallery">${it.photos.map((p,n)=>`<div class="gallery-tile"><img src="${attr(p.url)}" alt="${attr(it.title)} photo ${n+1}" loading="lazy"><div class="gallery-controls">${n!==0?`<button type="button" class="gallery-cover" data-action="make-cover" data-id="${it.id}" data-photo="${p.id}" aria-label="Make photo ${n+1} the cover">Make cover</button>`:'<span class="cover-label">COVER</span>'}<button type="button" class="gallery-delete" data-action="delete-photo" data-id="${it.id}" data-photo="${p.id}" aria-label="Remove photo ${n+1}" title="Remove photo">${icon('close',14)}</button></div></div>`).join('')}</div>`:'';}
function itemEditor(it=null){
 const sold=it?.status==='sold';if(sold){toast('Sold items cannot be edited.',true);return;}
 const moneyval=k=>it?(it[k]/100).toFixed(2):'0.00';
 modal(it?'Edit inventory item':'New inventory item',`<form id="item-form" data-id="${it?.id||''}"><div class="form-grid">
 <div class="wide">${field('title','Item title *',it?.title||'','text','e.g. Black leather ankle boots','required maxlength="180"')}</div>
 ${field('brand','Brand',it?.brand||'','text','e.g. AllSaints')}${field('sku','SKU',it?.sku||'','text','Auto-generated if left blank')}
 ${field('category','Category',it?.category||'','text','e.g. Boots')}${field('size','Size',it?.size||'','text','e.g. EU 39')}
 ${field('color','Color',it?.color||'','text','e.g. Black')}
 <div class="form-block"><label for="item-condition">Verified condition *</label><select id="item-condition" name="condition" required><option value="" ${(!it||it?.condition==='Unspecified')?'selected':''} disabled>Select the actual condition</option>${['New with tags','New without tags','Like new','Good','Fair'].map(c=>`<option ${it?.condition===c?'selected':''}>${c}</option>`).join('')}</select><div class="hint">Inspect tags, wear and flaws before selecting a condition.</div></div>
 ${field('price','Asking price ($)',moneyval('price_cents'),'number','0.00','min="0" max="1000000" step="0.01" required')}
 ${field('cost','Purchase cost ($)',moneyval('cost_cents'),'number','0.00','min="0" max="1000000" step="0.01"')}
 ${field('shipping','Estimated shipping ($)',moneyval('shipping_cents'),'number','0.00','min="0" max="1000000" step="0.01"')}
 ${field('quantity','Quantity',it?.quantity??1,'number','1','min="0" max="999"')}
 <div class="wide form-block"><label for="item-description">Description (factual; no invented details)</label><textarea id="item-description" name="description" maxlength="3000" placeholder="Material, fit, measurements, known flaws…">${escapeHtml(it?.description||'')}</textarea></div>
 <div class="wide form-block"><label for="item-notes">Private seller notes</label><textarea id="item-notes" name="notes" maxlength="1000" style="min-height:70px" placeholder="Acquisition date, storage location, etc.">${escapeHtml(it?.notes||'')}</textarea></div>
 <div class="wide form-block"><label for="item-photos">Product gallery · up to 8 images</label><input id="item-photos" name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple><div class="hint">Choose multiple photos (6 MB maximum each). Saved securely, resized and stripped of EXIF location metadata. ${it?.photo_count||0} of 8 currently saved.</div><div id="editor-gallery">${galleryHtml(it)}</div></div>
 </div><div class="row wrap" style="justify-content:flex-end"><button class="btn secondary" type="button" data-action="close">Cancel</button><button class="btn" type="submit">${it?'Save changes':'Create item'} ${icon('checkcircle')}</button></div></form>`, '', true);
}
async function itemFormSubmit(form){
 const f=new FormData(form),id=Number(form.dataset.id||0);
 const cents=k=>Math.round(Number(f.get(k)||0)*100);
 const body={};for(const k of ['title','brand','sku','category','size','color','condition','description','notes'])body[k]=String(f.get(k)||'').trim();
 Object.assign(body,{price_cents:cents('price'),cost_cents:cents('cost'),shipping_cents:cents('shipping'),quantity:Number(f.get('quantity')||1)});
 const item=await api(id?`/api/items/${id}`:'/api/items',{method:id?'PUT':'POST',body});
 const selected=f.getAll('photos').filter(x=>x instanceof File&&x.size);
 if(selected.length){try{
   if(selected.length+(id?item.photo_count||0:0)>8)throw Error('Maximum 8 photos per item.');
   if(selected.some(x=>x.size>6*1024*1024))throw Error('Each photo must be 6 MB or smaller.');
   const fd=new FormData();selected.forEach(photo=>fd.append('photos',photo));
   await api(`/api/items/${item.id}/photos`,{method:'POST',body:fd,form:true});
 }catch(e){toast('Item saved, but photos failed: '+e.message,true);}}
 if(!id){S.pages.inventory=0;S.filter='all';S.q='';}
 closeModal();toast(id?'Item updated':'Item created');await refresh();
}
function kitModal(it,channel){
 if(!it){toast('Choose a listing first',true);return;}S.activeId=it.id;S.selectedItem=it;
 api(`/api/items/${it.id}/kit/${channel}`).then(k=>{
  const st=it.channels[channel]?.status||'not_started';
  modal(`Prepare for ${S.channels[channel].name}`,`<div class="selected-item">${thumbnail(it)}<div><b>${escapeHtml(it.title)}</b><div class="tiny muted">${escapeHtml(it.sku)} · ${money(it.price_cents)}</div></div></div><div class="notice small">${icon('shield')} This tool does not auto-publish to ${escapeHtml(S.channels[channel].name)}. Complete posting in the destination app.</div>
  <div class="readiness-review"><div class="between"><b class="small">Listing preparation</b><span class="pill ${k.readiness.complete===k.readiness.total?'green':'amber'}">${k.readiness.complete}/${k.readiness.total} checks</span></div><ul class="readiness-list">${k.readiness.checks.map(c=>`<li class="${c.ok?'ready':'todo'}">${icon(c.ok?'tick':'alert',14)} ${escapeHtml(c.label)}</li>`).join('')}</ul><p class="tiny muted">Advisory only — always confirm garment details and marketplace requirements yourself.</p></div>
  <ol class="step-list"><li>Check the facts, condition, and asking price.</li><li>Copy the title and description and open the marketplace.</li><li>Publish there, then return here to confirm.</li></ol>
  <div class="kit-columns"><div class="kit-field"><div class="between"><b class="small">LISTING TITLE</b><button data-action="copy-title">${icon('download',13)} Copy</button></div><pre id="kit-title">${escapeHtml(k.title)}</pre></div><div class="kit-field"><div class="between"><b class="small">DESCRIPTION</b><button data-action="copy-description">${icon('download',13)} Copy</button></div><pre id="kit-description">${escapeHtml(k.description)}</pre></div></div>
  <div class="row wrap" style="margin:17px 0"><a target="_blank" rel="noopener noreferrer" href="${attr(k.destination)}" class="btn secondary">Open ${escapeHtml(S.channels[channel].name)} ${icon('arrow')}</a><button class="btn pale" data-action="ready" data-id="${it.id}" data-channel="${channel}">Mark draft ready</button></div>
  <form id="channel-form" data-id="${it.id}" data-channel="${channel}"><div class="form-block"><label for="channel-url">Link to your published listing (optional)</label><input id="channel-url" name="listing_url" type="url" placeholder="https://…" value="${attr(it.channels[channel]?.listing_url||'')}"></div><div class="row wrap"><button class="btn" type="submit">I published this myself ${icon('checkcircle')}</button>${st==='manually_published'?`<button class="btn secondary" type="button" data-action="mark-removed" data-id="${it.id}" data-channel="${channel}">I removed this listing</button>`:''}</div></form>
 <p class="fineprint" style="margin-top:15px">Listing status is self-reported. Dope Stuff does not verify remote publication or receive orders.</p>`, '', true);
 }).catch(e=>toast(e.message,true));
}
function soldModal(it){
 if(!it||it.status==='sold'){toast('Item unavailable for recording a sale',true);return;}
 if(it.quantity!==1){toast('This pilot currently supports single-quantity sales only.',true);return;}
 const opts=Object.entries(S.channels).map(([k,c])=>`<option value="${k}">${escapeHtml(c.name)}</option>`).join('');
 modal('Record a sale',`<p class="small">Record the actual transaction for <b>${escapeHtml(it.title)}</b>. Other marketplaces will be flagged for removal; they will NOT be delisted automatically.</p><form id="sale-form" data-id="${it.id}"><div class="form-grid"><div class="wide form-block"><label for="sale-channel">Sold on</label><select id="sale-channel" name="channel">${opts}<option value="other">Other / Offline</option></select></div>${field('sold','Sale price ($)',(it.price_cents/100).toFixed(2),'number','0.00','required min="0" step="0.01"')}${field('fee','Marketplace fees ($)','0.00','number','0.00','min="0" step="0.01"')}${field('ship','Actual shipping paid ($)','0.00','number','0.00','min="0" step="0.01"')}<div class="form-block"><label>Acquisition cost</label><div class="strong" style="padding:11px 0">${money(it.cost_cents)}</div></div></div><div class="alert small">${icon('alert')} You are responsible for removing any other live listing after the sale.</div><div class="row wrap" style="justify-content:flex-end;margin-top:20px"><button type="button" class="btn secondary" data-action="close">Cancel</button><button class="btn">Confirm sale</button></div></form>`);
}
function delistModal(it){
 const pending=Object.entries(it.channels||{}).filter(([,x])=>x.status==='delist_required');
 const live=Object.entries(it.channels||{}).filter(([,x])=>x.status==='manually_published');
 modal('Inventory protection',`<div class="alert small">${icon('alert')} Dope Stuff does not remove external listings. Confirm each removal on the marketplace itself.</div><h3 style="margin:22px 0 10px">${escapeHtml(it.title)}</h3>${pending.length?pending.map(([c,x])=>`<div class="seller-check"><div style="flex:1"><b>${escapeHtml(S.channels[c].name)}</b><div class="tiny muted">Manual removal needed</div>${x.listing_url?`<a class="inline-link" href="${attr(x.listing_url)}" target="_blank" rel="noopener noreferrer">Open your listing ${icon('arrow',12)}</a>`:''}</div><button class="btn small" data-action="mark-removed" data-id="${it.id}" data-channel="${c}">I removed it</button></div>`).join(''):`<p class="small muted">No channels currently flagged for delisting.</p>`}${live.length?`<div class="divider"></div><p class="small muted">Also reported live: ${live.map(([c])=>S.channels[c].name).join(', ')}</p>`:''}`);
}
function importModal(){S.pendingImport=null;modal('Import inventory',`<p class="small">Start with your existing inventory spreadsheet. We will preview your file and check for errors or duplicate SKUs <b>before importing anything</b>.</p><p><a class="inline-link" href="/api/import-template.csv">${icon('download',14)} Download blank inventory template</a></p><div class="notice small">CSV format · Max 200 pieces / 1 MB · Price, cost and shipping in USD. Photos are added separately after import.</div><form id="import-form" style="margin-top:20px"><div class="form-block"><label for="inventory-csv">Your inventory CSV</label><input id="inventory-csv" type="file" name="file" required accept=".csv,text/csv"></div><button class="btn" type="submit">Preview before import ${icon('arrow')}</button></form><div id="import-results" role="status" aria-live="polite"></div><p class="fineprint" style="margin-top:12px">Imported items remain private drafts. No external listings are created.</p>`);}
function pilotModal(){modal('Founding seller pilot',`<p>Join the interest list for future product updates and pricing research. Pilot account registration is currently free.</p><form id="pilot-form"><div class="form-block"><label for="pilot-email">Email address</label><input id="pilot-email" type="email" name="email" autocomplete="email" required placeholder="you@example.com"></div><button class="btn full">Request updates ${icon('arrow')}</button></form><p class="fineprint" style="margin-top:15px">No payment collected. No guaranteed access to future integrations.</p>`);}
function sampleItems(){return [
 {title:'Black leather ankle boots',sku:'SAMPLE-001',brand:'Designer sample',category:'Boots',size:'EU 39',color:'Black',condition:'Like new',description:'SAMPLE DATA. Replace with verified measurements and condition details before publishing.',notes:'Demonstration listing — not real stock.',price_cents:42000,cost_cents:19000,shipping_cents:1500,quantity:1},
 {title:'Vintage washed denim jacket',sku:'SAMPLE-002',brand:'Unbranded',category:'Jackets',size:'M',color:'Washed blue',condition:'Good',description:'SAMPLE DATA. Inspect and disclose any flaws before offering for sale.',notes:'Demonstration listing — not real stock.',price_cents:8900,cost_cents:2500,shipping_cents:1100,quantity:1},
 {title:'Oversized charcoal hoodie',sku:'SAMPLE-003',brand:'Unbranded',category:'Hoodies',size:'L',color:'Charcoal',condition:'New without tags',description:'SAMPLE DATA. Verify fabric, sizing and product details before publishing.',notes:'Demonstration listing — not real stock.',price_cents:12500,cost_cents:4000,shipping_cents:900,quantity:1}
];}
async function handleAction(el,e){
 const action=el.dataset.action;const id=Number(el.dataset.id||0),channel=el.dataset.channel;
 let item=S.items.find(x=>x.id===id)||S.catalog.find(x=>x.id===id)||(S.selectedItem?.id===id?S.selectedItem:null)||S.overview?.latest?.find(x=>x.id===id);
 try{
  if(action==='reload-lists'){await refresh();return;}
  if(action==='page'){
    const section=el.dataset.section,page=Number(el.dataset.page),before=S.pages[section];
    if(before===undefined||!Number.isInteger(page)||page<0||page>=Math.max(1,Math.ceil(S.totals[section]/PAGE_SIZE)))return;
    el.disabled=true;
    try{if(await reloadData({pages:{...S.pages,[section]:page},clearSelection:section==='publish'})){render();document.querySelector(`nav[aria-label="${section} pages"] [role="status"]`)?.focus({preventScroll:true});}}finally{el.disabled=false;}
    return;
  }
  if(id&&!item&&['edit','duplicate','prepare','kit','delist','sold','ready','mark-removed','make-cover'].includes(action))item=await api(`/api/items/${id}`);
  if(action==='close'||(action==='dismiss'&&e.target===el)){S.pendingImport=null;S.pendingRestore=null;closeModal();return;}
  if(action==='register'||action==='login'){authModal(action);return;}
  if(action==='forgot-password'){forgotPasswordModal();return;}
  if(action==='logout'){await api('/api/auth/logout',{method:'POST'});S.session=await api('/api/session');resetLists();authLanding();return;}
  if(action==='new'){itemEditor();return;}
  if(action==='edit'){itemEditor(item);return;}
  if(action==='duplicate'){
    if(!item)throw Error('Item unavailable');
    if(!confirm('Create a fresh draft from this item? Photos, published links and sales will not be copied.'))return;
    const copy=await api(`/api/items/${id}/duplicate`,{method:'POST'});
    S.pages.inventory=0;S.filter='all';S.q='';await reloadData();nav('inventory');toast('Draft copied. Add original photos and verify garment facts before publishing.');
    itemEditor(copy.item);return;
  }
  if(action==='prepare'){S.activeId=id;S.selectedItem=item;nav('publish');return;}
  if(action==='kit'){kitModal(item,channel);return;}
  if(action==='delist'){delistModal(item);return;}
  if(action==='sold'){soldModal(item);return;}
  if(action==='clear-delist'){
    const task=S.actions.find(a=>a.item_id===id&&a.channel===channel);
    if(!task)throw Error('Task is no longer available. Refresh your workspace.');
    if(!confirm('Have you personally removed this exact item from '+task.display_name+'? Dope Stuff cannot verify this.'))return;
    await api(`/api/items/${id}/channels/${channel}`,{method:'PUT',body:{status:'delisted',listing_url:task.listing_url||''}});
    await refresh();toast('Manual removal recorded. Dope Stuff did not access the marketplace.');return;
  }
  if(action==='ready'||action==='mark-removed'){
    const st=action==='ready'?'ready':'delisted';const url=item?.channels?.[channel]?.listing_url||'';
    await api(`/api/items/${id}/channels/${channel}`,{method:'PUT',body:{status:st,listing_url:url}});
    closeModal();await refresh();toast(action==='ready'?'Draft marked ready. Not published externally.':'Removal recorded. No external action was taken by Dope Stuff.');return;
  }
  if(action==='import'){importModal();return;}
  if(action==='delete-account'){deleteAccountModal();return;}
  if(action==='change-password'){passwordModal();return;}
  if(action==='restore-account'){restoreAccountModal();return;}
  if(action==='confirm-restore'){
    if(!S.pendingRestore)throw Error('Please preview the backup first.');
    const form=$('#restore-form');if(!form?.reportValidity())return;
    const fd=new FormData();fd.append('file',S.pendingRestore);fd.append('password',String($('#restore-password')?.value||''));fd.append('confirmation',String($('#restore-confirm')?.value||''));
    el.disabled=true;try{
      const r=await api('/api/account/restore',{method:'POST',body:fd,form:true});
      S.pendingRestore=null;closeModal();await refresh();toast(`${r.restored.items} items and ${r.restored.photos} photos restored. Review external listing statuses before selling.`);
    }finally{el.disabled=false;}return;
  }
  if(action==='make-cover'){
    const current=item;
    if(!current)throw Error('Item not available.');
    const chosen=Number(el.dataset.photo);
    const ordered=[chosen,...current.photos.map(x=>x.id).filter(x=>x!==chosen)];
    const result=await api(`/api/items/${id}/photos/order`,{method:'PUT',body:{photo_ids:ordered}});
    S.catalog=S.catalog.map(x=>x.id===id?result.item:x);
    S.items=S.items.map(x=>x.id===id?result.item:x);
    if(S.selectedItem?.id===id)S.selectedItem=result.item;
    if($('#editor-gallery'))$('#editor-gallery').innerHTML=galleryHtml(result.item);
    toast('Cover photo changed.');return;
  }
  if(action==='delete-photo'){
    if(!confirm('Remove this photo from Dope Stuff? This does not affect external marketplaces.'))return;
    const result=await api(`/api/items/${id}/photos/${Number(el.dataset.photo)}`,{method:'DELETE'});
    await reloadData();
    const updated=result.item;
    if($('#editor-gallery'))$('#editor-gallery').innerHTML=galleryHtml(updated);
    const hint=$('.modal .form-block .hint');if(hint)hint.textContent=`Saved photos: ${updated?.photo_count||0} of 8. You can add more before saving changes.`;
    toast(result.photo_cleanup_pending?'Photo removed from your inventory. Private storage cleanup is queued for retry.':'Photo removed from Dope Stuff.');return;
  }
  if(action==='confirm-import'){
    if(!S.pendingImport){toast('Preview your CSV again first.',true);return;}
    el.disabled=true;
    const fd=new FormData();fd.append('file',S.pendingImport);
    const r=await api('/api/import.csv',{method:'POST',body:fd,form:true});
    S.pendingImport=null;closeModal();await refresh();toast(`${r.imported} drafts imported. Add photos before publishing.`);return;
  }
  if(action==='export'){window.location.href='/api/export.csv';return;}
  if(action==='pilot'){pilotModal();return;}
  if(action==='copy-title'||action==='copy-description'){const text=$('#'+(action==='copy-title'?'kit-title':'kit-description'))?.textContent||'';await navigator.clipboard.writeText(text);toast('Copied');return;}
  if(action==='archive'){
    if(!confirm('Archive item in Dope Stuff? This will not remove external listings.'))return;
    await api(`/api/items/${id}`,{method:'DELETE'});await refresh();toast('Item archived locally.');return;
  }
 }catch(err){toast(err.message,true);}
}
function getFormData(f){return new FormData(f);}
document.addEventListener('click',e=>{
 const el=e.target.closest('[data-action]');if(el && (el.dataset.action!=='dismiss'||e.target===el)){e.preventDefault();handleAction(el,e);return;}
 const navEl=e.target.closest('[data-nav]');if(navEl){e.preventDefault();nav(navEl.dataset.nav);}
});
document.addEventListener('submit',async e=>{
 const form=e.target;if(!['auth-form','item-form','sale-form','channel-form','feedback-form','pilot-form','import-form','delete-account-form','restore-form','password-form','recovery-request-form','recovery-confirm-form'].includes(form.id))return;
 e.preventDefault();const btn=form.querySelector('button[type=submit],button:not([type])');if(btn)btn.disabled=true;
 try{
  const f=getFormData(form);
  if(form.id==='recovery-request-form'){
    const response=await api('/api/auth/recovery/request',{method:'POST',body:{email:String(f.get('email'))}});
    closeModal();toast(response.notice);
  }else if(form.id==='recovery-confirm-form'){
    if(!S.resetToken)throw Error('Your recovery link has expired. Request another one.');
    if(String(f.get('new_password'))!==String(f.get('confirm_password')))throw Error('The passwords do not match.');
    const response=await api('/api/auth/recovery/confirm',{method:'POST',body:{token:S.resetToken,new_password:String(f.get('new_password'))}});
    S.resetToken=null;S.session=await api('/api/session');closeModal();authLanding();toast(response.notice);
  }else if(form.id==='password-form'){
    await api('/api/account/password',{method:'POST',body:{current_password:String(f.get('current_password')),new_password:String(f.get('new_password'))}});
    S.session=await api('/api/session');closeModal();toast('Password updated. All other sessions were revoked.');
  }else if(form.id==='delete-account-form'){
    const response=await api('/api/account/delete',{method:'POST',body:{confirmation:String(f.get('confirmation')),password:String(f.get('password'))}});
    closeModal();S.session=await api('/api/session');resetLists();authLanding();toast(response.notice);location.hash='';
  }else if(form.id==='auth-form'){
    const body={email:String(f.get('email')),password:String(f.get('password'))};if(form.dataset.mode==='register'){body.name=String(f.get('name'));body.invite_code=String(f.get('invite_code')||'');}
    await api(`/api/auth/${form.dataset.mode}`,{method:'POST',body});S.session=await api('/api/session');resetLists();await reloadData();closeModal();nav('overview');toast('Your workspace is ready.');
  } else if(form.id==='item-form') await itemFormSubmit(form);
  else if(form.id==='sale-form'){
    const id=Number(form.dataset.id);const cents=k=>Math.round(Number(f.get(k)||0)*100);
    const result=await api(`/api/items/${id}/sale`,{method:'POST',body:{channel:String(f.get('channel')),sold_cents:cents('sold'),fee_cents:cents('fee'),ship_cents:cents('ship')}});
    closeModal();await refresh();toast('Sale recorded. Profit '+money(result.net_profit_cents));
    if(result.manual_delist_channels.length)toast('ACTION REQUIRED: Remove listings from '+result.manual_delist_channels.join(', '),true);
  }else if(form.id==='channel-form'){
    const id=Number(form.dataset.id),c=form.dataset.channel;
    await api(`/api/items/${id}/channels/${c}`,{method:'PUT',body:{status:'manually_published',listing_url:String(f.get('listing_url')||'')}});
    closeModal();await refresh();toast('Your publication confirmation was recorded.');
  }else if(form.id==='feedback-form'){
    await api('/api/feedback',{method:'POST',body:{rating:Number(f.get('rating')),message:String(f.get('message'))}});
    form.reset();toast('Feedback saved. Thank you.');
  }else if(form.id==='pilot-form'){
    await api('/api/pilot-request',{method:'POST',body:{email:String(f.get('email'))}});
    form.reset();closeModal();toast('Interest recorded. No payment taken.');
  }else if(form.id==='restore-form'){
    const file=f.get('file');if(!(file instanceof File)||!file.size)throw Error('Select a Dope Stuff backup ZIP.');
    if(file.size>128*1024*1024)throw Error('The backup exceeds the 128 MB pilot limit.');
    const fd=new FormData();fd.append('file',file);
    const preview=await api('/api/account/restore-preview',{method:'POST',body:fd,form:true});
    S.pendingRestore=file;
    const d=preview.summary;
    $('#restore-results').innerHTML=`<div class="notice restore-review"><h3>Archive verified</h3><p class="small">${d.items} items · ${d.photos} photos · ${d.sales} sales · ${d.manual_delists} manual removal reminders</p><p class="small"><strong>Before you continue:</strong> this restores your local history only. It does not confirm if marketplace listings are currently live.</p><div class="form-block"><label for="restore-confirm">Type RESTORE MY DATA</label><input id="restore-confirm" name="confirmation" required pattern="RESTORE MY DATA" placeholder="RESTORE MY DATA" autocomplete="off"></div><div class="form-block"><label for="restore-password">Your current account password</label><input id="restore-password" type="password" name="password" required minlength="10" autocomplete="current-password"></div><button class="btn full" type="button" data-action="confirm-restore">Restore verified backup ${icon('shield',14)}</button></div>`;
    toast('Backup checked. No records have been imported yet.');
  }else if(form.id==='import-form'){
    const file=f.get('file');const fd=new FormData();fd.append('file',file);
    const preview=await api('/api/import-preview.csv',{method:'POST',body:fd,form:true});
    S.pendingImport=preview.ok?file:null;
    const summary=$('#import-results');
    summary.innerHTML=`<div class="import-review ${preview.ok?'notice':'alert'}"><h3>${preview.ok?`${preview.ready} drafts ready to import`:'Review these issues first'}</h3><p class="small">${preview.total} rows checked. No data has been saved.</p>${preview.issues.length?`<ul>${preview.issues.map(x=>`<li>Row ${x.row}: ${escapeHtml(x.message)}</li>`).join('')}</ul>`:''}${preview.ok?`<div class="tiny muted" style="margin:10px 0">${preview.sample.map(x=>`${escapeHtml(x.title)} · ${money(x.price_cents)}`).join('<br>')}</div><button class="btn" type="button" data-action="confirm-import">Import ${preview.ready} drafts ${icon('checkcircle')}</button>`:''}</div>`;
    if(!preview.ok)toast('Nothing imported. Correct the CSV and preview again.',true);
  }
 }catch(err){toast(err.message,true);}finally{if(btn)btn.disabled=false;}
});
document.addEventListener('change',e=>{
 if(e.target.id==='publish-item'){S.activeId=Number(e.target.value||0);S.selectedItem=S.catalog.find(item=>item.id===S.activeId)||null;render();}
 if(e.target.id==='restore-file'){S.pendingRestore=null;const result=$('#restore-results');if(result)result.innerHTML='';}
 if(e.target.id==='inventory-csv'){S.pendingImport=null;const result=$('#import-results');if(result)result.innerHTML='';}
});
let searchTimeout;
document.addEventListener('input',e=>{
 if(['inventory-search','publish-search'].includes(e.target.id)){
  const field=e.target.id,q=e.target.value,section=field==='inventory-search'?'inventory':'publish';
  clearTimeout(searchTimeout);reloadGeneration++;S.pages[section]=0;
  if(section==='inventory')S.q=q;else{S.publishQ=q;S.activeId=null;S.selectedItem=null;}
  searchTimeout=setTimeout(async()=>{try{if(await reloadData()&&S.nav===section){$('#screen').innerHTML=section==='inventory'?inventoryView():publishView();$('#'+field)?.focus();$('#'+field)?.setSelectionRange(q.length,q.length);}}catch(err){toast(err.message,true);}},280);
 }
});
document.addEventListener('click',async e=>{
 const filter=e.target.closest('[data-filter]');if(filter){S.filter=filter.dataset.filter;S.pages.inventory=0;try{await refresh();}catch(err){toast(err.message,true);}}
});
document.addEventListener('keydown',e=>{
 if(e.key==='Escape'){closeModal();return;}
 if(e.key==='Tab'&&$('.modal')){
   const available=[...$('.modal').querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled])')].filter(el=>el.offsetParent!==null);
   if(!available.length)return;
   if(e.shiftKey&&document.activeElement===available[0]){e.preventDefault();available[available.length-1].focus();}
   else if(!e.shiftKey&&document.activeElement===available[available.length-1]){e.preventDefault();available[0].focus();}
 }
});
window.addEventListener('hashchange',()=>{const n=location.hash.slice(1);if(['overview','inventory','publish','sales','plans','feedback','account','actions'].includes(n)&&S.nav!==n){S.nav=n;render();}});
init();
