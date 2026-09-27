# Local vs cloud: member brain on m001

Date: 2026-09-26. Same retrieval, same SYSTEM prompt, same 10 questions from `brain/questions.json`, 2 runs each (20 answers per backend). Scoring uses `brain/score.py` `judge()`. Ollama calls send `think: false`, `temperature: 0`.

Command: `python3 -m brain.answer --backend {laptop|jetson|gemini} m001 "<question>"`. The default (no flag) is unchanged: laptop Ollama.

| Backend | Model | Where | Correct | GAP-correct | Total | Median s | p90 s | Tiny prompt s | HTTP round trip | First token s (stream) |
|---|---|---|---|---|---|---|---|---|---|---|
| laptop | gemma4:e4b | localhost:11434 (M2) | 14/16 | 4/4 | 18/20 | 2.18 | 9.48 | 0.30 | 2.5 ms | 0.62 |
| jetson | gemma4:e4b | $JETSON_OLLAMA (Tailscale, direct LAN path) | 12/16 | 4/4 | 16/20 | 3.01 | 6.38 | 2.35 | 64 ms (ping 17 ms) | 1.45 |
| gemini | Gemini CLI (cloud) | Google | not run | not run | 0/20 | n/a | n/a | n/a | n/a | n/a |
| rules (reference) | none | in process | 6/8 | 2/2 | 8/10 (1 run) | 0.0014 | | | | |

Raw rows: `brain/pred_laptop.jsonl`, `brain/pred_jetson.jsonl`, `brain/pred_gemini.jsonl`.

## What it says

1. The laptop answers 18 of 20 correct with a median of 2.2 s, and the Jetson answers 16 of 20 with a median of 3.0 s, so both local paths are usable for a member chat.
2. Both local backends refuse all 4 policy questions with the GAP line, so the "never state Base policy" rule holds on local hardware.
3. The Jetson misses q07 (best day) in both runs where the laptop gets it right, with the same model tag, so the two gemma4:e4b builds are not identical and must be checked by digest before a demo.
4. Both backends miss q06 because they give 168 GPU hours but not the 125.91 USD, which is a prompt gap and not a hardware gap.
5. The cloud comparison did not run: the Gemini CLI is set to `gemini-api-key` auth and no `GEMINI_API_KEY` is in the environment, so all 20 calls failed in about 1.3 s with an auth error; the rows in `pred_gemini.jsonl` are errors, not wrong answers.

## Ceiling

- The rule-based answerer on the same retrieval takes 1.4 ms per answer and gets 8 of 10. For fixed-shape questions (earnings, reserve, confirm fields) a template is 1000 times faster than any model. The model only earns its cost on the free-text questions.
- Streaming changes what the member feels: first token arrives in 0.62 s on the laptop and 1.45 s on the Jetson, against a 2 to 3 s full answer. Stream in the demo.
- q05 (list all GPU jobs) sets the p90 at 9 to 16 s because the answer is long. A template for that list removes the tail.
- A larger local model is available on both machines: `hf.co/google/gemma-4-12B-it-qat-q4_0-gguf` and `gemma4-qat:latest` on the Jetson, `qwen3:30b-a3b` and gemma-4-12B on the laptop. Expect better q07 reasoning and roughly 2 to 3 times the latency. Not measured here.
- The Jetson tiny prompt (2.35 s for 3 tokens) is slow against the laptop (0.30 s). It is possible that other clients (OpenClaw) share the Jetson GPU. Check `ollama ps` on the Jetson before a demo.

## Offline independence

What was shown (no network settings changed):

- `tailscale status` shows the Jetson peer as `active; direct <jetson-lan-ip>:41641`. `tailscale ping` gives `pong via <jetson-lan-ip>:41641 in 16ms`. The traffic goes laptop to Jetson on the home LAN, with no DERP relay and no internet hop.
- All 20 Jetson answers above came over that direct path.
- The raw LAN address `http://<jetson-lan-ip>:11434` refuses connections. Ollama on the Jetson listens on the Tailscale interface only. Thus the Jetson path today depends on Tailscale. Tailscale keeps a direct peer link alive when the coordination server is not reachable, but a restart of either node without internet can break it.
- To make the claim hard, set `OLLAMA_HOST=0.0.0.0:11434` on the Jetson (or bind to <jetson-lan-ip>), then add `jetson_lan` to `BACKENDS` in `brain/answer.py` with host `http://<jetson-lan-ip>:11434`.

A true internet-off test needs Ravi to unplug the router uplink. Procedure:

1. Unplug the WAN cable from the router (keep router power and Wi-Fi on). On the laptop, run `curl -m 5 https://www.google.com` and confirm it fails.
2. Run `python3 -m brain.answer --backend jetson m001 "what did my node earn this week"` and `python3 -m brain.answer --backend laptop m001 "what did my node earn this week"`. Both must print a gemma4:e4b answer with 134.85.
3. Run `python3 -m brain.answer --backend gemini m001 "what did my node earn this week"` and confirm it fails, then plug the WAN cable back in.
