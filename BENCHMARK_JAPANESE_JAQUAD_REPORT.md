# Japanese (CJK) Live Ingestion, Redundancy Consolidation & QA Benchmark (`JaQuAD`)

- **Dataset**: [SkelterLabsInc/JaQuAD](https://github.com/SkelterLabsInc/JaQuAD) (`data/dev/jaquad_dev_0000.json`, Japanese Wikipedia Question Answering)
- **Scale**:
  - **1x Baseline**: `407` Japanese Wikipedia passages across `29` articles, **`1,029` Japanese question-answer pairs**
  - **5x Redundancy Corpus**: `2,035` full Japanese documents across `5` waves (`407 × 5`), including re-titled archives, sentence-rotated digests, **blind-titled field memos** (where the article title is omitted from the document title), and reversed audit logs
- **Benchmark Script**: [evaluate_japanese_jaquad.py](file:///home/darwin/llm-wiki/scripts/evaluate_japanese_jaquad.py)
- **Raw Metrics Output**: [jaquad_benchmark_results.json](file:///home/darwin/llm-wiki/tests/fixtures/jaquad_benchmark_results.json)

---

## 1. What Was Upgraded for Japanese / CJK Support

Originally, four parts of the pipeline assumed Latin/ASCII word boundaries (`[a-z0-9]`, `\b`, and English punctuation `.!?`). We upgraded all four so Japanese (Kanji, Hiragana, Katakana) and CJK text work out of the box without affecting English performance:

1. **Unicode-Aware Slugification ([vault_manager.py](file:///home/darwin/llm-wiki/backend/vault_manager.py#L24-L33))**:
   - Applies `unicodedata.normalize("NFKC", text)` and preserves Hiragana (`\u3040-\u309f`), Katakana (`\u30a0-\u30ff`), Kanji/CJK Unified Ideographs (`\u4e00-\u9fff`, `\u3400-\u4dbf`), and Hangul (`\uac00-\ud7af`) in page slugs instead of stripping non-ASCII characters to `"untitled-page"`.
2. **Zero-Dependency Japanese/CJK Tokenizer & Title Matching ([similarity.py](file:///home/darwin/llm-wiki/backend/similarity.py#L27-L115))**:
   - Pure-ASCII strings take a fast path that keeps English tokenization 100% unchanged.
   - When CJK characters are present (`has_cjk(text)`), `tokenize()` normalizes with `NFKC` (unifying full-width digits/letters and half-width Katakana) and extracts:
     - Contiguous **Kanji runs** (`[\u4e00-\u9fff...]+`) plus **overlapping 2-character Kanji bigrams** for compound nouns (`>= 3` chars, e.g. `東大寺の仏像` -> `東大寺`, `東大`, `大寺`, `仏像`),
     - Contiguous **Katakana runs** (`[\u30a0-\u30ffー]+`) plus 2–3 character sub-grams for loanwords (`>= 4` chars),
     - **Hiragana content stems** with Japanese particle/auxiliary stripping (`JA_STOPWORDS`),
     - Embedded Latin/numeric identifiers (`[a-z0-9]+`).
   - Updated title substring thresholds in `search()` and `find_similar_for_candidate()` so 2–4 character Japanese titles (e.g. `東京タワー`, `条約改正`) are recognized without requiring `>= 5` ASCII characters.
3. **Japanese Sentence Splitting, Wikilinking & Counter-Aware Number Extraction ([llm_providers.py](file:///home/darwin/llm-wiki/backend/llm_providers.py#L466-L645))**:
   - `_split_technical_sentences()` now splits on Japanese sentence punctuation (`。！？`) as well as English `.!?`.
   - `_extract_numbers()` uses `(?<![a-zA-Z0-9])\d+(?:\.\d+)?(?![a-zA-Z0-9])` after `NFKC` normalization so numbers attached to Japanese counters (`1958年`, `333メートル`, `8世紀`) are extracted accurately (Python's `\b` fails between digits and Kanji because both are `\w`).
   - `_weave_wikilinks()` links Japanese entity/concept titles inside continuous Japanese sentences without requiring ASCII word boundaries.
4. **Japanese QA Normalization & Token/Character F1 ([evaluate_qa_and_updates.py](file:///home/darwin/llm-wiki/scripts/evaluate_qa_and_updates.py#L108-L162))**:
   - Added CJK-aware normalization and character/morpheme overlap scoring for Japanese answers.

---

## 2. 5x Redundancy Consolidation Results (`2,035` Japanese Passages -> `407` Pages)

Across `5` waves of `407` Japanese passages (`2,035` total documents), starting from an empty vault (`pages = {}`) at Wave 1 Document #1:

| Wave | Wave Description | Incoming Docs | Pages Created | Existing Pages Updated | Redundant Sentences Appended |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Wave 1** | Canonical Japanese Wikipedia passages | `407` | `406` | `1` *(near-duplicate pair)* | `0` |
| **Wave 2** | Re-titled archive (`【アーカイブ記録】...`) | `407` | `1` | `406` (`99.75%`) | `0` |
| **Wave 3** | Sentence-rotated Japanese digest (`... — 再構成ノート`) | `407` | `0` | `407` (`100.0%`) | `0` |
| **Wave 4** | **Blind-titled field memo** (`調査メモ #xxx: <middle clause>`) | `407` | `0` | `407` (`100.0%`) | `0` |
| **Wave 5** | Reversed sentence order audit log (`技術監査ログ xxx`) | `407` | `0` | `407` (`100.0%`) | `0` |
| **Total** | **All 5 Waves (`5x` Redundancy)** | **`2,035`** | **`407`** | **`1,628` (`99.94%` of Waves 2–5)** | **`0` (`100%` deduplicated)** |

- **Consolidation Speed**: **`10.96s`** on CPU (`~185` Japanese passages/sec), compared to **`585.69s`** to embed all `2,035` raw passages with `intfloat/multilingual-e5-large` on GPU.
- **Zero Duplicate Bloat**: Every re-ordered/duplicate sentence across Waves 2–5 (`1,628` documents) was recognized by `_is_redundant_unit()` and skipped (`0/407` pages had duplicate text appended).

---

## 3. Retrieval & Answer-in-Top-K Benchmark (`1,029` Japanese Questions)

### A. 1x Baseline (`407` Japanese Passages, `1,029` QAs)

| Retriever | Index Time | Topic `R@1` | Topic `R@3` | Topic `R@5` | Topic `R@10` | `MRR@10` | `Ans@1` | `Ans@3` | `Ans@5` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. `intfloat/multilingual-e5-large` (1x)** | `78.10s` (GPU) | `74.44%` | `91.84%` | `95.92%` | `98.54%` | `83.48%` | `80.47%` | `93.88%` | `97.08%` |
| **2. LLM Wiki Japanese Engine (1x)** | **`0.83s` (CPU)** | **`81.54%`** | **`95.04%`** | **`97.28%`** | **`98.64%`** | **`88.63%`** | **`86.01%`** | **`96.02%`** | **`97.96%`** |
| **3. Hybrid (LLM Wiki + E5 Fusion, 1x)** | `78.93s` | **`86.20%`** | **`97.67%`** | **`98.93%`** | **`99.71%`** | **`91.98%`** | **`91.06%`** | **`98.35%`** | **`99.32%`** |

### B. 5x Redundancy (`2,035` Incoming Japanese Docs, `1,029` QAs)

| Retriever | Active Docs / Pages | Ingest / Index Time | Topic `R@1` | Topic `R@3` | Topic `R@5` | Topic `R@10` | `MRR@10` | `Ans@1` | `Ans@3` | Unique Topics in Top-10 | Wasted Duplicate Slots |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. `multilingual-e5-large` Raw (`5x`)** | `2,035` docs | `585.69s` (GPU) | `80.37%` | `88.05%` *(↓3.79%)* | `91.93%` *(↓3.99%)* | `97.28%` *(↓1.26%)* | `85.42%` | `85.91%` | `91.93%` | `3.42 / 10` | **`65.79%`** |
| **2. LLM Wiki Consolidated (`5x -> 407`)** | **`407` pages** | **`10.96s` (CPU)** | **`81.44%`** | **`94.75%`** | **`97.38%`** | **`98.74%`** | **`88.54%`** | **`85.91%`** | **`95.72%`** | **`9.94 / 10`** | **`0.00%`** |
| **3. Hybrid LLM Wiki + E5 (`5x -> 407`)** | **`407` pages** | `89.06s` | **`84.55%`** | **`97.08%`** | **`98.15%`** | **`99.71%`** | **`90.95%`** | **`89.31%`** | **`97.86%`** | **`10.00 / 10`** | **`0.00%`** |

