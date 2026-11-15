from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from backend.vault_manager import WikiPage, slugify

STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
        "in", "is", "it", "its", "of", "on", "or", "that", "the", "to", "was", "were",
        "will", "with", "this", "these", "those", "into", "over", "about", "using",
        "via", "how", "what", "when", "where", "which", "who", "why", "can", "also",
        "their", "they", "them", "there", "some", "more", "many", "most", "other",
        "such", "only", "often", "been", "have", "had", "would", "could", "should",
        "than", "then", "because", "between", "through", "during", "before", "after",
        "under", "while", "known", "like", "used", "use", "make", "made",
        "may", "including", "include", "called", "does", "do", "did",
    }
)

JA_STOPWORDS = frozenset(
    {
        "の", "に", "は", "を", "た", "が", "で", "て", "と", "し", "れ", "さ",
        "ある", "いる", "も", "する", "から", "な", "こと", "として", "い", "や",
        "れる", "など", "なっ", "ない", "この", "ため", "その", "あっ", "よう",
        "また", "もの", "という", "あり", "まで", "られ", "なる", "へ", "か", "だ",
        "これ", "によって", "により", "おり", "より", "による", "ず", "なり",
        "られる", "において", "ば", "なかっ", "なく", "しかし", "について", "せ",
        "だっ", "その後", "できる", "それ", "う", "ので", "なお", "のみ", "でき",
        "き", "つ", "における", "および", "いう", "さらに", "でも", "ら", "たり",
        "その他", "に関する", "たち", "ます", "ん", "なら", "に対して", "特に",
        "せる", "及び", "これら", "とき", "では", "にて", "ほか", "ながら", "うち",
        "そして", "とともに", "ただし", "かつて", "それぞれ", "または", "お",
        "ほど", "ものの", "に対する", "ほとんど", "と共に", "といった", "です",
        "とも", "ところ", "ここ", "どこ", "だれ", "なに", "なん", "いつ", "どう",
        "どの", "なぜ", "いくつ", "いくら", "どのよう", "どんな", "ました",
        "ません", "ている", "ていた", "ており", "れた", "された", "される",
        "した", "して", "され", "あり", "おり", "事", "物", "時", "為", "等",
    }
)

_RE_HAS_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]")
_RE_MULTILINGUAL_RUN = re.compile(
    r"[a-z0-9]+|[\u30a0-\u30ffー]+|[\u4e00-\u9fff\u3400-\u4dbf々〆ヵヶ]+|[\u3040-\u309f]+"
)
_JA_PARTICLES_SUFFIX = ("について", "において", "における", "によって", "により", "による", "に対して", "に対する", "として", "から", "まで", "より", "など", "とは", "では", "には", "への", "での", "は", "が", "を", "に", "へ", "と", "で", "の", "も", "か", "や")


def has_cjk(text: str) -> bool:
    return bool(_RE_HAS_CJK.search(text))


def tokenize(text: str) -> list[str]:
    """Extract lowercase alphanumeric and Japanese/CJK tokens excluding common stopwords."""
    if not _RE_HAS_CJK.search(text):
        raw = re.findall(r"[a-z0-9]+", text.lower())
        return [tok for tok in raw if (len(tok) > 1 or tok.isdigit()) and tok not in STOPWORDS]

    norm = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    for match in _RE_MULTILINGUAL_RUN.finditer(norm):
        run = match.group(0)
        ch0 = run[0]
        if "a" <= ch0 <= "z" or "0" <= ch0 <= "9":
            if (len(run) > 1 or run.isdigit()) and run not in STOPWORDS:
                tokens.append(run)
        elif "\u30a0" <= ch0 <= "\u30ff" or ch0 == "ー":
            clean_k = run.strip("ー") if len(run) > 1 else run
            if clean_k and clean_k != "ー":
                tokens.append(clean_k)
                if len(clean_k) >= 4:
                    for i in range(len(clean_k) - 1):
                        tokens.append(clean_k[i : i + 2])
                    for i in range(len(clean_k) - 2):
                        tokens.append(clean_k[i : i + 3])
        elif "\u3040" <= ch0 <= "\u309f":
            if run in JA_STOPWORDS or len(run) < 2:
                continue
            stem = run
            for suf in _JA_PARTICLES_SUFFIX:
                if len(stem) > len(suf) + 1 and stem.endswith(suf):
                    stem = stem[: -len(suf)]
                    break
            if len(stem) >= 2 and stem not in JA_STOPWORDS:
                tokens.append(stem)
        else:
            # Kanji / CJK unified ideographs
            if run not in JA_STOPWORDS:
                tokens.append(run)
            if len(run) >= 3:
                for i in range(len(run) - 1):
                    bi = run[i : i + 2]
                    if bi not in JA_STOPWORDS:
                        tokens.append(bi)
    return tokens


def word_ngrams(tokens: list[str], n: int = 2) -> list[str]:
    if len(tokens) < n:
        return []
    return [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - n + 1)]


