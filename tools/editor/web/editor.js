'use strict';
// Pixel editing interactions adapted from tong/tool/editor.html.
const $ = id => document.getElementById(id);
let session, queue = [], filtered = [], current, rows = [], undo = [], redo = [];
let components = [], selection = null, tool = 'pen', drag = null, busy = false, dirty = false;
let reused = [], copied = null, loadNumber = 0, W = 13, H = 13, X = 1, CW = 14, CH = 14, BASE = null;
const grid = $('grid'), cell = 32;
let overlayImage = null, recommendationNumber = 0, queuedNavigation = null, readingGlyphs = [], readingMode = 'approved';
const drafts = new Map();
function hashID(){try{return decodeURIComponent(location.hash.replace(/^#(?:glyph=)?/,''));}catch{return '';}}
function setRoute(id, mode){
  if(mode==='none')return;
  const url='#glyph='+encodeURIComponent(id);
  if(mode==='replace'||location.hash===url)history.replaceState({glyph:id},'',url);
  else history.pushState({glyph:id},'',url);
}
function stashDraft(){
  if(!current)return;
  if(dirty)drafts.set(current.original.id,{base:structuredClone(current.current),rows:rows.slice(),note:$('note').value,reused:structuredClone(reused),undo:structuredClone(undo),redo:structuredClone(redo)});
  else drafts.delete(current.original.id);
}
function loadOverlay(id, url){
  overlayImage=null;
  const im=new Image();im.onload=()=>{if(current?.original.id===id){overlayImage=im;draw();}};
  im.onerror=()=>{if(current?.original.id===id&&$('overlay').checked)say('思源叠加图读取失败，请重试。',true);};im.src=url;
}
// “接下来建议修”: rank_representative.py orders unapproved SC/TC glyphs so that each next one brings
// components used by the most other glyphs (common characters first). Approved glyphs drop out.
let representative=new Map();
async function loadRepresentative(){
  try{const data=await (await fetch('/representative.json',{cache:'no-store'})).json();
    representative=new Map(data.glyphs.map((g,i)=>[g.id,{...g,rank:i}]));}catch{representative=new Map();}
}
function representativeNote(id){
  const r=representative.get(id);if(!r)return '';
  return `建议修第 ${r.rank+1} 位：带来 ${r.components.slice(0,6).map(c=>`${c.symbol}·${c.position}（${c.uses} 字用到）`).join('、')}${r.components.length>6?' 等':''}`;
}
const STATE_ZH={approved:'审核通过',edited:'人工改过 · 待审核',derived:'脚本连带改 · 待审核',ai:'AI 原稿 · 待审核','hangul-ai':'AI 韩文 · 待审核','hangul-composed':'拼合韩文 · 待审核',generated:'程序生成'};
function say(text, error = false) { $('notice').textContent = text; $('notice').classList.toggle('error', error); }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Review-Token': session.token}, body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}
function guard(fn) { return async (...args) => { try { await fn(...args); } catch (e) { say(e.message, true); window.ShapeUI?.reportError(e.message); } }; }
const equal = (a,b) => JSON.stringify(a) === JSON.stringify(b);
function snapshot() { return {rows: rows.slice(), reused: structuredClone(reused)}; }
function pushUndo(state = snapshot()) { undo.push(state); if (undo.length > 150) undo.shift(); redo = []; }
function updateDirty() {
  dirty = !!current && (!equal(rows, current.current.rows) || $('note').value !== current.current.note || !equal(reused, current.current.reused));
  if(current&&!dirty)drafts.delete(current.original.id);
  $('state').textContent = dirty ? '未保存' : STATE_ZH[current?.current.state] || current?.current.state || '待审核';
  $('state').classList.toggle('approved', !!current?.current.approved && !dirty);
  $('undo').disabled = busy || !undo.length; $('redo').disabled = busy || !redo.length;
  $('save').disabled = busy || !current;
  $('approve').disabled = busy || !current || (!dirty && current.current.approved);
  window.ShapeUI?.updateButtons();
  const others=[...drafts.keys()].filter(id=>id!==current?.original.id);
  $('drafts').hidden=!others.length;$('drafts').textContent=`另有 ${others.length} 字未保存草稿 · 返回处理`;
}
function paintCanvas(canvas, data, scale = 1) {
  canvas.width = CW * scale; canvas.height = CH * scale;
  const c = canvas.getContext('2d');c.fillStyle = 'white';c.fillRect(0,0,canvas.width,canvas.height);c.fillStyle = '#111';
  data.forEach((r,y) => [...r].forEach((v,x) => { if (v === '#') c.fillRect((x+X)*scale,y*scale,scale,scale); }));
}
function draw() {
  if (!current) return;
  // Proportional glyphs (.PR) may change width: the grid follows the rows (also after undo/redo).
  if(current.geometry?.flexible_width){W=CW=rows[0].length;}
  $('width-tools').hidden=!current.geometry?.flexible_width;
  if(current.geometry?.flexible_width)$('width-info').textContent=`宽 ${W} 像素（导出时右边固定留 1 列字距）`;
  grid.width = CW*cell;grid.height = CH*cell;grid.style.aspectRatio = `${CW} / ${CH}`;grid.style.width = `min(100%, ${CW*32}px)`;
  const c = grid.getContext('2d');c.fillStyle = '#e5ece8';c.fillRect(0,0,grid.width,grid.height);
  c.fillStyle = 'white';c.fillRect(X*cell,0,W*cell,H*cell);
  for(let y=0;y<H;y++) for(let x=0;x<W;x++) {
    if(rows[y][x]==='#'){c.fillStyle='#111';c.fillRect((x+X)*cell,y*cell,cell,cell);}
    if($('diff').checked && rows[y][x]!==current.original.rows[y][x]){c.strokeStyle='#d88737';c.lineWidth=2;c.strokeRect((x+X)*cell+2,y*cell+2,cell-4,cell-4);}
  }
  if($('overlay').checked&&overlayImage){c.save();c.globalAlpha=Number($('overlay-opacity').value)/100;c.drawImage(overlayImage,0,0,grid.width,grid.height);c.restore();}
  c.strokeStyle='#d5ddd7';c.lineWidth=1;
  for(let x=0;x<=CW;x++){c.beginPath();c.moveTo(x*cell+.5,0);c.lineTo(x*cell+.5,CH*cell);c.stroke();}
  for(let y=0;y<=CH;y++){c.beginPath();c.moveTo(0,y*cell+.5);c.lineTo(CW*cell,y*cell+.5);c.stroke();}
  if(BASE!==null){c.strokeStyle='#e0443e';c.lineWidth=2;c.beginPath();c.moveTo(0,BASE*cell);c.lineTo(CW*cell,BASE*cell);c.stroke();}
  if(selection){c.fillStyle='#508fb528';c.fillRect((selection.x+X)*cell,selection.y*cell,selection.w*cell,selection.h*cell);c.strokeStyle='#28759f';c.lineWidth=2;c.setLineDash([7,4]);c.strokeRect((selection.x+X)*cell+1,selection.y*cell+1,selection.w*cell-2,selection.h*cell-2);c.setLineDash([]);}
  window.ShapeUI?.drawLocks(c);
  paintCanvas($('native'),rows);paintCanvas($('preview'),rows);
  $('native').style.width=CW+'px';$('native').style.height=CH+'px';$('preview').style.width=CW*4+'px';$('preview').style.height=CH*4+'px';
  $('selection-info').textContent=selection ? `选区 ${selection.w}×${selection.h} · 墨迹坐标 (${selection.x}, ${selection.y})` : '尚未框选';
  updateDirty();
}
function renderQueue() {
  // Characters match exactly as typed (ɀ must not become Ɀ); IDs ignore case (u+0240.hw).
  const raw=$('search').value.trim(), q=raw.toUpperCase(), batch=$('batch').value, filter=$('filter').value;
  // An ID search is “U+…” or a 4–6 digit hex code point; anything else is the character itself (so “1” finds the digit).
  const isId=/^u\+/i.test(raw)||/^[0-9a-f]{4,6}$/i.test(raw);
  // Punctuation / western-letter views (Unicode category of the glyph's character).
  const isPunct=c=>/^\p{P}$/u.test(c), isLetter=c=>/^\p{L}$/u.test(c), west=g=>/\.(HW|PR)$/.test(g.id);
  const special={'punct-cjk':g=>isPunct(g.char)&&!west(g),'punct-west':g=>isPunct(g.char)&&west(g),
    'digits-west':g=>/^\p{N}$/u.test(g.char)&&west(g),'latin-hw':g=>isLetter(g.char)&&g.id.endsWith('.HW')&&!/^[\u3000-\uffff]$/.test(g.char),'latin-pr':g=>isLetter(g.char)&&g.id.endsWith('.PR')&&!/^[\u0e00-\u0e7f\u0600-\u06ff\ufb50-\ufeff]$/.test(g.char)}[filter];
  // Glyphs no font uses (e.g. a full-width ¤ where every font uses the western one) are hidden unless searched for.
  const hideUnused=$('hide-unused').checked&&!raw;
  const repLocale=/^rep-(SC|TC)$/.test(filter)?filter.slice(4):'';
  filtered=queue.filter(g=>(!raw || (isId ? g.id.includes(q) : g.char===raw)) && (!batch || g.batch===batch) && !(hideUnused&&g.unused) &&
    (repLocale ? representative.has(g.id)&&g.locale===repLocale&&!g.approved :
    special ? special(g) :
    filter==='all' || filter==='concern'&&g.concern || filter==='edited'&&g.edited || filter==='approved'&&g.approved || filter==='pending'&&!g.approved));
  if(special)filtered.sort((a,b)=>a.char.codePointAt(0)-b.char.codePointAt(0)||a.id.localeCompare(b.id));
  if(repLocale)filtered.sort((a,b)=>representative.get(a.id).rank-representative.get(b.id).rank);
  $('priority-summary').hidden=!repLocale;
  if(repLocale){const total=[...representative.values()].filter(r=>r.locale===repLocale).length;
    $('priority-summary').textContent=`接下来建议修的${repLocale==='SC'?'简体':'繁体'}字：共 ${total} 字，还剩 ${filtered.length} 字未通过。越靠前的字，所含部件被越多其他字用到（常用字优先）；修好并通过一个字，就给这些部件提供了通过的写法。已通过的字自动移出。`;}
  $('queue').replaceChildren();
  for(const g of filtered){
    const b=document.createElement('button');b.textContent=g.char;b.title=`${g.id} · ${STATE_ZH[g.batch]||g.batch}${repLocale?' · '+representativeNote(g.id):''}${g.concern?' · '+g.concern:''}`;
    b.setAttribute('aria-label',`${g.char} ${g.id} ${g.batch}`);b.classList.toggle('active',current?.original.id===g.id);b.classList.toggle('approved',g.approved);b.classList.toggle('edited',g.edited);b.classList.toggle('unused',!!g.unused);if(g.unused)b.title+=' · 字体里用不到';
    const detail=document.createElement('small');detail.textContent=g.locale+(g.approved?' ✓':g.edited?' 改':g.concern?' !':'');b.append(detail);b.onclick=guard(()=>show(g.id));$('queue').append(b);
  }
  if(!filtered.length){const p=document.createElement('p');p.className='empty';p.textContent='没有符合条件的字形';$('queue').append(p);}
  $('counts').textContent=`${queue.length} 字 · 已修改 ${queue.filter(g=>g.edited).length} · 已通过 ${queue.filter(g=>g.approved).length} · 用不到 ${queue.filter(g=>g.unused).length}`;
}
function fillStates(){const chosen=$('batch').value;$('batch').replaceChildren(new Option('所有状态',''));for(const b of Object.keys(STATE_ZH))if(queue.some(g=>g.batch===b))$('batch').add(new Option(`${b} · ${STATE_ZH[b]}`,b));$('batch').value=chosen;}
async function refreshQueue() { queue=await api('/api/queue');fillStates();renderQueue(); }
async function show(id, mode='push') {
  if(!queue.some(g=>g.id===id)){say('没有这个字形，或它与其他地区共用字形（别名）。',true);if(current)setRoute(current.original.id,'replace');return;}
  if(busy){queuedNavigation={id,mode};return;}
  if(current?.original.id===id){setRoute(id,mode==='none'?'none':'replace');return;}
  stashDraft();
  const n=++loadNumber;busy=true;updateDirty();
  try {
    const data=await api('/api/glyph/'+encodeURIComponent(id));if(n!==loadNumber)return;
    current=data;rows=data.current.rows.slice();reused=structuredClone(data.current.reused);undo=[];redo=[];selection=null;drag=null;
    const geom=data.geometry;W=geom.ink_width;H=geom.ink_height;X=geom.x_base;CW=geom.cell_width;CH=geom.cell_height;BASE=geom.baseline_row??null;
    const refName=geom.reference_label||`思源 ${data.original.locale} w400`;
    $('bigchar').textContent=data.original.char;$('identity').textContent=data.original.id;
    const shared=(data.aliases||[]).map(a=>a.split('.').pop());
    $('recipe').textContent=(BASE!==null?`${geom.kind==='mono'?'等宽':'比例'}字格 ${CW}×${CH} · 步进 ${geom.flexible_width?'墨迹宽+1':geom.advance}${geom.x_offset?` · x_offset ${geom.x_offset}`:''} · 红线=基线（${BASE} 行起为降部）`:`字格 ${CW}×${CH} · 墨迹 ${W}×${H}`)+(shared.length?` · ${shared.join('、')} 也用此字形`:'');
    $('reference-box').hidden=!data.reference;$('overlay-controls').hidden=!data.overlay;
    if(data.reference){$('reference').src=data.reference;$('reference-label').textContent=`${refName.replace(/ w\d+$/,'')} 参考`;}
    if(data.overlay){loadOverlay(id,data.overlay);$('overlay-info').textContent=BASE!==null?`青色：${refName} 轮廓，底稿字号，在基线上，横向按底稿墨迹对齐；黑色：当前点阵。`:`青色：思源 ${data.original.locale} w400，${geom.advance}px em，基线 ${geom.ascent}px；黑色：当前点阵。`;}else overlayImage=null;
    $('note').value=data.current.note;$('concern').textContent=data.original.note?'AI 原注：'+data.original.note:'AI 未留问题说明。';
    $('history').replaceChildren(new Option(data.history.length?'选择一个历史版本':'（没有 git 提交记录）',''));
    for(const r of data.history)$('history').add(new Option(`${r.saved_at.slice(0,16).replace('T',' ')} · ${STATE_ZH[r.state]||r.state} · ${r.subject}`,r.revision));
    $('original-label').textContent=data.original.base_label;$('restore').textContent='恢复到'+data.original.base_label;$('restore').title=`载入${data.original.base_label}的版本（尚未保存，可撤销）`+(data.original.base_label==='上次提交'?'':'。建立 git 仓库并提交后，这里会变成“上次提交”');paintCanvas($('original'),data.original.rows);
    $('ai-box').hidden=!data.original.ai_rows;$('restore-ai').hidden=!data.original.ai_rows;$('phase-draft').hidden=!session.phase_draft||!/\.(SC|TC|JP|KR|HW|PR)$/.test(id);
    if(data.original.ai_rows){const keep=[W,CW];if(geom.flexible_width){W=CW=data.original.ai_rows[0].length;}paintCanvas($('ai-original'),data.original.ai_rows);[W,CW]=keep;}
    dirty=false;
    renderSiblings(data);renderUsage(data.usage);
    const rep=representativeNote(data.original.id);if(rep&&!data.usage?.unused&&!data.current.approved){$('usage-note').hidden=false;$('usage-note').textContent=rep+'。这些部件的写法会被其他字参考复用，请把它们修规整。';}
    const draft=drafts.get(id);
    if(draft){current.current=draft.base;rows=draft.rows.slice();reused=structuredClone(draft.reused);$('note').value=draft.note;undo=structuredClone(draft.undo);redo=structuredClone(draft.redo);}
    setRoute(id,mode);
    try{localStorage.setItem('tong-editor-id',id);}catch{}
    renderQueue();loadComponents().catch(e=>say(e.message,true));say(draft?'已恢复此字未保存的草稿。浏览器前进／后退会保留本页草稿；关闭页面前请保存。':data.current.approved?'此版本已审核通过。再次修改后需要重新审核。':'修改后请保存；确认字形满意时再点“审核通过”。');
  } finally {busy=false;draw();resumeNavigation();}
}
function renderUsage(u){
  // A glyph no font uses: say so, why, and link to the glyphs the fonts use instead.
  const box=$('usage-note');box.replaceChildren();box.hidden=!u?.unused;if(!u?.unused)return;
  box.append(`这个字形在 8 个字体里都用不到，不必修${u.reason?`：${u.reason}`:''}。字体里实际用的是：`);
  (u.instead||[]).forEach((it,i)=>{if(i)box.append('、');const b=document.createElement('button');b.className='text-button';b.textContent=it.id;b.title='用在 '+it.faces.map(f=>'TongPixelSans'+f.replace(' ','')).join('、');b.onclick=guard(()=>show(it.id));box.append(b,`（${it.faces.join('、')}）`);});
  if(!u.instead?.length)box.append('（没有）');
}
function renderSiblings(data){
  const list=$('sibling-list');list.replaceChildren();const sibs=data.siblings||[];$('siblings').hidden=!sibs.length;
  for(const sb of sibs){
    const box=document.createElement('div');box.className='sibling';
    const g=sb.geometry,cw=g.cell_width,ch=g.cell_height,xb=g.x_base,sc=4,cv=document.createElement('canvas');
    cv.width=cw*sc;cv.height=ch*sc;const c=cv.getContext('2d');c.fillStyle='white';c.fillRect(0,0,cv.width,cv.height);c.fillStyle='#111';
    sb.rows.forEach((r,y)=>[...r].forEach((v,x)=>{if(v==='#')c.fillRect((x+xb)*sc,y*sc,sc,sc);}));
    const label=document.createElement('span');label.className='sib-label';
    label.textContent=`${sb.locale}${sb.approved?' ✓':sb.edited?' 改':''}${sb.links?` · 关联 ${sb.links}`:''}`;label.title=sb.id;
    const open=document.createElement('button');open.textContent='打开';open.onclick=guard(()=>show(sb.id));
    const copyBtn=document.createElement('button');copyBtn.textContent='完全复制过来';
    copyBtn.disabled=!sb.same_size;copyBtn.title=sb.same_size?`用 ${sb.id} 的全部像素和关联部件替换本字`:'字格大小不同，不能整字复制';
    copyBtn.onclick=guard(()=>copyFrom(sb.id));
    box.append(cv,label,open,copyBtn);list.append(box);
  }
}
async function copyFrom(source){
  if(!current||busy)return;const id=current.original.id;
  if(!confirm(`用 ${source} 完全替换 ${id}？\n本字当前的全部像素和关联会被清空，换成 ${source} 的像素和关联部件${dirty?'；未保存的修改也会丢弃':''}。之后可在历史版本中恢复。`))return;
  busy=true;updateDirty();
  try{
    const r=await api('/api/copy-from',{id,expected_revision:current.current.revision,source_id:source});
    drafts.delete(id);dirty=false;
  }finally{busy=false;}
  current=null;await refreshQueue();await show(id,'replace');
  say(`已从 ${source} 整字复制（像素与关联部件），尚未审核通过。`);
}
function changeWidth(side, delta){
  if(!current?.geometry?.flexible_width||busy)return;
  const w=rows[0].length;
  if(delta<0){
    if(w<=1){say('宽度至少 1 像素。',true);return;}
    const x=side==='left'?0:w-1;
    if(rows.some(r=>r[x]==='#')){say(`${side==='left'?'最左':'最右'}一列有黑点，先清空再删列。`,true);return;}
    pushUndo();rows=rows.map(r=>side==='left'?r.slice(1):r.slice(0,-1));
  }else{
    if(w>=16){say('比例字最宽 16 像素。',true);return;}
    pushUndo();rows=rows.map(r=>side==='left'?'.'+r:r+'.');
  }
  selection=null;draw();say(`宽度 ${rows[0].length} 像素，尚未保存；可撤销。`);
}
$('w-add-left').onclick=()=>changeWidth('left',1);$('w-del-left').onclick=()=>changeWidth('left',-1);
$('w-add-right').onclick=()=>changeWidth('right',1);$('w-del-right').onclick=()=>changeWidth('right',-1);
function resumeNavigation(){if(queuedNavigation){const next=queuedNavigation;queuedNavigation=null;queueMicrotask(()=>guard(()=>show(next.id,next.mode))());}}
async function save(approved) {
  if(!current || busy)return;
  busy=true;updateDirty();
  try{
    const result=await api('/api/save',{id:current.original.id,expected_revision:current.current.revision,rows:rows.slice(),note:$('note').value,approved,reused});
    current.current=result;reused=structuredClone(result.reused);dirty=false;drafts.delete(current.original.id);
    await refreshQueue();await loadComponents();
    const payload=await api('/api/glyph/'+encodeURIComponent(current.original.id));current.history=payload.history;
    say(approved?'已保存，并将当前版本标记为审核通过。':'修改已保存，仍待审核。');
  }finally{busy=false;draw();resumeNavigation();}
}
function point(e){const b=grid.getBoundingClientRect();const x=Math.floor((e.clientX-b.left)*CW/b.width)-X,y=Math.floor((e.clientY-b.top)*CH/b.height);return x>=0&&x<W&&y>=0&&y<H?{x,y}:null;}
function lockedAt(x,y){return (current?.linked_forms||[]).find(f=>f.rows[y]?.[x]==='#');}
function keepsLinkedInk(candidate){return !(current?.linked_forms||[]).some(f=>f.rows.some((r,y)=>[...r].some((v,x)=>v==='#'&&candidate[y][x]!=='#')));}
function setPixel(x,y,v){if(v==='.'&&lockedAt(x,y)){say('这个黑点属于关联形态。要删除它，请独立编辑形态或先解除关联。',true);return;}rows[y]=rows[y].slice(0,x)+v+rows[y].slice(x+1);}
function line(a,b,v){let dx=Math.abs(b.x-a.x),dy=-Math.abs(b.y-a.y),sx=a.x<b.x?1:-1,sy=a.y<b.y?1:-1,err=dx+dy;let x=a.x,y=a.y;for(;;){setPixel(x,y,v);if(x===b.x&&y===b.y)break;const e=2*err;if(e>=dy){err+=dy;x+=sx;}if(e<=dx){err+=dx;y+=sy;}}}
grid.onpointerdown=e=>{
  if(!current||busy)return;const p=point(e);if(!p)return;e.preventDefault();grid.focus();grid.setPointerCapture(e.pointerId);
  if(e.shiftKey||tool==='select'){drag={type:'select',start:p};selection={...p,w:1,h:1};}
  else if(lockedAt(p.x,p.y)&&e.button!==1){
    // Protected ink is not painted: left click finds its form, right click edits it.
    const edit=e.button===2;say(edit?'正在打开此黑点所属形态的编辑器。':'已定位到此黑点所属的形态；右键点它可直接编辑形态。');
    guard(()=>window.ShapeUI?.reveal(lockedAt(p.x,p.y).slot,edit))();return;
  }
  else {selection=null;pushUndo();drag={type:'paint',last:p,value:e.button===2?'.':rows[p.y][p.x]==='#'?'.':'#'};setPixel(p.x,p.y,drag.value);}
  draw();
};
grid.onpointermove=e=>{if(!drag){const q=point(e);grid.style.cursor=q&&tool!=='select'&&!e.shiftKey&&lockedAt(q.x,q.y)?'pointer':'';}if(!drag||busy)return;const p=point(e);if(!p)return;if(drag.type==='select'){const a=drag.start;selection={x:Math.min(a.x,p.x),y:Math.min(a.y,p.y),w:Math.abs(a.x-p.x)+1,h:Math.abs(a.y-p.y)+1};}else{line(drag.last,p,drag.value);drag.last=p;}draw();};
grid.onpointerup=grid.onpointercancel=()=>{drag=null;};grid.oncontextmenu=e=>e.preventDefault();
function move(dx,dy,whole=false){
  if(!current||busy)return;
  const area=whole?{x:0,y:0,w:W,h:H}:selection;if(!area)return;
  const pixels=[];for(let y=area.y;y<area.y+area.h;y++)for(let x=area.x;x<area.x+area.w;x++)if(rows[y][x]==='#')pixels.push([x,y]);
  if(pixels.some(([x,y])=>x+dx<0||y+dy<0||x+dx>=W||y+dy>=H)||(!whole&&(area.x+dx<0||area.y+dy<0||area.x+dx+area.w>W||area.y+dy+area.h>H))){say('移动会超出墨迹区域，未执行。',true);return;}
  const moved=rows.map(r=>[...r]);pixels.forEach(([x,y])=>moved[y][x]='.');pixels.forEach(([x,y])=>moved[y+dy][x+dx]='#');
  const next=moved.map(r=>r.join(''));
  if(!keepsLinkedInk(next)){say('移动会删除关联形态的黑点。请先解除关联，或独立编辑形态。',true);return;}
  pushUndo();rows=next;
  reused=reused.map(r=>whole||r.x===area.x&&r.y===area.y?{...r,x:r.x+dx,y:r.y+dy}:r);
  if(!whole)selection={...area,x:area.x+dx,y:area.y+dy};else selection=null;draw();
}
function undoAction(back){
  if(busy)return;const from=back?undo:redo,to=back?redo:undo;if(!from.length)return;
  const r=from[from.length-1];
  if(!keepsLinkedInk(r.rows)){say(`${back?'撤销':'重做'}会删除仍关联形态的黑点，请先解除相应关联。`,true);return;}
  to.push(snapshot());from.pop();rows=r.rows;reused=r.reused;selection=null;draw();
}
function copy(){if(!selection)throw Error('请先框选部件');copied={rows:rows.slice(selection.y,selection.y+selection.h).map(r=>r.slice(selection.x,selection.x+selection.w)),x:selection.x,y:selection.y};navigator.clipboard?.writeText(copied.rows.join('\n')).catch(()=>{});say('已复制选区。换字后可粘贴，再用方向键移动。');}
async function paste(){
  if(busy||!current)return;let data=copied?.rows;
  if(!data){const text=await navigator.clipboard.readText();data=text.trim().split(/\r?\n/);}
  if(!data?.length||data.some(r=>r.length!==data[0].length||/[^.#]/.test(r)))throw Error('剪贴板不是有效点阵');
  const w=data[0].length,h=data.length,x=selection?.x??copied?.x??0,y=selection?.y??copied?.y??0;
  if(x+w>W||y+h>H)throw Error('粘贴内容超出墨迹区域');
  pushUndo();
  data.forEach((r,dy)=>[...r].forEach((v,dx)=>{if(v==='#')setPixel(x+dx,y+dy,v);}));selection={x,y,w,h};draw();say('已粘贴，尚未保存。方向键可调整位置。');
}
async function loadComponents(){return window.ShapeUI?.load();}
function renderReading(){
  const box=$('reading-content');box.replaceChildren();
  const all=readingMode==='all', title=all?'预览所有字':'预览通过字';
  $('reading-title').textContent=title;
  $('reading-count').textContent=all
    ? `当前 ${readingGlyphs.length} 字 · 已通过 ${readingGlyphs.filter(g=>g.approved).length} · 未通过 ${readingGlyphs.filter(g=>!g.approved).length}，按原字序连续排文。`
    : `当前 ${readingGlyphs.length} 个通过字，按原字序连续排文。待审核和未保存草稿不进入排文。`;
  $('reading-description').textContent=(all?'使用当前已保存版本；未修改的字使用 AI 原稿，未保存草稿不进入排文。':'使用当前已通过版本的真实点阵。')+'按字格步进连续排列；各地区（SC / TC / JP）分开。点击字形可回到编辑器。';
  if(!readingGlyphs.length){box.textContent=all?'尚无已生成的字。':'尚无审核通过的字。';return;}
  const geom=session.geometry, zoom=Number($('reading-scale').value);
  for(const locale of [...new Set(['SC','TC',...readingGlyphs.map(g=>g.locale)])]){
    const glyphs=readingGlyphs.filter(g=>g.locale===locale);if(!glyphs.length)continue;
    const heading=document.createElement('h2');heading.textContent=`${locale} · ${glyphs.length} 字`;box.append(heading);
    for(const scale of [1,zoom]){
      const block=document.createElement('div');block.className='reading-block';
      const label=document.createElement('h3');label.textContent=scale===1?'1:1 · 实际字格':'放大 '+scale+'×';block.append(label);
      // Measure the block's real content box. Canvas bitmap pixels and CSS pixels
      // then stay 1:1, so the browser never rescales or drops narrow strokes.
      box.append(block);
      const style=getComputedStyle(block);
      const available=Math.max(geom.advance*scale,block.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight));
      // Lay glyphs out by their own advance (14 for full-width; variable for .HW/.PR).
      const adv=g=>g.advance??geom.advance, xb=g=>g.x_base??geom.x_base, lineHeight=geom.cell_height+4, width=Math.floor(available/scale);
      const lines=[[]];let used=0;
      for(const g of glyphs){if(used+adv(g)>width&&lines.at(-1).length){lines.push([]);used=0;}lines.at(-1).push({g,x:used});used+=Math.max(adv(g),1);}
      const perCanvas=Math.max(1,Math.floor(4096/(lineHeight*scale)));
      for(let start=0;start<lines.length;start+=perCanvas){
        const page=lines.slice(start,start+perCanvas),cv=document.createElement('canvas');
        cv.width=width*scale;cv.height=page.length*lineHeight*scale;
        cv.style.width=cv.width+'px';cv.style.height=cv.height+'px';cv.setAttribute('aria-label',locale+' '+title+' '+page.flat().map(p=>p.g.char).join(''));
        const ctx=cv.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,cv.width,cv.height);ctx.fillStyle='#111';
        page.forEach((line,li)=>line.forEach(({g,x:gx})=>g.rows.forEach((r,y)=>[...r].forEach((v,x)=>{if(v==='#')ctx.fillRect((gx+xb(g)+x)*scale,(li*lineHeight+y)*scale,scale,scale);}))));
        cv.onclick=guard(e=>{const rect=cv.getBoundingClientRect(),x=(e.clientX-rect.left)*cv.width/rect.width/scale,y=(e.clientY-rect.top)*cv.height/rect.height/scale;
          if(y%lineHeight>=geom.cell_height)return;
          const hit=page[Math.floor(y/lineHeight)]?.find(p=>x>=p.x&&x<p.x+Math.max(adv(p.g),1));
          if(hit){$('reading-dialog').close();return show(hit.g.id);}
        });block.append(cv);
      }
    }
  }
}
$('pen').onclick=()=>{tool='pen';$('pen').setAttribute('aria-pressed','true');$('select').setAttribute('aria-pressed','false');};
$('select').onclick=()=>{tool='select';$('pen').setAttribute('aria-pressed','false');$('select').setAttribute('aria-pressed','true');};
$('undo').onclick=()=>undoAction(true);$('redo').onclick=()=>undoAction(false);$('diff').onchange=draw;$('note').oninput=updateDirty;
$('save').onclick=guard(()=>save(false));$('approve').onclick=guard(()=>save(true));
$('previous').onclick=guard(()=>{const i=filtered.findIndex(g=>g.id===current?.original.id);if(i>0)return show(filtered[i-1].id);});
$('next').onclick=guard(()=>{const i=filtered.findIndex(g=>g.id===current?.original.id);if(i<filtered.length-1)return show(filtered[i+1].id);});
for(const id of ['search','batch','filter','hide-unused'])$(id).addEventListener(id==='search'?'input':'change',renderQueue);
$('copy').onclick=guard(copy);$('paste').onclick=guard(paste);
$('erase').onclick=()=>{if(!selection||busy)return;pushUndo();for(let y=selection.y;y<selection.y+selection.h;y++)for(let x=selection.x;x<selection.x+selection.w;x++)setPixel(x,y,'.');draw();};
$('clear-all').onclick=guard(()=>window.ShapeUI.clearAll());
function loadVersion(data,label){if(!current||busy||!data)return;if(!keepsLinkedInk(data)){say(`${label}缺少关联形态的黑点，请先解除相应关联。`,true);return;}if(current.geometry?.flexible_width===false&&data[0].length!==W){say(`${label}的字格大小不同，不能载入。`,true);return;}pushUndo();rows=data.slice();reused=[];selection=null;draw();say(`已载入${label}，尚未保存；可撤销。`);}
$('restore').onclick=()=>loadVersion(current?.original.rows,current?.original.base_label||'上次提交');
$('restore-ai').onclick=()=>loadVersion(current?.original.ai_rows,'AI 原稿');
$('phase-draft').onclick=guard(async()=>{
  if(!current||busy)return;
  say('正在计算相位底稿…');
  const d=await api('/api/phase/'+encodeURIComponent(current.original.id));
  if(!keepsLinkedInk(d.rows)){say('相位底稿缺少关联形态的黑点，请先解除相应关联。',true);return;}
  if(!current.geometry?.flexible_width&&d.rows[0].length!==rows[0].length){say(`相位底稿宽 ${d.rows[0].length}，与本字字格（宽 ${rows[0].length}）不同，未载入。`,true);return;}
  pushUndo();rows=d.rows.slice();reused=[];selection=null;draw();
  say(`已载入相位底稿（${d.label} 字面 ${d.face.join('×')}，横移 ${d.phase_k}/16 像素${d.phase_k===0?'，即 WorkBench 原样':''}），尚未保存；可撤销。`);
});
$('history-load').onclick=()=>{const r=current?.history.find(r=>r.revision===$('history').value);if(!r||busy)return;if(!keepsLinkedInk(r.rows)){say('历史版本与当前关联形态不一致，请先解除关联。',true);return;}pushUndo();rows=r.rows.slice();reused=structuredClone(r.reused);$('note').value=r.note;selection=null;draw();say('历史版本已载入。保存后会建立新版本，不会覆盖历史。');};
$('component-search').oninput=()=>window.ShapeUI?.renderSidebar();
document.addEventListener('keydown',e=>{
  if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)||document.querySelector('dialog[open]'))return;
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();guard(()=>save(false))();return;}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();undoAction(!e.shiftKey);return;}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();undoAction(false);return;}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='c'&&selection){e.preventDefault();guard(copy)();return;}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='v'){e.preventDefault();guard(paste)();return;}
  const ds={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
  if(ds[e.key]&&(selection||e.altKey)){e.preventDefault();move(...ds[e.key],e.altKey);}
  if(e.key==='Escape'){selection=null;draw();}if(e.key==='Delete'&&selection){e.preventDefault();$('erase').click();}
});
window.addEventListener('beforeunload',e=>{if(dirty||drafts.size||window.ShapeUI?.hasUnsavedShape()){e.preventDefault();e.returnValue='';}});
const followRoute=guard(()=>{const id=hashID();if(id&&id!==current?.original.id)return show(id,'none');});
window.addEventListener('popstate',followRoute);window.addEventListener('hashchange',followRoute);
$('drafts').onclick=guard(()=>{const id=[...drafts.keys()].find(id=>id!==current?.original.id);if(id)return show(id);});
$('overlay').onchange=()=>{$('overlay-info').hidden=!$('overlay').checked;draw();};
$('overlay-opacity').oninput=()=>{$('overlay-value').textContent=$('overlay-opacity').value+'%';draw();};
async function openReading(mode){
  const glyphs=await api(mode==='all'?'/api/reading':'/api/approved');
  readingMode=mode;readingGlyphs=glyphs;
  $('reading-dialog').showModal();renderReading();
}
$('reading-open').onclick=guard(()=>openReading('approved'));
$('reading-all-open').onclick=guard(()=>openReading('all'));
$('reading-close').onclick=()=>$('reading-dialog').close();$('reading-scale').onchange=renderReading;
let readingResize;window.addEventListener('resize',()=>{clearTimeout(readingResize);if($('reading-dialog').open)readingResize=setTimeout(renderReading,100);});
async function boot(){
  session=await api('/api/session');queue=await api('/api/queue');await loadRepresentative();fillStates();renderQueue();
  let remembered;try{remembered=localStorage.getItem('tong-editor-id');}catch{}
  const linked=hashID(),initial=queue.some(g=>g.id===linked)?linked:queue.some(g=>g.id===remembered)?remembered:queue[0]?.id;
  if(initial)await show(initial,'replace');else say('没有字形。');
}
