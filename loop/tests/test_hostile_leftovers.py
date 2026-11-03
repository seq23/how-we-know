"""Behavior coverage for withdrawn inventory, food dates, quota and picture time."""
import os
os.environ['LOOP_DRY_RUN'] = '1'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import contextlib
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import backfill, batch_queue, ledger, lengthen, shorts_lane, food_author
import tags_backfill as tags
import picture_time


class Leftovers(unittest.TestCase):
    def test_withdrawn_inventory(self):
        rows = [{'slug': 'cut', 'video_id': 'old', 'withdrawn_at': '2026-11-02'},
                {'slug': 'live', 'video_id': 'live'}]
        with contextlib.ExitStack() as st:
            st.enter_context(patch.object(ledger, 'load', return_value={'published': rows}))
            st.enter_context(patch.object(batch_queue, 'queued_entries', return_value=[{'slug': 'cut'}, {'slug': 'live'}]))
            st.enter_context(patch.object(backfill.render_gate if hasattr(backfill, 'render_gate') else __import__('render_gate'), 'held_slugs', return_value=set()))
            st.enter_context(patch.object(backfill, 'food_hold', return_value=None))
            st.enter_context(patch.object(lengthen, 'upload_hold', return_value=None))
            self.assertEqual(ledger.published_slugs(), {'live'})
            self.assertEqual(lengthen.published_slugs(), {'live'})
            self.assertEqual(set(batch_queue._published_questions()), {'live'})
            self.assertEqual([r[0] for r in backfill.library_pending(assets=lambda s: ('render', 'thumb'))], ['cut'])

    def test_food_waits_for_date_even_after_render(self):
        import domains
        with tempfile.TemporaryDirectory() as td, contextlib.ExitStack() as st:
            root = Path(td)
            food = root / 'food'; food.mkdir()
            specs = root / 'specs'; specs.mkdir()
            slug = 'combined-food'
            (food / f'{slug}.md').write_text(food_author.LANE_MARK)
            (specs / f'{slug}.json').write_text('{}')
            order = root / 'order.json'; order.write_text('{}')
            st.enter_context(patch.multiple(food_author, FOOD_DIR=food, SPECS=specs, ORDER=order))
            st.enter_context(patch.object(batch_queue, 'queued_entries', return_value=[{'slug': slug}]))
            st.enter_context(patch.object(shorts_lane, 'load_ledger', return_value={'published': []}))
            st.enter_context(patch.object(shorts_lane.render_gate, 'held_slugs', return_value=set()))
            st.enter_context(patch.object(shorts_lane, 'voice_blocked', return_value=set()))
            st.enter_context(patch.object(domains, 'domain_of_slug', return_value='food-science'))
            st.enter_context(patch.object(shorts_lane, 'cuts_for', return_value=1))
            st.enter_context(patch.object(shorts_lane, 'order_by_mix', side_effect=lambda out, **kw: out))
            for date, withdrawn, expected in [(None, False, False), ('2026-11-03T10:00:00Z', True, False), ('2026-11-03T10:00:00Z', False, True)]:
                row = {'slug': slug, 'scheduled_publish_at': date}
                if withdrawn: row['withdrawn_at'] = '2026-11-02'
                with patch.object(ledger, 'load', return_value={'published': [row]}):
                    self.assertEqual(bool(shorts_lane.pending(have=lambda *a: True, cfg={})), expected)
                    self.assertEqual(food_author.in_flight(), [] if expected else [slug])

    def test_tags_leave_reserve_unspent(self):
        read, update = tags.quota.VIDEO_READ, tags.quota.VIDEO_UPDATE
        for available, expected in [(1000 + read + update - 1, 0), (1000 + read + update, 1)]:
            with contextlib.ExitStack() as st:
                stage = MagicMock(); stage.__enter__.return_value = stage
                st.enter_context(patch.object(tags, 'Stage', return_value=stage))
                st.enter_context(patch.object(tags, 'config', return_value={}))
                st.enter_context(patch.object(tags.ytmeta, 'live_videos', return_value=[{'slug': str(i), 'video_id': str(i)} for i in range(3)]))
                st.enter_context(patch.object(tags, '_shorts_live', return_value=[]))
                st.enter_context(patch.object(tags, 'wanted_for_episode', return_value=(['tag'], ['hash'])))
                st.enter_context(patch.object(tags.up, 'load_credentials', return_value={'ok': True}))
                st.enter_context(patch.object(tags.up, 'access_token', return_value='fixture'))
                st.enter_context(patch.object(tags.quota, 'remaining', return_value=available))
                st.enter_context(patch.object(tags.quota, 'deferrable_reserve', return_value=1000))
                spend = st.enter_context(patch.object(tags.quota, 'spend'))
                get = st.enter_context(patch.object(tags.ytmeta, 'get_video', return_value={'snippet': {'title': 'Q', 'description': '', 'categoryId': '27'}}))
                put = st.enter_context(patch.object(tags.urllib.request, 'urlopen', return_value=MagicMock()))
                tags.run(dry_run=False)
                self.assertEqual(put.call_count, expected)
                self.assertEqual(get.call_count, expected)
                consumed = spend.call_args.args[0] if spend.called else 0
                self.assertEqual(consumed, expected * (read + update))
                self.assertGreaterEqual(available - consumed, 1000)

    def test_picture_time_preserves_voice_and_caption_gaps(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'visuals'))
        import captions
        plan = [{'narration': 'Opening', 'picture_target_s': 900}, {'narration': 'Evidence'}, {'narration': 'Closing'}]
        spoken = [20., 400., 80.]
        timeline, holds = picture_time.apply(plan, spoken)
        self.assertEqual(sum(timeline), 900)
        self.assertEqual(holds[0], 0)
        self.assertEqual(spoken, [20., 400., 80.])
        timed = [{**b, 'imagery_only_s': h} for b, h in zip(plan, holds)]
        cues = captions.build_cues(timed, timeline)
        self.assertEqual(cues[1]['end'], 420)
        self.assertEqual(cues[2]['start'], 620)
        self.assertEqual(cues[2]['end'], 700)
        self.assertEqual(picture_time.apply([{}], [950])[0], [950])
        self.assertEqual(picture_time.apply([{}], [50])[0], [50])

    def test_assembly_inserts_silence_between_existing_wavs(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'visuals'))
        import assemble, plan_domain, longform_picture as LP
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plan = [{'narration': 'Same words', 'seconds': d, 'picture_target_s': 900}
                    for d in [20, 400, 80]]
            plan_file = root / 'plan.json'; plan_file.write_text(json.dumps(plan))
            audio = root / 'audio'; audio.mkdir()
            for i in range(3): (audio / f'{i:04d}.wav').write_bytes(b'original')
            def probe(path):
                return [20, 400, 80][int(Path(path).stem)] if str(path).endswith('.wav') else 900
            with patch.object(assemble, 'probe', side_effect=probe), \
                 patch.object(plan_domain, 'foreign', return_value=[]), \
                 patch.object(LP, 'subject_clips', return_value=[]), \
                 patch.object(LP, 'subject_photos', return_value=[{'local_file': 'p.jpg', 'title': 'p'}]), \
                 patch.object(LP, 'render_shot', side_effect=lambda s, out, n: out) as shots, \
                 patch.object(assemble, 'write_picture_record'), \
                 patch.object(assemble.subprocess, 'run') as run:
                result = assemble.assemble(str(plan_file), str(root / 'out.mp4'),
                                           audio_dir=str(audio), music=False, frame_check=False)
            # The picture covers the padded beats (20 + 600 + 280 s), every frame.
            self.assertEqual(sum(c.args[2] for c in shots.call_args_list), 900 * assemble.FPS)
            pads = [c.args[0] for c in run.call_args_list if '-af' in c.args[0]]
            self.assertEqual([cmd[cmd.index('-af') + 1] for cmd in pads],
                             ['apad=pad_dur=0.0', 'apad=pad_dur=200.0', 'apad=pad_dur=200.0'])
            self.assertEqual(result['duration_s'], 900)
            self.assertEqual([p.read_bytes() for p in sorted(audio.glob('*.wav'))], [b'original'] * 3)

if __name__ == '__main__':
    unittest.main()
