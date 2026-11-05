"""Picture-less masters produce no Shorts; moving-footage masters still do."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'loop'), str(ROOT / 'visuals')]
os.environ['LOOP_DRY_RUN'] = '1'
import shorts as S
import shorts_lane as SL
import shorts_cloud as SC
from shorts_master import NoMasterFootage, evidence

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    for name in ('plans', 'audio/x', 'renders', 'shorts'):
        (root / name).mkdir(parents=True)
    (root / 'plans/x.json').write_text('[{}]')
    master = root / 'renders/x-final.mp4'
    master.write_bytes(b'master')
    record = Path(f'{master}.footage.json')
    stamp = {'bytes': master.stat().st_size, 'mtime': int(master.stat().st_mtime)}
    # Same cutting entry point, with deterministic media I/O. No network,
    # ffmpeg or live assets; do not replace the eligibility guard under test.
    with ExitStack() as stack:
        stack.enter_context(patch.object(S, 'ROOT', str(root)))
        replacements = {
            'probe_stream': lambda _: {'width': S.SRC_W, 'height': S.SRC_H},
            'beat_timeline': lambda *_: [{'i': 0, 'narration': 'Water moves.', 'video_s': 3}],
            'select_beats': lambda *_: {'beats': [0], 'anchor': 0, 'seconds': 3},
            'direct_answer': lambda _: 'Water moves.',
            'picture_credits': lambda *_: {0: 'NOAA'},
            'render_footage_record': lambda *_: {0: 'NOAA'},
            'resolve_credits': lambda *_: (['NOAA'], {}),
            'drop_stale_voice': lambda picked, _: (picked, {}),
            'cue_lines_for': lambda *_: (1, []),
            'opener_question': lambda *_: 'Why does water move?',
        }
        for name, fn in replacements.items():
            stack.enter_context(patch.object(S, name, fn))
        for rec in (None, {'master': stamp, 'footage_beats_expected': 0, 'beats': {'0': None}},
                    {'master': stamp, 'beats': {'0': None}}):
            if rec is not None:
                record.write_text(json.dumps(rec))
            try:
                S.make_short('x', str(root / 'shorts'), dry_run=True)
                raise AssertionError('picture-less master yielded a Short')
            except NoMasterFootage as e:
                assert 'SHORT_MASTER_NO_FOOTAGE' in str(e)
        record.write_text(json.dumps({'master': stamp, 'footage_beats_expected': 1, 'beats': {'0': 'NOAA'}}))
        cut = S.make_short('x', str(root / 'shorts'), dry_run=True)
        assert cut['beats'] == [0] and cut['master_footage']['footage_beats'] == 1
        assert cut['output'].endswith('x-short.mp4')

    # An old shelved cut cannot bypass the cutter's guard at upload.
    path = root / 'shorts/x-short.mp4'
    path.write_bytes(b'cut')
    receipt = Path(f'{path}.short.json')
    opener = {'kind': SL.OPENER_KIND, 'question': 'Why does water move?', 'manifest': 'rights.json'}
    receipt.write_text(json.dumps({'opener': opener}))
    notes, sent = [], []
    class Stage:
        note = lambda self, msg: notes.append(msg)
        work = lambda self, msg: None
    with ExitStack() as stack:
        import handoff
        stack.enter_context(patch.object(handoff, 'episode_link_for', lambda *_: 'EPISODE'))
        stack.enter_context(patch.object(SL.up, 'resumable_upload', lambda *args: sent.append(args) or 'NEW'))
        stack.enter_context(patch.object(SL.P, 'set_privacy', lambda *a, **k: None))
        stack.enter_context(patch.object(SL.P, 'read_status', lambda *_: {'privacy': 'private'}))
        stack.enter_context(patch.object(SL.time, 'sleep', lambda *_: None))
        stack.enter_context(patch.object(SL, 'load_ledger', lambda: {'published': []}))
        stack.enter_context(patch.object(SL, 'save_ledger', lambda *_: None))
        stack.enter_context(patch.object(SL.quota, 'spend', lambda *_: None))
        stack.enter_context(patch.object(SL, 'build_payload', lambda *a, **k: {'snippet': {'title': k['title']}}))
        at = datetime.now(timezone.utc)
        assert SL.upload_short(Stage(), '', 'x', '', path, at) == '' and not sent
        receipt.write_text(json.dumps({'opener': opener, 'master_footage': evidence(master)}))
        assert SL.upload_short(Stage(), '', 'x', '', path, at) == 'NEW' and len(sent) == 1

    # A withdrawn cut is eligible again and is not kept until its source
    # evidence matches the new master. No live ledger or YouTube writes.
    ledger = {'published': [{'slug': 'x', 'file': path.name, 'withdrawn_at': at.isoformat()}]}
    receipt.write_text(json.dumps({'opener': opener}))
    with patch.object(SL, 'load_ledger', lambda: ledger), patch.object(SL, 'cuts_for', lambda *_: 1):
        assert SL.cut_groups(root / 'renders', root / 'shorts') == {1: ['x']}
        receipt.write_text(json.dumps({'opener': opener, 'master_footage': evidence(master)}))
        assert SL.cut_groups(root / 'renders', root / 'shorts') == {}

    # Cloud selection also refuses the old receipt before spending quota.
    import r2
    class Shelf:
        def __init__(self):
            self.objects = {}
        def put(self, source, key):
            self.objects[key] = Path(source).read_bytes()
        def head(self, key):
            return {'bytes': len(self.objects[key])} if key in self.objects else None
        def get(self, key, dest):
            Path(dest).write_bytes(self.objects[key])
    shelf = Shelf()
    shelf.put(path, r2.short_key('x'))
    receipt.write_text(json.dumps({'opener': opener}))
    shelf.put(receipt, r2.short_receipt_key('x'))
    look = SC.shelf_lookup(shelf)
    assert look('x') is not True and look.no_footage == ['x']
    receipt.write_text(json.dumps({'opener': opener, 'master_footage': evidence(master)}))
    shelf.put(receipt, r2.short_receipt_key('x'))
    assert SC.shelf_lookup(shelf)('x') is True

    row = {'slug': 'x', 'uploaded_at': at.isoformat(), 'withdrawn_at': at.isoformat()}
    assert SL.published_trailing({'published': [row]}, at=at) == 0
print('PASS: no-footage masters yield no Short; footage masters yield a cut and upload; withdrawn rows do not count')
