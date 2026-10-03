"""The Short → episode hand-off, proven against a fake YouTube client.

Owner decision 2026-10-03: ~2,400 of 2,588 views came from 34 Shorts, the
episodes had 149. loop/handoff.py gives every live Short a first-line link to
its episode, one channel comment, puts a Shorts block on every live episode
and keeps two domain playlists complete. This proves, with no network and no
credential (LOOP_DRY_RUN=1, every ledger path pointed at scratch):

  1. a public Short of a public episode gets its description rewritten to
     open with the link, EXACTLY ONE channel comment, ONE playlist row each
     for the Short and the episode, the episode's Shorts block, and the two
     playlists created once — every one recorded on its ledger row;
  2. a second run with nothing changed writes NOTHING and takes the
     self-resolving HANDOFF_UP_TO_DATE stop (exit 0);
  3. a Short whose episode is still private is marked `handoff: pending` with
     no write, and becomes `done` — link written, comment posted — the run
     after the episode goes public;
  4. --dry-run reads, plans and writes nothing: no API write, no ledger byte;
  5. a day with no quota left applies nothing and takes HANDOFF_QUOTA_DEFERRED
     (exit 0) with the deferred ids recorded for V46;
  6. the channel-comment gate in loop/comments.py refuses a record with no
     source, a foreign video id and a second comment on the same video, each
     before any write; and the NEGATIVE proof — with the gate line removed the
     unbacked comment IS written;
  7. V46 fails on a settled Short without its hand-off and on a live video
     outside its playlist, passes on the recorded state, and is a green named
     stop while the lane has the item recorded as quota-deferred;
  8. shorts_lane.build_payload puts the link first when handed an episode id
     and leaves the payload as it was when not.

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import io
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

os.environ["LOOP_DRY_RUN"] = "1"                 # never a credential, never a real write
tmp = Path(tempfile.mkdtemp(prefix="handoff-test-"))
os.environ.setdefault("LOOP_STOPS_DIR", str(tmp / "stops"))
(tmp / "stops").mkdir(exist_ok=True)

import comments as C          # noqa: E402
import handoff as H           # noqa: E402
import ledger as L            # noqa: E402
import quota as Q             # noqa: E402
import shorts_lane as SL      # noqa: E402
import validate as V          # noqa: E402

# ---- every path the stage and the validator touch goes to scratch ----------
L.LEDGER = tmp / "ledger.json"
H.SHORTS_LEDGER = tmp / "shorts_ledger.json"
H.PLAYLISTS = tmp / "playlists.json"
H.HANDOFF_STATE = tmp / "handoff.json"
C.LEDGER = tmp / "comments_ledger.json"
C.SHORTS_LEDGER = H.SHORTS_LEDGER
C.COMMENTS_DIR = tmp
Q.STATE = tmp / "quota.json"
V.SHORTS_LEDGER_PATH = H.SHORTS_LEDGER
V.PLAYLISTS_STATE = H.PLAYLISTS
V.HANDOFF_STATE = H.HANDOFF_STATE

# Real slugs, one per allocated domain: domain_of_slug reads scripts/<slug>.md.
DEEP = "14-how-big-is-a-colossal-squid"
MAT = "how-strong-is-titanium"
for slug in (DEEP, MAT):
    assert (ROOT / "scripts" / f"{slug}.md").exists(), slug

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")
    else:
        print(f"  ok   {name}")


def iso(days: int) -> str:
    return (_dt.datetime.now(_dt.timezone.utc)
            + _dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- the fake YouTube ------------------------------------------------------

class FakeTube:
    def __init__(self, videos: dict, refuse_sections: bool = False):
        self.videos = videos                 # id -> {privacy, publishAt, snippet}
        self.playlists: dict[str, str] = {}  # id -> title
        self.items: dict[str, list] = {}     # playlist id -> [(item id, video id)]
        self.sections: list = []
        self.calls: list = []
        self.n = 0
        self.refuse_sections = refuse_sections

    def _id(self, prefix):
        self.n += 1
        return f"{prefix}{self.n}"

    def api_get(self, path, params):
        self.calls.append(("GET", path))
        if path == "videos":
            return {"items": [{"id": i, "status": {"privacyStatus": v["privacy"],
                                                   "publishAt": v.get("publishAt")},
                               "snippet": dict(v["snippet"])}
                              for i, v in self.videos.items()
                              if i in params["id"].split(",")]}
        if path == "playlists":
            return {"items": [{"id": i, "snippet": {"title": t}}
                              for i, t in self.playlists.items()]}
        if path == "playlistItems":
            return {"items": [{"id": iid, "snippet": {"resourceId": {"videoId": v}}}
                              for iid, v in self.items.get(params["playlistId"], [])]}
        raise AssertionError(f"unexpected GET {path}")

    def api_put(self, path, params, body):
        self.calls.append(("PUT", path, body))
        assert path == "videos"
        assert body["snippet"].get("title") and body["snippet"].get("categoryId")
        self.videos[body["id"]]["snippet"] = dict(body["snippet"])
        return body

    def api_post(self, path, params, body):
        self.calls.append(("POST", path, body))
        if path == "playlists":
            pid = self._id("PL")
            self.playlists[pid] = body["snippet"]["title"]
            self.items[pid] = []
            return {"id": pid}
        if path == "playlistItems":
            pid = body["snippet"]["playlistId"]
            vid = body["snippet"]["resourceId"]["videoId"]
            iid = self._id("PLI")
            self.items.setdefault(pid, []).append((iid, vid))
            return {"id": iid}
        if path == "channelSections":
            if self.refuse_sections:
                raise urllib.error.HTTPError(
                    "u", 403, "forbidden", {},
                    io.BytesIO(b'{"error":{"message":"channelSections insufficient"}}'))
            sid = self._id("SEC")
            self.sections.append((sid, body["contentDetails"]["playlists"][0]))
            return {"id": sid}
        raise AssertionError(f"unexpected POST {path}")

    def writes(self):
        return [c for c in self.calls if c[0] in ("PUT", "POST")]


comment_writes: list = []


def fake_write(token, path, params, body):
    comment_writes.append((path, body))
    return {"id": f"thread{len(comment_writes)}",
            "snippet": {"topLevelComment": {"id": f"cmt{len(comment_writes)}"}}}


C._write = fake_write


def seed(ep_privacy: dict, short_privacy: dict) -> FakeTube:
    """Two episodes, two Shorts, fresh ledgers; privacy per id."""
    for p in (L.LEDGER, H.SHORTS_LEDGER, H.PLAYLISTS, H.HANDOFF_STATE,
              C.LEDGER, Q.STATE):
        if p.exists():
            p.unlink()
    comment_writes.clear()
    eps = [{"slug": DEEP, "question": "how big is a colossal squid", "video_id": "EP1",
            "uploaded_at": iso(-30), "privacy": "private",
            "scheduled_publish_at": iso(-20)},
           {"slug": MAT, "question": "how strong is titanium", "video_id": "EP2",
            "uploaded_at": iso(-30), "privacy": "private",
            "scheduled_publish_at": iso(-10)}]
    shorts = [{"slug": DEEP, "video_id": "SH1", "file": "a.mp4", "uploaded_at": iso(-25),
               "privacy": "private", "scheduled_publish_at": iso(-24), "rank": 1,
               "lane": "shorts-cloud"},
              {"slug": MAT, "video_id": "SH2", "file": "b.mp4", "uploaded_at": iso(-12),
               "privacy": "private", "scheduled_publish_at": iso(-11), "rank": 1,
               "lane": "shorts-cloud"}]
    L.save({"published": eps, "queued": [], "updated": None})
    H.save_shorts({"published": shorts, "updated": None})
    snip = lambda t, d: {"title": t, "description": d, "tags": ["x"],  # noqa: E731
                         "categoryId": "27", "defaultLanguage": "en"}
    videos = {
        "EP1": {"privacy": ep_privacy["EP1"], "publishAt": iso(-20),
                "snippet": snip("How big is a colossal squid?",
                                "Answer.\n\nSources — every figure in this video traces to one of these:\n• NOAA\n\nEvidence-first explainers.\n\n#Squid #DeepSea #HowWeKnow")},
        "EP2": {"privacy": ep_privacy["EP2"], "publishAt": iso(-10),
                "snippet": snip("How strong is titanium?",
                                "Answer.\n\nEvidence-first explainers.\n\n#Titanium #Materials #HowWeKnow")},
        "SH1": {"privacy": short_privacy["SH1"], "publishAt": iso(-24),
                "snippet": snip("How big is a colossal squid?",
                                "Evidence-first answers from the deep sea. This is one chapter.\n\nFull episodes: https://youtube.com/@howweknowdeep\nhowweknowdeep.com\n\n#Squid #Shorts")},
        "SH2": {"privacy": short_privacy["SH2"], "publishAt": iso(-11),
                "snippet": snip("How strong is titanium?",
                                "Materials blurb. This is one chapter.\n\nFull episodes: https://youtube.com/@howweknowdeep\nhowweknowdeep.com\n\n#Titanium #Shorts")},
    }
    return FakeTube(videos)


def run(yt, dry_run=False) -> tuple[int, str]:
    """handoff.run() inside this process; Stage ends a stop with sys.exit."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        try:
            rc = H.run(dry_run=dry_run, yt=yt, token="fake-token")
        except SystemExit as e:
            rc = int(e.code or 0)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


