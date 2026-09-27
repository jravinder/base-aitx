# Extraction Example Lineage

These are locally copied Wikimedia Commons 1280-pixel-wide versions, with no
further image edits reported by the copying parent. The parent verified the live
source pages and visually inspected the local images. This audit verified local
dimensions, SHA-256 hashes, manifest attribution, and the exact saved-value mapping.
The original `panel/photos/` files are absent in this worktree, so byte identity
against those source files was not independently checked here.

| Local asset (under `web/assets/`) | Source lineage | Author | Dimensions |
| --- | --- | --- | --- |
| `extract-closed-panel.jpg` | `panel/photos/079.jpg` | Famartin | 1280 x 1707 |
| `extract-exterior.jpg` | `panel/photos/054.jpg` | W.carter | 1280 x 853 |
| `extract-wrong-equipment.jpg` | `panel/photos/004.jpg` | Vivan755 | 1280 x 960 |
| `extract-panel-rating.jpg` | `panel/photos/081.jpg` | Famartin | 1280 x 1707 |
| `extract-service-overview.jpg` | `panel/photos/084.jpg` | Rsparks3 | 1280 x 960 |

The service overview is **CC0**; the other four are **CC BY-SA 4.0**.
The two additions were copied without edits from the main checkout, visually
inspected, and their live Commons license pages checked on 2026-09-27.
`panel/manifest.json` supplies the Commons source
page and author lineage. `web/data/photo-examples.json` contains each image's
author, source-page URL, license name, and license URL for rendering attribution.
Retain those visible credits and links when reusing the assets; these are not
Base customer images or installation examples approved by Base.

## Local SHA-256

```text
86a94119edbd3de2a4ca5b758251873b5ac557400794c9c632769d58d0a0cc2a  extract-closed-panel.jpg
c208018bfeb962c58264cd070a6a1ce6c077c487dd808c80725cfc32270f9cba  extract-exterior.jpg
255fe74537361b6a5805a1549d43dc324efda0d1fc247fe9b36b577c3a5af812  extract-wrong-equipment.jpg
```

## Saved Result Mapping

Model: `gemma4:e4b`. Source: **`panel/pred_gemma4.jsonl`**, joined by `file` to
the Commons manifest. Do not use `pred_gemini.jsonl` or Flickr records: identical
numeric filenames across datasets do not establish image identity.

Only four fields are transformed into display values:

| Record | `photo_type` | `brand` | `main_breaker_amps` | `location` |
| --- | --- | --- | --- | --- |
| `079.jpg` | `panel_closed` -> Closed panel | null | null | `indoor` -> Indoor |
| `054.jpg` | `meter_exterior` -> Exterior meter | null | 60 -> 60 A | `outdoor` -> Outdoor |
| `004.jpg` | `panel_open` -> Open panel | null | null | `unknown` -> Unknown |
| `081.jpg` | `panel_open` -> Open panel | null | 200 -> 200 A | `indoor` -> Indoor |
| `084.jpg` | `other` -> Other | null | null | `outdoor` -> Outdoor |

The 200 A reading is saved model output, not engineering approval. The close-up
has an open outer door; it is a reference, not a request to open equipment.
The overview's visible brand names were missed by the model and remain null,
with a correction prompt. Neither example imports the model's pass flag or
unsupported safety/clearance conclusions.

These are **unverified saved model results**, not a fresh analysis. In particular,
the exterior result's **60 A is not a confirmed main breaker or home service
rating**; the source describes distribution equipment. The wrong-equipment
classification is over-broad and does not make it a residential panel.

No measured clearances, pass/approval result, or bounding boxes are supplied.
Original model `retake_reason`, `issues`, and unsafe opening/wiring instructions
are not imported. Keep protective covers closed and ask Base for safe next steps.
Do not infer engineering approval, eligibility, or readiness from these examples.

## Verification

Static assertions passed for all 12 transformed values, exactly four fields per
example, model name, and all three manifest source/author/license mappings.
Dimensions were read with `sips`; hashes use SHA-256 over the local asset bytes.
The exact-value check can be repeated from the repository root without writes:

```sh
node <<'NODE'
const fs = require('node:fs'), assert = require('node:assert/strict');
const examples = JSON.parse(fs.readFileSync('web/data/photo-examples.json')).examples;
const records = fs.readFileSync('panel/pred_gemma4.jsonl', 'utf8')
  .trim().split('\n').map(JSON.parse);
const types = {panel_closed: 'Closed panel', meter_exterior: 'Exterior meter', panel_open: 'Open panel'};
const locations = {indoor: 'Indoor', outdoor: 'Outdoor', unknown: 'Unknown'};
for (const [id, file] of [['closed-panel', '079.jpg'], ['exterior-rating', '054.jpg'], ['wrong-equipment', '004.jpg']]) {
  const example = examples.find(x => x.id === id);
  const matches = records.filter(x => x.file === file);
  assert.equal(matches.length, 1);
  const record = matches[0];
  assert.equal(example.model, 'gemma4:e4b');
  assert.equal(example.fields.length, 4);
  assert.deepEqual(Object.fromEntries(example.fields.map(x => [x.key, x.value])), {
    photo_type: types[record.photo_type], brand: record.brand,
    main_breaker_amps: record.main_breaker_amps === null ? null : `${record.main_breaker_amps} A`,
    location: locations[record.location]
  });
}
console.log('PASS: 12 exact transformed values');
NODE
```
