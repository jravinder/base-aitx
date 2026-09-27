# Compute plans

Page: [web/plans.html](../web/plans.html). Screenshot: `docs/shots/plans.jpg`. Compute track. A Base Fleet proposal.

Base made home energy a service through batteries and strong distribution. The same homes, installers and care can carry AI compute. Open models are close to the frontier; what people lack is the GPU. Base Fleet becomes the local AI compute layer next to the energy layer: members buy GPU time the way they buy energy, pick an open model, pay no frontier provider per token, and keep their data at home. Small and medium businesses and individuals buy the spare time.

## 1. Three offers

Same shape as the home battery: hardware at or near the house, the member served first, spare capacity sold to others.

| Offer | Who pays | Who owns the hardware | Where it runs | What the member gets |
|---|---|---|---|---|
| **Use.** Member picks an open model and asks privately. | The member, per GPU-hour. Member tier $1.20 (Simulation). | The member's home PC, or the Base Fleet station on the feeder. | Home PC, or the station on the member's feeder. | Private answers from the chosen model. GPU time, with no per-token fee to a frontier provider. |
| **Host.** Member keeps a GPU at home, or Base installs one next to the house. | Buyers of spare GPU time: businesses, Base, partners, marketplace. | The member, or Base when Base installs it. | At the member's house, on battery-backed power. | A share of revenue from time sold. The sim gives the gross per home; the member share is a dial to set. |
| **Sell.** Base sells spare station time to local businesses. | Small and medium businesses and individuals. Business tier $1.09 (Simulation). | Base Fleet station. | Isolated sandbox on the station. | Member questions run first and the backup reserve holds. Station revenue pays for the local compute members use. |

## 2. Rate card

Tier rates from `sim/fleet.py` TIERS, each pinned to a public price in `grid/RATES.md` (checked 2026-09-26).

| Tier | Buyer | $/GPU-hour | Public reference | Tag |
|---|---|---|---|---|
| member | The member's own questions | 1.20 | Local job rate set in the sim | Simulation |
| business | Local businesses | 1.09 | Lambda RTX A6000 48 GB on-demand, https://lambda.ai/service/gpu-cloud | Measured |
| base | Base forecast and telemetry | 0.79 | RunPod L40S 48 GB community, https://www.runpod.io/pricing | Measured |
| partner | Grid partner batch | 0.34 | RunPod RTX 4090 24 GB community, https://www.runpod.io/pricing | Measured |
| external | Public marketplace batch | 0.16 | RunPod RTX A5000 24 GB community, https://www.runpod.io/pricing | Measured |

Member earnings (Simulation, `data/members.json`, seed 7, 40 homes, 7 days replayed from ERCOT day-ahead 2026-09-07, 09-09, 09-26, 40% GPU use): sum of `week[].gpu_usd` per home is $36.41 median, $48.55 mean, $6.94 to $136.24. Battery alone: $5.42 mean. Fleet, 50 homes, 3 days: $142.14 power only, $1,182.82 with compute (`grid/RATES.md`).

These are gross GPU revenue per node, before the Host share and before power cost.

## 3. Model catalog

Parameter counts and licenses from the Hugging Face model cards (API, checked 2026-09-27). 4-bit weights = parameters x 0.5 bytes, weights only (Estimate); context memory comes on top. A machine fits a model when weights use 80% of its GPU memory or less.

Machines: browser (WebGPU, about 1 GB); home PC with one 24 GB GPU (fits to 19.2 GB); station with 4 x 48 GB = 192 GB (Assumed L40S class, fits to 153.6 GB).

| Model | Params | License | 4-bit weights | Browser | Home PC | Station | Our machines |
|---|---|---|---|---|---|---|---|
| [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) | 0.49 B | Apache 2.0 | 0.25 GB | fits | fits | fits | Runs in the browser with WebLLM, 945 MB GPU memory per the WebLLM 0.2.79 list (Measured) |
| [Gemma 4 E4B](https://huggingface.co/google/gemma-4-E4B-it) (gemma4:e4b) | 8.0 B total | Apache 2.0 | 4.0 GB | too large | fits | fits | Ollama tag 9.6 GB; laptop 18/20 at 2.2 s, Jetson 16/20 at 3.0 s, `brain/LOCAL_VS_CLOUD.md` (Measured) |
| [Gemma 4 12B](https://huggingface.co/google/gemma-4-12B-it) | 12.0 B | Apache 2.0 | 6.0 GB | too large | fits | fits | Pulled on laptop and Jetson, next to score |
| [gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) | 20.9 B | Apache 2.0 | 10.5 GB | too large | fits | fits | Next to score |
| [Qwen3-30B-A3B](https://huggingface.co/Qwen/Qwen3-30B-A3B) | 30.5 B total | Apache 2.0 | 15.3 GB | too large | fits, tight | fits | Pulled on laptop, next to score |
| [Qwen3-32B](https://huggingface.co/Qwen/Qwen3-32B) | 32.8 B | Apache 2.0 | 16.4 GB | too large | fits, tight | fits | Next to score |
| [Llama 3.3 70B Instruct](https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct) | 70.6 B | Llama 3.3 Community | 35.3 GB | too large | needs a station | fits | Next to score |
| [gpt-oss-120b](https://huggingface.co/openai/gpt-oss-120b) | 116.8 B | Apache 2.0 | 58.4 GB | too large | needs a station | fits | Next to score |
| [Qwen3-235B-A22B](https://huggingface.co/Qwen/Qwen3-235B-A22B) | 235.1 B total | Apache 2.0 | 117.5 GB | too large | needs a station | fits | Next to score |
| [DeepSeek-V3.1](https://huggingface.co/deepseek-ai/DeepSeek-V3.1) | 684.5 B total | MIT | 342 GB | too large | needs a station | several stations or larger GPUs | Next to score |

The largest open models need station-class memory. One home box carries the 4B to 32B class.

## 4. Comparison

| Path | Where data goes | Who is paid per token | Offline or in an outage | Price basis |
|---|---|---|---|---|
| Frontier API | Provider's data centre, over the internet | The frontier provider | Needs the internet | Per token; varies by provider |
| Hosted open-model API | Host's data centre, over the internet | The hosting provider | Needs the internet | Per token. Together AI Llama 3.1 8B $0.14 per 1M tokens, 2026-09-26 (Measured); other models vary by provider |
| Base Fleet local | Stays on the home PC or the station on the feeder | No one; GPU time is paid by the hour | Runs on the home network with battery power; internet-off test is next (`brain/LOCAL_VS_CLOUD.md`) | Per GPU-hour, $0.16 to $1.20 by tier (Simulation) |

## 5. The data rule

- A member's own questions run only on their home PC or their station.
- Jobs sold to others run only in an isolated sandbox on the station, always apart from member data.

## 6. Open gaps

- **#80** target PC speed: score the same questions on the x86 PC beside the battery.
- **#85** power draw: pick one PC power draw, 0.4 kW in the fleet sim or 350 W in the hub model, then run both again.
- **Demand**: 40% GPU use is a sim dial (`UTIL` in `sim/fleet.py`). Real buyer demand sets the earnings.
- **Model size**: gemma4:e4b is the largest model measured. Gemma 4 12B and Qwen3-30B-A3B are pulled and ready to score.
