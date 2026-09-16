(()=>{
const canvas=document.getElementById('brain-canvas'); if(!canvas)return;
const status=document.getElementById('viewer-status');
const gl=canvas.getContext('webgl2',{antialias:false,alpha:false,powerPreference:'high-performance',preserveDrawingBuffer:false});
if(!gl){status.textContent='WebGL2 unavailable';return;}

let CENTER=[376352,313268,538304],SCALE=1e-4,BRAIN_DISTANCE=140;
let target=[0,0,0],yaw=0,pitch=0.06,distance=BRAIN_DISTANCE;
let brainOpacity=.07,contextOpacity=.55,clipFraction=0,brainVisible=true,relatedVisible=false,synapsesVisible=true;
let brain=null,regions=[],skeletons=[],synapseObjects=[],geometry=null,synapseData=null,currentFinding=null,skeletonGeneration=0,contextLoadedFor=null;

const vs=`#version 300 es
in vec3 aPos; uniform mat4 uMVP; uniform float uPointSize; out vec3 vPos;
void main(){vPos=aPos;gl_Position=uMVP*vec4(aPos,1.0);gl_PointSize=uPointSize;}`;
const fs=`#version 300 es
precision highp float; in vec3 vPos; uniform vec4 uColor; uniform int uShaded; uniform int uPointMode; uniform int uClipEnabled; uniform float uClipPlane; out vec4 outColor;
void main(){
  if(uClipEnabled==1 && vPos.z>uClipPlane) discard;
  if(uPointMode==1){vec2 q=gl_PointCoord*2.0-1.0;if(dot(q,q)>1.0)discard;}
  vec3 c=uColor.rgb;
  if(uShaded==1){vec3 n=normalize(cross(dFdx(vPos),dFdy(vPos)));float l=.22+.78*abs(dot(n,normalize(vec3(.35,.72,.58))));c*=l;}
  outColor=vec4(c,uColor.a);
}`;
function shader(t,s){const x=gl.createShader(t);gl.shaderSource(x,s);gl.compileShader(x);if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(x));return x;}
const prog=gl.createProgram();gl.attachShader(prog,shader(gl.VERTEX_SHADER,vs));gl.attachShader(prog,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(prog);if(!gl.getProgramParameter(prog,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(prog));gl.useProgram(prog);
const aPos=gl.getAttribLocation(prog,'aPos'),uMVP=gl.getUniformLocation(prog,'uMVP'),uColor=gl.getUniformLocation(prog,'uColor'),uShaded=gl.getUniformLocation(prog,'uShaded'),uPointSize=gl.getUniformLocation(prog,'uPointSize'),uPointMode=gl.getUniformLocation(prog,'uPointMode'),uClipEnabled=gl.getUniformLocation(prog,'uClipEnabled'),uClipPlane=gl.getUniformLocation(prog,'uClipPlane');

function perspective(fovy,aspect,near,far){const f=1/Math.tan(fovy/2),nf=1/(near-far);return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0]);}
function lookAt(e,c,u){let zx=e[0]-c[0],zy=e[1]-c[1],zz=e[2]-c[2];let zl=Math.hypot(zx,zy,zz)||1;zx/=zl;zy/=zl;zz/=zl;let xx=u[1]*zz-u[2]*zy,xy=u[2]*zx-u[0]*zz,xz=u[0]*zy-u[1]*zx;let xl=Math.hypot(xx,xy,xz)||1;xx/=xl;xy/=xl;xz/=xl;let yx=zy*xz-zz*xy,yy=zz*xx-zx*xz,yz=zx*xy-zy*xx;return new Float32Array([xx,yx,zx,0,xy,yy,zy,0,xz,yz,zz,0,-(xx*e[0]+xy*e[1]+xz*e[2]),-(yx*e[0]+yy*e[1]+yz*e[2]),-(zx*e[0]+zy*e[1]+zz*e[2]),1]);}
function mul(a,b){const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)o[c*4+r]=a[r]*b[c*4]+a[4+r]*b[c*4+1]+a[8+r]*b[c*4+2]+a[12+r]*b[c*4+3];return o;}
function vsub(a,b){return[a[0]-b[0],a[1]-b[1],a[2]-b[2]];}function vlen(a){return Math.hypot(a[0],a[1],a[2])||1;}function vnorm(a){const l=vlen(a);return a.map(x=>x/l);}function vcross(a,b){return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}
function canonical(x,y,z){const ex=(x-CENTER[0])*SCALE,ey=(y-CENTER[1])*SCALE,ez=(z-CENTER[2])*SCALE;return[-ex,-ez,ey];}
function transformedPositions(raw,start,count,mult=1){const out=new Float32Array(count*3);for(let i=0;i<count;i++){const p=canonical(raw.getFloat32(start+i*12,true)*mult,raw.getFloat32(start+i*12+4,true)*mult,raw.getFloat32(start+i*12+8,true)*mult);out.set(p,i*3);}return out;}
function transformedTriples(points,mult=1){const out=new Float32Array(points.length*3);for(let i=0;i<points.length;i++){const p=canonical(points[i][0]*mult,points[i][1]*mult,points[i][2]*mult);out.set(p,i*3);}return out;}
function boundsOf(pos){let lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];for(let i=0;i<pos.length;i+=3){for(let k=0;k<3;k++){const v=pos[i+k];if(v<lo[k])lo[k]=v;if(v>hi[k])hi[k]=v;}}return{lo,hi,center:lo.map((x,k)=>(x+hi[k])/2),span:Math.max(...lo.map((x,k)=>hi[k]-x))};}
function makeObject(positions,indices,mode,role='region',shade=0){const vao=gl.createVertexArray();gl.bindVertexArray(vao);const vb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vb);gl.bufferData(gl.ARRAY_BUFFER,positions,gl.STATIC_DRAW);gl.enableVertexAttribArray(aPos);gl.vertexAttribPointer(aPos,3,gl.FLOAT,false,0,0);const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);gl.bindVertexArray(null);return{vao,count:indices.length,vertexCount:positions.length/3,mode,vb,ib,role,shade,bounds:boundsOf(positions)};}
function dropObject(o){if(!o)return;gl.deleteBuffer(o.vb);gl.deleteBuffer(o.ib);gl.deleteVertexArray(o.vao);}
function parseMesh(buf){const v=new DataView(buf),n=v.getUint32(0,true),triBytes=buf.byteLength-4-n*12;if(triBytes<0||triBytes%12)throw new Error('invalid MaleCNS mesh');const pos=transformedPositions(v,4,n),idx=new Uint32Array(buf.slice(4+n*12));return makeObject(pos,idx,gl.TRIANGLES,'brain',1);}
function parseSkeleton(buf,role){const v=new DataView(buf),n=v.getUint32(0,true),e=v.getUint32(4,true),need=8+n*12+e*8;if(buf.byteLength!==need)throw new Error('invalid MaleCNS skeleton');const pos=transformedPositions(v,8,n),idx=new Uint32Array(buf.slice(8+n*12));return makeObject(pos,idx,gl.LINES,role,0);}
function pointObject(points,role,mult=1){const pos=transformedTriples(points,mult),idx=new Uint32Array(points.length);for(let i=0;i<idx.length;i++)idx[i]=i;return makeObject(pos,idx,gl.POINTS,role,0);}