@dataclass
class SimilarityMatch:
    slug: str
    title: str
    category: str
    summary: str
    score: float
    title_score: float
    bm25_score: float
    tfidf_score: float
    graph_score: float
    matched_terms: list[str]
    tags: list[str]
    revision_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "category": self.category,
            "summary": self.summary,
            "score": round(self.score, 4),
            "breakdown": {
                "title_alias": round(self.title_score, 4),
                "bm25": round(self.bm25_score, 4),
                "tfidf_cosine": round(self.tfidf_score, 4),
                "graph_tags": round(self.graph_score, 4),
            },
            "matched_terms": self.matched_terms[:12],
            "tags": self.tags,
            "revision_count": self.revision_count,
        }


class HybridSimilarityEngine:
    """
    Hybrid Local Similarity & Deduplication Engine combining:
      1. Title / Slug / Alias Exact & Fuzzy Overlap (0.35)
      2. BM25 Lexical Relevance (0.25)
      3. Unigram + Bigram TF-IDF Cosine Similarity (0.25)
      4. Tag & Wikilink Concept Graph Jaccard Overlap (0.15)
    """

    W_TITLE = 0.35
    W_BM25 = 0.25
    W_TFIDF = 0.25
    W_GRAPH = 0.15

    def __init__(self, pages: dict[str, WikiPage], embedder: Any = None):
        self.pages = pages
        self.embedder = embedder
        self.doc_tokens: dict[str, list[str]] = {}
        self.doc_tf_maps: dict[str, Counter[str]] = {}
        self.doc_tok_sets: dict[str, set[str]] = {}
        self.body_tok_sets: dict[str, set[str]] = {}
        self.doc_bigram_maps: dict[str, Counter[str]] = {}
        self.doc_tf_vecs: dict[str, dict[str, float]] = {}
        self.doc_norms: dict[str, float] = {}
        self.doc_embeddings: dict[str, list[float]] = {}
        self.title_tok_sets: dict[str, set[str]] = {}
        self.title_candidates: dict[str, list[tuple[str, str, set[str]]]] = {}
        self.cand_title_tok_sets: dict[str, set[str]] = {}
        self.idf: dict[str, float] = {}
        self.bi_idf: dict[str, float] = {}
        self.feature_idf: dict[str, float] = {}
        self.uni_postings: dict[str, list[tuple[str, float]]] = {}
        self.bi_postings: dict[str, list[tuple[str, float]]] = {}
        self.tfidf_postings: dict[str, list[tuple[str, float]]] = {}
        self.avg_dl: float = 1.0
        self.avg_bi_dl: float = 1.0
        self._build_index()

    @staticmethod
    def _clean_prose_body(body: str) -> str:
        s = re.sub(r"^- Related trail:.*$", "", body, flags=re.MULTILINE)
        s = re.sub(r"^#{1,6}\s+.*$", "", s, flags=re.MULTILINE)
        s = re.sub(r"^[-*]\s+\*\*\[[^\]]+\]\*\*(?:\s*\([^)]+\))?:\s*", "", s, flags=re.MULTILINE)
        return s

    def _build_index(self) -> None:
        if not self.pages:
            return

        df: Counter[str] = Counter()
        bi_df: Counter[str] = Counter()
        ngram_df: Counter[str] = Counter()
        total_len = 0
        total_bi_len = 0

        raw_features: dict[str, Counter[str]] = {}
        for slug, page in self.pages.items():
            clean_body = re.sub(r"^- Related trail:.*$", "", page.body, flags=re.MULTILINE)
            prose_body = self._clean_prose_body(page.body)
            self.body_tok_sets[slug] = set(tokenize(prose_body))
            weighted_text = (
                f"{page.title} {page.title} "
                f"{' '.join(page.aliases)} "
                f"{' '.join(page.tags)} "
                f"{page.summary} "
                f"{clean_body}"
            )
            toks = tokenize(weighted_text)
            self.doc_tokens[slug] = toks
            tf_map = Counter(toks)
            self.doc_tf_maps[slug] = tf_map
            self.doc_tok_sets[slug] = set(tf_map.keys())
            total_len += len(toks)
            for t in tf_map:
                df[t] += 1

            bis = word_ngrams(toks, 2)
            bi_map = Counter(bis)
            self.doc_bigram_maps[slug] = bi_map
            total_bi_len += len(bis)
            for b in bi_map:
                bi_df[b] += 1

            feat_counts = Counter(toks + bis)
            raw_features[slug] = feat_counts
            for f in feat_counts:
                ngram_df[f] += 1

            self.title_tok_sets[slug] = set(
                tokenize(f"{page.title} {' '.join(page.aliases)}")
            )
            raw_cands = [
                p.strip()
                for p in [page.title, page.slug.replace("-", " "), *page.aliases]
                if p.strip()
            ]
            parsed_cands: list[tuple[str, str, set[str]]] = []
            cand_toks_union: set[str] = set()
            for p in raw_cands:
                p_toks = set(tokenize(p))
                parsed_cands.append((p.lower(), slugify(p), p_toks))
                cand_toks_union.update(p_toks)
            self.title_candidates[slug] = parsed_cands
            self.cand_title_tok_sets[slug] = cand_toks_union

        n_docs = len(self.pages)
        self.avg_dl = max(total_len / n_docs, 1.0)
        self.avg_bi_dl = max(total_bi_len / n_docs, 1.0)

        for term, freq in df.items():
            self.idf[term] = math.log((n_docs - freq + 0.5) / (freq + 0.5) + 1.0)

        for bi, freq in bi_df.items():
            self.bi_idf[bi] = math.log((n_docs - freq + 0.5) / (freq + 0.5) + 1.0)

        self.feature_idf = {
            feat: math.log((n_docs + 1.0) / (freq + 1.0)) + 1.0
            for feat, freq in ngram_df.items()
        }

        uni_postings: dict[str, list[tuple[str, float]]] = defaultdict(list)
        k1 = 1.5
        b = 0.75
        for slug, tf_map in self.doc_tf_maps.items():
            dl = len(self.doc_tokens[slug]) or 1
            norm_dl = k1 * (1.0 - b + b * (dl / self.avg_dl))
            for term, tf in tf_map.items():
                w = self.idf[term] * (tf * (k1 + 1.0)) / (tf + norm_dl)
                uni_postings[term].append((slug, w))
        self.uni_postings = dict(uni_postings)

        bi_postings: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for slug, bi_map in self.doc_bigram_maps.items():
            dl = sum(bi_map.values()) or 1
            norm_dl = 1.2 * (1.0 - 0.5 + 0.5 * (dl / self.avg_bi_dl))
            for bi, tf in bi_map.items():
                w = self.bi_idf[bi] * (tf * 2.2) / (tf + norm_dl)
                bi_postings[bi].append((slug, w))
        self.bi_postings = dict(bi_postings)

        tfidf_postings: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for slug, counts in raw_features.items():
            vec: dict[str, float] = {}
            norm_sq = 0.0
            for feat, cnt in counts.items():
                weight = (1.0 + math.log(cnt)) * self.feature_idf.get(feat, 1.0)
                vec[feat] = weight
                norm_sq += weight * weight
            norm = math.sqrt(norm_sq) if norm_sq > 0 else 1.0
            self.doc_tf_vecs[slug] = vec
            self.doc_norms[slug] = norm
            for feat, weight in vec.items():
                tfidf_postings[feat].append((slug, weight / norm))
        self.tfidf_postings = dict(tfidf_postings)

        if self.embedder is not None and self.pages:
            slugs = list(self.pages.keys())
            texts = [
                f"{self.pages[s].title}\n\n{self._clean_prose_body(self.pages[s].body)[:2400]}"
                for s in slugs
            ]
            vecs = self.embedder.embed_passages(texts)
            for s, vec in zip(slugs, vecs):
                self.doc_embeddings[s] = [float(x) for x in vec]

    def upsert_page(self, page: WikiPage) -> None:
        """Incrementally index or update a single WikiPage without rebuilding the whole corpus."""
        slug = page.slug
        old_tok_set = self.doc_tok_sets.get(slug, set())
        old_feat_set = set(self.doc_tf_vecs.get(slug, {}).keys())
        self.pages[slug] = page
        clean_body = re.sub(r"^- Related trail:.*$", "", page.body, flags=re.MULTILINE)
        self.body_tok_sets[slug] = set(tokenize(self._clean_prose_body(page.body)))
        weighted_text = (
            f"{page.title} {page.title} "
            f"{' '.join(page.aliases)} "
            f"{' '.join(page.tags)} "
            f"{page.summary} "
            f"{clean_body}"
        )
        toks = tokenize(weighted_text)
        self.doc_tokens[slug] = toks
        tf_map = Counter(toks)
        self.doc_tf_maps[slug] = tf_map
        self.doc_tok_sets[slug] = set(tf_map.keys())
        bis = word_ngrams(toks, 2)
        bi_map = Counter(bis)
        self.doc_bigram_maps[slug] = bi_map

        self.title_tok_sets[slug] = set(
            tokenize(f"{page.title} {' '.join(page.aliases)}")
        )
        raw_cands = [
            p.strip()
            for p in [page.title, page.slug.replace("-", " "), *page.aliases]
            if p.strip()
        ]
        parsed_cands: list[tuple[str, str, set[str]]] = []
        cand_toks_union: set[str] = set()
        for p in raw_cands:
            p_toks = set(tokenize(p))
            parsed_cands.append((p.lower(), slugify(p), p_toks))
            cand_toks_union.update(p_toks)
        self.title_candidates[slug] = parsed_cands
        self.cand_title_tok_sets[slug] = cand_toks_union

        n_docs = max(len(self.pages), 2)
        default_idf = math.log(n_docs + 1.0)
        dl = len(toks) or 1
        norm_dl = 1.5 * (1.0 - 0.75 + 0.75 * (dl / max(self.avg_dl, 1.0)))
        for term, tf in tf_map.items():
            idf_val = self.idf.get(term)
            if idf_val is None:
                idf_val = default_idf
                self.idf[term] = idf_val
            if term not in old_tok_set:
                w = idf_val * (tf * 2.5) / (tf + norm_dl)
                self.uni_postings.setdefault(term, []).append((slug, w))

        feat_counts = Counter(toks + bis)
        vec: dict[str, float] = {}
        norm_sq = 0.0
        for feat, cnt in feat_counts.items():
            f_idf = self.feature_idf.get(feat)
            if f_idf is None:
                f_idf = default_idf + 1.0
                self.feature_idf[feat] = f_idf
            weight = (1.0 + math.log(cnt)) * f_idf
            vec[feat] = weight
            norm_sq += weight * weight
        norm = math.sqrt(norm_sq) if norm_sq > 0 else 1.0
        self.doc_tf_vecs[slug] = vec
        self.doc_norms[slug] = norm
        for feat, weight in vec.items():
            if feat not in old_feat_set:
                self.tfidf_postings.setdefault(feat, []).append((slug, weight / norm))

        if self.embedder is not None:
            p_text = f"{page.title}\n\n{self._clean_prose_body(page.body)[:2400]}"
            vec = self.embedder.embed_passages([p_text])[0]
            self.doc_embeddings[slug] = [float(x) for x in vec]

    def _parse_query_titles(
        self, query_title: str, query_aliases: list[str]
    ) -> list[tuple[str, str, set[str]]]:
        candidates_q = [q.strip() for q in [query_title, *query_aliases] if q.strip()]
        return [(q.lower(), slugify(q), set(tokenize(q))) for q in candidates_q]

    def _title_alias_score_fast(
        self,
        parsed_q: list[tuple[str, str, set[str]]],
        page: WikiPage,
        *,
        min_score: float = 0.0,
    ) -> float:
        cached_p = self.title_candidates.get(page.slug)
        if cached_p is None:
            raw_p = [
                p.strip()
                for p in [page.title, page.slug.replace("-", " "), *page.aliases]
                if p.strip()
            ]
            cached_p = [(p.lower(), slugify(p), set(tokenize(p))) for p in raw_p]
        if not parsed_q or not cached_p:
            return 0.0

        best = 0.0
        for q_lower, q_slug, q_toks in parsed_q:
            len_q = len(q_lower)
            n_q_toks = len(q_toks)
            for p_lower, p_slug, p_toks in cached_p:
                if q_slug == p_slug:
                    return 1.0
                shared = len(q_toks & p_toks) if (q_toks and p_toks) else 0
                if len_q > 32 and shared == 0:
                    continue
                if shared > 0:
                    jaccard = shared / len(q_toks | p_toks)
                    containment = shared / min(n_q_toks, len(p_toks))
                    if n_q_toks >= 2 and len(p_toks) >= 2 and shared == 1:
                        tok_score = 0.75 * jaccard + 0.25 * containment
                    else:
                        tok_score = 0.55 * jaccard + 0.45 * containment
                else:
                    containment = 0.0
                    tok_score = 0.0
                if (len_q > 28 or len(p_lower) > 28) and containment < 0.50:
                    best = max(best, tok_score)
                    continue
                len_p = len(p_lower)
                seq_upper = (2.0 * min(len_q, len_p)) / max(len_q + len_p, 1)
                if 0.45 * seq_upper + 0.55 * tok_score <= max(best, min_score):
                    continue
                seq = SequenceMatcher(None, q_lower, p_lower).ratio()
                best = max(best, 0.45 * seq + 0.55 * tok_score)
        return min(best, 1.0)

    def _title_alias_score(
        self, query_title: str, query_aliases: list[str], page: WikiPage
    ) -> float:
        return self._title_alias_score_fast(
            self._parse_query_titles(query_title, query_aliases), page
        )

    def _bm25_unigram_scores(self, query_tokens: list[str]) -> dict[str, float]:
        if not query_tokens or not self.pages:
            return {}
        q_unique = list(dict.fromkeys(query_tokens))
        scores: dict[str, float] = defaultdict(float)
        for term in q_unique:
            for slug, w in self.uni_postings.get(term, ()):
                scores[slug] += w
        return scores

    def _bm25_raw_scores(self, query_tokens: list[str]) -> dict[str, float]:
        if not query_tokens or not self.pages:
            return {}
        q_unique = list(dict.fromkeys(query_tokens))
        scores = self._bm25_unigram_scores(q_unique)
        max_s = max(scores.values(), default=0.0)
        if max_s <= 0:
            return {slug: 0.0 for slug in self.pages}
        # Soft normalization preserving absolute confidence when query has few matching tokens
        scale = max(max_s, sum(self.idf.get(t, 0.8) for t in q_unique[:6]) * 0.65)
        return {slug: min(val / scale, 1.0) for slug, val in scores.items()}

    def _bigram_bm25_raw_scores(self, query_tokens: list[str]) -> dict[str, float]:
        if len(query_tokens) < 2 or not self.pages:
            return {}
        q_bis = list(dict.fromkeys(word_ngrams(query_tokens, 2)))
        scores: dict[str, float] = defaultdict(float)
        for bi in q_bis:
            for slug, w in self.bi_postings.get(bi, ()):
                scores[slug] += w
        max_s = max(scores.values(), default=0.0)
        if max_s <= 0:
            return {}
        return {slug: min(val / max_s, 1.0) for slug, val in scores.items()}

    def _query_tfidf_vector(self, query_tokens: list[str]) -> tuple[dict[str, float], float]:
        q_feats = Counter(query_tokens + word_ngrams(query_tokens, 2))
        q_vec: dict[str, float] = {}
        q_norm_sq = 0.0
        for feat, cnt in q_feats.items():
            w = (1.0 + math.log(cnt)) * self.feature_idf.get(feat, 1.0)
            q_vec[feat] = w
            q_norm_sq += w * w
        q_norm = math.sqrt(q_norm_sq) if q_norm_sq > 0 else 1.0
        return q_vec, q_norm

    def _tfidf_all_scores(self, query_tokens: list[str]) -> dict[str, float]:
        if not query_tokens or not self.pages:
            return {}
        q_vec, q_norm = self._query_tfidf_vector(query_tokens)
        scores: dict[str, float] = defaultdict(float)
        for feat, qw in q_vec.items():
            qn = qw / q_norm
            for slug, dw in self.tfidf_postings.get(feat, ()):
                scores[slug] += qn * dw
        return {slug: min(val, 1.0) for slug, val in scores.items()}

    def _tfidf_cosine_score(self, query_tokens: list[str], slug: str) -> float:
        if not query_tokens or slug not in self.doc_tf_vecs:
            return 0.0
        q_vec, q_norm = self._query_tfidf_vector(query_tokens)
        doc_vec = self.doc_tf_vecs[slug]
        dot = sum(w * doc_vec.get(feat, 0.0) for feat, w in q_vec.items())
        return min(dot / (q_norm * self.doc_norms[slug]), 1.0)

    @staticmethod
    def _graph_tag_score(
        query_tags: list[str], query_links: list[str], page: WikiPage
    ) -> float:
        q_set = {t.lower().strip() for t in query_tags if t.strip()} | {
            slugify(l) for l in query_links if l.strip()
        }
        p_set = {t.lower().strip() for t in page.tags if t.strip()} | {
            slugify(l) for l in page.outbound_links if l.strip()
        }
        if not q_set or not p_set:
            return 0.0
        return len(q_set & p_set) / len(q_set | p_set)

    def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        query_tags: list[str] | None = None,
        query_aliases: list[str] | None = None,
        query_links: list[str] | None = None,
        exclude_slug: str | None = None,
    ) -> list[SimilarityMatch]:
        if not self.pages or not query.strip():
            return []

        q_toks = tokenize(query)
        q_unique = list(dict.fromkeys(q_toks))
        q_tok_set = set(q_unique)
        q_lower = query.strip().lower()
        q_slug = slugify(query)
        aliases_q = query_aliases or []
        tags_q = query_tags or []
        links_q = query_links or []

        uni_raw = self._bm25_unigram_scores(q_unique)
        max_uni = max(uni_raw.values(), default=0.0)
        soft_scale = (
            max(max_uni, sum(self.idf.get(t, 0.8) for t in q_unique[:6]) * 0.65)
            if max_uni > 0
            else 1.0
        )
        tfidf_map = self._tfidf_all_scores(q_toks)
        plain_query = not tags_q and not links_q

        if plain_query:
            bi_map = self._bigram_bm25_raw_scores(q_toks)
            total_q_idf = sum(self.idf.get(t, 1.0) for t in q_unique) or 1.0
            cov_idf: dict[str, float] = defaultdict(float)
            for term in q_unique:
                t_idf = self.idf.get(term, 0.0)
                if t_idf <= 0.0:
                    continue
                for slug, _ in self.uni_postings.get(term, ()):
                    cov_idf[slug] += t_idf
        else:
            bi_map = {}
            total_q_idf = 1.0
            cov_idf = {}

        parsed_q_titles = self._parse_query_titles(query, aliases_q)
        need_exact_title = not plain_query or len(q_toks) < 3
        title_floor = 0.0 if need_exact_title else 0.4499

        dense_norm_map: dict[str, float] = {}
        if self.embedder is not None and self.doc_embeddings:
            q_emb = [float(x) for x in self.embedder.embed_query(query)]
            raw_dense: dict[str, float] = {}
            for s, d_emb in self.doc_embeddings.items():
                if exclude_slug and s == exclude_slug:
                    continue
                raw_dense[s] = sum(a * b for a, b in zip(q_emb, d_emb))
            if raw_dense:
                d_vals = sorted(raw_dense.values(), reverse=True)
                d_max = d_vals[0]
                d_min = d_vals[min(24, len(d_vals) - 1)]
                d_span = max(d_max - d_min, 1e-6)
                for s, v in raw_dense.items():
                    dense_norm_map[s] = max((v - d_min) / d_span, 0.0)

        candidates: list[tuple[float, str, float, bool, float, float, float]] = []
        for slug, page in self.pages.items():
            if exclude_slug and slug == exclude_slug:
                continue

            has_lexical = slug in uni_raw or slug in tfidf_map
            has_title_overlap = bool(q_tok_set & self.cand_title_tok_sets.get(slug, set()))
            d_norm = dense_norm_map.get(slug, 0.0)
            if (
                plain_query
                and not has_lexical
                and not has_title_overlap
                and not aliases_q
                and d_norm < 0.25
                and len(q_lower) > 32
            ):
                continue

            if has_title_overlap or aliases_q or len(q_lower) <= 32 or q_slug == page.slug:
                title_sc = self._title_alias_score_fast(
                    parsed_q_titles, page, min_score=title_floor
                )
                title_exact = need_exact_title or title_sc >= 0.45
            else:
                title_sc = 0.0
                title_exact = True

            b_raw = uni_raw.get(slug, 0.0)
            bm25_sc = min(b_raw / soft_scale, 1.0) if max_uni > 0 else 0.0
            tfidf_sc = tfidf_map.get(slug, 0.0)
            graph_sc = (
                self._graph_tag_score(tags_q, links_q, page) if not plain_query else 0.0
            )

            # If tags/links were not provided on a plain search query, use question-aware lexical ranking
            if plain_query:
                b_norm = (b_raw / max_uni) if max_uni > 0 else 0.0
                bi_norm = bi_map.get(slug, 0.0)
                cov_sc = min(cov_idf.get(slug, 0.0) / total_q_idf, 1.0)
                t_toks = self.title_tok_sets.get(slug, set())
                t_overlap = (
                    len(q_tok_set & t_toks) / max(len(q_tok_set), 1) if q_tok_set else 0.0
                )
                question_score = (
                    0.42 * b_norm
                    + 0.22 * bi_norm
                    + 0.22 * tfidf_sc
                    + 0.10 * cov_sc
                    + 0.04 * t_overlap
                )
                if len(q_toks) >= 3 and title_sc < 0.45:
                    composite = question_score
                else:
                    entity_score = 0.40 * title_sc + 0.32 * bm25_sc + 0.28 * tfidf_sc
                    composite = max(question_score, entity_score)
            else:
                composite = (
                    self.W_TITLE * title_sc
                    + self.W_BM25 * bm25_sc
                    + self.W_TFIDF * tfidf_sc
                    + self.W_GRAPH * graph_sc
                )

            # Strong boost when exact slug or title substring matches
            page_title_lower = page.title.lower()
            min_sub_q = 2 if has_cjk(q_lower) else 4
            if q_lower == page_title_lower or q_slug == page.slug:
                composite = max(composite, 0.96)
            elif len(q_lower) >= min_sub_q and (q_lower in page_title_lower or page_title_lower in q_lower):
                composite = max(composite, 0.68)

            if dense_norm_map:
                composite = 0.55 * composite + 0.45 * dense_norm_map.get(slug, 0.0)

            if composite > 0.02:
                candidates.append(
                    (
                        min(composite, 1.0),
                        slug,
                        title_sc,
                        title_exact,
                        bm25_sc,
                        tfidf_sc,
                        graph_sc,
                    )
                )

        candidates.sort(key=lambda row: row[0], reverse=True)
        matches: list[SimilarityMatch] = []
        for score, slug, title_sc, title_exact, bm25_sc, tfidf_sc, graph_sc in candidates[:top_k]:
            page = self.pages[slug]
            if not title_exact:
                title_sc = self._title_alias_score_fast(parsed_q_titles, page)
            matched = sorted(q_tok_set & self.doc_tok_sets.get(slug, set()))
            matches.append(
                SimilarityMatch(
                    slug=slug,
                    title=page.title,
                    category=page.category,
                    summary=page.summary,
                    score=score,
                    title_score=title_sc,
                    bm25_score=bm25_sc,
                    tfidf_score=tfidf_sc,
                    graph_score=graph_sc,
                    matched_terms=matched,
                    tags=page.tags,
                    revision_count=page.revision_count,
                )
            )

        return matches

    def find_similar_for_candidate(
        self,
        *,
        title: str,
        content: str,
        tags: list[str] | None = None,
        aliases: list[str] | None = None,
        links: list[str] | None = None,
        threshold: float = 0.35,
        exclude_slug: str | None = None,
    ) -> dict[str, Any]:
        """
        Determine whether a candidate topic should UPDATE an existing page or CREATE a new one.
        """
        cand_toks = tokenize(f"{title} {content[:8000]}")
        cand_tok_set = set(cand_toks)
        body_tok_set = set(tokenize(content[:8000])) or cand_tok_set
        title_tok_set = set(tokenize(f"{title} {' '.join(aliases or [])}"))
        bm25_toks = (
            sorted(cand_tok_set, key=lambda t: self.idf.get(t, 0.0), reverse=True)[:28]
            if len(cand_tok_set) > 28
            else list(cand_tok_set)
        )
        bm25_map = self._bm25_raw_scores(bm25_toks)
        q_vec, q_norm = self._query_tfidf_vector(cand_toks)

        approx_tfidf: dict[str, float] = defaultdict(float)
        top_q_feats = (
            sorted(q_vec.items(), key=lambda kv: kv[1], reverse=True)[:32]
            if len(q_vec) > 32
            else list(q_vec.items())
        )
        for feat, qw in top_q_feats:
            qn = qw / q_norm
            for s, dw in self.tfidf_postings.get(feat, ()):
                approx_tfidf[s] += qn * dw

        title_ov_scores: list[tuple[str, float]] = []
        q_slug = slugify(title)
        for s, p_tset in self.cand_title_tok_sets.items():
            if s == exclude_slug:
                continue
            if s == q_slug:
                title_ov_scores.append((s, 1.0))
            elif title_tok_set and p_tset:
                sh = len(title_tok_set & p_tset)
                if sh > 0:
                    title_ov_scores.append((s, sh / len(title_tok_set | p_tset)))
        top_title = sorted(title_ov_scores, key=lambda kv: kv[1], reverse=True)[:6]
        top_bm25 = sorted(bm25_map.items(), key=lambda kv: kv[1], reverse=True)[:6]
        top_tfidf = sorted(approx_tfidf.items(), key=lambda kv: kv[1], reverse=True)[:6]

        dense_cand_map: dict[str, float] = {}
        if self.embedder is not None and self.doc_embeddings:
            cand_emb = [
                float(x)
                for x in self.embedder.embed_passages([f"{title}\n\n{content[:2400]}"])[0]
            ]
            for s, d_emb in self.doc_embeddings.items():
                if s != exclude_slug:
                    dense_cand_map[s] = sum(a * b for a, b in zip(cand_emb, d_emb))
        top_dense = sorted(dense_cand_map.items(), key=lambda kv: kv[1], reverse=True)[:6]

        candidate_slugs = list(
            dict.fromkeys(
                [s for s, _ in top_title]
                + [s for s, v in top_bm25 if v > 0 and s != exclude_slug]
                + [s for s, v in top_tfidf if v > 0 and s != exclude_slug]
                + [s for s, _ in top_dense]
            )
        )

        rescored: list[SimilarityMatch] = []
        title_lower = title.strip().lower()
        parsed_q_titles = self._parse_query_titles(title, aliases or [])
        is_full_passage = len(body_tok_set) >= 12
        for slug in candidate_slugs:
            page = self.pages[slug]
            t_sc = self._title_alias_score_fast(parsed_q_titles, page)
            b_sc = bm25_map.get(slug, 0.0)
            doc_vec = self.doc_tf_vecs.get(slug, {})
            dot = sum(w * doc_vec.get(feat, 0.0) for feat, w in q_vec.items())
            tf_sc = min(dot / (q_norm * self.doc_norms.get(slug, 1.0)), 1.0)
            g_sc = self._graph_tag_score(tags or [], links or [], page)
            doc_tok_set = self.doc_tok_sets.get(slug, set())
            page_body_toks = self.body_tok_sets.get(slug) or doc_tok_set
            body_containment = len(body_tok_set & page_body_toks) / max(len(body_tok_set), 1)
            body_jaccard = len(body_tok_set & page_body_toks) / max(len(body_tok_set | page_body_toks), 1)
            page_title_lower = page.title.strip().lower()
            is_cjk_title = has_cjk(title_lower) or has_cjk(page_title_lower)
            min_title_chars = 2 if is_cjk_title else 5
            min_title_toks = 1 if is_cjk_title else 2
            has_substring_title = (
                min(len(page_title_lower), len(title_lower)) >= min_title_chars
                and (page_title_lower in title_lower or title_lower in page_title_lower)
                and len(tokenize(page_title_lower)) >= min_title_toks
                and len(tokenize(title_lower)) >= min_title_toks
            )
            has_title_inclusion = (
                q_slug == page.slug
                or any(slugify(a) == page.slug for a in (aliases or []))
                or any(q_slug == slugify(pa) for pa in page.aliases)
                or has_substring_title
            )
            is_near_dup_body = (
                tf_sc >= 0.84
                or (tf_sc >= 0.52 and body_containment >= 0.92 and body_jaccard >= 0.88)
            )
            dense_sc = dense_cand_map.get(slug, 0.0)
            is_semantic_paraphrase = bool(dense_cand_map) and (
                dense_sc >= 0.932 or (dense_sc >= 0.905 and tf_sc >= 0.28)
            )
            if not has_title_inclusion:
                if is_full_passage and not is_near_dup_body and not is_semantic_paraphrase:
                    b_sc = b_sc * (tf_sc * 0.35)
                    t_sc = t_sc * (tf_sc * 0.35)
                elif (
                    not is_semantic_paraphrase
                    and (
                        (tf_sc < 0.16 and body_containment < 0.28)
                        or (tf_sc < 0.12 and body_containment < 0.45)
                    )
                ):
                    b_sc = b_sc * (tf_sc / 0.16)
                    t_sc = t_sc * 0.65

            score = (
                self.W_TITLE * t_sc
                + self.W_BM25 * b_sc
                + self.W_TFIDF * tf_sc
                + self.W_GRAPH * g_sc
            )
            if is_full_passage and not has_title_inclusion and not is_near_dup_body and not is_semantic_paraphrase:
                score = min(score, 0.34 * tf_sc)
            if is_semantic_paraphrase:
                # Calibrated E5 semantic paraphrase boost (rescaled for E5 [0.85, 0.96] band)
                sem_norm = min(max((dense_sc - 0.85) / 0.11, 0.0), 1.0)
                score = max(score, 0.72 * sem_norm + 0.20 * tf_sc + 0.08 * b_sc)
            if q_slug == page.slug or any(slugify(a) == page.slug for a in (aliases or [])):
                score = max(score, 0.95)
            if any(q_slug == slugify(pa) for pa in page.aliases):
                score = max(score, 0.88)
            if has_substring_title:
                score = max(score, 0.72)
            if is_near_dup_body:
                score = max(
                    score,
                    min(
                        0.96,
                        0.45 * tf_sc
                        + 0.35 * body_containment
                        + 0.10 * b_sc
                        + 0.10 * t_sc,
                    ),
                )

            matched = sorted(cand_tok_set & doc_tok_set)

            rescored.append(
                SimilarityMatch(
                    slug=slug,
                    title=page.title,
                    category=page.category,
                    summary=page.summary,
                    score=min(score, 1.0),
                    title_score=t_sc,
                    bm25_score=b_sc,
                    tfidf_score=tf_sc,
                    graph_score=g_sc,
                    matched_terms=matched,
                    tags=page.tags,
                    revision_count=page.revision_count,
                )
            )

        rescored.sort(key=lambda x: x.score, reverse=True)
        rescored = rescored[:5]
        best_match = rescored[0] if rescored else None
        should_update = bool(best_match and best_match.score >= threshold)

        return {
            "action": "update" if should_update else "create",
            "threshold": threshold,
            "target_slug": best_match.slug if should_update and best_match else None,
            "target_title": best_match.title if should_update and best_match else None,
            "best_score": round(best_match.score, 4) if best_match else 0.0,
            "candidates": [c.to_dict() for c in rescored],
        }

    def find_near_duplicate_pairs(self, threshold: float = 0.55) -> list[dict[str, Any]]:
        """
        Fast pairwise near-duplicate detection across all pages using precomputed
        TF-IDF vectors, token containment, title/alias similarity, and concept graph overlap.
        """
        slugs = list(self.pages.keys())
        if len(slugs) < 2:
            return []

        tok_sets: dict[str, set[str]] = {
            s: set(self.doc_tokens.get(s, [])) for s in slugs
        }
        title_tok_sets: dict[str, set[str]] = {
            s: set(tokenize(f"{self.pages[s].title} {' '.join(self.pages[s].aliases)}"))
            for s in slugs
        }

        pairs: list[dict[str, Any]] = []
        for i in range(len(slugs)):
            slug_a = slugs[i]
            page_a = self.pages[slug_a]
            vec_a = self.doc_tf_vecs.get(slug_a, {})
            norm_a = self.doc_norms.get(slug_a, 1.0)
            toks_a = tok_sets[slug_a]
            if not toks_a:
                continue

            for j in range(i + 1, len(slugs)):
                slug_b = slugs[j]
                page_b = self.pages[slug_b]
                toks_b = tok_sets[slug_b]
                if not toks_b:
                    continue

                vec_b = self.doc_tf_vecs.get(slug_b, {})
                norm_b = self.doc_norms.get(slug_b, 1.0)

                # Iterate over the smaller feature dict for fast dot product
                if len(vec_a) <= len(vec_b):
                    dot = sum(w * vec_b.get(feat, 0.0) for feat, w in vec_a.items())
                else:
                    dot = sum(w * vec_a.get(feat, 0.0) for feat, w in vec_b.items())
                tf_sc = min(dot / (norm_a * norm_b), 1.0) if norm_a > 0 and norm_b > 0 else 0.0

                shared_toks = len(toks_a & toks_b)
                containment = shared_toks / max(min(len(toks_a), len(toks_b)), 1)

                # Early skip if neither lexical vectors, containment, nor title tokens overlap meaningfully
                if (
                    tf_sc < 0.18
                    and containment < 0.35
                    and not (title_tok_sets[slug_a] & title_tok_sets[slug_b])
                ):
                    continue

                t_sc = self._title_alias_score(page_a.title, page_a.aliases, page_b)
                g_sc = self._graph_tag_score(page_a.tags, page_a.outbound_links, page_b)
                if tf_sc < 0.22 and containment < 0.45:
                    t_sc = t_sc * 0.55

                score = 0.35 * t_sc + 0.35 * tf_sc + 0.20 * containment + 0.10 * g_sc
                if (
                    tf_sc >= 0.55
                    or (tf_sc >= 0.40 and containment >= 0.72)
                    or (tf_sc >= 0.30 and containment >= 0.78)
                    or (t_sc >= 0.85 and (tf_sc >= 0.32 or containment >= 0.65))
                ):
                    score = max(score, 0.82 if tf_sc >= 0.55 or t_sc >= 0.85 else 0.72)

                if score >= threshold:
                    pairs.append(
                        {
                            "slug_a": page_a.slug,
                            "title_a": page_a.title,
                            "slug_b": page_b.slug,
                            "title_b": page_b.title,
                            "score": round(min(score, 1.0), 4),
                        }
                    )

        pairs.sort(key=lambda item: item["score"], reverse=True)
        return pairs
