from __future__ import annotations

import json
import random
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_SITE = ROOT_DIR / ".venv" / "lib" / "python3.13" / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

from backend.config import RuntimeSettings
from backend.llm_providers import LLMService
from backend.similarity import HybridSimilarityEngine, tokenize
from backend.vault_manager import WikiPage, slugify, utc_now_iso


def encode_e5_length_sorted(
    tok: AutoTokenizer,
    model: AutoModel,
    device: str,
    texts: list[str],
    batch_size: int = 64,
) -> np.ndarray:
    n = len(texts)
    order = sorted(range(n), key=lambda i: len(texts[i]))
    sorted_texts = [texts[i] for i in order]
    sorted_embs: list[torch.Tensor] = []

    with torch.no_grad():
        for i in range(0, n, batch_size):
            batch = sorted_texts[i : i + batch_size]
            enc = tok(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(device)
            out = model(**enc)
            mask = enc["attention_mask"].unsqueeze(-1).expand(out.last_hidden_state.size()).float()
            pooled = torch.sum(out.last_hidden_state.float() * mask, 1) / torch.clamp(mask.sum(1), min=1e-9)
            sorted_embs.append(F.normalize(pooled, p=2, dim=1).cpu())

    cat_sorted = torch.cat(sorted_embs, dim=0)
    out_tensor = torch.empty_like(cat_sorted)
    inv_order = torch.tensor(order, dtype=torch.long)
    out_tensor[inv_order] = cat_sorted
    return out_tensor.numpy()

JAQUAD_PATH = ROOT_DIR / "tests" / "fixtures" / "jaquad_dev_0000.json"
OUT_JSON = ROOT_DIR / "tests" / "fixtures" / "jaquad_benchmark_results.json"
REPORT_PATH = ROOT_DIR / "BENCHMARK_JAPANESE_JAQUAD_REPORT.md"


def normalize_ja_answer(text: str) -> str:
    s = unicodedata.normalize("NFKC", text).lower()
    s = re.sub(r"[、。！？「」『』（）()\[\]【】・，．,:;\"'`~〜\s]+", "", s)
    return s


def answer_in_passages(passages: list[str], gold_answers: list[str]) -> bool:
    joined = normalize_ja_answer(" ".join(passages))
    for g in gold_answers:
        ng = normalize_ja_answer(g)
        if ng and ng in joined:
            return True
    return False


def build_jaquad_corpus() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw = json.loads(JAQUAD_PATH.read_text(encoding="utf-8"))
    passages: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []

    p_idx = 0
    for art in raw["data"]:
        art_title = art["title"].strip()
        for sec_i, para in enumerate(art["paragraphs"]):
            context = para["context"].strip()
            first_line = context.splitlines()[0].strip()
            first_clause = re.split(r"[。！？]", first_line)[0].strip()[:28]
            title = f"{art_title} 第{sec_i + 1}節 ({first_clause})"
            slug = f"jaquad-{p_idx:03d}-{slugify(art_title)}-{sec_i + 1}"

            passages.append(
                {
                    "passage_id": p_idx,
                    "article_title": art_title,
                    "title": title,
                    "expected_slug": slug,
                    "content": context,
                }
            )

            for qa in para["qas"]:
                ans_texts = list({a["text"].strip() for a in qa.get("answers", []) if a.get("text", "").strip()})
                if not ans_texts:
                    continue
                questions.append(
                    {
                        "id": qa["id"],
                        "question": qa["question"].strip(),
                        "answers": ans_texts,
                        "gold_passage_id": p_idx,
                        "gold_slug": slug,
                        "article_title": art_title,
                    }
                )
            p_idx += 1

    return passages, questions


def split_ja_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[。！？])\s*", text.strip()) if p.strip()]
    return parts if parts else [text.strip()]


