const getJSON = async p => { const r = await fetch(p); if (!r.ok) throw new Error(`${p}: ${r.status}`); return r.json(); };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const page = document.body.dataset.page;

function fmt(v){
  if(v===null || v===undefined) return '—';
  if(typeof v==='number') return Number.isInteger(v) ? v.toLocaleString() : (Math.abs(v)<0.001 && v!==0 ? v.toExponential(2) : v.toFixed(3).replace(/0+$/,'').replace(/\.$/,''));
  return String(v);
}
function findingRows(findings){
  return `<table><thead><tr><th>rank</th><th>method score</th><th>method</th><th>candidate</th><th>focus</th><th></th></tr></thead><tbody>${findings.map(f=>`<tr data-kind="${esc(f.kind)}" data-search="${esc((f.title+' '+f.summary+' '+f.focus_node).toLowerCase())}"><td>${esc(f.method_rank??'—')}</td><td class="score">${fmt(Number(f.score||0))}</td><td>${esc(f.kind.replaceAll('_',' '))}</td><td>${esc(f.summary)}</td><td>${esc(f.focus_node)}</td><td><a href="network.html?finding=${encodeURIComponent(f.id)}">3d</a></td></tr>`).join('')}</tbody></table>`;
}
async function overview(){
  const [findings, network, run] = await Promise.all([getJSON('data/findings.json'), getJSON('data/network.json'), getJSON('data/run.json')]);
  const core = network.nodes.filter(n=>n.core).length;
  const s = [
    ['dataset',run.dataset],['dopamine core',core],['snapshot nodes',network.nodes.length],['snapshot edges',network.edges.length],['candidates',findings.length]
  ];
  document.querySelector('#summary').innerHTML=s.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(fmt(v))}</dd></div>`).join('');
  document.querySelector('#top-table').innerHTML=findingRows(findings.slice(0,12));
  const m=run.snapshot_meta||{};
  document.querySelector('#method-note').textContent=`peer-aware discovery; convergence null degree scope: ${m.degree_scope||'unknown'}; eligible traced universe: ${fmt(m.eligible_traced_neurons)}.`;
}
async function findingsPage(){
  const findings=await getJSON('data/findings.json');
  const host=document.querySelector('#findings-table'); host.innerHTML=findingRows(findings);
  const apply=()=>{const q=document.querySelector('#finding-search').value.toLowerCase();const k=document.querySelector('#finding-kind').value;host.querySelectorAll('tbody tr').forEach(r=>r.style.display=((!q||r.dataset.search.includes(q))&&(!k||r.dataset.kind===k))?'':'none');};
  document.querySelector('#finding-search').addEventListener('input',apply);document.querySelector('#finding-kind').addEventListener('change',apply);
}
async function networkPage(){
  const findings=await getJSON('data/findings.json'); const select=document.querySelector('#network-finding');
  select.innerHTML=findings.map(f=>`<option value="${esc(f.id)}">${esc(f.kind.replaceAll('_',' '))} · ${esc(f.focus_node)} · score ${fmt(f.score)}</option>`).join('');
  const requested=new URLSearchParams(location.search).get('finding'); if(requested&&findings.some(f=>f.id===requested))select.value=requested;
  const render=()=>{const f=findings.find(x=>x.id===select.value)||findings[0];if(!f)return;document.querySelector('#network-detail').textContent=f.summary+' '+f.interpretation;const rows=[['id',f.id],['score',fmt(f.score)],['focus',f.focus_node],['related shown',(f.related_nodes||[]).length],['status',f.status]];if(f.q_value!==undefined)rows.push(['BH q',fmt(f.q_value)]);if(f.enrichment!==undefined)rows.push(['enrichment',fmt(f.enrichment)+'x']);document.querySelector('#network-kv').innerHTML=rows.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');window.dispatchEvent(new CustomEvent('dsc:finding',{detail:f}));};
  select.addEventListener('change',render); render();
}
async function runsPage(){document.querySelector('#run-manifest').textContent=JSON.stringify(await getJSON('data/run.json'),null,2);}
({overview,findings:findingsPage,network:networkPage,runs:runsPage}[page]||(()=>{}))().catch(err=>{console.error(err);document.body.insertAdjacentHTML('beforeend',`<pre>${esc(err)}</pre>`)});
