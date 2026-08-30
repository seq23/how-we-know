"""Read-only credential status. Safe to run any time; changes nothing.

    .venv/bin/python auth/check_auth.py          # human-readable
    .venv/bin/python auth/check_auth.py --json   # for the loop

The loop's upload lane calls this before attempting anything, so a broken
credential surfaces as a sentence naming the fix rather than as a failed
publish at 02:00 on a Thursday.

Exit codes follow the loop's contract:
    0  credentials are usable
    3  NAMED STOP — a known, named, actionable credential state

On quota: Google publishes **no API for remaining quota.** The console shows it
and nothing else does. Rather than invent a number, this reports the daily
allowance and what an upload costs, and points at the console. A fabricated
quota figure would be worse than none.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tokens as T  # noqa: E402

# Documented costs, not measured values.
DAILY_UNITS = 10_000
UPLOAD_COST = 1_600      # videos.insert
LIST_COST = 1            # channels.list / videos.list
UPDATE_COST = 50         # videos.update — the public flip


def status() -> dict:
    out: dict = {
        "client_secret_present": T.CLIENT_FILE.exists(),
        "token_present": T.TOKEN_FILE.exists(),
        "api_key_present": T.API_KEY_FILE.exists(),
        "secrets_dir": str(T.SECRETS),
    }
    res = T.load()
    out["status"] = res["status"]
    out["refresh_token_age_days"] = res.get("refresh_token_age_days")
    if res.get("detail"):
        out["detail"] = res["detail"]

    if res["status"] != "ok":
        out["usable"] = False
        out["oauth_error"] = res.get("oauth_error")
        msg = T.stop_message(res["status"])
        if res["status"] == "error":
            msg += "\n  " + T.error_message(res.get("oauth_error"))
        out["message"] = msg
        return out

    ch = T.channel(res["access_token"])
    out["usable"] = ch["ok"]
    out["channel"] = {k: v for k, v in ch.items() if k != "ok"}
    if ch["ok"] and not ch["matches_expected"]:
        out["usable"] = False
        out["status"] = "wrong_channel"
        out["message"] = (
            f"Authorised as {ch['handle'] or ch['title']}, expected "
            f"{T.EXPECTED_HANDLE}. Uploads would go to the wrong channel. "
            f"Revoke at myaccount.google.com/permissions, delete "
            f"{T.TOKEN_FILE.name}, re-run auth/youtube_auth.py.")

    age = out.get("refresh_token_age_days")
    if age is not None and age >= 6:
        out["warning"] = (
            f"The refresh token is {age} days old. A project in Testing mode "
            f"expires them at 7 days. Publish the app on the OAuth consent "
            f"screen, or re-run auth/youtube_auth.py.")

    out["quota"] = {
        "remaining": None,
        "why": "Google exposes no API for remaining quota; only the Cloud "
               "console shows it. No number is invented here.",
        "daily_units": DAILY_UNITS,
        "cost_per_upload": UPLOAD_COST,
        "cost_per_public_flip": UPDATE_COST,
        "cost_per_list": LIST_COST,
        "weekly_need_at_4_videos": 4 * (UPLOAD_COST + UPDATE_COST + LIST_COST),
        "headroom": f"4 uploads/week is {4 * UPLOAD_COST} of {DAILY_UNITS} "
                    f"units in one day — comfortable, but 6 uploads in a day "
                    f"would exceed it.",
        "console": "console.cloud.google.com → APIs & Services → YouTube Data "
                   "API v3 → Quotas",
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    s = status()

    if a.json:
        print(json.dumps(s, indent=2))
        return 0 if s.get("usable") else 3

    print("\n" + "=" * 64)
    print("  YouTube credential status")
    print("=" * 64)
    print(f"  client_secret.json : {'present' if s['client_secret_present'] else 'ABSENT'}")
    print(f"  youtube_token.json : {'present' if s['token_present'] else 'ABSENT'}")
    print(f"  api key file       : {'present' if s['api_key_present'] else 'absent (optional)'}")
    print(f"  status             : {s['status']}")

    if not s.get("usable"):
        print("\n" + "-" * 64)
        print(f"  NAMED STOP  [{s['status'].upper()}]")
        print("-" * 64)
        print("  " + (s.get("message", "") or "").replace("\n", "\n  "))
        print("=" * 64 + "\n")
        return 3

    ch = s["channel"]
    print(f"\n  channel            : {ch['title']}  {ch['handle']}")
    print(f"  channel id         : {ch['id']}")
    print(f"  videos / subs      : {ch['videos']} / {ch['subscribers']}")
    age = s.get("refresh_token_age_days")
    print(f"  refresh token age  : {age if age is not None else 'unknown'} day(s)")
    if s.get("warning"):
        print(f"\n  ! {s['warning']}")

    q = s["quota"]
    print(f"\n  quota remaining    : not obtainable via API — {q['console']}")
    print(f"  daily allowance    : {q['daily_units']} units")
    print(f"  one upload costs   : {q['cost_per_upload']} units")
    print(f"  one public flip    : {q['cost_per_public_flip']} units")
    print(f"  this loop needs    : {q['weekly_need_at_4_videos']} units/week")
    print("\n  ✓ credentials usable; the upload lane may run.")
    print("=" * 64 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
