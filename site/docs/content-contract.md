# Cross-Surface Content Contract

One admitted query produces one canonical evidence record, one article, one human-reviewed script and one published video. The article can exist before the video. The video cannot be marked published until its public metadata, final transcript, chapters, thumbnail, date, duration, and visible player are complete.

The canonical record is `content/questions.json`. Article rendering, direct answers, structured data, Watch status, video sitemap admission, and dormant video state all read from that record. Production documents may expand the explanation but may not silently change the canonical claim.

All ten initial video-queue records now map one-to-one to ten canonical question pages. The tenth query is no longer research-admission blocked.
