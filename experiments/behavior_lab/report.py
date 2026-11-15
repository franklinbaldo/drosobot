#!/usr/bin/env python3
"""Generate a self-contained, offline visualization for synthetic behaviour logs.

No network, no credentials. Private results are never uploaded automatically.
"""
import argparse
import html
import json
import os
from pathlib import Path

TEMPLATE=r'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><title>DrosoBot: comportamento sintético de 10 minutos</title>
<style>
*{box-sizing:border-box}body{font:14px system-ui,-apple-system,sans-serif;background:#0f1724;color:#e5eaf0;margin:0;padding:20px}main{max-width:1100px;margin:auto}
h1{font-size:clamp(24px,3vw,38px);letter-spacing:-.035em;margin:4px 0 6px}.muted{color:#97a8bc}p{line-height:1.5}
.grid{display:grid;grid-template-columns:1.3fr .7fr;gap:16px}.card{padding:16px;border:1px solid #34455c;border-radius:12px;background:#1a2636}
canvas{width:100%;height:auto;aspect-ratio:10/8;border-radius:8px;background:#111d2b}input{width:100%;accent-color:#78d5ba}
.stat{display:flex;justify-content:space-between;border-bottom:1px solid #2f4052;padding:9px 0;gap:8px}.stat:last-child{border:0}
.legend{display:flex;gap:16px;align-items:center;margin:8px 0 14px}.p{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}.cautious{background:#67d5b1}.aggressive{background:#f2a35e}
code{font-size:.92em}.wide{margin-top:16px}@media(max-width:800px){.grid{grid-template-columns:1fr}}button{background:#2e6470;border:1px solid #6eb9ab;color:white;padding:9px 14px;border-radius:7px;cursor:pointer}
</style></head><body><main>
<div class="muted">DROSOBOT / SIMULAÇÃO EMBREE / DADOS 100% SINTÉTICOS</div>
<h1>10 minutos de comportamento virtual</h1>
<p class="muted">O mapa exibe posições conhecidas somente pelo avaliador. Os controladores receberam observações com ruído, atraso e perdas. Isto não é uma gravação do robô físico nem uma validação de sua marcha.</p>
<div class="grid"><section class="card"><canvas id="map" width="1000" height="800" aria-label="Caminhos simulados de dois agentes numa sala de dez por oito metros"></canvas>
<div class="legend"><span><i class="p cautious"></i>Cauteloso</span><span><i class="p aggressive"></i>Agressivo</span></div>
<label for="time">Tempo reproduzido: <strong id="timeText">0:00</strong></label><input type="range" id="time" min="0" max="599" value="599" step="1"><button id="play" type="button">Reproduzir rapidamente</button>
</section><section class="card"><h2>Resultados</h2><div id="stats"></div><h3>Interpretação</h3><p class="muted">Interseções de raios vêm do Embree. Motores, sensores, iluminação, Wi-Fi e ruído são modelos hipotéticos. O MaleCNS e a memória DPH1 ainda não fecham este laço de controle.</p>
<p class="muted">Para avaliar realismo físico, faltam comparações com dimensões, velocidades, correntes, latências e sensores medidos no ESP-Hi real.</p></section></div>
<div class="card wide"><h2>Fases predefinidas</h2><p>0–200 s: iluminação alta, ruído menor e 2% de perda. 200–400 s: luz reduzida, atraso maior e 8% de perda. 400–600 s: escuridão simulada, 18% de perda e ruído de 10 cm.</p>
<p class="muted">O contador de colisões representa tentativas de avançar bloqueadas pelo simulador, não impactos nem danos físicos. Os testes exibem a coerência interna do modelo e sua estabilidade durante uma execução cronometrada.</p></div>
</main><script id="data" type="application/json">__DATA__</script><script>
"use strict";
const data=JSON.parse(document.getElementById('data').textContent);const summary=data.summary;const frames=data.frames;
const cv=document.getElementById('map'),cx=cv.getContext('2d'),slider=document.getElementById('time');
const colors=['#67d5b1','#f2a35e'];let running=false,timer=null;
function draw(sec){
cx.fillStyle='#101c29';cx.fillRect(0,0,cv.width,cv.height);
const px=x=>x*100,py=y=>y*100;
for(let x=0;x<=10;x++){cx.strokeStyle='#2c4054';cx.lineWidth=1;cx.beginPath();cx.moveTo(px(x),0);cx.lineTo(px(x),800);cx.stroke();}
for(let y=0;y<=8;y++){cx.beginPath();cx.moveTo(0,py(y));cx.lineTo(1000,py(y));cx.stroke();}
for(const [x1,y1,x2,y2] of summary.scene.rectangles_m){cx.fillStyle='#34465a';cx.fillRect(px(x1),py(y1),px(x2-x1),py(y2-y1));cx.strokeStyle='#d1dae4';cx.lineWidth=2;cx.strokeRect(px(x1),py(y1),px(x2-x1),py(y2-y1));}
for(let which=0;which<2;which++){
 cx.strokeStyle=colors[which];cx.lineWidth=3;cx.beginPath();let first=true,last=null;
 for(const f of frames){if(f.tick/10>sec)break;const a=f.agents[which];if(!a)continue;const [x,y,head]=a.pose_truth_for_evaluator;if(first){cx.moveTo(px(x),py(y));first=false;}else{cx.lineTo(px(x),py(y));}last=a;}
 cx.stroke();if(last){let [x,y,theta]=last.pose_truth_for_evaluator;cx.fillStyle=colors[which];cx.beginPath();cx.arc(px(x),py(y),9,0,Math.PI*2);cx.fill();cx.beginPath();cx.moveTo(px(x),py(y));cx.lineTo(px(x+.23*Math.cos(theta)),py(y+.23*Math.sin(theta)));cx.stroke();}
}
const m=Math.floor(sec/60),s=Math.floor(sec%60);document.getElementById('timeText').textContent=`${m}:${String(s).padStart(2,'0')}`;
}
function stat(label,value){const line=document.createElement('div');line.className='stat';const a=document.createElement('span');a.textContent=label;const b=document.createElement('strong');b.textContent=value;line.append(a,b);return line;}
const target=document.getElementById('stats');target.append(stat('Duração real',summary.wall_seconds+' s'));
for(const [name,m] of Object.entries(summary.metrics)){
 const title=document.createElement('h3');title.textContent=name==='cautious'?'Cauteloso':'Agressivo';target.append(title);
 target.append(stat('Distância',m.distance_m.toFixed(1)+' m'),stat('Movimentos bloqueados',String(m.collision_attempts)),
  stat('Células de 50 cm',String(m.unique_50cm_cells)),stat('Sensor útil',(m.sensor_usable_fraction*100).toFixed(1)+'%'),
  stat('Wi-Fi sintético: abstenção',(m.wifi_abstention_rate*100).toFixed(1)+'%'));
}
slider.addEventListener('input',()=>draw(Number(slider.value)));document.getElementById('play').addEventListener('click',()=>{
 if(running){running=false;clearInterval(timer);return;}running=true;slider.value=0;draw(0);timer=setInterval(()=>{let v=Number(slider.value)+4;if(v>599){v=599;running=false;clearInterval(timer);}slider.value=v;draw(v);},50);
});draw(599);
</script></body></html>'''


def generate(summary_path:Path, log_path:Path, output:Path):
    if output.exists() or output.is_symlink():raise ValueError('Refusing overwrite or symlink')
    summary=json.loads(summary_path.read_text())
    if summary.get('kind')!='synthetic_embree_behavior_10min':raise ValueError('Unexpected report type')
    frames=[json.loads(line) for line in log_path.read_text().splitlines()]
    if len(frames)!=summary['ticks']//10:raise ValueError('Second-by-second trace incomplete')
    dataset=json.dumps({'summary':summary,'frames':frames},separators=(',',':'),ensure_ascii=False)
    dataset=dataset.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(TEMPLATE.replace('__DATA__',dataset))
    return {'frames':len(frames),'bytes':output.stat().st_size}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary',required=True,type=Path);p.add_argument('--log',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();print(json.dumps(generate(a.summary,a.log,a.output)))
