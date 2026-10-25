#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口袋数字调试助手 - 交互式波形浏览器导出
========================================================
把采集（.sr / .bin）或任一解码器演示波形变成一个单文件 HTML，浏览器打开即可：
  · 8 通道逻辑波形：滚轮缩放、按住拖动平移
  · 单击放红色光标 A、Shift+单击放蓝色光标 B，自动算 Δt
  · 事件标注：黄色竖线 + 下方事件列表，点击列表跳转到波形
  · 每通道自动统计：平均频率 / 平均占空比 / 翻转次数
纯 Python 生成、单文件、无网络依赖、发给谁都能看；不烧录、不碰固件。

用法：
  py -3.12 proto_browser.py --demo i2c
  py -3.12 proto_browser.py capture.sr --decoder i2c
  py -3.12 proto_browser.py data.bin --rate 10000 --decoder servo
输出 proto_wave.html（默认自动用浏览器打开，--noopen 可关闭）。
"""
import os, sys, json, statistics
import proto_io
from proto_common import channel_bits, DECKS

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>@@TITLE@@</title>
<style>
body{margin:0;background:#0b0f14;color:#d7e2ee;font-family:Consolas,'Microsoft YaHei',monospace}
#bar{padding:8px 12px;background:#11161d;border-bottom:1px solid #26313d;font-size:14px}
#cv{display:block}
#info{padding:6px 12px;font-size:12px;color:#8fb0cc;background:#0e1319}
#events{padding:6px 12px;font-size:12px}
#events .ev{border-bottom:1px dotted #22303c;padding:1px 0;cursor:pointer}
#events .ev:hover{background:#14202b}
#events .t{color:#fbbf24;display:inline-block;width:88px}
table{border-collapse:collapse;margin:8px 12px;font-size:12px}
td,th{border:1px solid #26313d;padding:3px 10px}
th{background:#11161d;color:#8fb0cc}
</style>
</head>
<body>
<div id="bar"><b>@@TITLE@@</b> ｜ 滚轮缩放 · 按住拖动平移 · 单击=A光标 · Shift+单击=B光标</div>
<canvas id="cv" width="1200" height="260"></canvas>
<div id="info"></div>
<div id="events"></div>
<div id="stats">@@STATS@@</div>
<script>
var RATE=@@RATE@@, SAMPLES=@@SAMPLES@@, EVENTS=@@EVENTS@@;
var cv=document.getElementById('cv'), cx=cv.getContext('2d');
var W=cv.width, H=cv.height, TOP=24, ROWH=(H-TOP)/8;
var v0=0, spp=Math.max(1,Math.ceil(SAMPLES.length/W));
var curA=null, curB=null, drag=null;
function idxToX(i){return (i-v0)/spp;}
function draw(){
  cx.fillStyle='#0b0f14'; cx.fillRect(0,0,W,H);
  cx.strokeStyle='#1c2733';
  for(var g=0;g<8;g++){cx.beginPath();cx.moveTo(0,TOP+g*ROWH+0.5);cx.lineTo(W,TOP+g*ROWH+0.5);cx.stroke();}
  var v1=Math.min(SAMPLES.length, v0+Math.ceil(spp*W));
  var w=Math.min(W, Math.ceil((v1-v0)/spp));
  cx.font='12px Consolas,monospace';
  for(var ch=0;ch<8;ch++){
    cx.fillStyle='#7f95a8'; cx.fillText('D'+ch,2,TOP+ch*ROWH+15);
    var y=TOP+ch*ROWH, prev=-1, seg=0;
    for(var px=0;px<w;px++){
      var lv=(SAMPLES[v0+Math.floor(px*spp)]>>ch)&1;
      if(lv!==prev){
        if(prev===1){cx.fillStyle='#3ecf8e';cx.fillRect(seg,y+4,px-seg,ROWH-10);}
        prev=lv; seg=px;
      }
    }
    if(prev===1){cx.fillStyle='#3ecf8e';cx.fillRect(seg,y+4,w-seg,ROWH-10);}
  }
  cx.fillStyle='rgba(251,191,36,0.7)';
  for(var k=0;k<EVENTS.length;k++){
    var ii=Math.round(EVENTS[k].t*RATE);
    if(ii>=v0&&ii<=v1){cx.fillRect(idxToX(ii),2,1,H-4);}
  }
  if(curA!==null){cx.strokeStyle='#f87171';cx.beginPath();cx.moveTo(idxToX(curA),0);cx.lineTo(idxToX(curA),H);cx.stroke();}
  if(curB!==null){cx.strokeStyle='#38bdf8';cx.beginPath();cx.moveTo(idxToX(curB),0);cx.lineTo(idxToX(curB),H);cx.stroke();}
  var msg='视图 '+v0+'~'+v1+' / '+SAMPLES.length+' 点 · '+spp.toFixed(2)+' 点/像素';
  if(curA!==null){msg+='  |  A@'+((curA/RATE)*1000).toFixed(3)+'ms';}
  if(curB!==null){msg+='  |  B@'+((curB/RATE)*1000).toFixed(3)+'ms';}
  if(curA!==null&&curB!==null){msg+='  |  Δt='+(Math.abs(curB-curA)/RATE*1000).toFixed(3)+'ms';}
  document.getElementById('info').textContent=msg;
}
cv.addEventListener('wheel',function(ev){ev.preventDefault();
  var c=v0+ev.offsetX*spp;
  spp=Math.max(1,Math.min(64, spp*(ev.deltaY>0?1.3:0.77)));
  v0=Math.max(0,Math.min(SAMPLES.length-1, c-ev.offsetX*spp));
  draw();});
cv.addEventListener('mousedown',function(ev){drag={x:ev.offsetX,v0:v0,moved:false};});
window.addEventListener('mouseup',function(){drag=null;});
cv.addEventListener('mousemove',function(ev){
  if(!drag)return;
  drag.moved=true;
  v0=Math.max(0,Math.min(SAMPLES.length-1, drag.v0-(ev.offsetX-drag.x)*spp));
  draw();});
cv.addEventListener('click',function(ev){
  if(drag&&drag.moved){return;}
  var ii=Math.floor(v0+ev.offsetX*spp);
  if(ii<0||ii>=SAMPLES.length)return;
  if(ev.shiftKey){curB=ii;}else{curA=ii;}
  draw();});
function jump(i){v0=Math.max(0,Math.min(SAMPLES.length-1,i-W*spp/2));draw();}
(function(){
  var box=document.getElementById('events');
  if(!EVENTS.length){box.innerHTML='<div style="color:#5b6f83;padding:4px 0">无解码事件（未叠加解码器）</div>';return;}
  var n=Math.min(EVENTS.length,300), html='<div style="padding:4px 0;color:#8fb0cc">解码事件（前'+n+'条，点击跳转）：</div>';
  for(var i=0;i<n;i++){
    var e=EVENTS[i];
    var tx=String(e.text).replace(/</g,'&lt;').replace(/>/g,'&gt;');
    var ty=String(e.type).replace(/</g,'&lt;').replace(/>/g,'&gt;');
    html+='<div class="ev" onclick="jump('+Math.round(e.t*RATE)+')">'+
      '<span class="t">'+(e.t*1000).toFixed(3)+'ms</span>D'+e.ch+' <b>['+ty+']</b> '+tx+'</div>';
  }
  box.innerHTML=html;
})();
draw();
</script>
</body>
</html>
"""

