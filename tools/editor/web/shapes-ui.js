'use strict';
// A form owns only black pixels at fixed ink-grid coordinates; white is transparent.
// Reference extractions never become live links without a user's action.
window.ShapeUI = (() => {
  let catalog = {forms: [], parts: [], links: []}, catalogRequest = 0;
  let family = '', formEditor = null, shapeDrag = null, previewTimer, previewRequest = 0;
  let actionBusy = false, searchTimer, pendingPreview = null, libraryData = null, libraryRequest = 0;
  const expanded = new Set(), selectedSlots = new Map();
  const blank = () => Array(H).fill('.'.repeat(W));
  const el = (tag, cls, text) => {const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  const button = (text, fn, cls='') => {const b=el('button',cls,text);b.onclick=guard(fn);return b;};
  const formName = f => f.name || f.symbol;
  const matches = (f,q) => !q || [f.symbol,f.name,f.id,f.locale,...(f.sources||[]).map(s=>s.char+' '+s.id),...(f.users||[]).map(s=>s.char+' '+s.id)].join(' ').toLowerCase().includes(q.toLowerCase());
  const linked = (slot) => catalog.links.find(l=>l.slot===slot);
  const formsFor = symbol => catalog.forms.filter(f=>f.symbol===symbol).sort((a,b)=>(a.kind==='reference')-(b.kind==='reference')||a.locale.localeCompare(b.locale)||formName(a).localeCompare(formName(b)));
  function thumbnail(f, zoom=4){const c=el('canvas','form-bitmap');paintCanvas(c,f.rows);c.style.width=CW*zoom+'px';c.style.height=CH*zoom+'px';c.setAttribute('aria-label',f.symbol+'形态，固定字格位置');return c;}
  async function load(){
    if(!current)return;
    const id=current.original.id,n=++catalogRequest;
    $('structure-summary').textContent='正在读取部件与全部形态…';
    const data=await api('/api/shapes?glyph='+encodeURIComponent(id));
    if(n!==catalogRequest||current?.original.id!==id)return;
    catalog={...data,glyph:id};renderSidebar();
    if($('library-dialog').open)await fetchLibrary(false);
  }
  function groupParts(){
    const groups=new Map();
    for(const p of catalog.parts||[]){if(!groups.has(p.symbol))groups.set(p.symbol,[]);groups.get(p.symbol).push(p);}
    return groups;
  }
  function currentTarget(symbol){
    const parts=groupParts().get(symbol)||[];
    return parts.find(p=>p.key===selectedSlots.get(symbol))||parts[0];
  }
  function renderSidebar(){
    const box=$('components');box.replaceChildren();
    const q=$('component-search').value.trim(),groups=groupParts();
    const count=catalog.links.length;
    $('structure-summary').textContent=`${groups.size} 个数据库部件 · ${count} 处已关联${catalog.structure?.available?'':' · 结构资料不足'}`;
    $('unlink-all').hidden=!count;
    let visible=0;
    for(const [symbol,parts] of groups){
      const all=formsFor(symbol),forms=all.filter(f=>matches(f,q));
      if(q&&!symbol.includes(q)&&!forms.length)continue;
      visible++;
      const section=el('details','component-family');section.dataset.symbol=symbol;section.open=expanded.has(symbol)||!!q||visible===1;
      section.ontoggle=()=>{if(section.open)expanded.add(symbol);else expanded.delete(symbol);};
      const total=catalog.totals?.[symbol]??all.length;
      const summary=el('summary');summary.append(setLang(el('span','family-symbol',symbol),current?.original.locale),el('span','family-count',total+' 种形态'));
      if(parts.some(p=>linked(p.key)))summary.append(el('span','linked-badge','已关联'));
      section.append(summary);
      const head=el('div','family-actions');
      head.append(button('全部形态',()=>openLibrary(symbol),'text-button'),button('新增形态',()=>openNew(currentTarget(symbol)),'text-button'));
      section.append(head);
      if(parts.length>1){const tabs=el('div','occurrence-tabs');
        for(const p of parts){const b=button(p.label,()=>{selectedSlots.set(symbol,p.key);renderSidebar();});b.setAttribute('aria-pressed',currentTarget(symbol)?.key===p.key);tabs.append(b);}section.append(tabs);}
      const target=currentTarget(symbol),association=linked(target.key);
      const status=el('div','association-status');
      if(association){const f=catalog.forms.find(f=>f.id===association.shape_id);status.append(el('span','',`已关联：${f?formName(f):symbol}`),button('解除关联',()=>unlink(target),'text-button'));}
      else status.append(el('span','hint','未关联 · 可以自由编辑'));
      section.append(status);
      if(!forms.length)section.append(el('p','hint empty-form',q?'没有匹配的形态。':'还没有形态。可在独立编辑器中新增。'));
      for(const f of forms)section.append(formCard(f,target,'sidebar'));
      // The sidebar lists the forms closest to this glyph's ink; the library pages through the rest.
      if(total>all.length)section.append(button(`查看全部 ${total} 种形态（此处列出与本字最接近的 ${all.length} 种）`,()=>openLibrary(symbol),'text-button more-forms'));
      box.append(section);
    }
    if(!visible)box.append(el('p','empty','没有匹配的部件或形态。'));
    draw();
  }
  function formCard(f,target,mode){
    const card=el('article','form-card');card.dataset.formId=f.id;
    const isLinked=target&&linked(target.key)?.shape_id===f.id;
    card.classList.toggle('is-linked',!!isLinked);
    const top=el('div','form-top'),name=el('div','form-description');
    name.append(setLang(el('h3','form-name',formName(f)),f.locale));
    const b=f.bounds, dims=b?`${b[2]}×${b[3]} · ${f.pixel_count} 点`:'';
    const other=f.locale!==current?.original.locale;
    name.append(el('p','form-meta',`${f.locale}${other?'（其他地区）':''} · ${dims}`),el('p','form-meta',b?`字格坐标 (${b[0]}, ${b[1]})`:''));
    if(other&&f.region_note){const n=el('p','form-meta',(f.region_caution?'⚠ ':'')+f.region_note);if(f.region_caution)n.style.color='#b35c00';name.append(n);}
    top.append(thumbnail(f),name);card.append(top);
    const state=el('div','form-state');state.append(el('span',f.kind==='shared'?'shared-badge':'reference-badge',f.kind==='shared'?`${f.usage_count} 字关联`:'参考形态'));
    if(f.sibling_locale)state.append(el('span','sibling-badge',`同码位 ${f.sibling_locale} 在用`));
    if(f.movable)state.append(el('span','sibling-badge','可移动'));
    if(isLinked)state.append(el('span','using-badge','本字正在使用'));
    card.append(state);
    const actions=el('div','form-actions');
    if(target){
      const same=true;  // any region's form may be used; cross-region cautions are shown on the card
      if(isLinked)actions.append(button('解除关联',()=>unlink(target)));
      if(isLinked&&f.movable){const mv=el('span','move-buttons');mv.append(el('span','form-meta','本字中移动：'));
        for(const [lab,dx,dy] of [['←',-1,0],['→',1,0],['↑',0,-1],['↓',0,1]]){const b=button(lab,()=>moveForm(target,dx,dy),'text-button');b.title='只在本字里移动这一处，其他字不变';mv.append(b);}
        actions.append(mv);}
      else {const apply=button('关联并应用',()=>link(f,target),'apply-form');apply.disabled=!same||actionBusy||busy;apply.title='保存当前修改，并按固定坐标关联此形态'+(f.locale!==current?.original.locale?`（跨地区共用：${f.region_note||''}）`:'');actions.append(apply);}
      const preview=button('预览',()=>previewForm(f,target),'text-button');preview.disabled=!same;actions.append(preview);
    }
    if(f.kind==='shared'){
      actions.append(button('编辑 / 重命名',()=>openEditor(f),'text-button'),button(`关联字 ${f.usage_count}`,()=>showUsers(f),'text-button'));
    }else{
      actions.append(button('查看来源',()=>showSources(f),'text-button'));
      if(target)actions.append(button('以此新增',()=>openNew(target,f),'text-button'));
    }
    card.append(actions);
    return card;
  }
  function scrollWithin(target){
    // Scroll only the sidebar's own scroll area so the editing grid stays put.
    let box=target.parentElement;
    while(box&&box!==document.body){const o=getComputedStyle(box).overflowY;if((o==='auto'||o==='scroll')&&box.scrollHeight>box.clientHeight)break;box=box.parentElement;}
    if(!box||box===document.body){target.scrollIntoView({block:'center',behavior:'smooth'});return;}
    const b=box.getBoundingClientRect(),t=target.getBoundingClientRect();
    box.scrollTo({top:box.scrollTop+t.top-b.top-Math.max(0,(b.height-t.height)/2),behavior:'smooth'});
  }
  async function reveal(slot,edit){
    // A protected pixel on the grid leads to the form that owns it: expand its
    // component, pick the occurrence, scroll to the card; right click also edits it.
    if(!current)return;
    if(catalog.glyph!==current.original.id)await load();
    const part=(catalog.parts||[]).find(p=>p.key===slot);if(!part)return;
    const link=linked(slot),f=link&&catalog.forms.find(f=>f.id===link.shape_id);
    selectedSlots.set(part.symbol,slot);expanded.add(part.symbol);
    const q=$('component-search').value.trim();
    if(q&&!part.symbol.includes(q)&&!(f&&matches(f,q)))$('component-search').value='';
    renderSidebar();
    const section=[...$('components').querySelectorAll('.component-family')].find(s=>s.dataset.symbol===part.symbol);
    if(section){
      section.open=true;
      const target=(f&&section.querySelector(`[data-form-id="${f.id}"]`))||section;
      scrollWithin(target);
      target.classList.remove('flash');void target.offsetWidth;target.classList.add('flash');
    }
    if(edit&&f)await openEditor(f);
  }
  async function ensureSaved(){if(dirty)await save(false);}
  async function reloadGlyph(){
    const id=current?.original.id;if(!id)return;
    const before=snapshot(),history={undo,redo};
    current=null;drafts.delete(id);await refreshQueue();await show(id,'none');
    if(current?.original.id!==id)return;
    // Refresh saved revisions and links without discarding local pixel history.
    // Unlinking keeps the pixels, so it must not add an empty undo step.
    undo=history.undo;redo=history.redo;
    if(!equal(before,snapshot()))pushUndo(before);
    updateDirty();
  }
  // A movable form goes into the box you selected on the grid (if any).
  function linkPayload(f,target){return {id:current.original.id,expected_revision:current.current.revision,slot:target.key,shape_id:f.id,expected_shape_revision:f.revision,
    ...(f.movable&&selection?{selection:{x:selection.x,y:selection.y,w:selection.w,h:selection.h}}:{})};}
  async function runAction(fn){
    if(actionBusy||busy)return;actionBusy=true;updateButtons();
    try{await ensureSaved();await fn();await reloadGlyph();return true;}
    finally{actionBusy=false;updateButtons();}
  }
  async function link(f,target){
    if(await runAction(async()=>{await api('/api/shape-link',linkPayload(f,target));}))say(`已关联“${formName(f)}”并保存。共享区域请在独立形态编辑器中修改。`);
  }
  async function unlinkAll(){
    const n=catalog.links.length;if(!current||!n)return;
    if(!confirm(`解除“${current.original.char}”的全部 ${n} 处部件关联？\n当前像素和审核状态不变；没有其他字使用的形态会移出形态库。`))return;
    if(await runAction(async()=>{await api('/api/shape-unlink-all',{id:current.original.id,expected_revision:current.current.revision});}))say(`已解除全部 ${n} 处关联，当前像素保持不变。无关联字的形态已自动移出形态库。`);
  }
  $('unlink-all').onclick=guard(unlinkAll);
  async function clearAll(){
    // “全部清空”: unlink every form (saved at once, like 解除所有关联) and clear every pixel (a draft, undoable).
    if(!current||busy||actionBusy)return;
    const n=(current.current.links||[]).length,ch=current.original.char;
    if(!confirm(`全部清空“${ch}”？\n${n?`将解除全部 ${n} 处部件关联（立即保存；未保存的修改会先保存），并`:'将'}清除全部像素。\n清空后的像素尚未保存，可撤销；${n?'关联不会随撤销恢复，可在历史版本中找回。':''}`))return;
    if(n&&!await runAction(async()=>{await api('/api/shape-unlink-all',{id:current.original.id,expected_revision:current.current.revision});}))return;
    pushUndo();rows=rows.map(r=>'.'.repeat(r.length));reused=[];selection=null;draw();
    say(n?`已解除全部 ${n} 处关联并清空全部像素；像素尚未保存，可撤销。`:'已清空全部像素，尚未保存；可撤销。');
  }
  async function moveForm(target,dx,dy){
    if(await runAction(async()=>{await api('/api/shape-move',{id:current.original.id,expected_revision:current.current.revision,slot:target.key,dx,dy});}))say('已在本字中移动该形态并保存；其他关联字不变。');
  }
  async function unlink(target){
    if(await runAction(async()=>{await api('/api/shape-unlink',{id:current.original.id,expected_revision:current.current.revision,slot:target.key});}))say('已解除关联，当前像素保持不变。无关联字的形态已自动移出形态库。');
  }
  async function previewForm(f,target){
    await ensureSaved();const p=await api('/api/shape-preview',linkPayload(f,target));pendingPreview={f,target};
    $('form-preview-title').textContent=`${current.original.char} · ${formName(f)}`;
    $('form-preview-note').textContent='按固定坐标叠加形态黑点，空白位置全部透明。替换已有关联时，只移除原形态黑点；请比较应用前后。';
    const box=$('form-preview-images');box.replaceChildren();
    for(const [title,data] of [['当前',p.before],['应用后',p.after]]){const fig=el('figure');fig.append(el('figcaption','',title),thumbnail({rows:data,symbol:current.original.char},10),thumbnail({rows:data,symbol:current.original.char},1));box.append(fig);}
    $('shape-preview-dialog').showModal();
  }
  async function openLibrary(symbol=''){
    if(current&&!catalog.parts?.length)await load();family=symbol;$('library-search').value='';$('library-kind').value='all';
    if(!$('library-dialog').open)$('library-dialog').showModal();await fetchLibrary(false);
  }
  async function fetchLibrary(more){
    // The server filters and pages: the library can hold tens of thousands of forms.
    const n=++libraryRequest,offset=more&&libraryData?libraryData.forms.length:0;
    const params=new URLSearchParams({symbol:family,q:$('library-search').value.trim(),kind:$('library-kind').value,offset,limit:120});
    const data=await api('/api/shape-library?'+params);
    if(n!==libraryRequest)return;
    if(more&&libraryData)data.forms=libraryData.forms.concat(data.forms);
    libraryData=data;renderLibrary();
  }
  function renderLibrary(){
    if(!libraryData)return;
    const {symbols,forms,total}=libraryData,counts=new Map(symbols);
    $('library-count').textContent=`${symbols.length} 个部件 · ${symbols.reduce((a,[,n])=>a+n,0)} 种形态`;
    const nav=$('library-groups');nav.replaceChildren();
    const all=button('全部部件',()=>{family='';return fetchLibrary(false);});all.setAttribute('aria-current',!family);nav.append(all);
    for(const [symbol,n] of symbols){const b=button(symbol+'  '+n,()=>{family=symbol;return fetchLibrary(false);});b.setAttribute('aria-current',symbol===family);nav.append(b);}
    const content=$('library-content');content.replaceChildren();
    if(!forms.length){content.append(el('p','empty',family&&!counts.has(family)?'此部件没有符合筛选条件的形态。':'没有找到形态。换个关键词试试，或从修字页的数据库部件中新增。'));return;}
    for(const symbol of [...new Set(forms.map(f=>f.symbol))]){
      const list=forms.filter(f=>f.symbol===symbol),section=el('section','library-family'),head=el('div','section-title');
      head.append(el('h3','',symbol),el('span','hint',(counts.get(symbol)||list.length)+' 种形态'));
      const target=currentTarget(symbol);
      if(target)head.append(button(`为“${current.original.char}”新增形态`,()=>openNew(target),'text-button'));
      section.append(head);const occurrences=groupParts().get(symbol)||[];if(occurrences.length>1){const tabs=el('div','occurrence-tabs');for(const p of occurrences){const b=button(p.label,()=>{selectedSlots.set(symbol,p.key);renderSidebar();renderLibrary();});b.setAttribute('aria-pressed',target?.key===p.key);tabs.append(b);}section.append(tabs);}
      const grid=el('div','form-gallery');for(const f of list)grid.append(formCard(f,target,'library'));section.append(grid);content.append(section);
    }
    if(forms.length<total)content.append(button(`显示更多（已显示 ${forms.length} / ${total}）`,()=>fetchLibrary(true),'text-button more-forms'));
  }
  async function showUsers(f){
    const data=await api('/api/shape/'+f.id);$('users-title').textContent=formName(f)+' · 关联字';
    $('users-hint').textContent=`${data.users.length} 个字严格共用此形态的像素和坐标。点击字形返回修字。`;
    renderUserLinks(data.users);$('shape-users-dialog').showModal();
  }
  function showSources(f){
    $('users-title').textContent=formName(f)+' · 参考来源';
    $('users-hint').textContent='这些是参考像素的来源，尚未因此建立共享关联。分割可能由工具推测，应用前请检查。';
    renderUserLinks(f.sources||[]);$('shape-users-dialog').showModal();
  }
  function renderUserLinks(users){
    const box=$('users-list');box.replaceChildren();
    for(const u of users){const b=button('',async()=>{closeBrowseDialogs();await show(u.id);},'user-link');
      if(u.rows)b.append(thumbnail({rows:u.rows,symbol:u.char}));else b.append(el('strong','',u.char));
      b.append(el('span','',u.char+' · '+u.id));box.append(b);}
    if(!users.length)box.append(el('p','empty','暂无关联字。'));
  }
  function closeBrowseDialogs(){for(const id of ['shape-users-dialog','library-dialog','shape-preview-dialog'])if($(id).open)$(id).close();}
  function seedFromTarget(target){
    const prior=catalog.forms.find(f=>f.id===linked(target.key)?.shape_id);
    if(prior&&!selection)return {rows:prior.rows.slice(),care:prior.rows.slice()};
    const data=blank().map(r=>r.split('')),care=blank().map(r=>r.split(''));
    const rect=selection?[selection.x,selection.y,selection.w,selection.h]:target.rect;
    if(rect){const [x,y,w,h]=rect;for(let yy=y;yy<y+h;yy++)for(let xx=x;xx<x+w;xx++){data[yy][xx]=rows[yy][xx];care[yy][xx]=data[yy][xx];}}
    return {rows:data.map(r=>r.join('')),care:care.map(r=>r.join(''))};
  }
  async function openNew(target,reference=null){
    if(!target||busy||actionBusy)return;await ensureSaved();
    const data=reference?{rows:reference.rows.slice(),care:reference.rows.slice()}:seedFromTarget(target);
    formEditor={mode:'create',target,id:current.original.id,expectedRevision:current.current.revision,movable:!!target.movable,
      symbol:target.symbol,locale:current.original.locale,name:target.symbol+' · 新形态',...data,users:[],undo:[],redo:[],tool:'ink'};
    if(reference)formEditor.name=formName(reference)+' · 新形态';
    initializeEditor();
  }
  async function openEditor(f){
    if(busy||actionBusy)return;await ensureSaved();const d=await api('/api/shape/'+f.id);
    let formRows=d.shape.rows.slice();
    if(d.shape.movable){
      // A movable form is edited where this glyph uses it; all users follow the same change.
      const l=(current?.current.links||[]).find(l=>l.shape_id===d.shape.id);
      if(!l){say('可移动形态请在使用它的字里编辑：先打开任一关联字，再点“编辑”。',true);return;}
      const grid=blank().map(r=>r.split(''));
      d.shape.rows.forEach((r,y)=>[...r].forEach((v,x)=>{if(v==='#')grid[y+(l.y||0)][x+(l.x||0)]='#';}));
      formRows=grid.map(r=>r.join(''));
    }
    formEditor={mode:'edit',shape:d.shape,symbol:d.shape.symbol,locale:d.shape.locale,movable:!!d.shape.movable,
      contextId:current?.original.id,rows:formRows,care:formRows.slice(),name:d.shape.name,users:d.users,undo:[],redo:[],tool:'ink'};
    initializeEditor();
  }
  function initializeEditor(){
    const e=formEditor;e.initial=JSON.stringify([e.rows,e.care,e.name]);
    $('shape-name').value=e.name;$('shape-error').hidden=true;
    $('shape-title').textContent=(e.mode==='create'?'新增':'编辑')+'部件形态 · '+e.symbol;
    $('shape-eyebrow').textContent=`独立形态编辑 · ${e.locale}`;
    $('shape-save').textContent=e.mode==='create'?'创建并关联当前字':`保存并同步 ${e.users.length} 字`;
    $('shape-save-note').textContent=e.mode==='create'?'创建后关联当前字；解除最后一个关联时自动移出形态库。':'黑点变化后同步所有关联字，并设为待审核；各字在空隙中添加的像素会保留。';
    $('shape-users-title').textContent=e.mode==='create'?'应用到当前字':'关联字 · 修改前 / 修改后';
    $('shape-impact').textContent=e.mode==='create'?`将关联“${current.original.char}”，保留其他部件。新形态按当前坐标应用。`:`共 ${e.users.length} 字。保存一次，同步全部关联字；重命名不改变字形。`;
    if(!$('shape-dialog').open)$('shape-dialog').showModal();drawShape();scheduleImpact();
    $('shape-name').focus();
  }
  const editorSnapshot = () => ({rows:formEditor.rows.slice(),care:formEditor.care.slice()});
  function rememberShape(){formEditor.undo.push(editorSnapshot());if(formEditor.undo.length>150)formEditor.undo.shift();formEditor.redo=[];}
  function shapePoint(event){const b=$('shape-grid').getBoundingClientRect();const x=Math.floor((event.clientX-b.left)*CW/b.width)-X,y=Math.floor((event.clientY-b.top)*CH/b.height);return x>=0&&x<W&&y>=0&&y<H?{x,y}:null;}
  function setShapePixel(x,y,tool){const e=formEditor,v=tool==='ink'?'#':'.',c=v;e.rows[y]=e.rows[y].slice(0,x)+v+e.rows[y].slice(x+1);e.care[y]=e.care[y].slice(0,x)+c+e.care[y].slice(x+1);}
  function shapeLine(a,b,tool){let dx=Math.abs(b.x-a.x),dy=-Math.abs(b.y-a.y),sx=a.x<b.x?1:-1,sy=a.y<b.y?1:-1,err=dx+dy,x=a.x,y=a.y;for(;;){setShapePixel(x,y,tool);if(x===b.x&&y===b.y)break;const e=2*err;if(e>=dy){err+=dy;x+=sx;}if(e<=dx){err+=dx;y+=sy;}}}
  function drawShape(){
    if(!formEditor)return;const e=formEditor,sg=$('shape-grid');
    // The canvas follows this glyph's cell (7×14, proportional widths, 14×14), so clicks map 1:1.
    if(sg.width!==CW*cell||sg.height!==CH*cell){sg.width=CW*cell;sg.height=CH*cell;}
    sg.style.aspectRatio=`${CW} / ${CH}`;sg.style.width=`min(100%, ${CW*32}px)`;
    const c=sg.getContext('2d');c.fillStyle='#e5ece8';c.fillRect(0,0,CW*cell,CH*cell);
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      const xx=(x+X)*cell,yy=y*cell;c.fillStyle=e.rows[y][x]==='#'?'#18241e':'#e9ede9';c.fillRect(xx,yy,cell,cell);
      if(e.rows[y][x]!== '#'){c.save();c.beginPath();c.rect(xx,yy,cell,cell);c.clip();c.strokeStyle='#cbd4cd';c.lineWidth=1;for(let k=-cell;k<cell*2;k+=8){c.beginPath();c.moveTo(xx+k,yy);c.lineTo(xx+k+cell,yy+cell);c.stroke();}c.restore();}
    }
    c.strokeStyle='#bfcfc4';c.lineWidth=1;for(let x=0;x<=CW;x++){c.beginPath();c.moveTo(x*cell+.5,0);c.lineTo(x*cell+.5,CH*cell);c.stroke();}for(let y=0;y<=CH;y++){c.beginPath();c.moveTo(0,y*cell+.5);c.lineTo(CW*cell,y*cell+.5);c.stroke();}
    paintCanvas($('shape-large'),e.rows);paintCanvas($('shape-native'),e.rows);
    const n=e.rows.reduce((n,r)=>n+[...r].filter(v=>v==='#').length,0);
    $('shape-meta').textContent=e.movable?`${e.symbol} · 可移动形态 · ${n} 个黑点 · 在“${current?.original.char||''}”中的位置编辑；各关联字保持各自位置，整体移动会带动所有关联字`:`${e.symbol} · ${e.locale} · ${n} 个黑点 · 固定13×13墨迹坐标`;
    for(const t of ['ink','transparent'])$('shape-'+t).setAttribute('aria-pressed',e.tool===t);
    $('shape-undo').disabled=!e.undo.length;$('shape-redo').disabled=!e.redo.length;
  }
  function shapeUndo(back){if(!formEditor||actionBusy)return;const e=formEditor,from=back?e.undo:e.redo,to=back?e.redo:e.undo;if(!from.length)return;to.push(editorSnapshot());Object.assign(e,from.pop());drawShape();scheduleImpact();}
  function shiftShape(dx,dy){
    if(!formEditor||actionBusy)return;const e=formEditor,points=[];
    for(let y=0;y<H;y++)for(let x=0;x<W;x++)if(e.rows[y][x]==='#')points.push([x,y]);
    if(points.some(([x,y])=>x+dx<0||x+dx>=W||y+dy<0||y+dy>=H)){shapeError('移动会超出墨迹范围，未执行。');return;}
    rememberShape();const r=blank().map(r=>r.split('')),c=blank().map(r=>r.split(''));
    points.forEach(([x,y])=>{r[y+dy][x+dx]=e.rows[y][x];c[y+dy][x+dx]='#';});e.rows=r.map(r=>r.join(''));e.care=c.map(r=>r.join(''));drawShape();scheduleImpact();
  }
  function editPayload(){const e=formEditor;return {shape_id:e.shape.id,expected_shape_revision:e.shape.revision,
    expected_users:Object.fromEntries(e.users.map(u=>[u.id,u.revision])),name:$('shape-name').value,rows:e.rows.slice(),care:e.care.slice(),
    ...(e.movable?{context_id:e.contextId}:{})};}
  function shapeError(text){$('shape-error').textContent=text;$('shape-error').hidden=!text;}
  function scheduleImpact(){clearTimeout(previewTimer);const seq=++previewRequest;previewTimer=setTimeout(()=>renderImpact(seq),220);}
  async function renderImpact(seq){
    if(!formEditor||seq!==previewRequest)return;const e=formEditor;
    const box=$('shape-users');box.replaceChildren();
    let comparisons=[];
    if(e.mode==='edit'){
      const unsaved=e.users.filter(u=>drafts.has(u.id));
      if(unsaved.length){shapeError('以下关联字有未保存草稿，请先处理后再编辑形态：'+unsaved.map(u=>u.char).join('、'));$('shape-save').disabled=true;return;}
      try{const p=await api('/api/shape-edit',{...editPayload(),preview:true});if(seq!==previewRequest||formEditor!==e)return;comparisons=p.affected;shapeError('');$('shape-save').disabled=false;}
      catch(err){if(seq!==previewRequest||formEditor!==e)return;shapeError(err.message);$('shape-save').disabled=true;return;}
    }else {
      shapeError('');
      const after=rows.slice().map(r=>r.split(''));
      const target=e.target,prev=linked(target.key),prior=catalog.forms.find(f=>f.id===prev?.shape_id);
      if(prior){prior.rows.forEach((r,y)=>[...r].forEach((v,x)=>{if(v==='#')after[y][x]='.';}));}
      e.rows.forEach((r,y)=>[...r].forEach((v,x)=>{if(v==='#')after[y][x]=e.rows[y][x];}));
      for(const f of current.linked_forms||[])if(f.slot!==target.key)f.rows.forEach((r,y)=>[...r].forEach((v,x)=>{if(v==='#')after[y][x]=f.rows[y][x];}));
      comparisons=[{id:current.original.id,char:current.original.char,before:rows,after:after.map(r=>r.join(''))}];
      $('shape-save').disabled=false;
    }
    for(const u of comparisons){const row=el('div','impact-row');row.append(el('span','impact-char',u.char),thumbnail({rows:u.before,symbol:u.char},3),el('span','hint','→'),thumbnail({rows:u.after,symbol:u.char},3),el('span','impact-id',u.id));box.append(row);}
  }
  async function saveShape(){
    if(!formEditor||actionBusy)return;const e=formEditor;actionBusy=true;$('shape-save').disabled=true;clearTimeout(previewTimer);++previewRequest;
    try{
      let response;
      if(e.mode==='create')response=await api('/api/shape-create',{id:e.id,expected_revision:e.expectedRevision,slot:e.target.key,name:$('shape-name').value,rows:e.rows,care:e.care});
      else response=await api('/api/shape-edit',editPayload());
      formEditor=null;$('shape-dialog').close();await reloadGlyph();
      say(e.mode==='create'?(response.reused_existing?'已关联库中像素和坐标完全相同的已有形态。':'新形态已建立，并关联到当前字。'):`形态已保存，${response.updated_ids.length} 个关联字已同步。`);
    }catch(err){shapeError(err.message);}
    finally{actionBusy=false;$('shape-save').disabled=false;}
  }
  function hasUnsavedShape(){return !!formEditor&&formEditor.initial!==JSON.stringify([formEditor.rows,formEditor.care,$('shape-name').value]);}
  function closeEditor(){if(actionBusy)return;if(hasUnsavedShape()&&!confirm('形态修改尚未保存，放弃这些修改？'))return;formEditor=null;clearTimeout(previewTimer);++previewRequest;$('shape-dialog').close();}
  function updateButtons(){document.querySelectorAll('.apply-form').forEach(b=>{if(!b.title.includes('另一地区'))b.disabled=busy||actionBusy;});}
  function drawLocks(ctx){
    const forms=current?.linked_forms||[];$('linked-hint').hidden=!forms.length;
    $('linked-hint').textContent=`${forms.length} 处已关联共享形态。绿色角标是受保护的形态黑点：左键点它定位到所属形态，右键点它直接编辑该形态；其余位置均可自由加点、擦除。`;
    ctx.fillStyle='#4d9585';for(let y=0;y<H;y++)for(let x=0;x<W;x++)if(forms.some(f=>f.rows[y][x]==='#')){ctx.fillRect((x+X)*cell+2,y*cell+2,4,4);}
  }
  $('library-open').onclick=$('component-library').onclick=guard(()=>openLibrary());
  $('library-close').onclick=()=>$('library-dialog').close();
  $('library-search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(guard(()=>fetchLibrary(false)),250);};$('library-kind').onchange=guard(()=>fetchLibrary(false));
  $('users-close').onclick=()=>$('shape-users-dialog').close();
  $('form-preview-close').onclick=()=>$('shape-preview-dialog').close();
  $('form-preview-apply').onclick=guard(async()=>{if(pendingPreview){await link(pendingPreview.f,pendingPreview.target);$('shape-preview-dialog').close();}});
  $('shape-close').onclick=closeEditor;$('shape-dialog').addEventListener('cancel',e=>{e.preventDefault();closeEditor();});
  $('shape-name').oninput=scheduleImpact;
  $('shape-save').onclick=saveShape;
  $('shape-family').onclick=guard(()=>{const symbol=formEditor.symbol;if(hasUnsavedShape())throw Error('请先保存形态修改，再查看同部件的所有形态。');closeEditor();return openLibrary(symbol);});
  for(const tool of ['ink','transparent'])$('shape-'+tool).onclick=()=>{if(formEditor){formEditor.tool=tool;drawShape();}};
  $('shape-undo').onclick=()=>shapeUndo(true);$('shape-redo').onclick=()=>shapeUndo(false);
  document.querySelectorAll('[data-shift]').forEach(b=>b.onclick=()=>shiftShape(...b.dataset.shift.split(',').map(Number)));
  const sg=$('shape-grid');sg.oncontextmenu=e=>e.preventDefault();
  sg.onpointerdown=event=>{if(!formEditor||actionBusy)return;const p=shapePoint(event);if(!p)return;event.preventDefault();sg.focus();sg.setPointerCapture(event.pointerId);rememberShape();shapeDrag={last:p,tool:event.button===2?'transparent':formEditor.tool};setShapePixel(p.x,p.y,shapeDrag.tool);drawShape();};
  sg.onpointermove=event=>{if(!shapeDrag||!formEditor||actionBusy)return;const p=shapePoint(event);if(!p)return;shapeLine(shapeDrag.last,p,shapeDrag.tool);shapeDrag.last=p;drawShape();};
  sg.onpointerup=sg.onpointercancel=()=>{shapeDrag=null;scheduleImpact();};
  document.addEventListener('keydown',event=>{
    if(!$('shape-dialog').open||['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName))return;
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'){event.preventDefault();shapeUndo(!event.shiftKey);}
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();saveShape();}
    const arrows={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};if(arrows[event.key]){event.preventDefault();shiftShape(...arrows[event.key]);}
  });
  function reportError(message){const dialogs=[...document.querySelectorAll('dialog[open]')],dialog=dialogs[dialogs.length-1];if(!dialog)return;if(dialog.id==='shape-dialog'){shapeError(message);return;}let box=dialog.querySelector('.dialog-error');if(!box){box=el('p','inline-error dialog-error');box.setAttribute('role','alert');dialog.querySelector('.dialog-header').after(box);}box.textContent=message;}
  return {load,renderSidebar,updateButtons,drawLocks,hasUnsavedShape,reportError,reveal,clearAll};
})();
guard(boot)();
