"use strict";
const $ = id => document.getElementById(id);
const canvas = $("field");
const ctx = canvas.getContext("2d", { alpha: false });
const received = new Map();
let stream = null;
let maxSequence = null;
let totalBytes = 0;
let droppedCount = 0;
let elapsedOrigin = 0;
let rttResults = [];
const assert = (condition, message) => { if (!condition) throw new Error(message); };

function decodeFrame(bytes) {
  assert(bytes.byteLength >= 40, "quadro muito curto");
  const d = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  assert(String.fromCharCode(...bytes.slice(0, 4)) === "DPH1", "prefixo inválido");
  assert(d.getUint8(4) === 1 && d.getUint8(6) === 0 && d.getUint8(7) === 0, "versão inválida");
  const kind = d.getUint8(5);
  assert([0, 1, 2].includes(kind) && bytes.byteLength === (kind === 2 ? 44 : 40), "tamanho inválido");
  const scene = d.getUint32(8, true), seq = d.getUint32(12, true), tick = d.getUint32(16, true);
  assert(scene === 0x44524f53 && seq < 64 && tick < 1000000, "cena inválida");
  let data;
  if (kind === 0) {
    data = { width: d.getInt32(20, true), height: d.getInt32(24, true),
             origin: Number(d.getBigUint64(28, true)), tickms: d.getUint32(36, true) };
    assert(data.width > 0 && data.height > 0 && data.tickms > 0, "epoch inválido");
  } else if (kind === 1) {
    data = { photon: d.getUint32(20, true), x: d.getInt32(24, true), y: d.getInt32(28, true),
             dx: d.getInt32(32, true), dy: d.getInt32(36, true) };
  } else {
    data = { photon: d.getUint32(20, true), obj: d.getUint32(24, true),
             x: d.getInt32(28, true), y: d.getInt32(32, true),
             nx: d.getInt32(36, true), ny: d.getInt32(40, true) };
  }
  return { kind, scene, seq, tick, data, size: bytes.byteLength };
}

function b64Bytes(b64) {
  const raw = atob(b64);
  return Uint8Array.from(raw, s => s.charCodeAt(0));
}

function insertFrame(bytes) {
  const event = decodeFrame(bytes);
  const old = received.get(event.seq);
  if (old) {
    assert(JSON.stringify(old) === JSON.stringify(event), "sequência em conflito");
    return false;
  }
  received.set(event.seq, event);
  totalBytes += event.size;
  render();
  return true;
}

function missing() {
  if (maxSequence === null) return [];
  return Array.from({length:maxSequence + 1}, (_, i) => i).filter(i => !received.has(i));
}

function derive() {
  const epoch = received.get(0)?.data;
  if (!epoch) return { surfaces: new Map(), beams: [], epoch: null };
  const emissions = new Map();
  const contacts = [];
  for (const ev of [...received.values()].sort((a,b)=>a.seq-b.seq)) {
    if (ev.kind === 1 && !emissions.has(ev.data.photon)) emissions.set(ev.data.photon, ev);
    if (ev.kind === 2) contacts.push(ev);
  }
  const surfaces = new Map(), beams = [];
  for (const contact of contacts) {
    const source = emissions.get(contact.data.photon);
    if (!source || contact.tick < source.tick) continue;
    const flight = contact.tick - source.tick;
    const x = source.data.x + flight * source.data.dx;
    const y = source.data.y + flight * source.data.dy;
    const normalDot = source.data.dx * contact.data.nx + source.data.dy * contact.data.ny;
    if (x !== contact.data.x || y !== contact.data.y || normalDot !== -1000) continue;
    const {obj, nx, ny} = contact.data;
    if (obj < 1 || obj > 64 || ![[1,0],[-1,0],[0,1],[0,-1]].some(([a,b]) => a===nx && b===ny)) continue;
    beams.push({source:source.data, end:contact.data});
    let objData = surfaces.get(obj);
    if (!objData) {
      objData = {minx:x,maxx:x,miny:y,maxy:y,faces:new Set(),points:[]};
      surfaces.set(obj,objData);
    }
    objData.minx = Math.min(objData.minx, x);objData.maxx = Math.max(objData.maxx,x);
    objData.miny = Math.min(objData.miny, y);objData.maxy = Math.max(objData.maxy,y);
    objData.faces.add(`${nx},${ny}`);
    objData.points.push({x,y});
  }
  return {surfaces, beams, epoch};
}

