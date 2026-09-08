#!/usr/bin/env python3
"""Snake contribution graph generator. CLI: python scripts/generate_dragon.py <user> [--theme dark|light] [--out path.svg]"""
import argparse,json,math,os,sys,urllib.request,xml.etree.ElementTree as ET
from datetime import datetime,timezone
CELL=12;GAP=3;ROWS=7;MX=32;MY=28;BM=20;TD=18
MN=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
TH={"dark":{"bg":"#0D1117","br":"#30363D","em":"#161B22","lv":["#0E4429","#006D32","#26A641","#39D353"],"fc":"#CCFF00","fm":"#FF8C00","fo":"#CC2222","sb":"#3DDC6A","sbl":"#ADFFD4","ssc":"#1A6B33","sh":"#2AB856","sm":"#CC0000","sg":"#FF4466","sf":"#FFFFFF","st":"#FF2255","se":"#111111","sp":"#FFFF00","tx":"#8B949E","mt":"#8B949E"},"light":{"bg":"#FFFFFF","br":"#D0D7DE","em":"#EBEDF0","lv":["#9BE9A8","#40C463","#30A14E","#216E39"],"fc":"#CCFF00","fm":"#FF8C00","fo":"#CC2222","sb":"#1A7A3A","sbl":"#5FD48A","ssc":"#0D4420","sh":"#156030","sm":"#AA0000","sg":"#DD3355","sf":"#F0F0F0","st":"#DD1144","se":"#000000","sp":"#DDDD00","tx":"#57606A","mt":"#57606A"}}
LT="<"; GT=">"; SL="/"

def fetch(u):
    r=urllib.request.Request(f"https://github-contributions-api.jogruber.de/v4/{u}?y=last",headers={"User-Agent":"snake/1"})
    with urllib.request.urlopen(r,timeout=20) as x: d=json.loads(x.read().decode())
    now=datetime.now(timezone.utc).date()
    return [i for i in d.get("contributions",[]) if datetime.strptime(i["date"],"%Y-%m-%d").date()<=now][-371:]

def layout(days):
    c=[];sr=(datetime.strptime(days[0]["date"],"%Y-%m-%d").weekday()+1)%7 if days else 0;col=0;row=sr
    for d in days:
        x=MX+col*(CELL+GAP);y=MY+row*(CELL+GAP)
        c.append({"date":d["date"],"count":d.get("count",0),"level":d.get("level",0),"x":x,"y":y,"cx":x+CELL/2,"cy":y+CELL/2,"col":col,"row":row})
        row+=1
        if row>6: row=0;col+=1
    return c

def walkpath(cells):
    bc={}
    for c in cells:
        if c["count"]>0: bc.setdefault(c["col"],[]).append(c)
    o=[];gd=True
    for ci in sorted(bc): o.extend(sorted(bc[ci],key=lambda c:c["row"],reverse=not gd));gd=not gd
    return o

def tag(name,attrs="",content="",self_close=False):
    a=" "+attrs if attrs else ""
    if self_close: return f"{LT}{name}{a}/{GT}"
    return f"{LT}{name}{a}{GT}{content}{LT}{SL}{name}{GT}"

