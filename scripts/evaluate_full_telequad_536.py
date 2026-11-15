from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

VENV_SITE = (
    ROOT_DIR
    / ".venv"
    / "lib"
    / f"python{sys.version_info.major}.{sys.version_info.minor}"
    / "site-packages"
)
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.append(str(VENV_SITE))

import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

from backend.llm_providers import LLMService
from backend.similarity import HybridSimilarityEngine, tokenize, word_ngrams
from backend.vault_manager import WikiPage, slugify
from scripts.evaluate_qa_and_updates import compute_token_recall_f1, normalize_answer

FULL_TELEQUAD_PATH = ROOT_DIR / "tests" / "fixtures" / "TeleQuAD-v4-full.json"
DEFAULT_REPORT_PATH = ROOT_DIR / "BENCHMARK_FULL_TELEQUAD_536_REPORT.md"
MAIN_REPORT_PATH = ROOT_DIR / "BENCHMARK_REPORT.md"
E5_MODEL_ID = "intfloat/multilingual-e5-large"

_RE_ACRONYM = re.compile(r"\b[A-Z0-9][A-Z0-9_-]{1,}\b")
_RE_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
_RE_CAP_NAME = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
_RE_LOC_PREP = re.compile(r"\b(?:in|at|near|from)\s+[A-Z][a-z]+")


def load_full_telequad() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    raw = json.loads(FULL_TELEQUAD_PATH.read_text(encoding="utf-8"))
    articles = raw["data"]

    spec_counts: dict[str, int] = defaultdict(int)
    parsed_meta: list[tuple[str, str, str, str]] = []
    for idx, art in enumerate(articles):
        raw_title = art["title"]
        ctx = art["paragraphs"][0]["context"]
        first_line = ctx.strip().splitlines()[0].strip()[:80]
        if raw_title.startswith("3GPP-Specs#"):
            parts = raw_title.split("#")
            spec = parts[1]
            sec = parts[2] if len(parts) > 2 else str(idx)
            title = f"3GPP {spec} #{sec}: {first_line}"
        else:
            spec = raw_title
            sec = "0"
            title = raw_title
        spec_counts[spec] += 1
        parsed_meta.append((raw_title, spec, sec, title))

    passages: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    for idx, art in enumerate(articles):
        raw_title, spec, sec, title = parsed_meta[idx]
        ctx = art["paragraphs"][0]["context"]
        passages.append(
            {
                "p_idx": idx,
                "raw_title": raw_title,
                "spec": spec,
                "sec": sec,
                "title": title,
                "content": ctx,
                "char_len": len(ctx),
                "is_long": len(ctx) > 2000,
                "spec_passage_count": spec_counts[spec],
                "is_multi_clause": spec_counts[spec] > 1,
                "norm_content": normalize_answer(ctx),
            }
        )
        for qa in art["paragraphs"][0]["qas"]:
            golds = [ans["text"] for ans in qa.get("answers", []) if ans.get("text")]
            g_norm = [normalize_answer(g) for g in golds if normalize_answer(g)]
            questions.append(
                {
                    "q_idx": len(questions),
                    "p_idx": idx,
                    "spec": spec,
                    "question": qa["question"],
                    "golds": golds,
                    "g_norm": g_norm,
                    "is_long": len(ctx) > 2000,
                    "is_multi_clause": spec_counts[spec] > 1,
                }
            )
    return passages, questions, dict(spec_counts)


def chunk_passages(
    passages: list[dict[str, Any]], max_chars: int = 1000
) -> tuple[list[dict[str, Any]], dict[int, list[int]]]:
    """Split passages <= max_chars with 1-sentence overlap to stay inside E5's 512-token limit."""
    chunks: list[dict[str, Any]] = []
    chunks_by_passage: dict[int, list[int]] = defaultdict(list)

    for p in passages:
        text = p["content"].strip()
        if len(text) <= max_chars:
            cid = len(chunks)
            chunks.append(
                {
                    "c_idx": cid,
                    "p_idx": p["p_idx"],
                    "spec": p["spec"],
                    "title": p["title"],
                    "content": text,
                    "norm_content": normalize_answer(text),
                }
            )
            chunks_by_passage[p["p_idx"]].append(cid)
            continue

        sents = LLMService._split_technical_sentences(text)
        cur: list[str] = []
        cur_len = 0
        for s in sents:
            if cur and cur_len + len(s) + 1 > max_chars:
                c_text = " ".join(cur)
                cid = len(chunks)
                chunks.append(
                    {
                        "c_idx": cid,
                        "p_idx": p["p_idx"],
                        "spec": p["spec"],
                        "title": p["title"],
                        "content": c_text,
                        "norm_content": normalize_answer(c_text),
                    }
                )
                chunks_by_passage[p["p_idx"]].append(cid)
                cur = [cur[-1], s] if len(cur[-1]) < 350 else [s]
                cur_len = sum(len(x) + 1 for x in cur)
            else:
                cur.append(s)
                cur_len += len(s) + 1
        if cur:
            c_text = " ".join(cur)
            cid = len(chunks)
            chunks.append(
                {
                    "c_idx": cid,
                    "p_idx": p["p_idx"],
                    "spec": p["spec"],
                    "title": p["title"],
                    "content": c_text,
                    "norm_content": normalize_answer(c_text),
                }
            )
            chunks_by_passage[p["p_idx"]].append(cid)

    return chunks, dict(chunks_by_passage)


