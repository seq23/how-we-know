# Retention checkpoint

**2m10s average view duration** across 23 measured video(s), against a 146.0s floor. That is 23.6% of each video's own measured duration (23 of 23 measured).


## What the loop is doing about it

Opening rule in force: **stake-then-payoff** (loop/opening.py). Every script drafted from 2026-09-28 on must land its payoff in the first 30 seconds; a draft that does not is redrafted automatically. Published videos are untouched.

Measurement: stake-then-payoff vs pre-rule by average view duration, compared on 2026-12-10. If it is not ahead, the lane switches to the next variant itself and logs it. This week: wait - stake-then-payoff in force since 2026-10-13; its 3rd video airs 2026-11-12; compared with pre-rule on 2026-12-10.

| opening | measured videos | average view duration |
|---|---|---|
| pre-rule | 24 | 125.4s |