def shorts_rows() -> dict:
    return {r["video_id"]: r for r in H.load_shorts()["published"]}


def ep_rows() -> dict:
    return {r["video_id"]: r for r in L.load()["published"]}


# =============================================================== 1. the full pass
print("1. public Short, public episode: link, comment, block, playlists")
yt = seed({"EP1": "public", "EP2": "public"}, {"SH1": "public", "SH2": "public"})
rc, out = run(yt)
check("run exits 0 with work", rc == 0 and "HANDOFF_UP_TO_DATE" not in out, f"rc={rc}\n{out[-800:]}")
sh, ep = shorts_rows(), ep_rows()
d1 = yt.videos["SH1"]["snippet"]["description"]
check("Short description opens with the episode link and question",
      d1.split("\n")[0] == "Full episode: https://youtu.be/EP1 — How big is a colossal squid?", d1)
check("the rest of the Short's description is kept, hashtag line last",
      "Full episodes: https://youtube.com/@howweknowdeep" in d1 and d1.endswith("#Squid #Shorts"), d1)
check("Short rows are handoff: done with the episode id",
      all(sh[v].get("handoff") == "done" and sh[v].get("handoff_episode") == e
          for v, e in (("SH1", "EP1"), ("SH2", "EP2"))), json.dumps(sh)[:400])
