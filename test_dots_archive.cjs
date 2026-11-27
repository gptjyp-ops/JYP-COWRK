const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const core = require('./assets/dots/archive-core.js');
const manifest = require('./assets/dots/archive-manifest.json');

test('every catalog image remains addressable and PDF IDs stay stable', () => {
  assert.equal(manifest.items.length,161);
  assert.equal(new Set(manifest.items.map(x=>x.id)).size,161);
  assert.equal(manifest.missingSets.length,26);
  for(let i=0;i<128;i++) {
    const item=manifest.items[i];
    assert.equal(item.id,'D'+String(i+1).padStart(3,'0'));
    assert.equal(item.number,i+1);
    assert.ok(fs.statSync(item.src).size>0);
  }
  assert.equal(manifest.items.filter(x=>x.source==='legacy').length,33);
});

test('import only accepts known designs and text notes', () => {
  const incoming=JSON.parse('{"D006":{"note":"글씨만 유지"},"made-up":{"note":"not a design"},"__proto__":{"note":"invalid"},"D008":{"note":123}}');
  const safe=core.sanitizeSelection(incoming,manifest.items);
  assert.deepEqual(Object.keys(safe),['D006','D008']);
  assert.equal(safe.D006.note,'글씨만 유지');
  assert.equal(safe.D008.note,'');
  assert.equal(Object.getPrototypeOf(safe),null);
});

test('handoff carries exact IDs, notes, public images and restorable selection URL', () => {
  const chosen=core.sanitizeSelection({D006:{note:'로고만'},D008:{note:'컵 색감'},A01:{note:'기존 탐색'}},manifest.items);
  const text=core.makeText(manifest.items,chosen,'흰색 봉투로','https://gptjyp-ops.github.io/JYP-COWRK/');
  assert.ok(text.includes('D006 (PDF 6번)'));
  assert.ok(text.includes('반영할 부분: 로고만'));
  assert.ok(text.includes('assets/dots/archive/D008.webp'));
  assert.ok(text.includes('pick=D006%2CD008%2CA01'));
  assert.ok(text.includes('전체 요청: 흰색 봉투로'));
  assert.ok(!text.includes('D007 (PDF'));
});

test('selection export survives JSON round trip without losing notes', () => {
  const saved=JSON.stringify({selection:{D128:{note:'이전 번호 그대로'}},request:'컵에 적용'});
  const read=JSON.parse(saved);
  const restored=core.sanitizeSelection(read.selection,manifest.items);
  assert.equal(restored.D128.note,'이전 번호 그대로');
});
