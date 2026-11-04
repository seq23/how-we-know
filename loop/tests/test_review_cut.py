"""One behaviour test: ordinary variety stops; review renders, frames gate,
production publishing and overwrites are refused."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ['LOOP_DRY_RUN'] = '1'
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'visuals'), str(ROOT / 'loop')]
import frame_check as FC
import longform_picture as LP
import review_cut
import review_batch
import r2

with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=False):
    root = Path(td)
    slug = 'fixture'
    (root / 'renders').mkdir()
    source = root / 'renders/fixture-final.mp4.picture-check-failed'
    import subprocess
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=640x360:duration=1',
                    '-f', 'lavfi', '-i', 'anullsrc', '-t', '1', '-c:v', 'libx264', '-c:a', 'aac',
                    '-f', 'mp4', str(source)], check=True)
    Path(str(source) + '.footage.json').write_text(json.dumps({'shots': [{}]}))
    dest = root / 'renders/review-test'
    dest.mkdir()
    with patch.object(LP, 'variety_problems', return_value=['too-soon repeat', 'distinct floor']), \
         patch.object(FC, 'check', return_value={'frames': 1}) as frames:
        os.environ.pop('HWK_REVIEW_CUT', None)
        try:
            FC.check_render(str(source), slug)
            raise AssertionError('flag off accepted failed variety')
        except FC.PictureCheckFailed:
            pass
        frames.assert_not_called()
        os.environ['HWK_REVIEW_CUT'] = '1'
        review_batch.render_one(root, slug, dest)
        assert (dest / 'fixture-review.mp4').stat().st_size > 0
        assert (dest / 'fixture-review-phone.mp4').stat().st_size > 0
        frames.assert_called_once()
        for action in (lambda: r2.push(None),
                       lambda: review_cut.output_path(root / 'renders/fixture-final.mp4'),
                       lambda: review_cut.output_path(root / 'channel/approved_renders.json'),
                       lambda: review_cut.output_path(dest / 'fixture-review.mp4')):
            try:
                action()
                raise AssertionError('review allowed publish or overwrite')
            except (RuntimeError, FileExistsError):
                pass
        with patch.object(FC, 'check', side_effect=FC.PictureCheckFailed('bad frame', [(1, 'pillarbox')])):
            try:
                FC.check_render(str(source), slug)
                raise AssertionError('review bypassed frame check')
            except FC.PictureCheckFailed:
                pass
print('review cut: ok')