function eyePosition(){return[target[0]+distance*Math.cos(pitch)*Math.sin(yaw),target[1]+distance*Math.sin(pitch),target[2]+distance*Math.cos(pitch)*Math.cos(yaw)];}
function resize(){const cssW=Math.max(1,canvas.clientWidth),cssH=Math.max(1,canvas.clientHeight);const maxPixels=1800000;const pxScale=Math.min(devicePixelRatio||1,1.35,Math.sqrt(maxPixels/(cssW*cssH)));const w=Math.max(1,Math.floor(cssW*pxScale)),h=Math.max(1,Math.floor(cssH*pxScale));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}}
function mvp(){return mul(perspective(Math.PI/4,canvas.width/canvas.height,.1,2200),lookAt(eyePosition(),target,[0,1,0]));}
let renderQueued=false;function requestRender(){if(renderQueued)return;renderQueued=true;requestAnimationFrame(draw);}
function brainClipPlane(){if(!brain||clipFraction<=0)return 1e9;const lo=brain.bounds.lo[2],hi=brain.bounds.hi[2];return hi-(hi-lo)*clipFraction;}
function drawObject(o,color,pointSize=1,clip=false){gl.bindVertexArray(o.vao);gl.uniform4fv(uColor,color);gl.uniform1i(uShaded,o.shade);gl.uniform1f(uPointSize,pointSize);gl.uniform1i(uPointMode,o.mode===gl.POINTS?1:0);gl.uniform1i(uClipEnabled,clip&&clipFraction>0?1:0);gl.uniform1f(uClipPlane,brainClipPlane());gl.drawElements(o.mode,o.count,gl.UNSIGNED_INT,0);}
function draw(){renderQueued=false;resize();gl.clearColor(.018,.018,.018,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(prog);gl.uniformMatrix4fv(uMVP,false,mvp());
  if(brainVisible){gl.enable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);if(brain)drawObject(brain,[.55,.57,.60,brainOpacity],1,true);for(const o of regions)drawObject(o,[.50,.52,.55,Math.min(.09,brainOpacity)],1,true);gl.depthMask(true);}
  gl.disable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
  for(const o of skeletons){if(o.role==='related'&&!relatedVisible)continue;const focus=o.role==='focus';drawObject(o,focus?[1,1,1,1]:[.72,.72,.72,contextOpacity],focus?2.7:1.2,false);if(focus){gl.uniform1f(uPointSize,2.6);gl.uniform1i(uPointMode,1);gl.drawArrays(gl.POINTS,0,o.vertexCount);}}
  if(synapsesVisible){for(const o of synapseObjects){const pre=o.role==='synapse-pre';drawObject(o,pre?[.72,.72,.72,.85]:[1,1,1,.98],pre?4.2:5.2,false);}}
}
requestRender();

