const getJSON = async p => { const r = await fetch(p); if(!r.ok) throw new Error(`${p}: ${r.status}`); return r.json(); };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const page = document.body.dataset.page;

function findingCard(f){
  return `<article class="finding" data-kind="${esc(f.kind)}" data-search="${esc((f.title+' '+f.summary+' '+(f.focus_node||'')).toLowerCase())}">
    <div class="meta"><span>${esc(f.kind.replaceAll('_',' '))}</span><span class="score">score ${Number(f.score||0).toFixed(2)}</span></div>
    <h3>${esc(f.title)}</h3><p>${esc(f.summary)}</p>
    <div class="actions"><a href="network.html?finding=${encodeURIComponent(f.id)}">inspect network →</a></div>
  </article>`;
}

async function overview(){
  const [findings, network, run] = await Promise.all([getJSON('data/findings.json'),getJSON('data/network.json'),getJSON('data/run.json')]);
  const core = network.nodes.filter(n=>n.core).length;
  const stats = [
    [core,'dopamine core neurons'],[network.edges.length.toLocaleString(),'local edges'],[findings.length,'candidate findings'],[esc(run.dataset),'dataset']
  ];
  document.querySelector('#stats').innerHTML = stats.map(([v,l])=>`<div class="stat"><strong>${v}</strong><span>${l}</span></div>`).join('');
  document.querySelector('#top-findings').innerHTML = findings.slice(0,6).map(findingCard).join('') || '<p>No candidates above thresholds.</p>';
}

async function findingsPage(){
  const findings = await getJSON('data/findings.json');
  const box = document.querySelector('#all-findings');
  box.innerHTML = findings.map(findingCard).join('');
  const apply = () => {
    const q = document.querySelector('#finding-search').value.toLowerCase();
    const kind = document.querySelector('#finding-kind').value;
    box.querySelectorAll('.finding').forEach(el => el.style.display = ((!q || el.dataset.search.includes(q)) && (!kind || el.dataset.kind===kind)) ? '' : 'none');
  };
  document.querySelector('#finding-search').addEventListener('input', apply);
  document.querySelector('#finding-kind').addEventListener('change', apply);
}

function localGraph(network, finding){
  const focus = Number(finding.focus_node);
  const related = new Set((finding.related_nodes||[]).map(Number));
  related.add(focus);
  const touching = network.edges.filter(e => related.has(Number(e.pre)) || related.has(Number(e.post)));
  touching.sort((a,b)=>b.weight-a.weight);
  const edges = touching.slice(0,90);
  const ids = new Set([focus]);
  edges.forEach(e=>{ids.add(Number(e.pre));ids.add(Number(e.post));});
  (finding.related_nodes||[]).forEach(x=>ids.add(Number(x)));
  const nodes = network.nodes.filter(n=>ids.has(Number(n.id))).slice(0,70);
  const allowed = new Set(nodes.map(n=>Number(n.id)));
  return {nodes,edges:edges.filter(e=>allowed.has(Number(e.pre))&&allowed.has(Number(e.post)))};
}

function drawGraph(svg, graph, focus){
  const W=1000,H=650,cx=W/2,cy=H/2;
  const focusNode=graph.nodes.find(n=>Number(n.id)===Number(focus));
  const others=graph.nodes.filter(n=>Number(n.id)!==Number(focus));
  const pos=new Map(); pos.set(Number(focus),[cx,cy]);
  others.forEach((n,i)=>{const a=(Math.PI*2*i/Math.max(1,others.length))-Math.PI/2; const r=220+(i%3)*45; pos.set(Number(n.id),[cx+Math.cos(a)*r,cy+Math.sin(a)*r]);});
  const maxW=Math.max(1,...graph.edges.map(e=>e.weight));
  const lines=graph.edges.map(e=>{const a=pos.get(Number(e.pre)),b=pos.get(Number(e.post)); if(!a||!b)return''; const sw=0.6+4*Math.sqrt(e.weight/maxW); return `<line class="edge" x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke-width="${sw}"><title>${e.pre} → ${e.post}: ${e.weight}</title></line>`;}).join('');
  const circles=graph.nodes.map(n=>{const p=pos.get(Number(n.id)); const cls=Number(n.id)===Number(focus)?'node-focus':(n.core?'node-core':'node-partner'); const r=Number(n.id)===Number(focus)?12:(n.core?8:5); return `<g><circle class="${cls}" cx="${p[0]}" cy="${p[1]}" r="${r}"><title>${esc(n.type)} (${n.id})</title></circle><text class="node-label" x="${p[0]+10}" y="${p[1]-8}">${esc(n.type)}</text></g>`;}).join('');
  svg.innerHTML=lines+circles;
}

async function networkPage(){
  const [findings, network] = await Promise.all([getJSON('data/findings.json'),getJSON('data/network.json')]);
  const select=document.querySelector('#network-finding');
  select.innerHTML=findings.map(f=>`<option value="${esc(f.id)}">${esc(f.title)} — ${esc(f.focus_node)}</option>`).join('');
  const requested=new URLSearchParams(location.search).get('finding'); if(requested && findings.some(f=>f.id===requested)) select.value=requested;
  const render=()=>{const f=findings.find(x=>x.id===select.value)||findings[0]; if(!f)return; document.querySelector('#network-detail').innerHTML=`<strong>${esc(f.title)}</strong><br><br>${esc(f.summary)}<br><br>${esc(f.interpretation)}`; drawGraph(document.querySelector('#network-svg'),localGraph(network,f),f.focus_node);};
  select.addEventListener('change',render); render();
}

async function runsPage(){document.querySelector('#run-manifest').textContent=JSON.stringify(await getJSON('data/run.json'),null,2);}

({overview,findings:findingsPage,network:networkPage,runs:runsPage}[page]||(()=>{}))().catch(err=>{console.error(err);document.body.insertAdjacentHTML('beforeend',`<pre>${esc(err)}</pre>`)});
