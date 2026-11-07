# Retention checkpoint

**1m55s average view duration** across 35 measured video(s), against a 146.0s floor. That is 19.6% of each video's own measured duration (34 of 35 measured).


## What the loop is doing about it

Opening rule in force: **stake-then-payoff** (loop/opening.py). Every script drafted from 2026-09-28 on must land its payoff in the first 30 seconds; a draft that does not is redrafted automatically. Published videos are untouched.

Measurement: stake-then-payoff vs pre-rule by average view duration, compared on None. If it is not ahead, the lane switches to the next variant itself and logs it. This week: wait - not yet decidable: 2 published video(s) carry stake-then-payoff (in force since 2026-10-13); the comparison with pre-rule is set 28 days after the 3rd one airs, and every newly authored script carries it.

| opening | measured videos | average view duration |
|---|---|---|
| pre-rule | 36 | 112.5s |