check("exactly one channel comment per Short", len(comment_writes) == 2
      and all(p == "commentThreads" for p, _ in comment_writes), str(comment_writes))
check("the comment carries the question and the episode link",
      comment_writes[0][1]["snippet"]["topLevelComment"]["snippet"]["textOriginal"]
      == "How big is a colossal squid? Full episode: https://youtu.be/EP1", str(comment_writes[0]))
check("comment ids recorded on the Short rows",
      sh["SH1"].get("handoff_comment_id") == "cmt1" and sh["SH2"].get("handoff_comment_id") == "cmt2",
      json.dumps({k: v.get("handoff_comment_id") for k, v in sh.items()}))
cl = C.load_ledger()
check("comments ledger holds the channel comment as own_channel with the instruction source",
      cl["channel_comments"].get("SH1", {}).get("source") == H.INSTRUCTION["source"]
      and cl["seen"].get("cmt1", {}).get("class") == C.OWN_CLASS
      and any(a["action"] == "channel_comment" for a in cl["actions"]), json.dumps(cl)[:500])
e1 = yt.videos["EP1"]["snippet"]["description"]
check("episode description gains the Shorts block after the sources, before the hashtag line",
      "• NOAA\n\nEvidence-first explainers.\n\nShorts from this episode:\n• How big is a colossal squid? https://youtu.be/SH1\n\n#Squid #DeepSea #HowWeKnow" in e1, e1)
check("episode rows record the block", ep["EP1"].get("shorts_block") == ["SH1"]
      and ep["EP2"].get("shorts_block") == ["SH2"], json.dumps(ep)[:400])
