# Panel photo baseline: Gemini vs gemma4

Test set: `testset.json`, 21 Flickr photos (private test set, not redistributed), hand labeled by photo type.
Same prompt, same JSON schema (`read.py`), for both models.

## Photo type (21 photos)

| model | run | photo_type correct | amps read | brand read | median secs / photo |
|---|---|---|---|---|---|
| Gemini CLI 0.42 (cloud) | done | 18 / 21 | 0 | 13 | 12.7 |
| gemma4:e4b on node GPU (Ollama) | done, `pred_gemma4_flickr.jsonl` | 16 / 21 | 1 | 4 | 129 |

Gemini misses: 135.jpg panel_open read as other; 040.jpg other read as panel_closed; 093.jpg other read as meter_exterior.
gemma4 misses: 135, 158, 133, 006, 093. Three of its five misses call a non-panel photo panel_open (over-accepts). Both miss 135 and 093.

## What this says

- Neither model reads main breaker amps from a Flickr-quality photo. The permit and build-year path (`house/permits.py`) stays the primary amps guess. The photo confirms, it does not discover.
- Gemini is good at the gate question (is this a usable panel photo, what retake do we need) at 13 s per photo. That is the small-set path.
- gemma4 gets 16/21 at 10x the latency, and over-accepts non-panel photos. Usable as the sovereign gate if the retake question is asked in a second pass. One amps read out of 21 is noise, not signal.

## Ceiling

A model fine tuned on 200 labeled panel photos with the breaker label crop as a second input should read amps on most open-cover photos. We did not build that; the event only allows code written this weekend. The right approach is a two-step read: detect the main breaker, crop it, read the number.