def build(u,cells,ordered,th,dur):
    t=TH[th];n=len(ordered);mx=max((c["x"] for c in cells),default=MX)+CELL;W=mx+MX;H=MY+ROWS*(CELL+GAP)+BM
    sb=t["sb"];sbl=t["sbl"];ssc=t["ssc"];sh=t["sh"];sm=t["sm"];sg=t["sg"];sf=t["sf"];st=t["st"];se=t["se"];sp=t["sp"]
    p=[]
    p.append(f'{LT}svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}" width="{W}" height="{H}"{GT}')
    p.append(f'{LT}rect width="{W}" height="{H}" rx="10" fill="{t["bg"]}" stroke="{t["br"]}" stroke-width="1"/{GT}')
    # snake glyph def
    glyph=(f'{LT}path d="M -28,1 C -24,-6 -18,-7 -12,-3 C -6,1 -2,5 0,2" fill="none" stroke="{sb}" stroke-width="6.5" stroke-linecap="round"/{GT}'
           f'{LT}path d="M -28,2 C -24,-4 -18,-5 -12,-2 C -6,2 -2,6 0,3" fill="none" stroke="{sbl}" stroke-width="2.5" stroke-linecap="round" opacity="0.85"/{GT}'
           f'{LT}circle cx="-20" cy="-4" r="1.4" fill="{ssc}" opacity="0.65"/{GT}'
           f'{LT}circle cx="-12" cy="-1" r="1.4" fill="{ssc}" opacity="0.65"/{GT}'
           f'{LT}circle cx="-4" cy="4" r="1.4" fill="{ssc}" opacity="0.65"/{GT}'
           f'{LT}ellipse cx="1" cy="0" rx="5" ry="4.5" fill="{sh}"/{GT}'
           f'{LT}path d="M 2,-2 C 6,-3 11,-5 16,-5 L 18,-4 C 14,-3 8,-1 4,-1 Z" fill="{sm}"/{GT}'
           f'{LT}path d="M 2,4 C 6,6 11,8 16,8 L 18,7 C 14,6 8,4 4,3 Z" fill="{sm}"/{GT}'
           f'{LT}path d="M 4,-1 C 8,-1 14,-2 18,-3 L 18,6 C 14,7 8,6 4,5 Z" fill="{sg}" opacity="0.45"/{GT}'
           f'{LT}path d="M 0,-2 C 3,-4 7,-7 12,-8 C 15,-9 18,-8 18,-6 C 16,-6 12,-7 8,-6 C 4,-5 1,-3 0,-2 Z" fill="{sh}" stroke="{ssc}" stroke-width="0.5"/{GT}'
           f'{LT}path d="M 0,4 C 3,7 7,10 12,10 C 15,11 18,10 18,9 C 16,9 12,10 8,9 C 4,8 1,6 0,4 Z" fill="{sbl}" stroke="{ssc}" stroke-width="0.5"/{GT}'
           f'{LT}path d="M 8,-6 C 8,-4 7,1 7.5,3" fill="none" stroke="{sf}" stroke-width="1.3" stroke-linecap="round"/{GT}'
           f'{LT}ellipse cx="7.5" cy="3.5" rx="0.7" ry="0.5" fill="{sf}"/{GT}'
           f'{LT}path d="M 12,-7 C 12,-5 11,0 11.5,2" fill="none" stroke="{sf}" stroke-width="1.3" stroke-linecap="round"/{GT}'
           f'{LT}ellipse cx="11.5" cy="2.5" rx="0.7" ry="0.5" fill="{sf}"/{GT}'
           f'{LT}circle cx="4" cy="-4" r="2.5" fill="{se}"/{GT}'
           f'{LT}ellipse cx="4" cy="-4" rx="0.7" ry="2.0" fill="{sp}"/{GT}'
           f'{LT}circle cx="5" cy="-5" r="0.7" fill="white" opacity="0.6"/{GT}'
           f'{LT}path d="M 18,1.5 L 26,1.5 M 26,1.5 L 31,-1.5 M 26,1.5 L 31,4.5" fill="none" stroke="{st}" stroke-width="1.3" stroke-linecap="round"/{GT}'
           f'{LT}circle cx="31" cy="-1.5" r="0.9" fill="{st}"/{GT}'
           f'{LT}circle cx="31" cy="4.5" r="0.9" fill="{st}"/{GT}')
    p.append(f'{LT}defs{GT}{LT}g id="sn"{GT}{glyph}{LT}{SL}g{GT}{LT}{SL}defs{GT}')
    # labels
    lm=-1
    for c in cells:
        m=datetime.strptime(c["date"],"%Y-%m-%d").month
        if m!=lm and c["row"]<=1:
            p.append(f'{LT}text x="{c["x"]+CELL//2}" y="{MY-8}" font-family="Arial,sans-serif" font-size="9" fill="{t["mt"]}" text-anchor="middle"{GT}{MN[m-1]}{LT}{SL}text{GT}');lm=m
    for ri,lb in ((1,"Mon"),(3,"Wed"),(5,"Fri")):
        ly=MY+ri*(CELL+GAP)+CELL//2+3
        p.append(f'{LT}text x="{MX-4}" y="{ly}" font-family="Arial,sans-serif" font-size="8" fill="{t["tx"]}" text-anchor="end"{GT}{lb}{LT}{SL}text{GT}')
    # grid
    for c in cells:
        b=t["em"] if c["level"]==0 else t["lv"][min(c["level"]-1,3)];cid=f'c{c["date"]}'
        p.append(f'{LT}rect id="{cid}" x="{c["x"]}" y="{c["y"]}" width="{CELL}" height="{CELL}" rx="2.5" fill="{b}"{GT}{LT}title{GT}{c["date"]}: {c["count"]}{LT}{SL}title{GT}{LT}{SL}rect{GT}')
    # animation
    if n>0:
        pts=[(c["cx"],c["cy"]) for c in ordered];ds=[0.0]
        for i in range(1,n): ds.append(ds[-1]+math.hypot(pts[i][0]-pts[i-1][0],pts[i][1]-pts[i-1][1]))
        td2=ds[-1] or 1.0;times=[dur*d/td2 for d in ds]
        p.append(f'{LT}rect id="hb" x="-9999" y="-9999" width="1" height="1" opacity="0"{GT}{LT}animate attributeName="opacity" from="0" to="0" dur="{dur}s" repeatCount="indefinite"/{GT}{LT}{SL}rect{GT}')
        sk=max(0.5,min(1.4,dur/max(n,1)))
        for c,s in zip(ordered,times):
            cid=f'c{c["date"]}';b=t["lv"][min(c["level"]-1,3)] if c["level"]>0 else t["em"];bg=f'{s:.3f}s; hb.repeat(1)+{s:.3f}s'
            p.append(f'{LT}animate href="#{cid}" attributeName="fill" values="{b};{t["fc"]};{t["fm"]};{t["fo"]};{b}" keyTimes="0;0.10;0.40;0.70;1" dur="{sk:.3f}s" begin="{bg}" fill="freeze"/{GT}')
        pd="M "+" L ".join(f"{x:.1f},{y:.1f}" for x,y in pts)
        p.append(f'{LT}path id="fp" d="{pd}" fill="none" stroke="none"/{GT}')
        p.append(f'{LT}use href="#sn"{GT}{LT}animateMotion dur="{dur}s" repeatCount="indefinite" rotate="auto" calcMode="linear"{GT}{LT}mpath href="#fp"/{GT}{LT}{SL}animateMotion{GT}{LT}{SL}use{GT}')
    tc=sum(c["count"] for c in cells)
    p.append(f'{LT}text x="{MX}" y="{H-6}" font-family="Arial,sans-serif" font-size="8.5" fill="{t["tx"]}"{GT}@{u} \u00b7 {tc:,} contributions \u00b7 snake-powered \U0001f40d{LT}{SL}text{GT}')
    p.append(f'{LT}{SL}svg{GT}');return "\n".join(p)

ap=argparse.ArgumentParser();ap.add_argument("username");ap.add_argument("--theme",choices=["dark","light"],default="dark");ap.add_argument("--out",default=None);ap.add_argument("--total-dur",type=float,default=TD);args=ap.parse_args()
print(f"Fetching @{args.username}...");days=fetch(args.username)
if not days: print("No data",file=sys.stderr);sys.exit(1)
cells=layout(days);ordered=walkpath(cells);print(f"{len(cells)} cells, {len(ordered)} contributed.")
svg=build(args.username,cells,ordered,args.theme,args.total_dur)
out=args.out or f"assets/dragon-{args.theme}.svg"
os.makedirs(os.path.dirname(out) if os.path.dirname(out) else ".",exist_ok=True)
with open(out,"w",encoding="utf-8") as f: f.write(svg)
try: ET.fromstring(svg);print(f"Wrote {out}. XML valid.")
except ET.ParseError as e: print(f"XML INVALID:{e}",file=sys.stderr);sys.exit(2)