pl = H.load_playlists()
check("two playlists created with the decided titles",
      sorted(yt.playlists.values()) == ["Deep Sea Science", "Materials & Manufacturing"]
      and {d: p["id"] for d, p in pl["playlists"].items()}.keys()
      == {"deep-sea-ocean-science", "materials-and-manufacturing"}, json.dumps(pl))
deep_pid = pl["playlists"]["deep-sea-ocean-science"]["id"]
mat_pid = pl["playlists"]["materials-and-manufacturing"]["id"]
check("each video inserted into its domain playlist exactly once",
      sorted(v for _, v in yt.items[deep_pid]) == ["EP1", "SH1"]
      and sorted(v for _, v in yt.items[mat_pid]) == ["EP2", "SH2"], json.dumps(yt.items))
check("playlist item ids recorded on every row",
      all(r.get("playlist_item_id") for r in [*sh.values(), *ep.values()]),
      json.dumps({k: v.get("playlist_item_id") for k, v in {**sh, **ep}.items()}))
check("one channel section per playlist, recorded",
      len(yt.sections) == 2 and all(pl["sections"][d].get("id") for d in pl["sections"]),
      json.dumps(pl["sections"]))
n_writes = len(yt.writes()) + len(comment_writes)
check("quota charged 50 per write plus the reads",
      Q._load()["spent"] == n_writes * 50 + sum(1 for c in yt.calls if c[0] == "GET"),
      f"spent={Q._load()['spent']} writes={n_writes}")

# ========================================================== 2. nothing to do
print("2. a second run writes nothing and is HANDOFF_UP_TO_DATE")
before = (len(yt.writes()), len(comment_writes))
rc, out = run(yt)
check("second run exits 0 with the self-resolving stop", rc == 0 and "HANDOFF_UP_TO_DATE" in out, out[-600:])
check("second run made no write", (len(yt.writes()), len(comment_writes)) == before)

# ======================================================= 3. pending -> done
print("3. a Short whose episode is not public yet waits, then is handed off")
yt = seed({"EP1": "private", "EP2": "public"}, {"SH1": "public", "SH2": "private"})
rc, out = run(yt)
sh = shorts_rows()
check("SH1 is pending, no description write for it",
      sh["SH1"].get("handoff") == "pending"
      and not any(c[0] == "PUT" and c[2]["id"] == "SH1" for c in yt.calls), json.dumps(sh["SH1"]))
check("SH1 has no comment while its episode is private",
      not any(b["snippet"]["videoId"] == "SH1" for _, b in comment_writes))
check("SH2 (scheduled, episode public) gets its link now but no comment until it is public",
      sh["SH2"].get("handoff") == "done" and yt.videos["SH2"]["snippet"]["description"].startswith(H.LINK_PREFIX + "EP2")
      and not any(b["snippet"]["videoId"] == "SH2" for _, b in comment_writes), json.dumps(sh["SH2"]))
check("a private Short is not put in the playlist yet",
      not any(v == "SH2" for items in yt.items.values() for _, v in items), json.dumps(yt.items))
yt.videos["EP1"]["privacy"] = "public"
yt.videos["SH2"]["privacy"] = "public"
rc, out = run(yt)
sh = shorts_rows()
check("after the episode goes public SH1 is done with its link written",
      sh["SH1"].get("handoff") == "done"
      and yt.videos["SH1"]["snippet"]["description"].startswith("Full episode: https://youtu.be/EP1 — "),
      yt.videos["SH1"]["snippet"]["description"][:120])
check("both comments now posted, once each",
      sorted(b["snippet"]["videoId"] for _, b in comment_writes) == ["SH1", "SH2"], str(comment_writes))
check("SH2 joins the playlist once public",
      sum(1 for items in yt.items.values() for _, v in items if v == "SH2") == 1, json.dumps(yt.items))
rc, out = run(yt)
check("and the next run is up to date again", "HANDOFF_UP_TO_DATE" in out and rc == 0, out[-400:])

