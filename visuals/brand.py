"""Channel identity assets. Same palette/type as the videos."""
from PIL import Image, ImageDraw, ImageFont
from design import *
import os

OUT = "../channel/brand"; os.makedirs(OUT, exist_ok=True)
def F(p,s): return ImageFont.truetype(p,s)

def grad(w,h,top,bot):
    g=Image.new("RGB",(2,160)); px=g.load()
    for y in range(160):
        c=mix(top,bot,y/159); px[0,y]=c; px[1,y]=c
    return g.resize((w,h), Image.BILINEAR)

def snow(d,w,h,n,seed=3):
    import random
    r=random.Random(seed)
    for _ in range(n):
        x,y=r.random()*w, r.random()*h
        rad=r.uniform(1.0,2.6); a=int(r.uniform(35,120))
        d.ellipse([x-rad,y-rad,x+rad,y+rad], fill=(*PALE,a))

def mark(d, cx, cy, scale, alpha=255, lw=None):
    """The sounding mark: sea-level rule, a descent line, a reading at depth.
    Reads at any size because it is three shapes, not a picture."""
    lw = lw or max(2,int(6*scale))
    half=int(78*scale)
    d.line([(cx-half,cy-int(62*scale)),(cx+half,cy-int(62*scale))], fill=(*PALE,alpha), width=lw)
    d.line([(cx,cy-int(62*scale)),(cx,cy+int(46*scale))], fill=(*CYAN,alpha), width=lw)
    for i,dy in enumerate((-22,0,22)):
        t=int(26*scale)-i*int(6*scale)
        d.line([(cx-t,cy+int(dy*scale)),(cx+t,cy+int(dy*scale))], fill=(*CYAN,alpha), width=max(1,lw-1))
    r=int(13*scale)
    d.ellipse([cx-r,cy+int(46*scale)-r,cx+r,cy+int(46*scale)+r], fill=(*AMBER,alpha))

# ---------- avatar 800x800 ----------
a=grad(800,800,MID,INK).convert("RGBA")
ov=Image.new("RGBA",(800,800),(0,0,0,0)); d=ImageDraw.Draw(ov)
snow(d,800,800,55)
mark(d,400,400,3.5)
Image.alpha_composite(a,ov).convert("RGB").save(f"{OUT}/avatar_800.png")

# ---------- watermark 150x150, transparent ----------
w=Image.new("RGBA",(150,150),(0,0,0,0)); d=ImageDraw.Draw(w)
mark(d,75,72,0.62,alpha=255,lw=5)
w.save(f"{OUT}/watermark_150.png")

# ---------- banner 2048x1152, safe area 1235x338 centred ----------
BW,BH=2048,1152
b=grad(BW,BH,MID,INK).convert("RGBA")
ov=Image.new("RGBA",(BW,BH),(0,0,0,0)); d=ImageDraw.Draw(ov)
snow(d,BW,BH,150,seed=11)
cx,cy=BW//2,BH//2
sx,sy=(BW-1235)//2,(BH-338)//2          # safe area
mark(d,cx-470,cy-6,1.5)
f1=F(F_DISPLAY,120); f2=F(F_LABEL,34); f3=F(F_LABEL,27)
d.text((cx-330,cy-96),"How We Know",font=f1,fill=(*TEXT,255))
d.text((cx-326,cy+44),"Following the evidence chain to the bottom of the ocean.",
       font=f2,fill=(*MUTED,235))
d.text((cx-326,cy+100),"NEW EPISODES WEEKLY   ·   @howweknowdeep",font=f3,fill=(*CYAN,215))
Image.alpha_composite(b,ov).convert("RGB").save(f"{OUT}/banner_2048.png")

# circle-crop proof: exactly how YouTube will show it
av=Image.open(f"{OUT}/avatar_800.png").convert("RGBA")
m=Image.new("L",(800,800),0); ImageDraw.Draw(m).ellipse([0,0,799,799],fill=255)
cir=Image.new("RGBA",(800,800),(20,20,20,255)); cir.paste(av,(0,0),m)
cir.convert("RGB").save(f"{OUT}/avatar_circle_proof.png")
small=cir.resize((96,96),Image.LANCZOS); small.convert("RGB").save(f"{OUT}/avatar_96_proof.png")

for n in ("avatar_800.png","watermark_150.png","banner_2048.png"):
    im=Image.open(f"{OUT}/{n}")
    print(f"{n:22} {im.size[0]}x{im.size[1]}  {os.path.getsize(f'{OUT}/{n}')/1024:.0f} KB")
