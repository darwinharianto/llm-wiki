from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_SITE = (
    ROOT_DIR
    / ".venv"
    / "lib"
    / f"python{sys.version_info.major}.{sys.version_info.minor}"
    / "site-packages"
)
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import torch
import torch.nn.functional as F
from google import genai
from transformers import AutoModel, AutoTokenizer

from backend.config import RuntimeSettings
from backend.llm_providers import LLMService
from backend.similarity import HybridSimilarityEngine
from backend.telemetry import TelemetryTracker
from backend.vault_manager import WikiPage, slugify, utc_now_iso
from scripts.evaluate_qa_and_updates import compute_token_recall_f1, normalize_answer

TELEQUAD_PATH = ROOT_DIR / "tests" / "fixtures" / "TeleQuAD-v4-full.json"
CACHE_PATH = ROOT_DIR / "tests" / "fixtures" / "telequad_50q_4x_llm_rephrased.json"
OUT_JSON = ROOT_DIR / "tests" / "fixtures" / "telequad_50q_4x_results.json"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


class E5Embedder:
    """Thin wrapper around intfloat/multilingual-e5-large for HybridSimilarityEngine."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-large") -> None:
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()
        self._passage_cache: dict[str, list[float]] = {}
        self._query_cache: dict[str, list[float]] = {}

    def _encode(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        out_vecs: list[list[float]] = []
        with torch.no_grad():
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                enc = self.tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                ).to(self.device)
                out = self.model(**enc)
                mask = enc["attention_mask"].unsqueeze(-1).expand(out.last_hidden_state.size()).float()
                pooled = torch.sum(out.last_hidden_state.float() * mask, 1) / torch.clamp(mask.sum(1), min=1e-9)
                normed = F.normalize(pooled, p=2, dim=1).cpu().numpy()
                for row in normed:
                    out_vecs.append(row.tolist())
        return out_vecs

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        missing_idx = [i for i, t in enumerate(texts) if t not in self._passage_cache]
        if missing_idx:
            prefixed = [f"passage: {texts[i]}" for i in missing_idx]
            vecs = self._encode(prefixed)
            for idx, vec in zip(missing_idx, vecs):
                self._passage_cache[texts[idx]] = vec
        return [self._passage_cache[t] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        if text not in self._query_cache:
            self._query_cache[text] = self._encode([f"query: {text}"])[0]
        return self._query_cache[text]


def sample_50_telequad_items() -> list[dict[str, Any]]:
    raw = json.loads(TELEQUAD_PATH.read_text(encoding="utf-8"))
    pool: list[dict[str, Any]] = []
    for art in raw["data"]:
        spec = art["title"]
        for p_i, para in enumerate(art["paragraphs"]):
            ctx = para["context"].strip()
            qas = [qa for qa in para["qas"] if qa.get("answers")]
            if not qas or len(ctx) < 120:
                continue
            first_line = ctx.splitlines()[0].strip()[:80]
            pool.append(
                {
                    "spec": spec,
                    "title": f"{spec} — {first_line}",
                    "content": ctx,
                    "qa": qas[0],
                }
            )
    rng = random.Random(42)
    sampled = rng.sample(pool, 50)
    for idx, item in enumerate(sampled):
        item["topic_id"] = idx
        item["gold_slug"] = f"tq50-{idx:02d}-{slugify(item['spec'])[:24]}"
    return sampled


def generate_3_llm_rephrases(
    sampled: list[dict[str, Any]], telemetry: TelemetryTracker
) -> list[dict[str, Any]]:
    if CACHE_PATH.exists():
        cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if len(cached) == 50:
            print(f"Loaded cached 50x4 LLM-rephrased corpus from {CACHE_PATH}")
            return cached

    client = genai.Client(api_key=GEMINI_API_KEY)
    schema = {
        "type": "object",
        "properties": {
            "rephrases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["title", "body"],
                },
            }
        },
        "required": ["rephrases"],
    }

    dataset: list[dict[str, Any]] = []
    for i, item in enumerate(sampled):
        prompt = (
            "You are paraphrasing a 3GPP telecom specification passage to test semantic deduplication.\n"
            "Create exactly 3 distinct paraphrased versions of the passage below.\n"
            "Rules:\n"
            "1. Rephrase sentences using different wording, active/passive voice changes, synonyms, and re-ordered explanations so it is NOT a copy-paste.\n"
            "2. Give each version a different descriptive title (at least 1 version should NOT mention the 3GPP TS number in its title).\n"
            "3. Preserve ALL technical facts, entities, and numeric parameters accurately so questions about the passage remain answerable.\n\n"
            f"Original Title: {item['title']}\n"
            f"Original Passage:\n{item['content'][:3500]}"
        )
        t0 = time.perf_counter()
        rephrases: list[dict[str, str]] = []
        for attempt in range(3):
            try:
                resp = client.interactions.create(
                    model=GEMINI_MODEL,
                    input=prompt,
                    store=False,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": schema,
                    },
                )
                raw_txt = resp.output_text or "{}"
                parsed = json.loads(raw_txt)
                rephrases = parsed.get("rephrases") or []
                in_t, out_t, th_t, ca_t, tot_t, src = LLMService._extract_gemini_usage(
                    resp, prompt, raw_txt
                )
                telemetry.record_event(
                    operation="generate_llm_rephrase",
                    llm_used=True,
                    execution_mode="llm_api",
                    provider="gemini",
                    model=GEMINI_MODEL,
                    status="ok",
                    input_tokens=in_t,
                    output_tokens=out_t,
                    thought_tokens=th_t,
                    cached_tokens=ca_t,
                    total_tokens=tot_t,
                    token_source=src,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    target_slug=item["gold_slug"],
                    reason=f"Generated 3 LLM rephrases for topic {i+1}/50",
                )
                if len(rephrases) >= 3:
                    break
            except Exception as exc:
                print(f"  Retry {attempt+1} for item {i}: {exc}")
                time.sleep(1.5)

        while len(rephrases) < 3:
            rephrases.append(
                {
                    "title": f"Technical Summary Note #{i:02d}-{len(rephrases)+1}",
                    "body": item["content"],
                }
            )

        dataset.append(
            {
                "topic_id": item["topic_id"],
                "gold_slug": item["gold_slug"],
                "spec": item["spec"],
                "original_title": item["title"],
                "original_content": item["content"],
                "rephrases": rephrases[:3],
                "qa": item["qa"],
            }
        )
        if (i + 1) % 10 == 0:
            print(f"  Rephrased {i+1}/50 passages via {GEMINI_MODEL}...")

    CACHE_PATH.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved 50x4 LLM-rephrased corpus to {CACHE_PATH}")
    return dataset


def build_4x_wave_docs(dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for wave in range(1, 5):
        items = list(dataset)
        if wave > 1:
            random.Random(100 + wave).shuffle(items)
        for item in items:
            if wave == 1:
                title = item["original_title"]
                content = item["original_content"]
            else:
                rep = item["rephrases"][wave - 2]
                title = rep["title"]
                content = rep["body"]
            docs.append(
                {
                    "wave": wave,
                    "topic_id": item["topic_id"],
                    "gold_slug": item["gold_slug"],
                    "title": title,
                    "content": content,
                    "source_name": f"tq50-t{item['topic_id']:02d}-w{wave}.md",
                }
            )
    return docs


def run_wiki_consolidation(
    wave_docs: list[dict[str, Any]],
    embedder: E5Embedder | None,
    telemetry: TelemetryTracker,
    label: str,
) -> tuple[dict[str, WikiPage], HybridSimilarityEngine, dict[str, Any]]:
    settings = RuntimeSettings(provider="local_smart", similarity_threshold=0.35)
    llm = LLMService(settings, telemetry=telemetry)
    pages: dict[str, WikiPage] = {}
    engine = HybridSimilarityEngine(pages, embedder=embedder)

    t0 = time.perf_counter()
    created = 0
    updated = 0
    wave_stats = {w: {"created": 0, "updated": 0} for w in range(1, 5)}
    slug_to_tids: dict[str, set[int]] = {}
    current_wave = 0

    for doc in wave_docs:
        w = doc["wave"]
        if w != current_wave:
            if current_wave == 1 and pages:
                engine._build_index()
            current_wave = w

        tid = doc["topic_id"]
        tags = llm._extract_tags(doc["title"], doc["content"], {})
        sim = engine.find_similar_for_candidate(
            title=doc["title"],
            content=doc["content"],
            tags=tags,
            aliases=[],
            links=[],
            threshold=0.35,
        )
        if sim["action"] == "update" and sim["target_slug"] in pages:
            tgt = sim["target_slug"]
            ex = pages[tgt]
            syn = llm._local_synthesize_page_update(
                existing_page=ex,
                new_title=doc["title"],
                new_content=doc["content"],
                source_name=doc["source_name"],
                new_tags=tags,
                all_pages=pages,
            )
            ex.body = syn["updated_body"]
            ex.revision_count += 1
            engine.upsert_page(ex)
            updated += 1
            wave_stats[w]["updated"] += 1
            slug_to_tids.setdefault(tgt, set()).add(tid)
        else:
            base_slug = doc["gold_slug"] if w == 1 else slugify(doc["title"])
            slug = base_slug
            idx = 2
            while slug in pages:
                slug = f"{base_slug}-{idx}"
                idx += 1
            page = WikiPage(
                slug=slug,
                title=doc["title"],
                category="concepts",
                summary=doc["content"][:160],
                tags=tags,
                aliases=[],
                sources=[doc["source_name"]],
                updated_at=utc_now_iso()[:10],
                revision_count=1,
                body=f"# {doc['title']}\n\n{doc['content']}",
                path=Path(f"wiki/concepts/{slug}.md"),
            )
            pages[slug] = page
            engine.upsert_page(page)
            created += 1
            wave_stats[w]["created"] += 1
            slug_to_tids.setdefault(slug, set()).add(tid)

    engine._build_index()
    elapsed = time.perf_counter() - t0
    w2_4_tot = sum(wave_stats[w]["created"] + wave_stats[w]["updated"] for w in range(2, 5))
    w2_4_upd = sum(wave_stats[w]["updated"] for w in range(2, 5))
    return pages, engine, {
        "label": label,
        "total_docs": len(wave_docs),
        "final_pages": len(pages),
        "created": created,
        "updated": updated,
        "dedup_rate_waves_2_to_4_pct": round(w2_4_upd / max(w2_4_tot, 1) * 100, 2),
        "wave_stats": wave_stats,
        "elapsed_s": round(elapsed, 2),
        "slug_to_tids": slug_to_tids,
    }


def evaluate_retriever(
    questions: list[dict[str, Any]],
    get_top10_tids_fn: Any,
) -> dict[str, Any]:
    r1 = r3 = r5 = r10 = 0
    mrr = 0.0
    uniq_sum = 0
    for q in questions:
        tid = q["topic_id"]
        top10_tids = get_top10_tids_fn(q["question"])
        uniq_sum += len(set(top10_tids))
        if tid in top10_tids:
            rank = top10_tids.index(tid) + 1
            if rank == 1:
                r1 += 1
            if rank <= 3:
                r3 += 1
            if rank <= 5:
                r5 += 1
            if rank <= 10:
                r10 += 1
            mrr += 1.0 / rank
    nq = len(questions)
    avg_uniq = round(uniq_sum / nq, 2)
    return {
        "R@1": round(r1 / nq * 100, 2),
        "R@3": round(r3 / nq * 100, 2),
        "R@5": round(r5 / nq * 100, 2),
        "R@10": round(r10 / nq * 100, 2),
        "MRR@10": round(mrr / nq * 100, 2),
        "avg_unique_topics_top10": avg_uniq,
        "wasted_duplicate_slots_pct": round((10.0 - avg_uniq) / 10.0 * 100, 2),
    }


def main() -> None:
    telemetry = TelemetryTracker()
    sampled = sample_50_telequad_items()
    dataset = generate_3_llm_rephrases(sampled, telemetry)
    wave_docs = build_4x_wave_docs(dataset)
    print(f"Prepared 4x LLM-rephrased TeleQuAD corpus: {len(wave_docs)} docs for 50 questions")

    print("Loading intfloat/multilingual-e5-large...")
    embedder = E5Embedder("intfloat/multilingual-e5-large")

    # 1. Pure E5-Large over 200 raw docs (4x redundant)
    raw_texts = [f"{d['title']}\n\n{d['content'][:2400]}" for d in wave_docs]
    t0 = time.perf_counter()
    raw_embs = np.array(embedder.embed_passages(raw_texts), dtype=np.float32)
    e5_index_s = round(time.perf_counter() - t0, 2)

    questions = [
        {
            "topic_id": item["topic_id"],
            "question": item["qa"]["question"],
            "answers": [a["text"] for a in item["qa"]["answers"] if a.get("text")],
        }
        for item in dataset
    ]

    def e5_raw_top10(q_text: str) -> list[int]:
        qv = np.array(embedder.embed_query(q_text), dtype=np.float32)
        sims = raw_embs @ qv
        idx = np.argsort(-sims)[:10].tolist()
        return [wave_docs[i]["topic_id"] for i in idx]

    e5_metrics = evaluate_retriever(questions, e5_raw_top10)

    # 2. LLM Wiki (Lexical Only: BM25 + TF-IDF + Graph)
    lex_pages, lex_engine, lex_consol = run_wiki_consolidation(
        wave_docs, embedder=None, telemetry=telemetry, label="LLM Wiki (Lexical Only)"
    )
    lex_slug_to_tids = lex_consol.pop("slug_to_tids")

    def lex_wiki_top10(q_text: str) -> list[int]:
        matches = lex_engine.search(q_text, top_k=10)
        out: list[int] = []
        for m in matches:
            tids = sorted(lex_slug_to_tids.get(m.slug, set()))
            out.append(tids[0] if tids else -1)
        return out

    lex_metrics = evaluate_retriever(questions, lex_wiki_top10)

    # 3. LLM Wiki + E5 Dense Similarity (Unified HybridSimilarityEngine with embedder)
    e5w_pages, e5w_engine, e5w_consol = run_wiki_consolidation(
        wave_docs, embedder=embedder, telemetry=telemetry, label="LLM Wiki + E5 Dense"
    )
    e5w_slug_to_tids = e5w_consol.pop("slug_to_tids")

    def e5w_wiki_top10(q_text: str) -> list[int]:
        matches = e5w_engine.search(q_text, top_k=10)
        out: list[int] = []
        for m in matches:
            tids = sorted(e5w_slug_to_tids.get(m.slug, set()))
            out.append(tids[0] if tids else -1)
        return out

    e5w_metrics = evaluate_retriever(questions, e5w_wiki_top10)

    # 4. Run live Gemini QA over Top-3 retrieved pages for E5-Raw vs LLM Wiki + E5
    qa_llm = LLMService(
        RuntimeSettings(
            provider="gemini",
            gemini_api_key=GEMINI_API_KEY,
            gemini_model=GEMINI_MODEL,
        ),
        telemetry=telemetry,
    )

    def eval_qa_system(name: str, get_pages_fn: Any) -> dict[str, Any]:
        rec_sum = f1_sum = em_sum = 0.0
        for q in questions:
            retrieved = get_pages_fn(q["question"])
            ans = qa_llm.answer_wiki_query(
                question=q["question"],
                history=[],
                retrieved_pages=retrieved,
                index_markdown="",
            )
            direct = ans.split("### Direct Answer", 1)[-1].split("\n> **Extractive")[0].split("\n### ")[0].strip()
            rec, f1 = compute_token_recall_f1(direct, q["answers"])
            rec_sum += rec
            f1_sum += f1
            norm_pred = normalize_answer(direct)
            if any(normalize_answer(g) in norm_pred for g in q["answers"] if normalize_answer(g)):
                em_sum += 1.0
        nq = len(questions)
        return {
            "system": name,
            "token_recall_pct": round(rec_sum / nq * 100, 2),
            "token_f1_pct": round(f1_sum / nq * 100, 2),
            "answer_contains_gold_pct": round(em_sum / nq * 100, 2),
        }

    def get_e5_raw_pages(q_text: str) -> list[tuple[WikiPage, float]]:
        qv = np.array(embedder.embed_query(q_text), dtype=np.float32)
        sims = raw_embs @ qv
        idx = np.argsort(-sims)[:3].tolist()
        return [
            (
                WikiPage(
                    slug=f"raw-{i}",
                    title=wave_docs[i]["title"],
                    category="sources",
                    summary="",
                    tags=[],
                    body=wave_docs[i]["content"],
                    path=Path(f"raw/{i}.md"),
                ),
                float(sims[i]),
            )
            for i in idx
        ]

    def get_e5w_pages(q_text: str) -> list[tuple[WikiPage, float]]:
        matches = e5w_engine.search(q_text, top_k=3)
        return [(e5w_pages[m.slug], m.score) for m in matches if m.slug in e5w_pages]

    qa_e5_raw = eval_qa_system("Pure E5-Large (Top-3 Raw Docs)", get_e5_raw_pages)
    qa_e5_wiki = eval_qa_system("LLM Wiki + E5 Dense (Top-3 Consolidated Pages)", get_e5w_pages)

    report = {
        "experiment": "50 TeleQuAD Questions x 4x LLM-Rephrased Redundancy (200 Docs)",
        "rephrase_model": GEMINI_MODEL,
        "embedding_model": "intfloat/multilingual-e5-large",
        "consolidation": {
            "lexical_only": lex_consol,
            "wiki_plus_e5": e5w_consol,
        },
        "retrieval": {
            "pure_e5_4x_raw": {**e5_metrics, "index_s": e5_index_s, "active_docs": len(wave_docs)},
            "llm_wiki_lexical_only": {**lex_metrics, "active_docs": len(lex_pages)},
            "llm_wiki_plus_e5_dense": {**e5w_metrics, "active_docs": len(e5w_pages)},
        },
        "qa_end_to_end": {
            "pure_e5_4x_raw": qa_e5_raw,
            "llm_wiki_plus_e5_dense": qa_e5_wiki,
        },
        "telemetry_summary": telemetry.summary(limit_recent=10)["totals"],
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
