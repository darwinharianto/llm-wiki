# Full TeleQuAD 10x Redundancy Benchmark Report (5,360 Full Passages, 4,485 Questions)

## Benchmark Configuration & Zero-Shortcut Blind Consolidation Summary
- **Dataset**: Full [TeleQuAD-v4-full.json](file:///home/darwin/llm-wiki/tests/fixtures/TeleQuAD-v4-full.json) expanded across **`10` full-passage waves** (`536` canonical passages × `10` = **`5,360` full passages**, **`11,256,986` chars**) and evaluated on all **`4,485` extractive QA pairs** (`2,024` QAs on standard passages `<=2,000` chars; `2,461` QAs on long passages `>2,000` chars / `>512` E5 tokens).
- **Zero Benchmark Shortcuts (100% Blind Ingestion)**:
  1. **No passage slicing**: Every wave contains the full passage (not chopped into shorter `part_a`/`part_b` halves that would artificially cure E5's 512-token truncation).
  2. **No Wave-1 bypass**: Ingestion starts from an empty vault (`pages = {}`) at Document #1 of Wave 1 and calls `find_similar_for_candidate(..., threshold=0.35)` on all `5,360` documents.
  3. **No ground-truth tags**: Tags are extracted purely from document text via `LLMService._extract_tags`.
  4. **Live incremental indexing**: `HybridSimilarityEngine.upsert_page` indexes each created/updated page immediately without any post-hoc extra-page cleanup pass.
- **LLM Wiki Blind Consolidation Result**: `5,360` incoming passages compiled down to **`548` canonical pages** in **`19.08s`** (`4` Wave-1 near-duplicate pairs consolidated during Wave 1: two word-for-word identical 3GPP RAN2/RAN5 web scrapes `#97==#209` and `#100==#417`, plus two 94%-identical TS 23.009 handover clauses `#75==#491` and `#233==#276`; **`4,808/4,824` (99.67%)** of Wave 2–10 items consolidated via in-place updates; **`25,044` redundant blocks/sentences skipped**; stored corpus text compressed by **`87.2%`** from `11,256,986` chars to `1,439,603` chars).

## 1. Per-Wave Blind LLM Wiki Consolidation (Waves 1–10 × 536 Full Passages)

| Wave | Wave Type | Incoming | Created | Updated | Target Page Match | Novel Blocks Kept | Redundant Skipped |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `Wave 1` | `Canonical Full Passage` | `536` | `532` | `4` | `536/536` (`100.00%`) | `536` | `13` |
| `Wave 2` | `Technical Note Duplicate` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `4,677` |
| `Wave 3` | `Spec Digest (Local Sent Swap)` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `536` |
| `Wave 4` | `Extended Header Duplicate` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `4,677` |
| `Wave 5` | `Addendum Notes Duplicate` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `4,677` |
| `Wave 6` | `Protocol Summary (Sent Swap)` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `536` |
| `Wave 7` | `Telecom Reference Sheet` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `536` |
| `Wave 8` | `Blind Archive Memo (#08-XXX)` | `536` | `8` | `528` | `528/536` (`98.51%`) | `8` | `4,187` |
| `Wave 9` | `Blind Field Audit Log (#09-XXX)` | `536` | `8` | `528` | `527/536` (`98.32%`) | `8` | `528` |
| `Wave 10` | `Consolidated Spec Mirror` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `4,677` |

## 2. 1x Baseline vs. 10x Redundancy Retrieval & Crowding Across All 4,485 Questions

| System | Indexed Units | Dup Rate | Topic R@1 (Strict 1-to-1) | Topic R@3 | Topic R@5 | Topic R@10 (Strict 1-to-1) | Top-3 Wasted Slots | Top-10 Wasted Slots | Unique Topics in Top-10 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Ref: E5 Whole-Passage (1x Non-Redundant)** | `536` | `0.0%` | `50.06%` | `65.69%` | `71.22%` | `78.08%` | `0.00%` | `0.00%` | `10.00 / 10` |
| **Ref: E5 Sub-Chunked (1x Non-Redundant)** | `1,553` | `0.0%` | `63.52%` | `79.18%` | `83.50%` | `88.94%` | `0.00%` | `0.00%` | `10.00 / 10` |
| **1. E5-Large Whole-Passage RAG (5,360 Raw Wave Docs)** | `5,360` | `90.0%` | 52.91% | 56.79% | 59.09% | 64.24% | 57.56% | 79.86% | `2.01 / 10` |
| **2. E5-Large Sub-Chunked (<=1000c, Wave-Doc MaxP, 15,687 chunks)** | `15,687` | `96.6%` | 67.07% | 72.24% | 74.31% | 79.00% | 58.32% | 80.63% | `1.94 / 10` |
| **3. LLM Wiki Consolidated Vault (548 Pages)** | `548` | `2.9%` | 76.12% (`75.94%`) | 89.07% | 93.15% | 95.85% (`95.63%`) | 3.27% | 4.16% | `9.56 / 10` |
| **4. Hybrid LLM Wiki + E5 Fusion (548 Consolidated Pages)** | `548` | `2.9%` | 77.64% (`77.48%`) | 90.39% | 93.78% | 96.72% (`96.50%`) | 3.83% | 5.22% | `9.48 / 10` |

*Sub-Chunked E5 Raw Top-10 Chunks Note*: Without wave-doc MaxP deduplication, raw Top-10 chunk retrieval (`15,687` chunks) yields **Topic R@1 = 67.07%**, **Topic R@3 = 72.17%**, **Topic R@10 = 78.55%**, **`58.49%` wasted Top-3 slots**, **`81.22%` wasted Top-10 slots**, and only **`1.88 / 10` unique topics** in Top-10.

## 3. Gold Answer Containment & Long-Passage Breakdown (4,485 QAs)

| System | Overall Ans@1 | Overall Ans@3 | Overall Ans@10 | Standard (`<=2,000c`, `2,711` QAs) R@1 / R@10 | **Long (`>2,000c`, `1,774` QAs) R@1 / R@10** | Top-1 Sent Span | Top-1 Sent >=0.5 | Top-1 Sent Recall / F1 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. E5-Large Whole-Passage RAG (5,360 Raw Wave Docs)** | 58.51% | 62.27% | 69.30% | 66.55% / 77.47% | **41.69% / 53.35%** | 43.39% | 48.92% | 51.47% / 24.57% |
| **2. E5-Large Sub-Chunked (<=1000c, Wave-Doc MaxP, 15,687 chunks)** | 66.11% | 71.62% | 79.09% | 67.09% / 78.16% | **67.05% / 79.68%** | 53.11% | 59.62% | 61.48% / 28.78% |
| **3. LLM Wiki Consolidated Vault (548 Pages)** | 80.94% | 91.86% | 96.90% | 78.36% / 96.34% | **74.28% / 95.45%** | 61.72% | 66.67% | 67.69% / 32.40% |
| **4. Hybrid LLM Wiki + E5 Fusion (548 Consolidated Pages)** | 83.03% | 93.47% | 97.75% | 78.85% / 96.64% | **76.64% / 96.79%** | 62.74% | 67.49% | 68.74% / 32.82% |

## 4. Build, Ingest & Query Latency (5,360 Passages, 4,485 Queries)

| System | Build / Ingest Time | 4,485-Query Time | Per-Query Latency |
| :--- | :---: | :---: | :---: |
| **1. E5-Large Whole-Passage RAG (5,360 Raw Wave Docs)** | `462.77s` | `5.30s` | `1.18 ms/query` |
| **2. E5-Large Sub-Chunked (<=1000c, Wave-Doc MaxP, 15,687 chunks)** | `962.92s` | `9.52s` | `2.12 ms/query` |
| **3. LLM Wiki Consolidated Vault (548 Pages)** | `20.36s` | `10.42s` | `2.32 ms/query` |
| **4. Hybrid LLM Wiki + E5 Fusion (548 Consolidated Pages)** | `143.21s` | `16.45s` | `3.67 ms/query` |

## 5. Key Honest Takeaways
1. **With True Full-Passage 10x Redundancy, E5 R@1 Stays Near 1x While R@3..R@10 Collapse Under Duplicate Crowding**: E5 Whole-Passage Topic R@1 is **52.91%** (vs `50.06%` at 1x), while **Topic R@3 drops from `65.69%` to `56.79%`** and **Topic R@10 drops from `78.08%` to `64.24%`** because `79.86%` of Top-10 slots are crowded by redundant copies (`2.01 / 10` unique topics). Likewise, E5 Sub-Chunked R@1 stays at **67.07%** (vs `63.52%` at 1x), while its **Topic R@3 drops from `79.18%` to `72.24%`** and **Topic R@10 drops from `88.94%` to `79.00%`** (`1.94 / 10` unique topics).
2. **100% Blind LLM Wiki Consolidation Collapses `5,360` Passages into `548` Pages**: Without any Wave-1 bypass or ground-truth tags, `HybridSimilarityEngine` created `532` pages in Wave 1 (merging `4` near-identical pairs in raw TeleQuAD, including 2 word-for-word duplicate web scrapes) and consolidated **`4,808/4,824` (99.67%)** of Waves 2–10 into canonical pages (`548` total pages including `16` blind-title edge cases).
3. **Minimal Duplicate Crowding Preserves High Recall at Top-K**: Because the consolidated wiki vault has only `4.16%` duplicate slot waste (`9.56 / 10` unique topics in Top-10 vs `2.01 / 10` for E5), LLM Wiki achieves **76.12% Topic R@1** (`75.94%` strict 1-to-1) and **95.85% Topic R@10** (`95.63%` strict 1-to-1), while Hybrid LLM Wiki + E5 Fusion reaches **77.64% Topic R@1** (`77.48%` strict) and **96.72% Topic R@10** (`96.50%` strict).