# ============================================================== 4. dry run
print("4. --dry-run writes nothing")
yt = seed({"EP1": "public", "EP2": "public"}, {"SH1": "public", "SH2": "public"})
snap = {p: p.read_bytes() for p in (L.LEDGER, H.SHORTS_LEDGER) if p.exists()}
rc, out = run(yt, dry_run=True)
check("dry run exits 0 and prints the plan with its quota",
      rc == 0 and "write(s)" in out and "DRY RUN" in out and "short_desc" in out, out[-600:])
check("dry run made no API write", not yt.writes() and not comment_writes)
check("dry run changed no ledger byte and wrote no state",
      all(p.read_bytes() == b for p, b in snap.items())
      and not H.PLAYLISTS.exists() and not H.HANDOFF_STATE.exists() and not Q.STATE.exists())

# ========================================================== 5. no quota left
print("5. no quota: nothing applied, HANDOFF_QUOTA_DEFERRED, deferred ids recorded")
yt = seed({"EP1": "public", "EP2": "public"}, {"SH1": "public", "SH2": "public"})
from common import write_json as _wj                                     # noqa: E402
_wj(Q.STATE, {"day": Q._today(), "spent": Q.DAILY, "by_lane": {"cloud-upload": Q.DAILY}})
rc, out = run(yt)
check("exits 0 with HANDOFF_QUOTA_DEFERRED", rc == 0 and "HANDOFF_QUOTA_DEFERRED" in out, out[-600:])
check("no write was attempted", not yt.writes() and not comment_writes, str(yt.writes())[:300])
hs = json.loads(H.HANDOFF_STATE.read_text())
check("handoff.json records the deferred ids and the reset time",
      {"SH1", "SH2", "EP1", "EP2"} <= set(hs["deferred"]) and hs.get("resets_at"), json.dumps(hs))
check("the stop record carries resets_at (the policy requires it)",
      any("resets_at" in json.loads(p.read_text()).get("detail", {})
          for p in Path(os.environ["LOOP_STOPS_DIR"]).glob("*-handoff.json")))

# ====================================================== 6. the comment gate
print("6. the channel-comment gate")
yt = seed({"EP1": "public", "EP2": "public"}, {"SH1": "public", "SH2": "public"})
led = C.load_ledger()
for name, args in (("no source", ("SH1", "text", {**H.INSTRUCTION, "source": ""})),
                   ("no text", ("SH1", "  ", H.INSTRUCTION)),
                   ("foreign video", ("NOT_OURS", "text", H.INSTRUCTION))):
    try:
        C.post_channel_comment("tok", *args, led)
        check(f"gate refuses {name}", False, "no Unbacked raised")
    except C.Unbacked:
        check(f"gate refuses {name}", True)
check("refusals wrote nothing", not comment_writes)
cid = C.post_channel_comment("tok", "SH1", "Q? Full episode: https://youtu.be/EP1", H.INSTRUCTION, led)
try:
    C.post_channel_comment("tok", "SH1", "again", H.INSTRUCTION, led)
    check("gate refuses a second comment on the same video", False, "no Unbacked raised")
except C.Unbacked:
    check("gate refuses a second comment on the same video", True)
check("one write for the backed comment", len(comment_writes) == 1 and cid == "cmt1")
# negative proof: remove the gate line and the unbacked comment IS written
src = (LOOP / "comments.py").read_text()
needle = "    assert_channel_comment_backed(video_id, text, record, led)\n    out = _write("
check("the channel-comment gate line exists where the proof expects it", needle in src)
broken = src.replace(needle, "    pass\n    out = _write(")
bp = tmp / "comments_broken.py"
bp.write_text(broken)
spec = importlib.util.spec_from_file_location("comments_broken", bp)
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
bcalls: list = []
B._write = lambda *a: bcalls.append(a) or {"id": "t", "snippet": {"topLevelComment": {"id": "c"}}}
B.post_channel_comment("tok", "NOT_OURS", "text", {**H.INSTRUCTION, "source": ""}, C.load_ledger())
check("NEGATIVE PROOF: with the gate removed the unbacked channel comment IS written",
      len(bcalls) == 1, str(bcalls))

