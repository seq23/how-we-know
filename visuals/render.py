import sys, os, subprocess, shutil
from design import W, H, FPS
import segments as S

def render(name, fn, secs, outdir, **kw):
    d = os.path.join(outdir, name); os.makedirs(d, exist_ok=True)
    n = int(secs * FPS)
    for i in range(n):
        S.__dict__[fn](i / max(n - 1, 1), **kw).save(f"{d}/{i:05d}.png")
    clip = os.path.join(outdir, f"{name}.mp4")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-framerate",str(FPS),
                    "-i",f"{d}/%05d.png","-c:v","libx264","-pix_fmt","yuv420p","-crf","20",clip],check=True)
    shutil.rmtree(d)
    return clip

if __name__ == "__main__":
    out = "sample"; os.makedirs(out, exist_ok=True)
    plan = [
challenge := ("01_descent","depth_descent",7,dict(to_depth=11034,label="CHALLENGER DEEP")),
        ("02_stat","stat_card",4,dict(value="11,034",unit="METRES",
             caption="Deeper than Everest is tall.",source="NOAA")),
        ("03_compare","comparison",5,dict()),
        ("04_zones","zone_column",6,dict(highlight="MIDNIGHT")),
        ("05_quote","quote_card",6,dict(
             text="No horizon, no light, no way to tell up from down.", attrib="— Producer note")),
    ]
    clips=[]
    for nm,fn,secs,kw in plan:
        print("rendering",nm,f"({secs}s)",flush=True)
        clips.append(render(nm,fn,secs,out,**kw))
    with open(f"{out}/list.txt","w") as f:
        for c in clips: f.write(f"file '{os.path.basename(c)}'\n")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0",
                    "-i",f"{out}/list.txt","-c","copy","sample_reel.mp4"],check=True)
    print("\nDONE -> sample_reel.mp4")
