(()=>{
const canvas=document.getElementById('brain-canvas'); if(!canvas)return;
const status=document.getElementById('viewer-status');
const gl=canvas.getContext('webgl2',{antialias:false,alpha:false,powerPreference:'high-performance',preserveDrawingBuffer:false});
if(!gl){status.textContent='WebGL2 unavailable';return;}

let CENTER=[376352,313268,538304],SCALE=1e-4,BRAIN_DISTANCE=140;
let target=[0,0,0],yaw=-0.55,pitch=0.18,distance=BRAIN_DISTANCE;
const vs=`#version 300 es
in vec3 aPos; uniform mat4 uMVP; uniform float uPointSize; out vec3 vPos;
void main(){vPos=aPos;gl_Position=uMVP*vec4(aPos,1.0);gl_PointSize=uPointSize;}`;
const fs=`#version 300 es
precision highp float; in vec3 vPos; uniform vec4 uColor; uniform int uShaded; out vec4 outColor;
void main(){
  vec3 c=uColor.rgb;
  if(uShaded==1){vec3 n=normalize(cross(dFdx(vPos),dFdy(vPos)));float l=.34+.66*abs(dot(n,normalize(vec3(.42,.72,.55))));c*=l;}
  outColor=vec4(c,uColor.a);
}`;
function shader(t,s){const x=gl.createShader(t);gl.shaderSource(x,s);gl.compileShader(x);if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(x));return x;}
const prog=gl.createProgram();gl.attachShader(prog,shader(gl.VERTEX_SHADER,vs));gl.attachShader(prog,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(prog);if(!gl.getProgramParameter(prog,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(prog));gl.useProgram(prog);
const aPos=gl.getAttribLocation(prog,'aPos'),uMVP=gl.getUniformLocation(prog,'uMVP'),uColor=gl.getUniformLocation(prog,'uColor'),uShaded=gl.getUniformLocation(prog,'uShaded'),uPointSize=gl.getUniformLocation(prog,'uPointSize');
function perspective(fovy,aspect,near,far){const f=1/Math.tan(fovy/2),nf=1/(near-far);return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0]);}
function lookAt(e,c,u){let zx=e[0]-c[0],zy=e[1]-c[1],zz=e[2]-c[2];let zl=Math.hypot(zx,zy,zz)||1;zx/=zl;zy/=zl;zz/=zl;let xx=u[1]*zz-u[2]*zy,xy=u[2]*zx-u[0]*zz,xz=u[0]*zy-u[1]*zx;let xl=Math.hypot(xx,xy,xz)||1;xx/=xl;xy/=xl;xz/=xl;let yx=zy*xz-zz*xy,yy=zz*xx-zx*xz,yz=zx*xy-zy*xx;return new Float32Array([xx,yx,zx,0,xy,yy,zy,0,xz,yz,zz,0,-(xx*e[0]+xy*e[1]+xz*e[2]),-(yx*e[0]+yy*e[1]+yz*e[2]),-(zx*e[0]+zy*e[1]+zz*e[2]),1]);}
function mul(a,b){const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)o[c*4+r]=a[r]*b[c*4]+a[4+r]*b[c*4+1]+a[8+r]*b[c*4+2]+a[12+r]*b[c*4+3];return o;}
function transformedPositions(raw,start,count){const out=new Float32Array(count*3);for(let i=0;i<count;i++){out[i*3]=(raw.getFloat32(start+i*12,true)-CENTER[0])*SCALE;out[i*3+1]=(raw.getFloat32(start+i*12+4,true)-CENTER[1])*SCALE;out[i*3+2]=(raw.getFloat32(start+i*12+8,true)-CENTER[2])*SCALE;}return out;}
function boundsOf(pos){let lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];for(let i=0;i<pos.length;i+=3){for(let k=0;k<3;k++){const v=pos[i+k];if(v<lo[k])lo[k]=v;if(v>hi[k])hi[k]=v;}}return{lo,hi,center:lo.map((x,k)=>(x+hi[k])/2),span:Math.max(...lo.map((x,k)=>hi[k]-x))};}
function makeObject(positions,indices,mode,color,role='region',shade=0){const vao=gl.createVertexArray();gl.bindVertexArray(vao);const vb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vb);gl.bufferData(gl.ARRAY_BUFFER,positions,gl.STATIC_DRAW);gl.enableVertexAttribArray(aPos);gl.vertexAttribPointer(aPos,3,gl.FLOAT,false,0,0);const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);gl.bindVertexArray(null);return{vao,count:indices.length,vertexCount:positions.length/3,mode,color,vb,ib,role,shade,bounds:boundsOf(positions)};}
function dropObject(o){if(!o)return;gl.deleteBuffer(o.vb);gl.deleteBuffer(o.ib);gl.deleteVertexArray(o.vao);}
function grayForRegion(id){let x=(Number(id)*1103515245+12345)>>>0;return .24+(x%8)*.012;}
function parseMesh(buf,id){const v=new DataView(buf),n=v.getUint32(0,true),triBytes=buf.byteLength-4-n*12;if(triBytes<0||triBytes%12)throw new Error('invalid MaleCNS LOD mesh');const pos=transformedPositions(v,4,n),idx=new Uint32Array(buf.slice(4+n*12));const g=grayForRegion(id);return makeObject(pos,idx,gl.TRIANGLES,[g,g,g,1],'region',1);}
function parseSkeleton(buf,color,role){const v=new DataView(buf),n=v.getUint32(0,true),e=v.getUint32(4,true),need=8+n*12+e*8;if(buf.byteLength!==need)throw new Error('invalid MaleCNS skeleton');const pos=transformedPositions(v,8,n),idx=new Uint32Array(buf.slice(8+n*12));return makeObject(pos,idx,gl.LINES,color,role,0);}