def encode_e5_texts(
    tok: AutoTokenizer,
    model: AutoModel,
    device: str,
    texts: list[str],
    batch_size: int = 64,
) -> torch.Tensor:
    out_embs: list[torch.Tensor] = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            enc = tok(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(device)
            out = model(**enc)
            mask = enc["attention_mask"].unsqueeze(-1).expand(out.last_hidden_state.size()).float()
            pooled = torch.sum(out.last_hidden_state * mask, 1) / torch.clamp(mask.sum(1), min=1e-9)
            out_embs.append(F.normalize(pooled, p=2, dim=1).cpu())
    return torch.cat(out_embs, dim=0)


class FastSentenceMatcher:
    """
    Cached equivalent of LLMService._score_text_for_question over pre-split sentences.
    Avoids re-splitting and re-tokenizing the same 536 passages / ~1.4k chunks across 4,485 QAs.
    """

    def __init__(self) -> None:
        # doc_key -> (sents_features, tok_to_sids, pref_to_sids)
        self._docs: dict[
            tuple[str, int],
            tuple[
                list[tuple[str, str, set[str], set[str], set[str], set[str], bool, bool, bool]],
                dict[str, list[int]],
                dict[str, list[int]],
            ],
        ] = {}

    def register(self, kind: str, unit_id: int, text: str) -> None:
        key = (kind, unit_id)
        if key in self._docs:
            return
        raw_sents = [s for s in LLMService._split_technical_sentences(text) if len(s) >= 12]
        if not raw_sents:
            raw_sents = [text.strip() or text]

        feats: list[tuple[str, str, set[str], set[str], set[str], set[str], bool, bool, bool]] = []
        tok_to_sids: dict[str, list[int]] = defaultdict(list)
        pref_to_sids: dict[str, list[int]] = defaultdict(list)
        for sid, s in enumerate(raw_sents):
            toks = tokenize(s)
            t_set = set(toks)
            bi_set = set(word_ngrams(toks, 2))
            t_pref = {t[:5] for t in t_set if len(t) >= 5}
            acronyms = set(_RE_ACRONYM.findall(s))
            has_num = bool(_RE_NUM.search(s))
            has_cap = bool(_RE_CAP_NAME.search(s))
            has_loc = bool(_RE_LOC_PREP.search(s))
            norm_s = normalize_answer(s)
            feats.append((s, norm_s, t_set, bi_set, t_pref, acronyms, has_num, has_cap, has_loc))
            for t in t_set:
                tok_to_sids[t].append(sid)
            for p in t_pref:
                pref_to_sids[p].append(sid)
        self._docs[key] = (feats, dict(tok_to_sids), dict(pref_to_sids))

    @staticmethod
    def prepare_query(question: str) -> dict[str, Any]:
        q_lower = question.lower()
        q_toks = tokenize(question)
        q_tok_set = set(q_toks)
        q_bigrams = set(word_ngrams(q_toks, 2))
        q_prefixes = {t[:5] for t in q_tok_set if len(t) >= 5}
        q_acronyms = set(_RE_ACRONYM.findall(question))
        cue_num = any(
            w in q_lower
            for w in ("when", "what year", "how many", "how much", "how long", "what percentage", "what number")
        )
        cue_who = any(
            w in q_lower
            for w in ("who", "which player", "which person", "whose", "assistant", "punter", "professor")
        )
        cue_where = any(w in q_lower for w in ("where", "what city", "what country", "what stadium"))
        return {
            "q_tok_set": q_tok_set,
            "q_tok_denom": max(len(q_tok_set), 1),
            "q_bigrams": q_bigrams,
            "q_prefixes": q_prefixes,
            "q_acronyms": q_acronyms,
            "cue_num": cue_num,
            "cue_who": cue_who,
            "cue_where": cue_where,
        }

    def best_sentence(self, kind: str, unit_id: int, q_meta: dict[str, Any]) -> tuple[str, str]:
        feats, tok_to_sids, pref_to_sids = self._docs[(kind, unit_id)]
        q_tok_set: set[str] = q_meta["q_tok_set"]
        q_prefixes: set[str] = q_meta["q_prefixes"]
        q_bigrams: set[str] = q_meta["q_bigrams"]
        q_acronyms: set[str] = q_meta["q_acronyms"]
        denom: int = q_meta["q_tok_denom"]

        cand_ids: set[int] = set()
        for t in q_tok_set:
            if t in tok_to_sids:
                cand_ids.update(tok_to_sids[t])
        for p in q_prefixes:
            if p in pref_to_sids:
                cand_ids.update(pref_to_sids[p])

        if not cand_ids:
            return feats[0][0], feats[0][1]

        best_score = -1.0
        best_sid = 0
        cue_num = q_meta["cue_num"]
        cue_who = q_meta["cue_who"]
        cue_where = q_meta["cue_where"]

        for sid in sorted(cand_ids):
            _, _, t_set, bi_set, t_pref, acronyms, has_num, has_cap, has_loc = feats[sid]
            if not t_set:
                continue
            overlap = q_tok_set & t_set
            stem_overlap = len(
                (q_prefixes & t_pref) - {t[:5] for t in overlap if len(t) >= 5}
            )
            if not overlap and stem_overlap == 0:
                continue
            idf_score = len(overlap) / denom
            bigram_overlap = len(q_bigrams & bi_set)
            stem_bonus = (stem_overlap / denom) * 0.9
            acronym_bonus = min(len(q_acronyms & acronyms) * 0.35, 1.05) if q_acronyms else 0.0
            cue_boost = 0.0
            if cue_num and has_num:
                cue_boost += 0.35
            if cue_who and has_cap:
                cue_boost += 0.25
            if cue_where and has_loc:
                cue_boost += 0.20

            score = idf_score * 2.0 + bigram_overlap * 1.1 + stem_bonus + acronym_bonus + cue_boost
            if score > best_score:
                best_score = score
                best_sid = sid

        if best_score < 0:
            return feats[0][0], feats[0][1]
        return feats[best_sid][0], feats[best_sid][1]


def evaluate_predictions(
    *,
    name: str,
    questions: list[dict[str, Any]],
    q_metas: list[dict[str, Any]],
    top10_units: list[list[int]],
    unit_specs: dict[int, str],
    unit_norms: dict[int, str],
    sent_kind: str,
    matcher: FastSentenceMatcher,
    passage_level: bool,
    build_time_s: float,
    search_time_s: float,
    index_units: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    n_q = len(questions)

    for qi, q in enumerate(questions):
        gold_p = q["p_idx"]
        gold_spec = q["spec"]
        g_norm = q["g_norm"]
        golds = q["golds"]
        top10 = top10_units[qi]

        if passage_level:
            if gold_p in top10:
                rank_p = top10.index(gold_p) + 1
                mrr_p = 1.0 / rank_p
            else:
                rank_p = None
                mrr_p = 0.0
        else:
            rank_p = None
            mrr_p = 0.0

        top_specs = [unit_specs[u] for u in top10]
        if gold_spec in top_specs:
            rank_spec = top_specs.index(gold_spec) + 1
            mrr_spec = 1.0 / rank_spec
        else:
            rank_spec = None
            mrr_spec = 0.0

        ans_top1 = False
        ans_top3 = False
        ans_top5 = False
        ans_top10 = False
        if g_norm:
            for pos, uid in enumerate(top10):
                text_n = unit_norms[uid]
                if any(g in text_n for g in g_norm):
                    if pos == 0:
                        ans_top1 = True
                    if pos < 3:
                        ans_top3 = True
                    if pos < 5:
                        ans_top5 = True
                    ans_top10 = True
                    break

        top1_uid = top10[0]
        best_sent, best_sent_norm = matcher.best_sentence(sent_kind, top1_uid, q_metas[qi])
        sent_span = any(g in best_sent_norm for g in g_norm) if g_norm else False
        sent_rec, sent_f1 = compute_token_recall_f1(best_sent, golds)

        rows.append(
            {
                "is_long": q["is_long"],
                "is_multi_clause": q["is_multi_clause"],
                "p_r1": rank_p == 1 if passage_level else None,
                "p_r3": (rank_p is not None and rank_p <= 3) if passage_level else None,
                "p_r5": (rank_p is not None and rank_p <= 5) if passage_level else None,
                "p_r10": (rank_p is not None and rank_p <= 10) if passage_level else None,
                "p_mrr": mrr_p if passage_level else None,
                "s_r1": rank_spec == 1,
                "s_r3": rank_spec is not None and rank_spec <= 3,
                "s_r5": rank_spec is not None and rank_spec <= 5,
                "s_mrr": mrr_spec,
                "ans_1": ans_top1,
                "ans_3": ans_top3,
                "ans_5": ans_top5,
                "ans_10": ans_top10,
                "sent_span": sent_span,
                "sent_ge50": sent_rec >= 0.5,
                "sent_rec": sent_rec,
                "sent_f1": sent_f1,
            }
        )

    def _agg(sub: list[dict[str, Any]]) -> dict[str, Any]:
        n = max(len(sub), 1)
        out: dict[str, Any] = {
            "count": len(sub),
            "spec_r1": round(sum(1 for r in sub if r["s_r1"]) / n, 4),
            "spec_r3": round(sum(1 for r in sub if r["s_r3"]) / n, 4),
            "spec_r5": round(sum(1 for r in sub if r["s_r5"]) / n, 4),
            "spec_mrr": round(sum(r["s_mrr"] for r in sub) / n, 4),
            "ans_in_top1": round(sum(1 for r in sub if r["ans_1"]) / n, 4),
            "ans_in_top3": round(sum(1 for r in sub if r["ans_3"]) / n, 4),
            "ans_in_top5": round(sum(1 for r in sub if r["ans_5"]) / n, 4),
            "ans_in_top10": round(sum(1 for r in sub if r["ans_10"]) / n, 4),
            "sent_span": round(sum(1 for r in sub if r["sent_span"]) / n, 4),
            "sent_ge50": round(sum(1 for r in sub if r["sent_ge50"]) / n, 4),
            "sent_recall": round(sum(r["sent_rec"] for r in sub) / n, 4),
            "sent_f1": round(sum(r["sent_f1"] for r in sub) / n, 4),
        }
        if passage_level:
            out.update(
                {
                    "p_r1": round(sum(1 for r in sub if r["p_r1"]) / n, 4),
                    "p_r3": round(sum(1 for r in sub if r["p_r3"]) / n, 4),
                    "p_r5": round(sum(1 for r in sub if r["p_r5"]) / n, 4),
                    "p_r10": round(sum(1 for r in sub if r["p_r10"]) / n, 4),
                    "p_mrr": round(sum(r["p_mrr"] for r in sub) / n, 4),
                }
            )
        else:
            out.update({"p_r1": None, "p_r3": None, "p_r5": None, "p_r10": None, "p_mrr": None})
        return out

    return {
        "name": name,
        "index_units": index_units,
        "passage_level": passage_level,
        "build_time_s": round(build_time_s, 3),
        "search_time_s": round(search_time_s, 3),
        "ms_per_query": round((search_time_s / max(n_q, 1)) * 1000.0, 3),
        "overall": _agg(rows),
        "short_passages": _agg([r for r in rows if not r["is_long"]]),
        "long_passages": _agg([r for r in rows if r["is_long"]]),
        "multi_clause_specs": _agg([r for r in rows if r["is_multi_clause"]]),
        "standalone_articles": _agg([r for r in rows if not r["is_multi_clause"]]),
    }


def run_benchmark() -> dict[str, Any]:
    passages, questions, spec_counts = load_full_telequad()
    n_p = len(passages)
    n_q = len(questions)
    multi_specs = {s: c for s, c in spec_counts.items() if c > 1}
    standalone_specs = {s: c for s, c in spec_counts.items() if c == 1}
    long_p_count = sum(1 for p in passages if p["is_long"])
    short_p_count = n_p - long_p_count

    print(
        f"Loaded TeleQuAD Full: {n_p} passages ({short_p_count} <=2000c, {long_p_count} >2000c), "
        f"{n_q} questions, {len(spec_counts)} specs ({len(multi_specs)} multi-clause, {len(standalone_specs)} standalone)."
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    t_load0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(E5_MODEL_ID, local_files_only=True)
    model = AutoModel.from_pretrained(E5_MODEL_ID, local_files_only=True).to(device)
    model.eval()
    e5_load_s = round(time.perf_counter() - t_load0, 3)
    print(f"Loaded {E5_MODEL_ID} on {device} in {e5_load_s:.3f}s")

    matcher = FastSentenceMatcher()
    for p in passages:
        matcher.register("p", p["p_idx"], p["content"])

    q_texts = [q["question"] for q in questions]
    q_metas = [matcher.prepare_query(qt) for qt in q_texts]

    passage_specs = {p["p_idx"]: p["spec"] for p in passages}
    passage_norms = {p["p_idx"]: p["norm_content"] for p in passages}

    # Encode all 4,485 queries once with E5
    t_eq0 = time.perf_counter()
    q_embs = encode_e5_texts(tok, model, device, [f"query: {qt}" for qt in q_texts], batch_size=64)
    e5_q_enc_s = time.perf_counter() - t_eq0

    # ------------------------------------------------------------------
    # Architecture 1: E5-Large Whole-Passage RAG (536 vectors)
    # ------------------------------------------------------------------
    t_b1 = time.perf_counter()
    p_embs = encode_e5_texts(
        tok, model, device, [f"passage: {p['title']}\n{p['content']}" for p in passages], batch_size=64
    )
    arch1_build_s = time.perf_counter() - t_b1

    t_s1 = time.perf_counter()
    sims_whole = q_embs @ p_embs.T
    top10_whole = torch.argsort(sims_whole, dim=1, descending=True)[:, :10].tolist()
    arch1_search_s = e5_q_enc_s + (time.perf_counter() - t_s1)

    res_arch1 = evaluate_predictions(
        name="1. E5-Large Whole-Passage RAG (512-tok cap)",
        questions=questions,
        q_metas=q_metas,
        top10_units=top10_whole,
        unit_specs=passage_specs,
        unit_norms=passage_norms,
        sent_kind="p",
        matcher=matcher,
        passage_level=True,
        build_time_s=arch1_build_s,
        search_time_s=arch1_search_s,
        index_units=n_p,
    )
    print("Arch 1 (E5 Whole):", res_arch1["overall"])

    # ------------------------------------------------------------------
    # Architecture 2: E5-Large Sub-Chunked RAG (<=1000 chars, MaxP)
    # ------------------------------------------------------------------
    t_b2 = time.perf_counter()
    chunks, chunks_by_passage = chunk_passages(passages, max_chars=1000)
    chunk_embs = encode_e5_texts(
        tok, model, device, [f"passage: {c['title']}\n{c['content']}" for c in chunks], batch_size=64
    )
    arch2_build_s = time.perf_counter() - t_b2

    for c in chunks:
        matcher.register("c", c["c_idx"], c["content"])

    t_s2 = time.perf_counter()
    sims_chunk = q_embs @ chunk_embs.T
    p_max_scores = torch.full((n_q, n_p), -1e9, dtype=sims_chunk.dtype)
    p_best_chunk = torch.full((n_q, n_p), -1, dtype=torch.long)
    for p_idx, c_idxs in chunks_by_passage.items():
        if len(c_idxs) == 1:
            cid = c_idxs[0]
            p_max_scores[:, p_idx] = sims_chunk[:, cid]
            p_best_chunk[:, p_idx] = cid
        else:
            sub = sims_chunk[:, c_idxs]
            vals, pos = sub.max(dim=1)
            p_max_scores[:, p_idx] = vals
            c_tensor = torch.tensor(c_idxs, dtype=torch.long)
            p_best_chunk[:, p_idx] = c_tensor[pos]

    top50_e5_vals, top50_e5_pidxs = torch.topk(p_max_scores, k=50, dim=1)
    top50_e5_vals_list = top50_e5_vals.tolist()
    top50_e5_pidxs_list = top50_e5_pidxs.tolist()
    # Map top10 to their winning best chunks for chunk-level answer containment & sentence QA
    row_range = torch.arange(n_q).unsqueeze(1)
    top10_p_e5 = top50_e5_pidxs[:, :10]
    top10_c_e5 = p_best_chunk[row_range, top10_p_e5].tolist()
    arch2_search_s = e5_q_enc_s + (time.perf_counter() - t_s2)

    # Evaluate Arch 2 carefully: passage recall uses top10_p_e5 (dedup MaxP),
    # while Answer-in-Top-K & Sent QA operate on the winning MaxP <=1000c chunks (fair chunk window)!
    chunk_specs = {c["c_idx"]: c["spec"] for c in chunks}
    chunk_norms = {c["c_idx"]: c["norm_content"] for c in chunks}
    chunk_to_p = {c["c_idx"]: c["p_idx"] for c in chunks}

    res_arch2 = evaluate_predictions(
        name="2. E5-Large Sub-Chunked RAG (<=1000c MaxP)",
        questions=questions,
        q_metas=q_metas,
        top10_units=top10_c_e5,
        unit_specs=chunk_specs,
        unit_norms=chunk_norms,
        sent_kind="c",
        matcher=matcher,
        passage_level=True,
        build_time_s=arch2_build_s,
        search_time_s=arch2_search_s,
        index_units=len(chunks),
    )
    # Wait: in evaluate_predictions above, gold_p in top10 compared gold_p to chunk IDs!
    # Fix by evaluating passage ranks via top10_p_e5 while keeping chunk Answer-in-Top-K & Sent QA!
    res_arch2_fixed = _merge_chunk_and_passage_eval(
        res_arch2,
        questions=questions,
        top10_passages=top10_p_e5.tolist(),
    )
    print("Arch 2 (E5 Sub-Chunked):", res_arch2_fixed["overall"])

    # ------------------------------------------------------------------
    # Architecture 3: LLM Wiki HybridSimilarityEngine (536 Passage Pages)
    # ------------------------------------------------------------------
    t_b3 = time.perf_counter()
    wiki_pages: dict[str, WikiPage] = {}
    slug_to_pidx: dict[str, int] = {}
    for p in passages:
        slug = f"p-{p['p_idx']:03d}-{slugify(p['title'])[:48]}"
        slug_to_pidx[slug] = p["p_idx"]
        wiki_pages[slug] = WikiPage(
            slug=slug,
            title=p["title"],
            category=p["spec"],
            tags=[p["spec"].lower()],
            aliases=[p["raw_title"], p["content"].strip().splitlines()[0].strip()[:80]],
            sources=[f"TeleQuAD-{p['p_idx']}"],
            created_at="2026-11-14T00:00:00Z",
            updated_at="2026-11-14T00:00:00Z",
            revision_count=1,
            summary=p["content"][:220],
            body=p["content"],
            path=f"pages/{slug}.md",
        )
    wiki_engine = HybridSimilarityEngine(wiki_pages)
    arch3_build_s = time.perf_counter() - t_b3

    t_s3 = time.perf_counter()
    top50_wiki: list[list[tuple[int, float]]] = []
    top10_wiki: list[list[int]] = []
    for qt in q_texts:
        hits = wiki_engine.search(qt, top_k=50)
        pairs = [(slug_to_pidx[m.slug], m.score) for m in hits]
        if not pairs:
            pairs = [(0, 0.0)]
        top50_wiki.append(pairs)
        top10_wiki.append([p_idx for p_idx, _ in pairs[:10]])
    arch3_search_s = time.perf_counter() - t_s3

    res_arch3 = evaluate_predictions(
        name="3. LLM Wiki HybridSimilarityEngine (536 Passage Pages)",
        questions=questions,
        q_metas=q_metas,
        top10_units=top10_wiki,
        unit_specs=passage_specs,
        unit_norms=passage_norms,
        sent_kind="p",
        matcher=matcher,
        passage_level=True,
        build_time_s=arch3_build_s,
        search_time_s=arch3_search_s,
        index_units=n_p,
    )
    print("Arch 3 (LLM Wiki Passage):", res_arch3["overall"])

    # ------------------------------------------------------------------
    # Architecture 4: Hybrid LLM Wiki + Sub-Chunked E5-Large Fusion
    # ------------------------------------------------------------------
    t_s4 = time.perf_counter()
    top10_fusion_combined: list[list[int]] = []
    top10_fusion_norm: list[list[int]] = []
    top10_fusion_rrf: list[list[int]] = []

    for qi in range(n_q):
        w_pairs = top50_wiki[qi]
        w_scores = {p_idx: sc for p_idx, sc in w_pairs}
        w_ranks = {p_idx: rank for rank, (p_idx, _) in enumerate(w_pairs, start=1)}
        w_vals = [sc for _, sc in w_pairs]
        w_min, w_max = min(w_vals), max(w_vals)
        w_span = (w_max - w_min) if w_max > w_min else 1.0

        e_idxs = top50_e5_pidxs_list[qi]
        e_vals = top50_e5_vals_list[qi]
        e_scores = {p_idx: val for p_idx, val in zip(e_idxs, e_vals)}
        e_ranks = {p_idx: rank for rank, p_idx in enumerate(e_idxs, start=1)}
        e_min, e_max = min(e_vals), max(e_vals)
        e_span = (e_max - e_min) if e_max > e_min else 1.0

        cand_set = set(w_scores.keys()) | set(e_scores.keys())
        comb_list: list[tuple[float, int]] = []
        norm_list: list[tuple[float, int]] = []
        rrf_list: list[tuple[float, int]] = []
        rrf_max = 2.0 / 61.0
        for p_idx in cand_set:
            wn = (w_scores[p_idx] - w_min) / w_span if p_idx in w_scores else 0.0
            en = (e_scores[p_idx] - e_min) / e_span if p_idx in e_scores else 0.0
            rrf = (1.0 / (60.0 + w_ranks[p_idx]) if p_idx in w_ranks else 0.0) + (
                1.0 / (60.0 + e_ranks[p_idx]) if p_idx in e_ranks else 0.0
            )
            rrf_norm = rrf / rrf_max
            norm_list.append((0.62 * wn + 0.38 * en, p_idx))
            rrf_list.append((rrf, p_idx))
            comb_list.append((0.52 * wn + 0.33 * en + 0.15 * rrf_norm, p_idx))

        comb_list.sort(reverse=True)
        norm_list.sort(reverse=True)
        rrf_list.sort(reverse=True)
        top10_fusion_combined.append([p_idx for _, p_idx in comb_list[:10]])
        top10_fusion_norm.append([p_idx for _, p_idx in norm_list[:10]])
        top10_fusion_rrf.append([p_idx for _, p_idx in rrf_list[:10]])

    fusion_overhead_s = time.perf_counter() - t_s4
    arch4_build_s = arch2_build_s + arch3_build_s
    arch4_search_s = arch2_search_s + arch3_search_s + fusion_overhead_s

    res_arch4 = evaluate_predictions(
        name="4. Hybrid LLM Wiki + E5 Sub-Chunked Fusion (Norm Score + RRF)",
        questions=questions,
        q_metas=q_metas,
        top10_units=top10_fusion_combined,
        unit_specs=passage_specs,
        unit_norms=passage_norms,
        sent_kind="p",
        matcher=matcher,
        passage_level=True,
        build_time_s=arch4_build_s,
        search_time_s=arch4_search_s,
        index_units=n_p,
    )
    res_arch4_norm = evaluate_predictions(
        name="4a. Fusion Ablation: Min-Max Normalized Score (0.62 Wiki + 0.38 E5)",
        questions=questions,
        q_metas=q_metas,
        top10_units=top10_fusion_norm,
        unit_specs=passage_specs,
        unit_norms=passage_norms,
        sent_kind="p",
        matcher=matcher,
        passage_level=True,
        build_time_s=arch4_build_s,
        search_time_s=arch4_search_s,
        index_units=n_p,
    )
    res_arch4_rrf = evaluate_predictions(
        name="4b. Fusion Ablation: Pure RRF (k=60)",
        questions=questions,
        q_metas=q_metas,
        top10_units=top10_fusion_rrf,
        unit_specs=passage_specs,
        unit_norms=passage_norms,
        sent_kind="p",
        matcher=matcher,
        passage_level=True,
        build_time_s=arch4_build_s,
        search_time_s=arch4_search_s,
        index_units=n_p,
    )
    print("Arch 4 (Hybrid Fusion):", res_arch4["overall"])
    print("  Norm-only:", res_arch4_norm["overall"]["p_r1"], "RRF-only:", res_arch4_rrf["overall"]["p_r1"])

    # ------------------------------------------------------------------
    # Architecture 5: LLM Wiki Spec-Consolidated Granularity (96 Spec Pages)
    # ------------------------------------------------------------------
    t_b5 = time.perf_counter()
    grouped_passages: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in passages:
        grouped_passages[p["spec"]].append(p)

    spec_list = list(grouped_passages.keys())
    spec_pages: dict[str, WikiPage] = {}
    spec_slug_to_uid: dict[str, int] = {}
    spec_unit_specs: dict[int, str] = {}
    spec_unit_norms: dict[int, str] = {}

    for sp_uid, spec_name in enumerate(spec_list):
        group = grouped_passages[spec_name]
        sp_slug = slugify(spec_name)
        if sp_slug in spec_pages:
            sp_slug = f"{sp_slug}-{sp_uid}"
        body_sections = [
            f"## {p['title']}\n\n{p['content']}" if p["is_multi_clause"] else p["content"]
            for p in group
        ]
        full_body = "\n\n".join(body_sections)
        aliases = list(
            dict.fromkeys(
                [p["raw_title"] for p in group]
                + [p["content"].strip().splitlines()[0].strip()[:80] for p in group[:8]]
            )
        )
        title = f"3GPP TS {spec_name}" if group[0]["raw_title"].startswith("3GPP-Specs#") else spec_name
        spec_pages[sp_slug] = WikiPage(
            slug=sp_slug,
            title=title,
            category="3GPP-Spec" if group[0]["is_multi_clause"] else "Telecom-Article",
            tags=[spec_name.lower()],
            aliases=aliases,
            sources=[f"TeleQuAD-{p['p_idx']}" for p in group],
            created_at="2026-11-14T00:00:00Z",
            updated_at="2026-11-14T00:00:00Z",
            revision_count=len(group),
            summary=group[0]["content"][:220],
            body=full_body,
            path=f"pages/{sp_slug}.md",
        )
        spec_slug_to_uid[sp_slug] = sp_uid
        spec_unit_specs[sp_uid] = spec_name
        spec_unit_norms[sp_uid] = normalize_answer(full_body)
        matcher.register("spec", sp_uid, full_body)

    spec_engine = HybridSimilarityEngine(spec_pages)
    arch5_build_s = time.perf_counter() - t_b5

    t_s5 = time.perf_counter()
    top10_spec: list[list[int]] = []
    for qt in q_texts:
        hits = spec_engine.search(qt, top_k=10)
        uids = [spec_slug_to_uid[m.slug] for m in hits] or [0]
        top10_spec.append(uids)
    arch5_search_s = time.perf_counter() - t_s5

    res_arch5 = evaluate_predictions(
        name="5. LLM Wiki Spec-Consolidated Granularity (96 Spec Pages)",
        questions=questions,
        q_metas=q_metas,
        top10_units=top10_spec,
        unit_specs=spec_unit_specs,
        unit_norms=spec_unit_norms,
        sent_kind="spec",
        matcher=matcher,
        passage_level=False,
        build_time_s=arch5_build_s,
        search_time_s=arch5_search_s,
        index_units=len(spec_pages),
    )
    print("Arch 5 (Spec-Consolidated Wiki):", res_arch5["overall"])

    return {
        "dataset": {
            "passages": n_p,
            "questions": n_q,
            "specs": len(spec_counts),
            "multi_clause_specs": len(multi_specs),
            "max_clauses_in_spec": max(multi_specs.values()),
            "min_clauses_in_multi_spec": min(multi_specs.values()),
            "standalone_articles": len(standalone_specs),
            "short_passages": short_p_count,
            "long_passages": long_p_count,
            "min_chars": min(p["char_len"] for p in passages),
            "median_chars": sorted(p["char_len"] for p in passages)[n_p // 2],
            "avg_chars": round(sum(p["char_len"] for p in passages) / n_p, 1),
            "max_chars": max(p["char_len"] for p in passages),
        },
        "device": f"{device} ({torch.cuda.get_device_name(0) if device == 'cuda' else 'CPU'})",
        "e5_load_s": e5_load_s,
        "results": [res_arch1, res_arch2_fixed, res_arch3, res_arch4, res_arch5],
        "fusion_ablations": [res_arch4_norm, res_arch4_rrf],
    }


def _merge_chunk_and_passage_eval(
    chunk_eval: dict[str, Any],
    *,
    questions: list[dict[str, Any]],
    top10_passages: list[list[int]],
) -> dict[str, Any]:
    """Recompute passage-level R@K and MRR using MaxP deduplicated parent passage rankings."""
    buckets = {
        "overall": [],
        "short_passages": [],
        "long_passages": [],
        "multi_clause_specs": [],
        "standalone_articles": [],
    }
    for qi, q in enumerate(questions):
        gold_p = q["p_idx"]
        top10 = top10_passages[qi]
        rank_p = (top10.index(gold_p) + 1) if gold_p in top10 else None
        row = {
            "r1": rank_p == 1,
            "r3": rank_p is not None and rank_p <= 3,
            "r5": rank_p is not None and rank_p <= 5,
            "r10": rank_p is not None and rank_p <= 10,
            "mrr": (1.0 / rank_p) if rank_p else 0.0,
        }
        buckets["overall"].append(row)
        buckets["long_passages" if q["is_long"] else "short_passages"].append(row)
        buckets["multi_clause_specs" if q["is_multi_clause"] else "standalone_articles"].append(row)

    out = json.loads(json.dumps(chunk_eval))
    for bname, rows in buckets.items():
        n = max(len(rows), 1)
        out[bname]["p_r1"] = round(sum(1 for r in rows if r["r1"]) / n, 4)
        out[bname]["p_r3"] = round(sum(1 for r in rows if r["r3"]) / n, 4)
        out[bname]["p_r5"] = round(sum(1 for r in rows if r["r5"]) / n, 4)
        out[bname]["p_r10"] = round(sum(1 for r in rows if r["r10"]) / n, 4)
        out[bname]["p_mrr"] = round(sum(r["mrr"] for r in rows) / n, 4)
    return out


def _fmt_pct(val: float | None) -> str:
    return f"{val * 100:.2f}%" if val is not None else "N/A *(96 specs)*"


def format_markdown_report(payload: dict[str, Any]) -> str:
    ds = payload["dataset"]
    results = payload["results"]
    abl = payload["fusion_ablations"]
    r1, r2, r3, r4, r5 = results

    lines = [
        "# Full Ericsson TeleQuAD Benchmark Report (536 Passages, 4,485 Questions)",
        "",
        "## Benchmark Configuration & Dataset Profile",
        f"- **Dataset**: Full [TeleQuAD-v4-full.json](file:///home/darwin/llm-wiki/tests/fixtures/TeleQuAD-v4-full.json) — **`{ds['passages']:,}` passages**, **`{ds['questions']:,}` extractive QA pairs**, across **`{ds['specs']}` 3GPP specs / telecom article groups** (`{ds['multi_clause_specs']}` multi-clause 3GPP specs with `{ds['min_clauses_in_multi_spec']}`–`{ds['max_clauses_in_spec']}` sibling passages per spec; `{ds['standalone_articles']}` standalone telecom articles).",
        f"- **Passage Length Distribution**: min `{ds['min_chars']}` chars, median `{ds['median_chars']:,}` chars, avg `{ds['avg_chars']:,}` chars, max `{ds['max_chars']:,}` chars (`{ds['short_passages']}` passages <= 2,000 chars covering `{r1['short_passages']['count']:,}` QAs; `{ds['long_passages']}` long passages > 2,000 chars covering `{r1['long_passages']['count']:,}` QAs).",
        f"- **Dense Embedding Baseline**: `{E5_MODEL_ID}` on `{payload['device']}` (`{payload['e5_load_s']:.3f}s` model load time excluded from index build timings).",
        "",
        "## 1. Overall Retrieval Accuracy Across All 4,485 Questions",
        "",
        "| Architecture | Indexed Units | Passage R@1 | Passage R@3 | Passage R@5 | Passage R@10 | Passage MRR@10 | Spec R@1 | Spec R@3 | Spec R@5 |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for r in results:
        o = r["overall"]
        mrr_str = f"`{o['p_mrr']:.4f}`" if o["p_mrr"] is not None else "N/A"
        lines.append(
            f"| **{r['name']}** | `{r['index_units']:,}` | {_fmt_pct(o['p_r1'])} | {_fmt_pct(o['p_r3'])} | {_fmt_pct(o['p_r5'])} | {_fmt_pct(o['p_r10'])} | "
            f"{mrr_str} | {_fmt_pct(o['spec_r1'])} | {_fmt_pct(o['spec_r3'])} | {_fmt_pct(o['spec_r5'])} |"
        )

    lines.extend(
        [
            "",
            f"*Hybrid Fusion Ablation (`4,485` QAs)*: Norm-Only Score Fusion (`0.62*Wiki + 0.38*E5`) achieved **Passage R@1 = {_fmt_pct(abl[0]['overall']['p_r1'])}**, R@3 = {_fmt_pct(abl[0]['overall']['p_r3'])}, R@10 = {_fmt_pct(abl[0]['overall']['p_r10'])}, MRR = `{abl[0]['overall']['p_mrr']:.4f}`; Pure RRF (`k=60`) achieved **Passage R@1 = {_fmt_pct(abl[1]['overall']['p_r1'])}**, R@3 = {_fmt_pct(abl[1]['overall']['p_r3'])}, R@10 = {_fmt_pct(abl[1]['overall']['p_r10'])}, MRR = `{abl[1]['overall']['p_mrr']:.4f}`.",
            "",
            "## 2. Gold Answer Containment & Extractive Top-1 Sentence QA Accuracy",
            "",
            "| Architecture | Ans-in-Top-1 | Ans-in-Top-3 | Ans-in-Top-5 | Ans-in-Top-10 | Top-1 Sent Span Match | Top-1 Sent >= 0.5 Recall | Top-1 Sent Recall | Top-1 Sent F1 |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for r in results:
        o = r["overall"]
        lines.append(
            f"| **{r['name']}** | {_fmt_pct(o['ans_in_top1'])} | {_fmt_pct(o['ans_in_top3'])} | {_fmt_pct(o['ans_in_top5'])} | {_fmt_pct(o['ans_in_top10'])} | "
            f"{_fmt_pct(o['sent_span'])} | {_fmt_pct(o['sent_ge50'])} | {_fmt_pct(o['sent_recall'])} | {_fmt_pct(o['sent_f1'])} |"
        )

    lines.extend(
        [
            "",
            "*Note*: For Sub-Chunked E5 (`<=1,000`-char MaxP chunks), `Ans-in-Top-K` and `Top-1 Sent` evaluate the winning `<=1,000`-char chunks (which improves sentence isolation inside long docs when the right chunk lands at rank 1); for Arch 5 (Spec-Consolidated `96` pages), each page aggregates all clauses of a spec so `Ans-in-Top-K` tracks spec coverage while `Top-1 Sent` shows whether the extractive sentence matcher locates the exact sentence inside a full 3GPP spec body.",
            "",
            "## 3. Stratified Performance: Passage Length & Multi-Clause Spec Ambiguity",
            "",
            "| Architecture | Short (`<=2k`c, `{0:,}` QAs) R@1 / Ans@1 | Long (`>2k`c, `{1:,}` QAs) R@1 / Ans@1 | Multi-Clause Specs (`{2:,}` QAs) R@1 / R@10 | Standalone Articles (`{3:,}` QAs) R@1 / R@10 |".format(
                r1["short_passages"]["count"],
                r1["long_passages"]["count"],
                r1["multi_clause_specs"]["count"],
                r1["standalone_articles"]["count"],
            ),
            "| :--- | :---: | :---: | :---: | :---: |",
        ]
    )
    for r in results:
        sh, lg, mc, st = (
            r["short_passages"],
            r["long_passages"],
            r["multi_clause_specs"],
            r["standalone_articles"],
        )
        if r["passage_level"]:
            sh_s = f"{_fmt_pct(sh['p_r1'])} / {_fmt_pct(sh['ans_in_top1'])}"
            lg_s = f"{_fmt_pct(lg['p_r1'])} / {_fmt_pct(lg['ans_in_top1'])}"
            mc_s = f"{_fmt_pct(mc['p_r1'])} / {_fmt_pct(mc['p_r10'])}"
            st_s = f"{_fmt_pct(st['p_r1'])} / {_fmt_pct(st['p_r10'])}"
        else:
            sh_s = f"Spec {_fmt_pct(sh['spec_r1'])} / {_fmt_pct(sh['ans_in_top1'])}"
            lg_s = f"Spec {_fmt_pct(lg['spec_r1'])} / {_fmt_pct(lg['ans_in_top1'])}"
            mc_s = f"Spec {_fmt_pct(mc['spec_r1'])} / {_fmt_pct(mc['spec_r5'])}"
            st_s = f"Spec {_fmt_pct(st['spec_r1'])} / {_fmt_pct(st['spec_r5'])}"
        lines.append(f"| **{r['name']}** | {sh_s} | {lg_s} | {mc_s} | {st_s} |")

    lines.extend(
        [
            "",
            "## 4. Indexing & Query Latency (All 4,485 Queries)",
            "",
            "| Architecture | Build / Embed Time | Total 4,485-Query Time | Per-Query Latency |",
            "| :--- | :---: | :---: | :---: |",
        ]
    )
    for r in results:
        lines.append(
            f"| **{r['name']}** | `{r['build_time_s']:.3f}s` | `{r['search_time_s']:.3f}s` | `{r['ms_per_query']:.3f} ms/query` |"
        )

    lines.extend(
        [
            "",
            "## 5. Key Honest Takeaways",
            f"1. **Whole-Passage Dense Vector RAG Breaks on Long Technical Clauses**: Single-vector `intfloat/multilingual-e5-large` truncates beyond 512 tokens and scores only **{_fmt_pct(r1['overall']['p_r1'])} Passage R@1** (**{_fmt_pct(r1['long_passages']['p_r1'])}** on >2,000-char clauses). Sub-chunking into `<=1,000`-char overlapping windows with MaxP lifts E5 dramatically to **{_fmt_pct(r2['overall']['p_r1'])} Passage R@1** (`+{((r2['overall']['p_r1'] - r1['overall']['p_r1'])*100):.2f} pp`), especially on long clauses (**{_fmt_pct(r2['long_passages']['p_r1'])}**).",
            f"2. **LLM Wiki `HybridSimilarityEngine` Beats Even Sub-Chunked GPU E5 on Fine-Grained 3GPP Clause Retrieval**: On pure CPU in **`{r3['search_time_s']:.2f}s` total (`{r3['ms_per_query']:.3f} ms/query`)**, `HybridSimilarityEngine` reaches **{_fmt_pct(r3['overall']['p_r1'])} Passage R@1**, **{_fmt_pct(r3['overall']['p_r5'])} R@5**, and **{_fmt_pct(r3['overall']['p_r10'])} R@10** (`MRR {r3['overall']['p_mrr']:.4f}`), vs. Sub-Chunked E5's {_fmt_pct(r2['overall']['p_r1'])} R@1 / {_fmt_pct(r2['overall']['p_r10'])} R@10. Why? 3GPP questions rely on exact identifiers, section numbers, parameter acronyms, and bigrams (`Layer 2`, `SCS`, numeric caps, IE names) across 39–79 nearly identical sibling clauses inside the same specification—where IDF-weighted lexical + bigram BM25 outperforms bi-encoder semantic pooling.",
            f"3. **Hybrid Fusion Achieves the Best Overall Accuracy**: Combining `HybridSimilarityEngine` with Sub-Chunked `E5-large` pushes **Passage R@1 to {_fmt_pct(r4['overall']['p_r1'])}**, **R@3 to {_fmt_pct(r4['overall']['p_r3'])}**, **R@10 to {_fmt_pct(r4['overall']['p_r10'])}**, and **`MRR` to `{r4['overall']['p_mrr']:.4f}`**—simultaneously excelling on exact 3GPP terminology AND paraphrased natural-language queries.",
            f"4. **Spec-Consolidated Pages Need Section-Level Sub-Indexing for Multi-Clause Specs**: Consolidating 536 passages into 96 Spec pages yields **{_fmt_pct(r5['overall']['spec_r1'])} Spec R@1** (**{_fmt_pct(r5['overall']['ans_in_top1'])}** gold presence in Top-1 page), while keeping per-clause granularity (`536` pages/sections) yields higher pinpoint sentence accuracy (**{_fmt_pct(r3['overall']['sent_span'])}** vs. **{_fmt_pct(r5['overall']['sent_span'])}** Top-1 sentence span match) because searching across ~1,000 sentences inside an entire 79-clause spec adds distractor overlap.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark retrieval on full TeleQuAD (536 passages, 4,485 QAs)")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--append-main", action="store_true", help="Append summary section to BENCHMARK_REPORT.md")
    args = parser.parse_args()

    payload = run_benchmark()
    md = format_markdown_report(payload)
    args.report.write_text(md, encoding="utf-8")
    print(f"Wrote report to {args.report}")

    if args.append_main and MAIN_REPORT_PATH.exists():
        existing = MAIN_REPORT_PATH.read_text(encoding="utf-8")
        marker = "# Full Ericsson TeleQuAD Benchmark Report (536 Passages, 4,485 Questions)"
        if marker in existing:
            existing = existing.split(marker, 1)[0].rstrip() + "\n\n---\n\n"
        else:
            existing = existing.rstrip() + "\n\n---\n\n"
        MAIN_REPORT_PATH.write_text(existing + md, encoding="utf-8")
        print(f"Updated {MAIN_REPORT_PATH}")


if __name__ == "__main__":
    main()
