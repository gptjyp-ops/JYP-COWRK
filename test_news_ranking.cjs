const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const nodes={};
function node(id){return nodes[id]??={value:'',innerHTML:'',textContent:'',querySelectorAll:()=>[]};}
const script=fs.readFileSync('stock-miner.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1].split("if('serviceWorker'in navigator)")[0];
const context={document:{getElementById:node},Date,URL,console};vm.createContext(context);vm.runInContext(script,context);
node('newsScope').value='watch';node('newsWindow').value='24';node('newsSort').value='latest';
vm.runInContext(`
const testNow=Date.parse('2026-10-06T04:00:00Z');
fixedWatch=[{code:'A',name:'A'},{code:'B',name:'B'}];
rows=[{code:'A',name:'A',foreign5:10,inst5:20,collected_at:'2026-10-06T03:50:00Z',investor_dates:['20261006','20261005','20261002','20261001','20260930']},{code:'B',name:'B',foreign5:100,inst5:200,collected_at:'2026-10-06T00:00:00Z',investor_dates:['20261006','20261005','20261002','20261001','20260930']}];
newsMeta={stocks:{A:{news:[{title:'A 계약',published:'2026-10-06T03:30:00Z'},{title:'A 계약 - 뉴스',published:'2026-10-06T03:20:00Z'},{title:'미래 기사',published:'2026-10-07T00:00:00Z'},{title:'시각 없음'}]},B:{news:[{title:'B 계약',published:'2026-10-06T03:45:00Z'}]}}};
`,context);
const run=expr=>JSON.parse(JSON.stringify(vm.runInContext(expr,context)));
assert.deepEqual(run('rankedNews(testNow).map(x=>x.row.code)'),['B','A']);
assert.equal(run('rankedNews(testNow).find(x=>x.row.code==="A").items.length'),1);
node('newsSort').value='combined';assert.deepEqual(run('rankedNews(testNow).map(x=>x.row.code)'),['A','B']);
node('newsSort').value='both';assert.deepEqual(run('rankedNews(testNow).map(x=>x.row.code)'),['A']);
assert.equal(run('flowEvidence(rows[1],testNow).points'),0);
assert.equal(run('flowEvidence({foreign5:null,inst5:null},testNow).has'),false);
assert.equal(run('newsTimestamp("2026-10-06T13:00:00")'),null);
node('q').value='B';assert.equal(run('rankedNews(testNow).length'),0);
node('q').value='';node('newsSort').value='latest';
vm.runInContext("newsMeta={stocks:{}};renderWatchNews()",context);
assert.ok(node('watchNewsPending').innerHTML.includes('A'));
assert.ok(node('watchNewsPending').innerHTML.includes('미수집'));
console.log('Ranking, duplicate/future/missing timestamps, stale/missing flows, filter and no-news watch cards passed');

vm.runInContext("flowMeta={stocks:{C:{code:'C',name:'C',foreign5:10,inst5:-2,investor_dates:['20261002'],collected_at:'2026-10-06T03:55:00Z'},A:{code:'A',foreign5:999,inst5:999,investor_dates:['20261002'],collected_at:'2026-10-06T03:55:00Z'}}}",context);
assert.equal(run("watchMarketRow({code:'C',name:'C'}).foreign5"),10);
assert.equal(run("watchMarketRow({code:'A',name:'A'}).foreign5"),10);
assert.equal(run("flowEvidence(watchMarketRow({code:'C'}),testNow).fresh"),false);
assert.equal(run("flowEvidence({...rows[0],flow_status:'error'},testNow).fresh"),false);