function brainFit(){const b=brain?.bounds||regions[0]?.bounds;if(b){target=[...b.center];const span=Math.max(8,b.span);distance=Math.max(18,span/Math.tan(Math.PI/8)*.78);}else{target=[0,0,0];distance=BRAIN_DISTANCE;}yaw=0;pitch=.06;requestRender();}
function neuronFit(){const f=skeletons.find(o=>o.role==='focus');if(!f)return;target=[...f.bounds.center];const span=Math.max(2.5,f.bounds.span);distance=Math.max(6,Math.min(BRAIN_DISTANCE,span*1.8));requestRender();}
function setPreset(name){if(name==='anterior'){yaw=0;pitch=0;}else if(name==='posterior'){yaw=Math.PI;pitch=0;}else if(name==='dorsal'){yaw=0;pitch=1.45;}else if(name==='ventral'){yaw=0;pitch=-1.45;}else if(name==='left'){yaw=-Math.PI/2;pitch=0;}else if(name==='right'){yaw=Math.PI/2;pitch=0;}requestRender();}
function cameraState(){return[yaw,pitch,distance,...target].map(v=>Number(v).toFixed(4)).join(',');}
function restoreCameraFromURL(){const s=new URLSearchParams(location.search).get('cam');if(!s)return false;const a=s.split(',').map(Number);if(a.length!==6||a.some(x=>!Number.isFinite(x)))return false;[yaw,pitch,distance,target[0],target[1],target[2]]=a;return true;}
async function copyView(){const u=new URL(location.href);u.searchParams.set('cam',cameraState());if(currentFinding?.id)u.searchParams.set('finding',currentFinding.id);try{await navigator.clipboard.writeText(u.toString());status.textContent='view URL copied';}catch{history.replaceState(null,'',u);status.textContent='view stored in address bar';}}

let dragMode=null,last=[0,0],pointerId=null;
canvas.addEventListener('contextmenu',e=>e.preventDefault());
canvas.addEventListener('pointerdown',e=>{pointerId=e.pointerId;last=[e.clientX,e.clientY];dragMode=(e.shiftKey||e.button===1||e.button===2)?'pan':'orbit';canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointerup',e=>{if(e.pointerId===pointerId){dragMode=null;pointerId=null;}});canvas.addEventListener('pointercancel',()=>{dragMode=null;pointerId=null;});
canvas.addEventListener('pointermove',e=>{if(!dragMode||e.pointerId!==pointerId)return;const dx=e.clientX-last[0],dy=e.clientY-last[1];last=[e.clientX,e.clientY];if(dragMode==='orbit'){yaw+=dx*.006;pitch=Math.max(-1.50,Math.min(1.50,pitch+dy*.006));}else{const eye=eyePosition(),forward=vnorm(vsub(target,eye)),right=vnorm(vcross(forward,[0,1,0])),up=vnorm(vcross(right,forward)),s=distance*.0015;for(let k=0;k<3;k++)target[k]+=(-dx*right[k]+dy*up[k])*s;}requestRender();});
canvas.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(2,Math.min(800,distance*Math.exp(e.deltaY*.001)));requestRender();},{passive:false});
canvas.addEventListener('dblclick',()=>neuronFit());window.addEventListener('resize',requestRender);

