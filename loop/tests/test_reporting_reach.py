"""Fixture-only reach ingestion and negative controls for median judging."""
import copy
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demand as D
import reach as R

DAY = date(2026, 11, 2)
HEADER = 'date,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n'


class API:
    def __init__(self):
        self.job_list = []
        self.created = 0
        self.downloads = []
        self.data = HEADER + '20261101,V,100,2\n20261101,V,300,6\n20261101,S,900,99\n20261001,V,1000,99\n'
        self.available = True

    def jobs(self):
        return self.job_list

    def create(self):
        self.created += 1
        self.job_list = [{'id': 'job', 'reportTypeId': R.REPORT_TYPE}]
        return self.job_list[0]

    def reports(self, job):
        return ([{'id': 'r', 'startTime': '2026-11-01', 'endTime': '2026-11-02',
                  'createTime': '2026-11-02', 'downloadUrl': 'fixture'}] if self.available else [])

    def download(self, url):
        self.downloads.append(url)
        return self.data


class ReachTests(unittest.TestCase):
    def test_weighted_window_exclusions_rerun_and_expiry(self):
        api, doc = API(), {'videos': {}}
        with patch.object(D, 'longform_rows', return_value=[{'video_id': 'V'}, {'video_id': 'S'}]), patch.object(D, 'short_ids', return_value={'S'}):
            rows = R.ingest(api, doc, DAY)
            self.assertEqual(rows[0]['impressions'], 400)
            self.assertEqual(rows[0]['ctr_pct'], 5)
            self.assertNotIn('S', doc['videos'])
            self.assertEqual(R.ingest(api, doc, DAY), rows)
            self.assertEqual(api.created, 1)
            self.assertEqual(len(api.downloads), 1)
            R.ingest(api, doc, DAY + timedelta(days=29))
            self.assertEqual(doc['videos']['V']['ctr'], D.UNKNOWN)

    def test_empty_duplicate_and_malformed(self):
        api = API()
        api.available = False
        notes = []
        R.ingest(api, {}, DAY, notes.append)
        self.assertTrue(notes)
        api.job_list *= 2
        with self.assertRaises(ValueError):
            R.ingest(api, {}, DAY)
        api.job_list = api.job_list[:1]
        api.available = True
        api.data = 'wrong,columns\n1,2\n'
        with self.assertRaises(ValueError):
            R.ingest(api, {}, DAY)

    def test_reissued_report_replaces_old_range(self):
        api, doc = API(), {}
        with patch.object(D, 'longform_rows', return_value=[{'video_id': 'V'}]), patch.object(D, 'short_ids', return_value=set()):
            R.ingest(api, doc, DAY)
            original = api.reports('job')[0]
            api.data = HEADER + '20261101,V,200,8\n'
            with patch.object(api, 'reports', return_value=[original, dict(original, id='new', createTime='2026-11-03')]):
                rows = R.ingest(api, doc, DAY)
            self.assertEqual(rows[0]['impressions'], 200)
            self.assertEqual(rows[0]['ctr_pct'], 8)

    def test_missing_scope_stops_before_api(self):
        import upload
        from common import NamedStop
        class Stop:
            def named_stop(self, code, message, unblock):
                self.code, self.unblock = code, unblock
                raise RuntimeError('stopped')
        stop = Stop()
        with patch.object(upload, 'load_credentials', return_value={'source': 'secrets', 'scopes': []}), patch.object(upload, 'access_token') as token:
            with self.assertRaises(RuntimeError):
                D._api(stop)
            token.assert_not_called()
        self.assertEqual(stop.code, 'OAUTH_REJECTED')
        self.assertIn('auth/youtube_auth.py', stop.unblock)

    def test_pagination(self):
        api = R.Reporting('fixture')
        with patch.object(api, 'request', side_effect=['{"jobs": [{"id":"a"}], "nextPageToken":"next"}', '{"jobs": [{"id":"b"}]}']) as call:
            self.assertEqual([j['id'] for j in api.jobs()], ['a', 'b'])
            self.assertIn('pageToken=next', call.call_args.args[0])

    def test_judge_uses_topic_then_channel_and_sample_not_views(self):
        def video(i, pct, topic):
            return {'video_id': str(i), 'public': True, 'domain': topic,
                    'ctr': {'pct': pct, 'impressions': 100},
                    'current': {'views': 1, 'avp_pct': 20, 'retention_30s_pct': 20},
                    'lifetime': {'views': 1, 'watch_minutes': 1}}
        videos = [video(i, pct, 'a') for i, pct in enumerate([1, 2, 3, 4, 5])]
        videos += [video(5, 40, 'b'), video(6, 50, 'b')]
        doc = {'videos': {v['video_id']: v for v in videos}}
        with patch('longform_title.load', return_value={'titles': {}}):
            D.judge(doc, DAY)
            self.assertEqual(videos[3]['ctr_baseline']['pct'], 3)
            self.assertEqual(videos[3]['floors']['ctr'], 'pass')
            self.assertEqual(videos[5]['ctr_baseline']['pct'], 4)
            self.assertEqual(videos[0]['verdict'], 'FAIL')
            videos[0]['ctr']['impressions'] = 99
            D.judge(doc, DAY)
            self.assertEqual(videos[0]['verdict'], 'INSUFFICIENT')
            self.assertEqual(videos[3]['ctr_baseline']['pct'], 4.5)
            videos[0]['ctr'] = D.UNKNOWN
            videos[0]['current']['views'] = 30
            D.judge(doc, DAY)
            self.assertEqual(videos[0]['verdict'], 'FAIL')
            videos[0]['current']['views'] = 29
            D.judge(doc, DAY)
            self.assertEqual(videos[0]['verdict'], 'INSUFFICIENT')


if __name__ == '__main__':
    unittest.main()