def load(path, rate):
    """读取 .sr 或 .bin → (rate, samples)。"""
    if path.lower().endswith(".sr"):
        r, s = proto_io.read_sr(path)
        if rate:
            r = rate
        return r, s
    r = rate or 10000
    return r, proto_io.read_bin(path, r)[1]

def build_html(title, rate, samples, events):
    """生成单文件 HTML。"""
    # 每通道统计
    stats_rows = []
    for ch in range(8):
        bits = channel_bits(samples, ch)
        rises = [i for i in range(1, len(bits)) if bits[i - 1] == 0 and bits[i] == 1]
        falls = [i for i in range(1, len(bits)) if bits[i - 1] == 1 and bits[i] == 0]
        edges = len(rises) + len(falls)
        freq_txt = duty_txt = "--"
        if len(rises) >= 2:
            per = statistics.mean([rises[k + 1] - rises[k]
                                   for k in range(len(rises) - 1)]) / rate
            if per > 0:
                freq_txt = f"{1.0 / per:.1f} Hz"
                highs = []
                fi = 0
                for r in rises:
                    while fi < len(falls) and falls[fi] <= r:
                        fi += 1
                    if fi < len(falls):
                        highs.append(falls[fi] - r)
                if highs:
                    duty_txt = f"{statistics.mean(highs) / rate / per * 100:.1f}%"
        stats_rows.append(f"<tr><td>D{ch}</td><td>{freq_txt}</td>"
                          f"<td>{duty_txt}</td><td>{edges}</td></tr>")
    stats_html = ("<table><tr><th>通道</th><th>平均频率</th><th>平均占空比</th>"
                  "<th>翻转次数</th></tr>" + "".join(stats_rows) + "</table>")

    title_safe = title.replace("&", "&amp;").replace("<", "&lt;")
    info = (f"采样率 {rate} Hz · {len(samples)} 点 · "
            f"时长 {len(samples) / rate * 1000:.1f} ms · 事件 {len(events)} 条")
    js_events = json.dumps([{"t": e["t"], "ch": e["ch"], "type": e["type"],
                             "text": e["text"]} for e in events],
                           ensure_ascii=False)
    js_samples = json.dumps(samples)
    return (TEMPLATE
            .replace("@@TITLE@@", title_safe)
            .replace("@@INFO@@", info)
            .replace("@@RATE@@", str(rate))
            .replace("@@SAMPLES@@", js_samples)
            .replace("@@EVENTS@@", js_events)
            .replace("@@STATS@@", stats_html))

