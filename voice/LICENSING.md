# Voice cloning engine — licence audit

Requirement: the narration is for a **monetised** YouTube channel, so the model
**weights** (not just the code) must permit commercial use. Several popular
cloning models ship permissive code with non-commercial weights — that is the
trap this audit exists to avoid.

Audited 2026-08-30.

| Tool | Code licence | **Weights licence** | Commercial? | Source |
|---|---|---|---|---|
| **Chatterbox** (Resemble AI) | MIT | **MIT** | **YES — chosen** | https://huggingface.co/ResembleAI/chatterbox |
| OpenVoice v2 (MyShell) | MIT | MIT | Yes (backup) | https://github.com/myshell-ai/OpenVoice |
| F5-TTS | MIT | **CC-BY-NC-4.0** | **NO** | https://huggingface.co/SWivid/F5-TTS |
| XTTS-v2 (Coqui) | MPL-2.0 | **CPML (non-commercial)** | **NO** | https://huggingface.co/coqui/XTTS-v2/blob/main/LICENSE.txt |

## Detail

### Chatterbox — MIT, commercial use permitted (SELECTED)
The HuggingFace model card for `ResembleAI/chatterbox` declares `license: mit`.
MIT covers the released weights, not merely the inference code, so commercial and
monetised use is permitted with attribution.

**Watermarking:** every generated file is stamped with Resemble AI's "Perth"
perceptual neural watermark. This is automatic and is *not* a licence restriction —
it is a provenance feature. It is inaudible and survives MP3 encoding. It does not
restrict monetisation, but be aware the audio is detectably machine-generated. This
is normal and is true of most modern TTS.

### F5-TTS — REJECTED
The `SWivid/F5-TTS` model card declares `license: cc-by-nc-4.0`. The **NC** term
forbids commercial use. The code is MIT but the published checkpoints are not, and
they inherit the restriction from the Emilia training corpus. Disqualified.

### XTTS-v2 — REJECTED
`.models.json` in coqui-ai/TTS lists the `xtts_v2` licence as `CPML`
(Coqui Public Model License), which grants rights only "for any **non-commercial**
purpose". The Python library is MPL-2.0 and is commercially fine; the trained
weights are not. Worse, Coqui Inc. shut down in January 2024, so **no commercial
licence can be purchased any more** — this cannot be cured by paying. Disqualified.

### OpenVoice v2 — viable backup
README states "OpenVoice V1 and V2 are MIT Licensed. Free for both commercial and
research use." Kept as the fallback because it is far lighter than Chatterbox, which
matters on this 8 GB machine. It is a *tone-colour converter* layered on MeloTTS
rather than a true zero-shot TTS, so prosody comes from MeloTTS and only timbre is
transferred — a less faithful clone, but much cheaper to run.

## Verdict
Use **Chatterbox**. It is the only candidate that is simultaneously MIT-on-weights
and a true zero-shot cloner. No payment, no subscription, no API. All inference is
local; the reference voice never leaves the machine.