const brainBtn=document.getElementById('fit-brain'),neuronBtn=document.getElementById('fit-neuron'),regionBtn=document.getElementById('toggle-regions'),relatedBtn=document.getElementById('toggle-related'),synBtn=document.getElementById('toggle-synapses'),copyBtn=document.getElementById('copy-view');
if(brainBtn)brainBtn.onclick=brainFit;if(neuronBtn)neuronBtn.onclick=neuronFit;if(copyBtn)copyBtn.onclick=copyView;
if(regionBtn)regionBtn.onclick=e=>{brainVisible=!brainVisible;e.currentTarget.textContent=`brain: ${brainVisible?'on':'off'}`;requestRender();};
if(relatedBtn)relatedBtn.onclick=async e=>{relatedVisible=!relatedVisible;e.currentTarget.textContent=`context: ${relatedVisible?'on':'off'}`;if(relatedVisible&&currentFinding)await loadRelatedSkeletons(currentFinding);requestRender();};
if(synBtn)synBtn.onclick=e=>{synapsesVisible=!synapsesVisible;e.currentTarget.textContent=`synapses: ${synapsesVisible?'on':'off'}`;requestRender();};
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>setPreset(b.dataset.view)));
function bindRange(id,valueId,handler,format){const el=document.getElementById(id),out=document.getElementById(valueId);if(!el)return;const apply=()=>{handler(Number(el.value));if(out)out.textContent=format(Number(el.value));requestRender();};el.addEventListener('input',apply);apply();}
bindRange('brain-opacity','brain-opacity-value',v=>brainOpacity=v/100,v=>`${v}%`);bindRange('context-opacity','context-opacity-value',v=>contextOpacity=v/100,v=>`${v}%`);bindRange('clip-depth','clip-depth-value',v=>clipFraction=v/100,v=>v===0?'off':`${v}%`);

