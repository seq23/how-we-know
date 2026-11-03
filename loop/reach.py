"""Daily bulk reach ingestion. API contract: developers.google.com/youtube/reporting/v1.

Cache report aggregates in the demand snapshot so reruns need no downloads.
Reissued reports replace the same date range, rather than double counting it.
"""
from __future__ import annotations

import csv
import io
import json
import math
import urllib.parse
import urllib.request
from datetime import timedelta

BASE = 'https://youtubereporting.googleapis.com/v1'
REPORT_TYPE = 'channel_reach_basic_a1'
SCOPE = 'https://www.googleapis.com/auth/yt-analytics.readonly'


class Reporting:
    def __init__(self, token):
        self.token = token

    def request(self, url, body=None):
        # Never send the OAuth token to an arbitrary download host.
        host = urllib.parse.urlparse(url)
        if host.scheme != 'https' or not (host.hostname or '').endswith('.googleapis.com'):
            raise ValueError('untrusted reporting URL')
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                     headers={'Authorization': f'Bearer {self.token}',
                                              'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.read().decode('utf-8-sig')

    def items(self, path, key):
        page, out = '', []
        while True:
            query = '?' + urllib.parse.urlencode({'pageToken': page}) if page else ''
            data = json.loads(self.request(BASE + path + query))
            out.extend(data.get(key) or [])
            page = data.get('nextPageToken')
            if not page:
                return out

    def jobs(self):
        return self.items('/jobs', 'jobs')

    def create(self):
        return json.loads(self.request(BASE + '/jobs',
                          {'reportTypeId': REPORT_TYPE, 'name': 'Daily long-form reach'}))

    def reports(self, job):
        return self.items('/jobs/' + urllib.parse.quote(job, safe='') + '/reports', 'reports')

    def download(self, url):
        return self.request(url)


def ingest(api, doc, day, note=print):
    import demand as D
    jobs = [j for j in api.jobs() if j.get('reportTypeId') == REPORT_TYPE]
    if len(jobs) > 1:
        raise ValueError('multiple reach jobs exist; refusing to create or choose a duplicate')
    job = jobs[0] if jobs else api.create()
    state = doc.setdefault('reach', {'reports': {}})
    cache = state.setdefault('reports', {})
    reports = api.reports(job['id'])
    for report in sorted(reports, key=lambda r: (r['createTime'], r['id'])):
        if report['id'] in cache:
            continue
        reader = csv.DictReader(io.StringIO(api.download(report['downloadUrl'])))
        required = {'date', 'video_id', 'video_thumbnail_impressions',
                    'video_thumbnail_impressions_ctr'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('reach report missing required columns')
        daily = {}
        for row in reader:
            stamp = row['date']
            stamp = D._d(stamp) if '-' in stamp else D.datetime.strptime(stamp, '%Y%m%d').date()
            if stamp is None:
                raise ValueError('invalid reach date')
            n, pct = int(row['video_thumbnail_impressions']), float(row['video_thumbnail_impressions_ctr'])
            if n < 0 or not math.isfinite(pct) or not 0 <= pct <= 100:
                raise ValueError('invalid reach metric')
            key = stamp.isoformat() + '/' + row['video_id']
            agg = daily.setdefault(key, [0, 0.0])
            agg[0] += n
            agg[1] += n * pct
        cache[report['id']] = {'start': report['startTime'], 'end': report['endTime'],
                               'created': report['createTime'], 'daily': daily}
    if not reports:
        note('Reach: no reports yet; first reports can take up to 48h after job creation.')
    # Latest generated version wins for each covered interval, including empty reports.
    latest = {}
    for rid, r in cache.items():
        interval = (r['start'], r['end'])
        if interval not in latest or (r['created'], rid) > latest[interval][0]:
            latest[interval] = ((r['created'], rid), r)
    allowed = {r['video_id'] for r in D.longform_rows()} - D.short_ids()
    totals = {}
    start = day - timedelta(days=27)
    for _, report in latest.values():
        for key, (n, weighted) in report['daily'].items():
            stamp, vid = key.split('/', 1)
            if vid not in allowed or not start <= D._d(stamp) <= day:
                continue
            agg = totals.setdefault(vid, [0, 0.0])
            agg[0] += n
            agg[1] += weighted
    rows = []
    for vid in allowed:
        v = doc.setdefault('videos', {}).setdefault(vid, {'video_id': vid})
        n, weighted = totals.get(vid, (0, 0))
        if n:
            pct = weighted / n
            v['ctr'] = {'pct': pct, 'impressions': n, 'as_of': day.isoformat(), 'source': 'reporting'}
            rows.append({'date': day.isoformat(), 'video_id': vid, 'source': 'reporting',
                         'impressions': n, 'ctr_pct': pct})
        elif isinstance(v.get('ctr'), dict) and v['ctr'].get('source') == 'reporting':
            v['ctr'] = D.UNKNOWN
    state.update(job_id=job['id'], as_of=day.isoformat(), window_start=start.isoformat(), merged=len(rows))
    return rows
