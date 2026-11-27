(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const data = window.DOTS_ARCHIVE;
  if (!data?.items || !window.DotsArchiveCore) { $('load-error').hidden = false; return; }
  const {sanitizeSelection, selectedItems, makeText} = window.DotsArchiveCore;
  const items = data.items;
  const byId = new Map(items.map(item => [item.id, item]));
  const labels = {all:'전체 사진',board:'브랜드 보드',product:'컵·봉투·제품',storefront:'매장·간판',logo:'로고·심벌',sticker:'스티커',legacy:'이전 아카이브'};
  const key = 'dots.archive.selection.v1';
  const publicBase = 'https://gptjyp-ops.github.io/JYP-COWRK/';
  let selection = Object.create(null), request = '', category = 'all', onlySelected = false, visible = [], currentId = null, toastTimer;
  try { const saved = JSON.parse(localStorage.getItem(key) || '{}'); selection = sanitizeSelection(saved.selection, items); request = typeof saved.request === 'string' ? saved.request.slice(0,10000) : ''; }
  catch { $('storage-note').textContent = '이 브라우저에서는 자동 저장을 사용할 수 없어요. 선택 저장으로 파일을 남겨 주세요.'; }
  const shared = new URL(location.href).searchParams.get('pick');
  if (shared) for (const id of shared.split(',').slice(0,items.length)) if (byId.has(id)) selection[id] ||= {note:''};

  function el(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text != null) node.textContent = text; return node; }
  function src(item) { return item.src || window.DOTS_IMAGES?.[item.legacyIndex] || ''; }
  function toast(text) { clearTimeout(toastTimer); $('toast').textContent = text; $('toast').hidden = false; toastTimer = setTimeout(() => { $('toast').hidden = true; },4500); }
  function persist() {
    try { localStorage.setItem(key, JSON.stringify({selection, request})); }
    catch { $('storage-note').textContent = '자동 저장에 실패했어요. 선택 저장으로 파일을 남겨 주세요.'; }
  }
  function toggle(id, checked) {
    if (!byId.has(id)) return;
    if (checked) selection[id] ||= {note:''}; else delete selection[id];
    persist(); render(); renderSelection();
    if (currentId === id) $('lightbox-check').checked = checked;
  }
  function render() {
    const query = $('search').value.trim().toLocaleLowerCase();
    const month = $('month').value;
    const sort = $('sort').value;
    visible = items.filter(item => (category === 'all' || item.category === category) && (month === 'all' || (item.date || 'unknown').startsWith(month)) && (!onlySelected || Object.hasOwn(selection,item.id)) && (!query || `${item.id} ${item.number || ''} ${item.title} ${item.filename} ${item.date || ''}`.toLocaleLowerCase().includes(query)));
    if (sort !== 'number') visible.sort((a,b) => {
      if (!a.date || !b.date) return a.date ? -1 : b.date ? 1 : 0;
      return sort === 'new' ? b.date.localeCompare(a.date) : a.date.localeCompare(b.date);
    });
    const frag = document.createDocumentFragment();
    for (const item of visible) {
      const chosen = Object.hasOwn(selection,item.id);
      const card = el('article','card' + (chosen ? ' is-selected' : '')); card.dataset.id = item.id;
      const open = el('button','image-open'); open.type = 'button'; open.dataset.open = item.id; open.setAttribute('aria-label',item.id + ' ' + item.title + ' 확대');
      const image = el('img'); image.src = src(item); image.alt = item.title; image.loading = 'lazy'; image.decoding = 'async';
      image.addEventListener('error', () => { image.alt = '사진을 불러오지 못했어요. 다시 열어 주세요.'; },{once:true});
      open.append(image,el('span','expand-label','크게 보기 ↗'));
      const body = el('div','card-body');
      const meta = el('div','card-meta'); meta.append(el('span','card-id',item.id + (item.number ? ' / PDF ' + item.number : '')),el('span','',item.date || '이전 기록'));
      const choose = el('label','choose-row');
      const check = el('input'); check.type = 'checkbox'; check.checked = chosen; check.dataset.select = item.id; check.setAttribute('aria-label',item.id + ' 선택');
      choose.append(check,el('span','',chosen ? '선택됨' : '이 시안 선택'),el('span','kind-tag',labels[item.category]));
      body.append(meta,el('h3','',item.title),choose); card.append(open,body); frag.append(card);
    }
    $('gallery').replaceChildren(frag);
    $('empty').hidden = visible.length !== 0;
    $('result-count').textContent = `${visible.length}장의 사진${onlySelected ? ' · 선택한 시안' : ''}`;
    for (const button of $('categories').children) {
      const active = button.dataset.category === category; button.classList.toggle('active',active); button.setAttribute('aria-pressed',String(active));
    }
  }
  function renderSelection() {
    const chosen = selectedItems(items,selection);
    for (const id of ['selection-count','sticky-count','selected-badge']) $(id).textContent = chosen.length;
    for (const id of ['save-selection','save-top','copy-request','send-chatgpt']) $(id).disabled = chosen.length === 0;
    $('selection-empty').hidden = chosen.length !== 0;
    const frag = document.createDocumentFragment();
    for (const item of chosen) {
      const box = el('div','selection-item');
      const image = el('img'); image.src = src(item); image.alt = item.title; image.loading = 'lazy';
      const body = el('div'); body.append(el('strong','',`${item.id} · ${item.title}`));
      const note = el('textarea'); note.rows = 2; note.maxLength = 5000; note.value = selection[item.id].note; note.placeholder = '마음에 드는 부분을 적어주세요. 예: 글씨만, 봉투 색감'; note.setAttribute('aria-label',item.id+' 반영할 부분');
      note.addEventListener('input',() => { selection[item.id].note = note.value; persist(); }); body.append(note);
      const remove = el('button','','선택 해제 ×'); remove.addEventListener('click',() => toggle(item.id,false));
      box.append(image,body,remove); frag.append(box);
    }
    $('selection-list').replaceChildren(frag);
  }
  function openPhoto(id) {
    const item = byId.get(id); if (!item) return; currentId = id;
    $('lightbox-title').textContent = `${item.id} · ${item.title}`;
    $('lightbox-image').src = src(item); $('lightbox-image').alt = item.title;
    $('lightbox-check').checked = Object.hasOwn(selection,id);
    if (item.src) { $('lightbox-original').href = item.src; $('lightbox-original').hidden = false; } else $('lightbox-original').hidden = true;
    if (!$('lightbox').open) $('lightbox').showModal();
  }
  function movePhoto(delta) {
    const pool = visible.some(item => item.id === currentId) ? visible : items;
    const index = pool.findIndex(item => item.id === currentId); if (!pool.length) return;
    openPhoto(pool[(index + delta + pool.length) % pool.length].id);
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; }
    catch {
      const box = el('textarea'); box.value = text; box.style.cssText='position:fixed;left:-9999px;top:0';
      // A modal must contain the fallback textarea for browsers that trap focus.
      const parent = $('handoff').open ? $('handoff') : document.body;
      parent.append(box); box.select(); let ok = false;
      try { ok = document.execCommand('copy'); } catch {} box.remove(); return ok;
    }
  }
  function requestText() { return makeText(items,selection,request,publicBase); }
  async function prepareHandoff() {
    if (!Object.keys(selection).length) return;
    const text = requestText(); $('handoff-text').value = text;
    $('handoff').showModal();
    const copied = await copy(text);
    $('handoff-help').textContent = copied ? '선택 내용이 복사됐어요. ‘이 대화 열기’를 누르고 붙여넣은 뒤 전송해 주세요.' : '자동 복사가 안 됐어요. 아래 내용을 길게 누르거나 전체 선택해 복사한 뒤, 이 대화에 붙여넣어 주세요.';
    $('handoff-title').textContent = copied ? '복사했어요. 이제 채팅으로!' : '선택 내용을 복사해 주세요.';
    if (!copied) { $('handoff-text').focus(); $('handoff-text').select(); }
  }
  function exportSelection() {
    const payload = {type:'dots-design-selection',version:1,archiveVersion:data.version,selection,request,items:selectedItems(items,selection).map(item => ({id:item.id,title:item.title,filename:item.filename,src:item.src || null})),text:requestText()};
    const blob = new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});
    const url = URL.createObjectURL(blob); const a=el('a'); a.href=url; a.download='dots-selection-'+new Date().toISOString().slice(0,10)+'.json'; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
    toast('선택 파일을 저장했어요. 이 채팅에 파일을 첨부해도 돼요.');
  }

  $('photo-total').textContent = `확인한 사진 ${items.length}장`;
  $('archive-scope').textContent = '복구한 128장 + 이전 보관함 33장';
  for (const [id,label] of Object.entries(labels)) {
    const button = el('button','category'); button.dataset.category = id;
    button.append(el('span','',label),el('b','',String(id==='all'?items.length:items.filter(item=>item.category===id).length)));
    button.addEventListener('click',() => { category=id; render(); }); $('categories').append(button);
  }
  const months = [...new Set(items.map(item=>item.date?.slice(0,7)).filter(Boolean))].sort().reverse();
  for (const month of months) { const option=el('option','',month.replace('-','년 ')+'월'); option.value=month; $('month').append(option); }
  const unknown=el('option','','날짜 미확인'); unknown.value='unknown'; $('month').append(unknown);
  $('request').value=request;
  $('request').addEventListener('input',() => { request=$('request').value.slice(0,10000); persist(); });
  $('search').addEventListener('input',render); $('month').addEventListener('change',render); $('sort').addEventListener('change',render);
  $('selected-only').addEventListener('click',() => { onlySelected=!onlySelected; $('selected-only').setAttribute('aria-pressed',String(onlySelected)); render(); });
  $('reset-filters').addEventListener('click',() => { category='all';onlySelected=false; $('selected-only').setAttribute('aria-pressed','false'); $('search').value=''; $('month').value='all';render(); });
  $('gallery').addEventListener('click',event => { const button=event.target.closest('[data-open]'); if(button)openPhoto(button.dataset.open); });
  $('gallery').addEventListener('change',event => { if(event.target.dataset.select)toggle(event.target.dataset.select,event.target.checked); });
  $('clear-selection').addEventListener('click',() => { if(!Object.keys(selection).length)return; if(!confirm('선택한 시안과 시안별 메모를 비울까요? 전체 요청 내용은 남겨둡니다.'))return; selection=Object.create(null);persist();render();renderSelection(); });
  $('lightbox-close').addEventListener('click',() => $('lightbox').close());
  $('lightbox-prev').addEventListener('click',() => movePhoto(-1)); $('lightbox-next').addEventListener('click',() => movePhoto(1));
  $('lightbox-check').addEventListener('change',event => toggle(currentId,event.target.checked));
  $('lightbox').addEventListener('keydown',event => { if(event.key==='ArrowLeft')movePhoto(-1); if(event.key==='ArrowRight')movePhoto(1); });
  $('send-chatgpt').addEventListener('click',prepareHandoff);
  $('handoff-close').addEventListener('click',() => $('handoff').close());
  $('handoff-copy').addEventListener('click',async () => { if(await copy($('handoff-text').value))toast('다시 복사했어요. 채팅에 붙여넣어 주세요.'); else {$('handoff-text').focus();$('handoff-text').select();} });
  $('copy-request').addEventListener('click',async () => { if(await copy(requestText()))toast('선택한 시안과 요청 내용을 복사했어요.'); else prepareHandoff(); });
  $('save-selection').addEventListener('click',exportSelection);
  $('save-top').addEventListener('click',exportSelection);
  $('import-open').addEventListener('click',() => $('import-file').click());
  $('import-file').addEventListener('change',async event => {
    const file=event.target.files?.[0]; if(!file)return;
    try {
      if(file.size>2*1024*1024)throw new Error('size'); const value=JSON.parse(await file.text());
      if(value.type!=='dots-design-selection' || value.version!==1)throw new Error('format');
      const imported=sanitizeSelection(value.selection,items);
      if(!Object.keys(imported).length)throw new Error('empty');
      for(const [id,entry] of Object.entries(imported))selection[id]=entry;
      if(typeof value.request==='string')request=value.request.slice(0,10000);
      $('request').value=request;persist();render();renderSelection();toast('저장한 선택을 불러왔어요.');
    }catch{toast('닷츠에서 저장한 선택 JSON 파일을 골라 주세요.');}
    event.target.value='';
  });
  $('missing-count').textContent=`${data.missingSets.length}개`;
  for(const item of data.missingSets){const row=el('div');const time=el('time','',item.date);time.dateTime=item.date;row.append(time,el('span','',item.title));$('missing-list').append(row);}
  if(shared)persist(); render();renderSelection();
})();
