# Retention checkpoint

**1m51s average view duration** across 18 measured video(s), against a 146.0s floor. That is 21.5% of each video's own measured duration (16 of 18 measured).

## The format is wrong, not the topics

11 of 18 videos lose the average viewer inside the first 2.0 minutes.

Viewers are leaving before the first real explanation lands. That is not a topic-selection problem and better ranking will not fix it - the same thing will happen to the next four videos.

**What this invalidates:** the cold-open-then-method structure, or the opening - not the runtime. The 10-minute floor is an owner decision and a longer video that holds is MORE watch time, not less; the fix is moving the concrete payoff into the first 30 seconds, never a shorter cut.

This is the one finding that should stop the content design being treated as settled.

## What the loop is doing about it

Opening rule in force: **cold-open-payoff** (loop/opening.py). Every script drafted from 2026-09-28 on must land its payoff in the first 30 seconds; a draft that does not is redrafted automatically. Published videos are untouched.

Measurement: cold-open-payoff vs pre-rule by average view duration, compared on 2026-10-26. If it is not ahead, the lane switches to the next variant itself and logs it. This week: wait - cold-open-payoff in force since 2026-09-28; compared with pre-rule on 2026-10-26.

| opening | measured videos | average view duration |
|---|---|---|
| pre-rule | 20 | 100.0s |