const yieldFrame=()=>new Promise(resolve=>setTimeout(resolve,0));async function fetchBuffer(url){const r=await fetch(url);if(!r.ok)throw new Error(`${r.status}`);return r.arrayBuffer();}
function skeletonIds(f){return [Number(f.focus_node),...(f.related_nodes||[]).map(Number)].filter((x,i,a)=>Number.isFinite(x)&&a.indexOf(x)===i);}
function skeletonUrl(id){const vendored=new Set((geometry?.vendored_skeleton_ids||[]).map(Number));const template=vendored.has(id)&&geometry?.local_skeleton_url_template?geometry.local_skeleton_url_template:geometry?.source_skeleton_url_template;return template?.replace('{body_id}',String(id));}
async function loadBrain(){
  try{const r=await fetch('data/geometry.json');if(!r.ok)throw new Error(`${r.status}`);geometry=await r.json();}catch(e){status.textContent='geometry manifest missing; run the real MaleCNS workflow';return;}
  if(Array.isArray(geometry.display_center)&&geometry.display_center.length===3)CENTER=geometry.display_center.map(Number);if(Number.isFinite(Number(geometry.display_scale)))SCALE=Number(geometry.display_scale);
  if(currentFinding)await loadFocusSkeleton(currentFinding);
  if(geometry.geometry_mode==='major-shell'&&geometry.brain_shell?.local_url){status.textContent='loading official MaleCNS major shell…';try{brain=parseMesh(await fetchBuffer(geometry.brain_shell.local_url));const span=brain.bounds.span;BRAIN_DISTANCE=Math.max(18,span/Math.tan(Math.PI/8)*.78);if(!restoreCameraFromURL())brainFit();status.textContent=`MaleCNS major shell ready · ${Number(geometry.brain_shell.display_triangles||0).toLocaleString()} triangles`;requestRender();return;}catch(e){console.warn('major shell',e);}}
  const recs=geometry.regions||[];status.textContent=`loading MaleCNS ROI fallback · ${recs.length} regions`;let cursor=0,done=0;const workers=Array.from({length:2},async()=>{while(cursor<recs.length){const rec=recs[cursor++];try{regions.push(parseMesh(await fetchBuffer(rec.local_url||rec.source_url)));}catch(e){console.warn('region',rec.label,e);}done++;if(done%3===0||done===recs.length){status.textContent=`ROI fallback ${done}/${recs.length}`;requestRender();await yieldFrame();}}});await Promise.all(workers);if(regions.length){const all=regions.map(x=>x.bounds);const lo=[0,1,2].map(k=>Math.min(...all.map(b=>b.lo[k]))),hi=[0,1,2].map(k=>Math.max(...all.map(b=>b.hi[k])));const pos=new Float32Array([...lo,...hi]);const b=boundsOf(pos);BRAIN_DISTANCE=Math.max(18,b.span/Math.tan(Math.PI/8));if(!restoreCameraFromURL()){target=b.center;distance=BRAIN_DISTANCE;}}status.textContent=`MaleCNS ROI fallback ready · ${regions.length} regions`;requestRender();
}
async function loadFocusSkeleton(f){currentFinding=f;if(!geometry)return;const gen=++skeletonGeneration;contextLoadedFor=null;for(const o of skeletons)dropObject(o);for(const o of synapseObjects)dropObject(o);skeletons=[];synapseObjects=[];relatedVisible=false;if(relatedBtn)relatedBtn.textContent='context: off';const id=Number(f.focus_node),url=skeletonUrl(id);if(!url)return;status.textContent=`loading focus neuron ${id}…`;try{const obj=parseSkeleton(await fetchBuffer(url),'focus');if(gen!==skeletonGeneration){dropObject(obj);return;}skeletons.push(obj);loadSynapsesForFinding(f);status.textContent=`focus ${id} loaded`;if(!new URLSearchParams(location.search).has('cam'))neuronFit();}catch(e){console.warn('focus skeleton',id,e);if(gen===skeletonGeneration)status.textContent=`focus skeleton ${id} unavailable`;}}
async function loadRelatedSkeletons(f){if(!geometry||contextLoadedFor===f.id)return;contextLoadedFor=f.id;const gen=skeletonGeneration;const ids=skeletonIds(f).slice(1,9);let loaded=0;for(const id of ids){if(gen!==skeletonGeneration||!relatedVisible)return;try{const url=skeletonUrl(id);if(!url)continue;const obj=parseSkeleton(await fetchBuffer(url),'related');if(gen!==skeletonGeneration){dropObject(obj);return;}skeletons.push(obj);loaded++;status.textContent=`focus ${f.focus_node} · context ${loaded}/${ids.length}`;requestRender();await yieldFrame();}catch(e){console.warn('context skeleton',id,e);}}}
async function loadSynapseManifest(){try{const r=await fetch('data/synapses.json');if(r.ok)synapseData=await r.json();}catch(e){console.warn('synapses manifest',e);}}
function loadSynapsesForFinding(f){for(const o of synapseObjects)dropObject(o);synapseObjects=[];const rec=synapseData?.findings?.[f.id];if(!rec||rec.status!=='ok'||!Array.isArray(rec.points)||!rec.points.length){requestRender();return;}const scale=Number(synapseData.coordinate_scale_to_nm||8);const pre=rec.points.map(p=>p.pre_xyz).filter(Boolean),post=rec.points.map(p=>p.post_xyz).filter(Boolean);if(pre.length)synapseObjects.push(pointObject(pre,'synapse-pre',scale));if(post.length)synapseObjects.push(pointObject(post,'synapse-post',scale));requestRender();}
window.addEventListener('dsc:finding',async e=>{currentFinding=e.detail;if(geometry)await loadFocusSkeleton(currentFinding);else requestRender();});
Promise.all([loadSynapseManifest(),loadBrain()]).then(()=>{if(currentFinding)loadSynapsesForFinding(currentFinding);}).catch(e=>{console.error(e);status.textContent=`3D load failed: ${e.message}`;});
})();