function render() {
  const W=canvas.width,H=canvas.height;
  ctx.fillStyle="#0c1723";ctx.fillRect(0,0,W,H);
  const margin=60;
  const {surfaces,beams,epoch}=derive();
  const w=epoch?.width || 10000,h=epoch?.height || 8000;
  const scale=Math.min((W-2*margin)/w,(H-2*margin)/h);
  const ox=(W-w*scale)/2,oy=(H-h*scale)/2;
  const px=x=>ox+x*scale,py=y=>oy+y*scale;
  ctx.fillStyle="#142535";ctx.fillRect(ox,oy,w*scale,h*scale);
  ctx.strokeStyle="#294355";ctx.lineWidth=1;
  for(let x=0;x<=w;x+=1000){ctx.beginPath();ctx.moveTo(px(x),oy);ctx.lineTo(px(x),py(h));ctx.stroke();}
  for(let y=0;y<=h;y+=1000){ctx.beginPath();ctx.moveTo(ox,py(y));ctx.lineTo(px(w),py(y));ctx.stroke();}
  ctx.strokeStyle="#4c728a";ctx.strokeRect(ox,oy,w*scale,h*scale);
  ctx.font="16px system-ui";ctx.fillStyle="#7fa2b7";ctx.fillText("0 m",ox,oy-12);
  ctx.fillText(`${w/1000} m`,px(w)-42,py(h)+28);
  for(const beam of beams){
    ctx.beginPath();ctx.moveTo(px(beam.source.x),py(beam.source.y));ctx.lineTo(px(beam.end.x),py(beam.end.y));
    ctx.strokeStyle="rgba(113,180,234,.75)";ctx.lineWidth=3;ctx.stroke();
    ctx.beginPath();ctx.arc(px(beam.end.x),py(beam.end.y),6,0,Math.PI*2);
    ctx.fillStyle="#f4b76e";ctx.fill();
  }
  for(const [id,s] of surfaces){
    const complete=s.faces.size===4;
    ctx.strokeStyle=complete?"#72d5b8":"#dfbd79";ctx.lineWidth=complete?4:2;
    ctx.setLineDash(complete?[]:[8,7]);
    const rw=(s.maxx-s.minx)*scale,rh=(s.maxy-s.miny)*scale;
    if (rw>1 && rh>1) ctx.strokeRect(px(s.minx),py(s.miny),rw,rh);
    ctx.setLineDash([]);
    ctx.fillStyle=complete?"#8ee0c7":"#f0c591";
    ctx.font="bold 16px system-ui";
    ctx.fillText(`Objeto ${id} · ${s.faces.size}/4 faces`,px(s.minx)+6,py(s.miny)-10);
  }
  $("received").textContent = `${received.size} / ${maxSequence === null ? 17 : maxSequence + 1}`;
  $("objects").textContent = `${[...surfaces.values()].filter(s=>s.faces.size===4).length} / 2`;
  $("bytes").textContent = String(totalBytes);
  $("missing").textContent = String(missing().length);
  $("scene-status").textContent = epoch ? `${beams.length} contatos válidos` : "Aguardando epoch";
}

function message(text) { $("message").textContent = text; }
function stopStream() { if (stream) { stream.close(); stream=null; } $("start").disabled=false; }
function start() {
  stopStream();received.clear();maxSequence=null;totalBytes=0;droppedCount=0;
  render();$("repair").disabled=true;$("start").disabled=true;
  message("Recebendo eventos do IFRO conforme o tempo lógico da simulação...");
  stream=new EventSource("/events");
  stream.addEventListener("photon",ev=>{
    try {
      const packet=b64Bytes(ev.data);
      const frame=decodeFrame(packet);
      if ($("loss").value === "2" && frame.seq>0 && frame.seq%7===0) { droppedCount++;return; }
      insertFrame(packet);
    }catch(error){message(`Quadro rejeitado: ${error.message}`);stopStream();}
  });
  stream.addEventListener("complete",ev=>{
    try{maxSequence=JSON.parse(ev.data).highest_sequence;}catch{maxSequence=16;}
    stopStream();render();const lost=missing();
    $("repair").disabled=lost.length===0;
    message(`Transmissão concluída. Perdas simuladas: ${droppedCount}. Sequências faltantes: ${lost.join(", ")||"nenhuma"}.`);
  });
  stream.onerror=()=>{if(stream){stopStream();message("Transmissão interrompida. Verifique a conexão e tente novamente.");}};
}
async function repair(){
  $("repair").disabled=true;
  try{
    const response=await fetch("/journal",{cache:"no-store"});assert(response.ok,"falha no download do histórico");
    const bytes=new Uint8Array(await response.arrayBuffer());let i=0,recovered=0;
    const targets=new Set(missing());
    while(i<bytes.length){
      assert(i+20<=bytes.length,"log truncado");
      const len=bytes[i+5]===2?44:40;
      assert(i+len<=bytes.length,"log truncado");
      const packet=bytes.slice(i,i+len);const frame=decodeFrame(packet);
      if(targets.has(frame.seq)){insertFrame(packet);recovered++;}
      i+=len;
    }
    render();message(`Histórico recebido: ${bytes.length} bytes. Eventos recuperados: ${recovered}. Objetos completos: ${$("objects").textContent}.`);
  }catch(error){message(`Falha no replay: ${error.message}`);$("repair").disabled=false;}
}
async function measureRTT(){
  $("rtt").disabled=true;message("Medindo RTT HTTP, sem estimar distância...");
  try{
    const samples=[];
    for(let i=0;i<12;i++){
      const start=performance.now();
      const response=await fetch("/ping",{cache:"no-store"});
      assert(response.status===204,"endpoint de RTT indisponível");
      samples.push(performance.now()-start);
    }
    samples.sort((a,b)=>a-b);
    const ms=x=>`${x.toFixed(1)} ms`;
    $("rtt-p50").textContent=ms((samples[5]+samples[6])/2);
    $("rtt-p95").textContent=ms(samples[Math.ceil(.95*samples.length)-1]);
    message("RTT medido neste navegador. Inclui processamento HTTP; não fornece tempo de voo de rádio nem distância física.");
  }catch(e){message(`Não foi possível medir RTT: ${e.message}`);}
  finally{$("rtt").disabled=false;}
}
$("start").addEventListener("click",start);
$("repair").addEventListener("click",repair);
$("rtt").addEventListener("click",measureRTT);
render();
