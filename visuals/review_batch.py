"""Resume the exact failed 3 Nov batch masters as local review cuts.

HWK_REVIEW_CUT=1 python visuals/review_batch.py /path/to/main/checkout
No planning, narration regeneration, shelving, or approved-render writes.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'loop'))
import review_cut
import frame_check as FC


def episodes(root):
    slug = None
    found = []
    for line in (root / 'logs/batch-oneshot-2026-11-03.log').read_text().splitlines():
        match = re.match(r'  === (\S+) \d', line)
        if match:
            slug = match[1]
        if 'NAMED STOP [PICTURE_CHECK_FAILED]' in line and '(variety)' in line:
            if not slug or slug in found:
                raise RuntimeError('Unexpected batch log: missing or duplicate slug')
            found.append(slug)
    if len(found) != 8:
        raise RuntimeError(f'Expected eight variety failures, got {len(found)}')
    return found


def render_one(root, slug, dest):
    if not review_cut.enabled():
        raise RuntimeError('Review rendering requires HWK_REVIEW_CUT=1')
    source = root / 'renders' / f'{slug}-final.mp4.picture-check-failed'
    out = review_cut.output_path(dest / f'{slug}-review.mp4')
    phone = dest / f'{slug}-review-phone.mp4'
    if phone.exists():
        raise FileExistsError(phone)
    record = Path(str(source) + '.footage.json')
    if not source.is_file() or not record.is_file():
        raise RuntimeError(f'Missing exact batch master/shot record: {source}')
    # The batch already rendered and mixed this cut. Validate its identical
    # frames, then remux without changing a single picture or audio packet.
    checked = FC.check_render(str(source), slug)
    subprocess.run(['ffmpeg', '-v', 'error', '-n', '-i', str(source),
                    '-map', '0', '-c', 'copy', '-movflags', '+faststart', str(out)], check=True)
    rec = json.loads(record.read_text())
    rec['review_only'] = True
    rec['review_findings'] = checked.get('findings', [])
    rec['review_frame_check'] = checked
    rec['master'] = {'bytes': out.stat().st_size, 'mtime': int(out.stat().st_mtime)}
    with Path(str(out) + '.footage.json').open('x') as fh:
        json.dump(rec, fh, indent=2)
    subprocess.run(['ffmpeg', '-v', 'error', '-n', '-i', str(out),
                    '-vf', 'scale=-2:360', '-c:v', 'libx264', '-profile:v', 'baseline',
                    '-level', '3.0', '-pix_fmt', 'yuv420p', '-preset', 'fast',
                    '-b:v', '190k', '-maxrate', '210k', '-bufsize', '420k',
                    '-c:a', 'aac', '-b:a', '40k', '-ac', '1',
                    '-movflags', '+faststart', str(phone)], check=True)
    if phone.stat().st_size >= 25_000_000:
        raise RuntimeError(f'Phone copy exceeds 25 MB: {phone}')
    with (dest / 'findings.txt').open('a') as fh:
        fh.write(slug + ': ' + '; '.join(checked.get('findings', [])) + '\n')
    print(f'FINISHED {slug}: {checked["frames"]} frames passed; phone {phone.stat().st_size} bytes', flush=True)


def main():
    if not review_cut.enabled():
        raise RuntimeError('Review rendering requires HWK_REVIEW_CUT=1')
    root = Path(sys.argv[1]).resolve()
    # Media, subject lists and credentials belong to the main checkout;
    # executable pipeline and free-model policy remain from this worktree.
    import shot_list
    shot_list.ROOT = root
    shot_list.STORE = root / 'channel/imagery/shot_lists.json'
    shot_list.SCRIPTS = root / 'scripts'
    dest = root / 'renders/review-2026-11-03'
    dest.mkdir(exist_ok=True)
    os.environ['LLM_ROUTE_LEDGER'] = str(dest / 'route-ledger.json')
    lock = dest / '.review.lock'
    lock.mkdir()  # refuse a concurrent review batch
    try:
        for slug in episodes(root):
            render_one(root, slug, dest)
    finally:
        lock.rmdir()


if __name__ == '__main__':
    main()