let drag=false,last=[0,0],regionsVisible=true,relatedVisible=false,regions=[],skeletons=[];
let geometry=null,currentFinding=null,skeletonGeneration=0,contextLoadedFor=null;
function brainFit(){target=[0,0,0];distance=BRAIN_DISTANCE;yaw=-.55;pitch=.18;requestRender();}
function neuronFit(){const f=skeletons.find(o=>o.role==='focus');if(!f)return;target=[...f.bounds.center];const span=Math.max(3,f.bounds.span);distance=Math.max(8,Math.min(BRAIN_DISTANCE,span*1.8));requestRender();}
function resize(){const cssW=Math.max(1,canvas.clientWidth),cssH=Math.max(1,canvas.clientHeight);const maxPixels=1800000;const pxScale=Math.min(devicePixelRatio||1,1.35,Math.sqrt(maxPixels/(cssW*cssH)));const w=Math.max(1,Math.floor(cssW*pxScale)),h=Math.max(1,Math.floor(cssH*pxScale));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}}
function mvp(){const eye=[target[0]+distance*Math.cos(pitch)*Math.sin(yaw),target[1]+distance*Math.sin(pitch),target[2]+distance*Math.cos(pitch)*Math.cos(yaw)];return mul(perspective(Math.PI/4,canvas.width/canvas.height,.1,2000),lookAt(eye,target,[0,1,0]));}
let renderQueued=false;function requestRender(){if(renderQueued)return;renderQueued=true;requestAnimationFrame(draw);}
function draw(){renderQueued=false;resize();gl.clearColor(.025,.025,.025,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(prog);gl.uniformMatrix4fv(uMVP,false,mvp());gl.disable(gl.BLEND);
  if(regionsVisible){gl.enable(gl.DEPTH_TEST);gl.depthMask(true);gl.uniform1f(uPointSize,1);for(const o of regions){gl.bindVertexArray(o.vao);gl.uniform4fv(uColor,o.color);gl.uniform1i(uShaded,o.shade);gl.drawElements(o.mode,o.count,gl.UNSIGNED_INT,0);}}
  gl.disable(gl.DEPTH_TEST);gl.uniform1i(uShaded,0);for(const o of skeletons){if(o.role==='related'&&!relatedVisible)continue;gl.bindVertexArray(o.vao);gl.uniform4fv(uColor,o.color);gl.uniform1f(uPointSize,o.role==='focus'?2.4:1.2);gl.drawElements(o.mode,o.count,gl.UNSIGNED_INT,0);if(o.role==='focus')gl.drawArrays(gl.POINTS,0,o.vertexCount);}
}
requestRender();

canvas.addEventListener('pointerdown',e=>{drag=true;last=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId)});canvas.addEventListener('pointerup',()=>drag=false);canvas.addEventListener('pointercancel',()=>drag=false);canvas.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-last[0],dy=e.clientY-last[1];last=[e.clientX,e.clientY];yaw-=dx*.006;pitch=Math.max(-1.45,Math.min(1.45,pitch-dy*.006));requestRender();});canvas.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(3,Math.min(500,distance*Math.exp(e.deltaY*.001)));requestRender();},{passive:false});
const brainBtn=document.getElementById('fit-brain'),neuronBtn=document.getElementById('fit-neuron'),regionBtn=document.getElementById('toggle-regions'),relatedBtn=document.getElementById('toggle-related');
if(brainBtn)brainBtn.onclick=brainFit;
if(neuronBtn)neuronBtn.onclick=neuronFit;
if(regionBtn)regionBtn.onclick=e=>{regionsVisible=!regionsVisible;e.currentTarget.textContent=`regions: ${regionsVisible?'on':'off'}`;requestRender();};
if(relatedBtn)relatedBtn.onclick=async e=>{relatedVisible=!relatedVisible;e.currentTarget.textContent=`context: ${relatedVisible?'on':'off'}`;if(relatedVisible&&currentFinding)await loadRelatedSkeletons(currentFinding);requestRender();};

