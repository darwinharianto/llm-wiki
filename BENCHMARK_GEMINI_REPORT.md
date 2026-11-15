# Live Gemini Free-Tier Benchmark Report

Provider Mode: **`gemini`** (`gemini-3.5-flash-lite` via Google Gemini Interactions API)

## 1. Gemini Model Latency & Structured JSON Comparison

| Model | Status | Latency (s) | Valid JSON Schema | Extracted 3GPP SCS (kHz) |
| :--- | :---: | :---: | :---: | :--- |
| `gemini-3.5-flash-lite` | OK | 1.407s | PASS | 15, 30, 60, 120, 240 |
| `gemini-3.1-flash-lite` | OK | 8.091s | PASS | 15, 30, 60, 120, 240 |
| `gemini-4-hydrogen` | OK | 46.549s | PASS | 15, 30, 60, 120, 240 |

## 2. Similarity-First Multi-Wave Ingest & Live Gemini Synthesis (20 Passages)

- **Elapsed Time (20 Ingests + Auto-Maintain + 5 Live Gemini Syntheses)**: `11.342s`
- **Final Vault State**: `14` wiki pages (`9` starter + `5` canonical TeleQuAD), `23` raw sources, Health Score `100%`, `0` near-duplicates

| Wave (5 Passages Each) | Wave Type | Created | Updated | Canonical Match | Novel Added | Redundant Skipped | Body Growth (chars) | Live Gemini Calls |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Wave 1** | `canonical_create` | 5 | 0 | 5/5 | 0 | 0 | 0 | 0 |
| **Wave 2** | `exact_copy_varied_title` | 0 | 5 | 5/5 | 0 | 5 | 0 | 0 |
| **Wave 3** | `reordered_part_a` | 0 | 5 | 5/5 | 0 | 5 | 0 | 0 |
| **Wave 4** | `hybrid_part_b_plus_counterfactual` | 0 | 5 | 5/5 | 5 | 6 | 6604 | 5 |

### Wave 4 Live Gemini Update Synthesis Samples

| Target Page | Rev | Contradictions Tracked | Gemini-Synthesized Change Note |
| :--- | :---: | :---: | :--- |
| `[[3gpp-23273-g50-support-of-concurrent-location-requests]]` | r4 → r5 | No | Integrated extended procedures for request combining across V-GMLC, AMF, LMF, and UE along with H-GMLC bulk request conditions under clauses |
| `[[3gpp-23009-g00-enhanced-srns-relocation]]` | r4 → r5 | No | Integrated post-response procedures including IU-ENHANCED-RELOCATION-COMPLETE messages, Iu UP initialization, and the final IURELEASECOMMAND |
| `[[3gpp-21915-f00-numerologies-waveform-and-frame-structure]]` | r3 → r4 | No | Integrated new details covering slot symbol structures, extended CP for 60 kHz SCS, FDD/TDD symbol classification, and ultra-short transmiss |
| `[[3gpp-32240-f50-charging-levels-and-correlation]]` | r4 → r5 | Yes | Integrated the 2026 Release-99 Chronos Audit Override specifying CHRONOS-BILLING-X9 quantum receipts, a 3 transit IOI cap, and the X-3GPP-AU |
| `[[uniform-resource-identifier-uri-list]]` | r3 → r4 | Yes | Replaced the legacy email application process to the TSG CT WG1 Secretary with portal URN-GATEWAY-77B and cipher tag NID-QUANTUM-55 per TSG- |

## 3. Live Gemini Grounded Chat QA (6 TeleQuAD + 2 Counterfactual Override QAs)

- **Chat Evaluation Runtime (8 Live Queries)**: `9.525s` (avg `1.166s/query`)
- **Gemini Telemetry (`llm_stats`)**: `13/13` succeeded, `0` failed, `16.8338s` cumulative Gemini API time

| Metric | Overall (8 QAs) | TeleQuAD (6 QAs) | Counterfactual R99 (2 QAs) |
| :--- | :---: | :---: | :---: |
| **Retrieval Recall@1** | 100.0% | 100.0% | 100.0% |
| **Retrieval Recall@3** | 100.0% | 100.0% | 100.0% |
| **Citation Accuracy** | 100.0% | 100.0% | 100.0% |
| **Pure Gemini Prose Match** | 75.0% | 66.7% | 100.0% |
| **Pure Gemini Token Recall** | 100.0% | 100.0% | 100.0% |
| **Wiki Hybrid Direct Span Match** | 100.0% | 100.0% | 100.0% |
| **Gold Span Match (Full Chat Answer)** | 100.0% | 100.0% | 100.0% |
