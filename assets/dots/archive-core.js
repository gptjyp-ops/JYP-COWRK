(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DotsArchiveCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function sanitizeSelection(value, items) {
    const ids = new Set(items.map(item => item.id));
    const out = Object.create(null);
    if (!value || typeof value !== 'object' || Array.isArray(value)) return out;
    for (const [id, data] of Object.entries(value)) {
      if (ids.has(id)) out[id] = {note: typeof data?.note === 'string' ? data.note.slice(0, 5000) : ''};
    }
    return out;
  }
  function selectedItems(items, selection) { return items.filter(item => Object.hasOwn(selection, item.id)); }
  function makeText(items, selection, request, base) {
    const chosen = selectedItems(items, selection);
    const url = new URL('dots.html', base);
    url.searchParams.set('pick', chosen.map(item => item.id).join(','));
    const lines = ['닷츠 디자인 선택 요청', '', '내가 직접 선택한 기존 시안이야. 아래 시안과 메모를 기준으로 반영해줘.', ''];
    for (const item of chosen) {
      lines.push(`${item.id}${item.number ? ` (PDF ${item.number}번)` : ''} · ${item.title}${item.date ? ` · ${item.date}` : ''}`);
      if (selection[item.id].note.trim()) lines.push('반영할 부분: ' + selection[item.id].note.trim());
      if (item.src) lines.push('사진: ' + new URL(item.src, base).href);
      lines.push('');
    }
    lines.push('선택 목록: ' + url.href);
    lines.push('사진 목록: ' + new URL('assets/dots/archive-manifest.json', base).href);
    if (request.trim()) lines.push('', '전체 요청: ' + request.trim());
    lines.push('', '선택하지 않은 시안은 임의로 확정하거나 반영하지 말아줘.');
    return lines.join('\n');
  }
  return {sanitizeSelection, selectedItems, makeText};
});