# ================================================================= 7. V46
print("7. V46 against planted state")
yt = seed({"EP1": "public", "EP2": "public"}, {"SH1": "public", "SH2": "public"})
r = V.v46_shorts_handoff()
check("V46 FAILS before the hand-off has run (settled Shorts, no playlists)",
      not r.ok and r.examined > 0 and any("does not open with the episode link" in f for f in r.failures),
      "\n".join(r.failures)[:600])
rc, out = run(yt)
r = V.v46_shorts_handoff()
check("V46 passes on the recorded state", r.ok and r.examined >= 6 and not r.stops,
      "\n".join(r.failures)[:600] or r.status)
# break one row each way, watch it fail, restore
doc = H.load_shorts()
doc["published"][0].pop("playlist_item_id")
H.save_shorts(doc)
r = V.v46_shorts_handoff()
check("V46 fails a live Short outside its playlist", not r.ok and any("not in its domain playlist" in f for f in r.failures))
doc["published"][0]["playlist_item_id"] = "PLI-x"
doc["published"][0]["handoff"] = "pending"
H.save_shorts(doc)
r = V.v46_shorts_handoff()
check("V46 fails a settled Short still pending on a settled episode",
      not r.ok and any("does not open with the episode link" in f for f in r.failures))
_wj(H.HANDOFF_STATE, {"last_run_at": H.now(), "deferred": ["SH1"], "resets_at": Q.next_reset()})
r = V.v46_shorts_handoff()
check("V46 is a GREEN named stop while the lane records the item as quota-deferred",
      r.ok and r.stops and r.stops[0]["code"] == "HANDOFF_AWAITING_QUOTA", r.status)
_wj(H.HANDOFF_STATE, {"last_run_at": "2026-01-01T00:00:00+00:00", "deferred": ["SH1"]})
r = V.v46_shorts_handoff()
check("a stale deferral (lane not running) does not excuse it", not r.ok)
doc["published"][0]["handoff"] = "done"
H.save_shorts(doc)
r = V.v46_shorts_handoff()
check("V46 passes again once restored", r.ok, "\n".join(r.failures)[:300])
for p in (L.LEDGER, H.SHORTS_LEDGER):
    p.unlink()
L.save({"published": [], "queued": [], "updated": None})
H.save_shorts({"published": [], "updated": None})
H.PLAYLISTS.unlink()
r = V.v46_shorts_handoff()
check("V46 with nothing live and no playlists fails rather than passing on an empty loop",
      not r.ok, r.status)
check("V46 is registered in validate.run_all",
      "v46_shorts_handoff()" in (LOOP / "validate.py").read_text().split("def run_all(")[1])

# ===================================================== 8. build_payload
print("8. shorts_lane.build_payload")
plain = SL.build_payload(DEEP, "how big is a colossal squid")
linked = SL.build_payload(DEEP, "how big is a colossal squid", episode_video_id="EP1")
check("without an episode id the payload is unchanged (channel link, no first-line link)",
      not plain["snippet"]["description"].startswith(H.LINK_PREFIX)
      and "Full episodes: https://youtube.com/@howweknowdeep" in plain["snippet"]["description"])
check("with an episode id the first line is the hand-off",
      linked["snippet"]["description"].split("\n")[0]
      == "Full episode: https://youtu.be/EP1 — How big is a colossal squid?"
      and linked["snippet"]["description"].endswith(plain["snippet"]["description"].split("\n")[-1]),
      linked["snippet"]["description"][:160])
check("everything but the description is identical",
      {k: v for k, v in plain["snippet"].items() if k != "description"}
      == {k: v for k, v in linked["snippet"].items() if k != "description"}
      and plain["status"] == linked["status"])
check("episode_link_for reads nothing under LOOP_DRY_RUN", H.episode_link_for("tok", DEEP) is None)
check("upload_short asks for the hand-off id and records the state",
      "handoff.episode_link_for(token, slug)" in (LOOP / "shorts_lane.py").read_text()
      and '"handoff": "done" if episode_id else "pending"' in (LOOP / "shorts_lane.py").read_text())

print(f"\n{examined} check(s), {len(fails)} failure(s)")
if examined == 0:
    print("FAIL: examined zero cases")
    sys.exit(1)
sys.exit(1 if fails else 0)