def main():
    argv = sys.argv[1:]
    deck_name = None
    dec_name = None
    path = None
    rate = None
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "proto_wave.html")
    noopen = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--demo":
            deck_name = argv[i + 1]
            i += 2
        elif a == "--decoder":
            dec_name = argv[i + 1]
            i += 2
        elif a == "--rate":
            rate = int(argv[i + 1])
            i += 2
        elif a == "--out":
            out = argv[i + 1]
            i += 2
        elif a == "--noopen":
            noopen = True
            i += 1
        elif not a.startswith("--"):
            path = a
            i += 1
        else:
            i += 1

    events = []
    if deck_name:
        if deck_name not in DECKS:
            print("未知解码器:", deck_name, "可选:", list(DECKS))
            sys.exit(1)
        rate = rate or 10000
        samples = DECKS[deck_name]["make"](rate)
        events = DECKS[deck_name]["decode"](samples, rate)
        title = f"{deck_name} · {DECKS[deck_name]['desc']} 演示波形"
    elif path:
        r, samples = load(path, rate)
        rate = r
        if dec_name:
            if dec_name not in DECKS:
                print("未知解码器:", dec_name, "可选:", list(DECKS))
                sys.exit(1)
            try:
                events = DECKS[dec_name]["decode"](samples, rate)
            except Exception as exc:
                print("解码失败(忽略):", exc)
        title = f"{os.path.basename(path)} · {rate} Hz"
    else:
        print(__doc__)
        print("（未给参数，默认用 servo 演示波形生成）")
        rate = 10000
        samples = DECKS["servo"]["make"](rate)
        events = DECKS["servo"]["decode"](samples, rate)
        title = "servo · 舵机PWM/PPM 演示波形"

    html = build_html(title, rate, samples, events)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成: {out}  ({os.path.getsize(out)} 字节)")
    if not noopen:
        try:
            os.startfile(out)
        except Exception:
            print("（未能自动打开，请手动双击该文件）")

if __name__ == "__main__":
    main()