def build_5x_redundant_waves(passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Build 5 waves of full Japanese passages (407 * 5 = 2,035 documents):
    - Wave 1: Canonical passage
    - Wave 2: Re-titled duplicate ("【アーカイブ資料】{title}")
    - Wave 3: Sentence-reordered full passage (cyclic shift of Japanese sentences)
    - Wave 4: Blind-title field memo (title has NO article name, only first 18 chars of a middle sentence)
    - Wave 5: Cross-audit note with editorial prefix + full passage
    """
    rng = random.Random(42)
    wave_docs: list[dict[str, Any]] = []

    for wave_num in range(1, 6):
        order = list(passages)
        if wave_num > 1:
            rng.shuffle(order)
        for p in order:
            pid = p["passage_id"]
            title = p["title"]
            content = p["content"]
            sents = split_ja_sentences(content)

            if wave_num == 1:
                w_title = title
                w_body = content
            elif wave_num == 2:
                w_title = f"【アーカイブ記録】{title}"
                w_body = content
            elif wave_num == 3:
                rotated = sents[1:] + sents[:1] if len(sents) > 1 else sents
                w_title = f"{title} — 再構成ノート"
                w_body = "".join(rotated)
            elif wave_num == 4:
                mid_sent = sents[len(sents) // 2] if sents else content
                snippet = re.sub(r"[、。！？\s]+", "", mid_sent)[:18]
                w_title = f"調査メモ #{pid:03d}: {snippet}"
                w_body = content
            else:
                rotated = list(reversed(sents)) if len(sents) > 1 else sents
                w_title = f"技術監査ログ {pid:03d} ({p['article_title']})"
                w_body = "".join(rotated)

            wave_docs.append(
                {
                    "wave": wave_num,
                    "passage_id": pid,
                    "gold_slug": p["expected_slug"],
                    "title": w_title,
                    "content": w_body,
                    "source_name": f"jaquad-w{wave_num}-p{pid:03d}.md",
                }
            )
    return wave_docs


def consolidate_with_llm_wiki(
    wave_docs: list[dict[str, Any]],
) -> tuple[dict[str, WikiPage], HybridSimilarityEngine, dict[str, Any]]:
    settings = RuntimeSettings(provider="local_smart", similarity_threshold=0.35)
    llm = LLMService(settings)
    pages: dict[str, WikiPage] = {}
    engine = HybridSimilarityEngine(pages)

    t0 = time.perf_counter()
    created_count = 0
    updated_count = 0
    wave_stats: dict[int, dict[str, int]] = {w: {"created": 0, "updated": 0} for w in range(1, 6)}
    slug_to_pids: dict[str, set[int]] = {}
    current_wave = 0

    for doc in wave_docs:
        w = doc["wave"]
        if w != current_wave:
            if current_wave == 1 and pages:
                engine._build_index()
            current_wave = w
        pid = doc["passage_id"]
        cand_tags = llm._extract_tags(doc["title"], doc["content"], {})
        sim = engine.find_similar_for_candidate(
            title=doc["title"],
            content=doc["content"],
            tags=cand_tags,
            aliases=[],
            links=[],
            threshold=0.35,
        )
        if sim["action"] == "update" and sim["target_slug"] in pages:
            target_slug = sim["target_slug"]
            existing_page = pages[target_slug]
            syn = llm._local_synthesize_page_update(
                existing_page=existing_page,
                new_title=doc["title"],
                new_content=doc["content"],
                source_name=doc["source_name"],
                new_tags=cand_tags,
                all_pages=pages,
            )
            existing_page.body = syn["updated_body"]
            existing_page.revision_count += 1
            engine.upsert_page(existing_page)
            updated_count += 1
            wave_stats[w]["updated"] += 1
            slug_to_pids.setdefault(target_slug, set()).add(pid)
        else:
            base_slug = doc["gold_slug"] if w == 1 else slugify(doc["title"])
            slug = base_slug
            idx = 2
            while slug in pages:
                slug = f"{base_slug}-{idx}"
                idx += 1
            body = f"# {doc['title']}\n\n{doc['content']}"
            page = WikiPage(
                slug=slug,
                title=doc["title"],
                category="concepts",
                summary=doc["content"][:140],
                tags=cand_tags,
                aliases=[],
                sources=[doc["source_name"]],
                updated_at=utc_now_iso()[:10],
                revision_count=1,
                body=body,
                path=Path(f"wiki/concepts/{slug}.md"),
            )
            pages[slug] = page
            engine.upsert_page(page)
            created_count += 1
            wave_stats[w]["created"] += 1
            slug_to_pids.setdefault(slug, set()).add(pid)

    engine._build_index()
    elapsed = time.perf_counter() - t0
    stats = {
        "total_docs_ingested": len(wave_docs),
        "created_pages": created_count,
        "updated_pages": updated_count,
        "dedup_rate_waves_2_to_5": round(
            sum(wave_stats[w]["updated"] for w in range(2, 6))
            / max(sum(wave_stats[w]["created"] + wave_stats[w]["updated"] for w in range(2, 6)), 1)
            * 100,
            2,
        ),
        "wave_stats": wave_stats,
        "elapsed_s": round(elapsed, 2),
        "slug_to_pids": slug_to_pids,
    }
    return pages, engine, stats


def main() -> None:
    passages, questions = build_jaquad_corpus()
    print(f"Loaded JaQuAD: {len(passages)} Japanese passages, {len(questions)} Japanese QAs")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading intfloat/multilingual-e5-large on {device}...")
    e5_tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
    e5_model = AutoModel.from_pretrained("intfloat/multilingual-e5-large").to(device)
    e5_model.eval()

    # Encode all 1,029 questions once
    q_texts = [f"query: {q['question']}" for q in questions]
    t_q = time.perf_counter()
    q_embs = encode_e5_length_sorted(e5_tok, e5_model, device, q_texts, batch_size=64)
    q_encode_s = time.perf_counter() - t_q

    # =========================================================================
    # PART 1: 1x Standard Evaluation (407 Japanese Passages, 1,029 QAs)
    # =========================================================================
    print("Running 1x evaluation (407 passages)...")
    p_texts_1x = [f"passage: {p['title']}\n\n{p['content']}" for p in passages]
    t_e5_1x = time.perf_counter()
    p_embs_1x = encode_e5_length_sorted(e5_tok, e5_model, device, p_texts_1x, batch_size=64)
    e5_1x_index_s = time.perf_counter() - t_e5_1x

    sim_1x = np.matmul(q_embs, p_embs_1x.T)

    # Build 1x LLM Wiki engine
    pages_1x: dict[str, WikiPage] = {}
    for p in passages:
        slug = p["expected_slug"]
        pages_1x[slug] = WikiPage(
            slug=slug,
            title=p["title"],
            category="concepts",
            summary=p["content"][:140],
            tags=tokenize(p["title"])[:5],
            aliases=[p["article_title"]],
            sources=[f"jaquad-p{p['passage_id']:03d}.md"],
            updated_at="2026-11-14",
            revision_count=1,
            body=f"# {p['title']}\n\n{p['content']}",
            path=Path(f"wiki/concepts/{slug}.md"),
        )
    t_w1 = time.perf_counter()
    wiki_engine_1x = HybridSimilarityEngine(pages_1x)
    wiki_1x_index_s = time.perf_counter() - t_w1

    slug_to_pid_1x = {p["expected_slug"]: p["passage_id"] for p in passages}

    metrics_1x = {
        "e5_1x": {"r1": 0, "r3": 0, "r5": 0, "r10": 0, "mrr": 0.0, "ans1": 0, "ans3": 0, "ans5": 0},
        "wiki_1x": {"r1": 0, "r3": 0, "r5": 0, "r10": 0, "mrr": 0.0, "ans1": 0, "ans3": 0, "ans5": 0},
        "hybrid_1x": {"r1": 0, "r3": 0, "r5": 0, "r10": 0, "mrr": 0.0, "ans1": 0, "ans3": 0, "ans5": 0},
    }

    for q_i, q in enumerate(questions):
        gold_pid = q["gold_passage_id"]
        gold_ans = q["answers"]

        # E5 1x
        scores_e5 = sim_1x[q_i]
        top_e5_idx = np.argsort(-scores_e5)[:10].tolist()
        if gold_pid in top_e5_idx:
            rank = top_e5_idx.index(gold_pid) + 1
            if rank == 1:
                metrics_1x["e5_1x"]["r1"] += 1
            if rank <= 3:
                metrics_1x["e5_1x"]["r3"] += 1
            if rank <= 5:
                metrics_1x["e5_1x"]["r5"] += 1
            if rank <= 10:
                metrics_1x["e5_1x"]["r10"] += 1
            metrics_1x["e5_1x"]["mrr"] += 1.0 / rank
        if answer_in_passages([passages[i]["content"] for i in top_e5_idx[:1]], gold_ans):
            metrics_1x["e5_1x"]["ans1"] += 1
        if answer_in_passages([passages[i]["content"] for i in top_e5_idx[:3]], gold_ans):
            metrics_1x["e5_1x"]["ans3"] += 1
        if answer_in_passages([passages[i]["content"] for i in top_e5_idx[:5]], gold_ans):
            metrics_1x["e5_1x"]["ans5"] += 1

        # LLM Wiki 1x
        w_matches = wiki_engine_1x.search(query=q["question"], top_k=10)
        top_w_pids = [slug_to_pid_1x[m.slug] for m in w_matches]
        if gold_pid in top_w_pids:
            rank = top_w_pids.index(gold_pid) + 1
            if rank == 1:
                metrics_1x["wiki_1x"]["r1"] += 1
            if rank <= 3:
                metrics_1x["wiki_1x"]["r3"] += 1
            if rank <= 5:
                metrics_1x["wiki_1x"]["r5"] += 1
            if rank <= 10:
                metrics_1x["wiki_1x"]["r10"] += 1
            metrics_1x["wiki_1x"]["mrr"] += 1.0 / rank
        if answer_in_passages([pages_1x[m.slug].body for m in w_matches[:1]], gold_ans):
            metrics_1x["wiki_1x"]["ans1"] += 1
        if answer_in_passages([pages_1x[m.slug].body for m in w_matches[:3]], gold_ans):
            metrics_1x["wiki_1x"]["ans3"] += 1
        if answer_in_passages([pages_1x[m.slug].body for m in w_matches[:5]], gold_ans):
            metrics_1x["wiki_1x"]["ans5"] += 1

        # Hybrid 1x (RRF + normalized score fusion)
        w_all = wiki_engine_1x.search(query=q["question"], top_k=25)
        w_map = {slug_to_pid_1x[m.slug]: m.score for m in w_all}
        w_max = max(w_map.values(), default=1.0) or 1.0
        e5_top25 = np.argsort(-scores_e5)[:25].tolist()
        cand_pids = set(w_map.keys()) | set(e5_top25)
        e5_min = float(np.min(scores_e5[e5_top25]))
        e5_span = max(float(np.max(scores_e5[e5_top25])) - e5_min, 1e-6)
        fused = []
        for pid in cand_pids:
            wn = w_map.get(pid, 0.0) / w_max
            en = max((float(scores_e5[pid]) - e5_min) / e5_span, 0.0)
            fused.append((0.55 * wn + 0.45 * en, pid))
        fused.sort(reverse=True)
        top_h_pids = [pid for _, pid in fused[:10]]
        if gold_pid in top_h_pids:
            rank = top_h_pids.index(gold_pid) + 1
            if rank == 1:
                metrics_1x["hybrid_1x"]["r1"] += 1
            if rank <= 3:
                metrics_1x["hybrid_1x"]["r3"] += 1
            if rank <= 5:
                metrics_1x["hybrid_1x"]["r5"] += 1
            if rank <= 10:
                metrics_1x["hybrid_1x"]["r10"] += 1
            metrics_1x["hybrid_1x"]["mrr"] += 1.0 / rank
        if answer_in_passages([passages[i]["content"] for i in top_h_pids[:1]], gold_ans):
            metrics_1x["hybrid_1x"]["ans1"] += 1
        if answer_in_passages([passages[i]["content"] for i in top_h_pids[:3]], gold_ans):
            metrics_1x["hybrid_1x"]["ans3"] += 1
        if answer_in_passages([passages[i]["content"] for i in top_h_pids[:5]], gold_ans):
            metrics_1x["hybrid_1x"]["ans5"] += 1

    # =========================================================================
    # PART 2: 5x Redundancy Evaluation (2,035 Japanese Wave Docs, 1,029 QAs)
    # =========================================================================
    print("Building 5x redundant Japanese wave corpus (2,035 docs)...")
    wave_docs = build_5x_redundant_waves(passages)
    pages_5x, wiki_engine_5x, consol_stats = consolidate_with_llm_wiki(wave_docs)
    slug_to_pids_5x = consol_stats.pop("slug_to_pids")
    print(
        f"LLM Wiki consolidated {len(wave_docs)} Japanese docs -> {len(pages_5x)} pages "
        f"({consol_stats['dedup_rate_waves_2_to_5']}% Wave 2-5 dedup rate) in {consol_stats['elapsed_s']}s"
    )

    # Encode all 2,035 raw wave docs with E5-Large
    w_texts = [f"passage: {d['title']}\n\n{d['content']}" for d in wave_docs]
    t_e5_5x = time.perf_counter()
    w_embs_5x = encode_e5_length_sorted(e5_tok, e5_model, device, w_texts, batch_size=64)
    e5_5x_index_s = time.perf_counter() - t_e5_5x
    sim_e5_5x = np.matmul(q_embs, w_embs_5x.T)

    # Also encode the consolidated LLM Wiki pages for Hybrid 5x
    cons_slugs = list(pages_5x.keys())
    cons_texts = [f"passage: {pages_5x[s].title}\n\n{pages_5x[s].body}" for s in cons_slugs]
    cons_embs = encode_e5_length_sorted(e5_tok, e5_model, device, cons_texts, batch_size=64)
    sim_cons_e5 = np.matmul(q_embs, cons_embs.T)
    slug_to_cons_idx = {s: i for i, s in enumerate(cons_slugs)}

    metrics_5x = {
        "e5_5x_raw": {
            "r1": 0,
            "r3": 0,
            "r5": 0,
            "r10": 0,
            "mrr": 0.0,
            "ans1": 0,
            "ans3": 0,
            "ans5": 0,
            "unique_topics_top10": 0,
            "wasted_slots_top10": 0,
        },
        "wiki_5x_consolidated": {
            "r1": 0,
            "r3": 0,
            "r5": 0,
            "r10": 0,
            "mrr": 0.0,
            "ans1": 0,
            "ans3": 0,
            "ans5": 0,
            "unique_topics_top10": 0,
            "wasted_slots_top10": 0,
        },
        "hybrid_5x_consolidated": {
            "r1": 0,
            "r3": 0,
            "r5": 0,
            "r10": 0,
            "mrr": 0.0,
            "ans1": 0,
            "ans3": 0,
            "ans5": 0,
            "unique_topics_top10": 0,
            "wasted_slots_top10": 0,
        },
    }

    for q_i, q in enumerate(questions):
        gold_pid = q["gold_passage_id"]
        gold_ans = q["answers"]

        # 1. E5-Large on 2,035 raw wave docs
        sc_raw = sim_e5_5x[q_i]
        top_raw_idx = np.argsort(-sc_raw)[:10].tolist()
        top_raw_pids = [wave_docs[i]["passage_id"] for i in top_raw_idx]
        uniq_raw = len(set(top_raw_pids))
        metrics_5x["e5_5x_raw"]["unique_topics_top10"] += uniq_raw
        metrics_5x["e5_5x_raw"]["wasted_slots_top10"] += 10 - uniq_raw
        if gold_pid in top_raw_pids:
            rank = top_raw_pids.index(gold_pid) + 1
            if rank == 1:
                metrics_5x["e5_5x_raw"]["r1"] += 1
            if rank <= 3:
                metrics_5x["e5_5x_raw"]["r3"] += 1
            if rank <= 5:
                metrics_5x["e5_5x_raw"]["r5"] += 1
            if rank <= 10:
                metrics_5x["e5_5x_raw"]["r10"] += 1
            metrics_5x["e5_5x_raw"]["mrr"] += 1.0 / rank
        if answer_in_passages([wave_docs[i]["content"] for i in top_raw_idx[:1]], gold_ans):
            metrics_5x["e5_5x_raw"]["ans1"] += 1
        if answer_in_passages([wave_docs[i]["content"] for i in top_raw_idx[:3]], gold_ans):
            metrics_5x["e5_5x_raw"]["ans3"] += 1
        if answer_in_passages([wave_docs[i]["content"] for i in top_raw_idx[:5]], gold_ans):
            metrics_5x["e5_5x_raw"]["ans5"] += 1

        # 2. LLM Wiki Consolidated Vault
        w_matches = wiki_engine_5x.search(query=q["question"], top_k=10)
        top_w_slugs = [m.slug for m in w_matches]
        seen_pids: set[int] = set()
        hit_rank = None
        for r_idx, s in enumerate(top_w_slugs, start=1):
            pids = slug_to_pids_5x.get(s, set())
            seen_pids.update(pids)
            if hit_rank is None and gold_pid in pids:
                hit_rank = r_idx
        uniq_w = min(len(seen_pids), 10)
        metrics_5x["wiki_5x_consolidated"]["unique_topics_top10"] += uniq_w
        metrics_5x["wiki_5x_consolidated"]["wasted_slots_top10"] += max(len(top_w_slugs) - uniq_w, 0)
        if hit_rank is not None:
            if hit_rank == 1:
                metrics_5x["wiki_5x_consolidated"]["r1"] += 1
            if hit_rank <= 3:
                metrics_5x["wiki_5x_consolidated"]["r3"] += 1
            if hit_rank <= 5:
                metrics_5x["wiki_5x_consolidated"]["r5"] += 1
            if hit_rank <= 10:
                metrics_5x["wiki_5x_consolidated"]["r10"] += 1
            metrics_5x["wiki_5x_consolidated"]["mrr"] += 1.0 / hit_rank
        if answer_in_passages([pages_5x[s].body for s in top_w_slugs[:1]], gold_ans):
            metrics_5x["wiki_5x_consolidated"]["ans1"] += 1
        if answer_in_passages([pages_5x[s].body for s in top_w_slugs[:3]], gold_ans):
            metrics_5x["wiki_5x_consolidated"]["ans3"] += 1
        if answer_in_passages([pages_5x[s].body for s in top_w_slugs[:5]], gold_ans):
            metrics_5x["wiki_5x_consolidated"]["ans5"] += 1

        # 3. Hybrid LLM Wiki + E5 on Consolidated Vault
        w_all = wiki_engine_5x.search(query=q["question"], top_k=25)
        w_map = {m.slug: m.score for m in w_all}
        w_max = max(w_map.values(), default=1.0) or 1.0
        sc_ce5 = sim_cons_e5[q_i]
        e5_top25_idx = np.argsort(-sc_ce5)[:25].tolist()
        cand_slugs = set(w_map.keys()) | {cons_slugs[i] for i in e5_top25_idx}
        e5_min = float(np.min(sc_ce5[e5_top25_idx]))
        e5_span = max(float(np.max(sc_ce5[e5_top25_idx])) - e5_min, 1e-6)
        fused_s = []
        for s in cand_slugs:
            wn = w_map.get(s, 0.0) / w_max
            c_idx = slug_to_cons_idx[s]
            en = max((float(sc_ce5[c_idx]) - e5_min) / e5_span, 0.0)
            fused_s.append((0.55 * wn + 0.45 * en, s))
        fused_s.sort(reverse=True)
        top_h_slugs = [s for _, s in fused_s[:10]]
        seen_h_pids: set[int] = set()
        h_rank = None
        for r_idx, s in enumerate(top_h_slugs, start=1):
            pids = slug_to_pids_5x.get(s, set())
            seen_h_pids.update(pids)
            if h_rank is None and gold_pid in pids:
                h_rank = r_idx
        uniq_h = min(len(seen_h_pids), 10)
        metrics_5x["hybrid_5x_consolidated"]["unique_topics_top10"] += uniq_h
        metrics_5x["hybrid_5x_consolidated"]["wasted_slots_top10"] += max(len(top_h_slugs) - uniq_h, 0)
        if h_rank is not None:
            if h_rank == 1:
                metrics_5x["hybrid_5x_consolidated"]["r1"] += 1
            if h_rank <= 3:
                metrics_5x["hybrid_5x_consolidated"]["r3"] += 1
            if h_rank <= 5:
                metrics_5x["hybrid_5x_consolidated"]["r5"] += 1
            if h_rank <= 10:
                metrics_5x["hybrid_5x_consolidated"]["r10"] += 1
            metrics_5x["hybrid_5x_consolidated"]["mrr"] += 1.0 / h_rank
        if answer_in_passages([pages_5x[s].body for s in top_h_slugs[:1]], gold_ans):
            metrics_5x["hybrid_5x_consolidated"]["ans1"] += 1
        if answer_in_passages([pages_5x[s].body for s in top_h_slugs[:3]], gold_ans):
            metrics_5x["hybrid_5x_consolidated"]["ans3"] += 1
        if answer_in_passages([pages_5x[s].body for s in top_h_slugs[:5]], gold_ans):
            metrics_5x["hybrid_5x_consolidated"]["ans5"] += 1

    nq = len(questions)
    summary = {
        "dataset": "JaQuAD dev_0000 (Japanese Wikipedia Question Answering)",
        "total_passages_1x": len(passages),
        "total_docs_5x": len(wave_docs),
        "total_questions": nq,
        "consolidation_5x": consol_stats,
        "results_1x": {
            k: {
                "R@1": round(v["r1"] / nq * 100, 2),
                "R@3": round(v["r3"] / nq * 100, 2),
                "R@5": round(v["r5"] / nq * 100, 2),
                "R@10": round(v["r10"] / nq * 100, 2),
                "MRR@10": round(v["mrr"] / nq * 100, 2),
                "Ans@1": round(v["ans1"] / nq * 100, 2),
                "Ans@3": round(v["ans3"] / nq * 100, 2),
                "Ans@5": round(v["ans5"] / nq * 100, 2),
            }
            for k, v in metrics_1x.items()
        },
        "results_5x": {
            k: {
                "R@1": round(v["r1"] / nq * 100, 2),
                "R@3": round(v["r3"] / nq * 100, 2),
                "R@5": round(v["r5"] / nq * 100, 2),
                "R@10": round(v["r10"] / nq * 100, 2),
                "MRR@10": round(v["mrr"] / nq * 100, 2),
                "Ans@1": round(v["ans1"] / nq * 100, 2),
                "Ans@3": round(v["ans3"] / nq * 100, 2),
                "Ans@5": round(v["ans5"] / nq * 100, 2),
                "avg_unique_topics_top10": round(v["unique_topics_top10"] / nq, 2),
                "wasted_duplicate_slots_pct": round(v["wasted_slots_top10"] / (nq * 10) * 100, 2),
            }
            for k, v in metrics_5x.items()
        },
        "timings_s": {
            "e5_1x_index_s": round(e5_1x_index_s, 2),
            "wiki_1x_index_s": round(wiki_1x_index_s, 2),
            "e5_5x_index_s": round(e5_5x_index_s, 2),
            "wiki_5x_consolidate_s": consol_stats["elapsed_s"],
            "q_encode_s": round(q_encode_s, 2),
        },
    }

    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