const yieldFrame=()=>new Promise(resolve=>setTimeout(resolve,0));
async function fetchBuffer(url){const r=await fetch(url);if(!r.ok)throw new Error(`${r.status}`);return r.arrayBuffer();}
async function loadRegions(){
  try{const r=await fetch('data/geometry.json');if(!r.ok)throw new Error(`${r.status}`);geometry=await r.json();}catch(e){status.textContent='geometry manifest missing; run the real MaleCNS workflow';return;}
  if(Array.isArray(geometry.display_center)&&geometry.display_center.length===3)CENTER=geometry.display_center.map(Number);
  if(Number.isFinite(Number(geometry.display_scale)))SCALE=Number(geometry.display_scale);
  if(geometry.bounds){const lo=geometry.bounds[0],hi=geometry.bounds[1];const dx=(hi[0]-lo[0])*SCALE,dy=(hi[1]-lo[1])*SCALE,dz=(hi[2]-lo[2])*SCALE;const radius=.5*Math.hypot(dx,dy,dz);BRAIN_DISTANCE=Math.max(18,radius/Math.tan(Math.PI/8)*1.08);distance=BRAIN_DISTANCE;}
  if(currentFinding)await loadFocusSkeleton(currentFinding);
  const lod=geometry.region_lod||{};status.textContent=`loading low-detail MaleCNS context · ${Number(lod.display_triangles_total||0).toLocaleString()} triangles`;
  let done=0,cursor=0;const workers=Array.from({length:2},async()=>{while(cursor<geometry.regions.length){const rec=geometry.regions[cursor++];try{const buf=await fetchBuffer(rec.local_url||rec.source_url);regions.push(parseMesh(buf,rec.source_id));}catch(err){console.warn('region',rec.label,err);}done++;if(done%2===0||done===geometry.regions.length){status.textContent=`brain context ${done}/${geometry.regions.length} · focus ${currentFinding?.focus_node||'—'}`;requestRender();await yieldFrame();}}});await Promise.all(workers);status.textContent=`MaleCNS LOD context ready · ${regions.length} regions · focus ${currentFinding?.focus_node||'—'}`;requestRender();
}
function skeletonIds(f){return [Number(f.focus_node),...(f.related_nodes||[]).map(Number)].filter((x,i,a)=>Number.isFinite(x)&&a.indexOf(x)===i);}
function skeletonUrl(id){const vendored=new Set((geometry?.vendored_skeleton_ids||[]).map(Number));const template=vendored.has(id)&&geometry?.local_skeleton_url_template?geometry.local_skeleton_url_template:geometry?.source_skeleton_url_template;return template?.replace('{body_id}',String(id));}
async function loadFocusSkeleton(f){
  currentFinding=f;if(!geometry)return;const gen=++skeletonGeneration;contextLoadedFor=null;for(const o of skeletons)dropObject(o);skeletons=[];relatedVisible=false;if(relatedBtn)relatedBtn.textContent='context: off';
  const id=Number(f.focus_node),url=skeletonUrl(id);if(!url)return;status.textContent=`loading focus neuron ${id}…`;
  try{const obj=parseSkeleton(await fetchBuffer(url),[1,1,1,1],'focus');if(gen!==skeletonGeneration){dropObject(obj);return;}skeletons.push(obj);status.textContent=`focus ${id} loaded · context off`;neuronFit();}catch(e){console.warn('focus skeleton',id,e);if(gen===skeletonGeneration)status.textContent=`focus skeleton ${id} unavailable`;}
}
async function loadRelatedSkeletons(f){
  if(!geometry||contextLoadedFor===f.id)return;contextLoadedFor=f.id;const gen=skeletonGeneration;const ids=skeletonIds(f).slice(1,9);let loaded=0;for(const id of ids){if(gen!==skeletonGeneration||!relatedVisible)return;try{const url=skeletonUrl(id);if(!url)continue;const obj=parseSkeleton(await fetchBuffer(url),[.62,.62,.62,1],'related');if(gen!==skeletonGeneration){dropObject(obj);return;}skeletons.push(obj);loaded++;status.textContent=`focus ${f.focus_node} · context ${loaded}/${ids.length}`;requestRender();await yieldFrame();}catch(e){console.warn('context skeleton',id,e);}}if(gen===skeletonGeneration)status.textContent=`focus ${f.focus_node} · context ${loaded}/${ids.length} loaded`;}
window.addEventListener('dsc:finding',async e=>{currentFinding=e.detail;if(geometry)await loadFocusSkeleton(currentFinding);});
loadRegions().catch(e=>{console.error(e);status.textContent=`3D load failed: ${e.message}`;});
})();
