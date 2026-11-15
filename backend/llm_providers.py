from __future__ import annotations

import json
import re
import time
import unicodedata
from typing import Any

import httpx

from backend.config import RuntimeSettings
from backend.similarity import has_cjk, tokenize, word_ngrams
from backend.telemetry import TelemetryTracker, compute_cost_usd, estimate_tokens
from backend.vault_manager import WikiPage, slugify, utc_now_iso

_RE_NUMBER = re.compile(r"(?<![a-zA-Z0-9])\d+(?:\.\d+)?(?![a-zA-Z0-9])")


def _extract_numbers(text: str) -> set[str]:
    return set(_RE_NUMBER.findall(unicodedata.normalize("NFKC", text)))


CONTRADICTION_MARKERS = (
    "however",
    "contrary",
    "contrary to",
    "unlike",
    "instead of",
    "supersedes",
    "replaces",
    "disproves",
    "although",
    "in contrast",
    "whereas",
    "critique",
    "limitation",
    "declassified",
    "revision",
    "addendum",
    "disputed",
    "audit",
    "しかし",
    "一方で",
    "従来とは異なり",
    "改訂",
    "修正",
    "差し替え",
    "廃止",
)


class LLMService:
    """
    Unified multi-provider LLM client (Gemini Interactions API, OpenAI, Ollama)
    with a deterministic Smart Offline Synthesis fallback so the wiki works out of the box.
    """

    def __init__(self, settings: RuntimeSettings, telemetry: TelemetryTracker | None = None):
        self.settings = settings
        self.telemetry = telemetry or TelemetryTracker()
        self._gemini_client: Any = None
        self.stats: dict[str, Any] = {
            "calls_attempted": 0,
            "calls_succeeded": 0,
            "calls_failed": 0,
            "local_executions": 0,
            "dedup_llm_skips": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "thought_tokens": 0,
            "total_tokens": 0,
            "estimated_tokens_saved": 0,
            "total_cost_usd": 0.0,
            "estimated_cost_saved_usd": 0.0,
            "total_latency_s": 0.0,
            "last_provider": self.active_mode(),
            "last_model": self.active_model_name(),
            "last_llm_used": False,
            "last_error": "",
        }

    def _get_gemini_client(self) -> Any:
        if self._gemini_client is None:
            from google import genai

            self._gemini_client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._gemini_client

    def active_mode(self) -> str:
        if self.settings.provider == "gemini" and self.settings.gemini_api_key:
            return "gemini"
        if self.settings.provider == "openai" and self.settings.openai_api_key:
            return "openai"
        if self.settings.provider == "ollama":
            return "ollama"
        return "local_smart"

    def active_model_name(self) -> str:
        mode = self.active_mode()
        if mode == "gemini":
            return self.settings.gemini_model or "gemini-3.5-flash-lite"
        if mode == "openai":
            return self.settings.openai_model or "gpt-4o-mini"
        if mode == "ollama":
            return self.settings.ollama_model or "llama3.2"
        return "local_smart"

    def _sync_stats_from_event(self, ev: Any) -> None:
        self.stats["last_provider"] = ev.provider
        self.stats["last_model"] = ev.model
        self.stats["last_llm_used"] = ev.llm_used
        if ev.llm_used:
            self.stats["input_tokens"] += ev.input_tokens
            self.stats["output_tokens"] += ev.output_tokens
            self.stats["thought_tokens"] += ev.thought_tokens
            self.stats["total_tokens"] += ev.total_tokens
            self.stats["total_cost_usd"] = round(self.stats["total_cost_usd"] + ev.cost_usd, 8)
        else:
            self.stats["local_executions"] += 1
            if ev.execution_mode == "local_dedup_prefilter":
                self.stats["dedup_llm_skips"] += 1
            self.stats["estimated_tokens_saved"] += ev.estimated_tokens_saved
            self.stats["estimated_cost_saved_usd"] = round(
                self.stats["estimated_cost_saved_usd"] + ev.estimated_cost_saved_usd, 8
            )

    @staticmethod
    def _extract_gemini_usage(
        interaction: Any, prompt_text: str, output_text: str
    ) -> tuple[int, int, int, int, int, str]:
        usage = getattr(interaction, "usage", None) or getattr(interaction, "usage_metadata", None)
        if usage is not None:
            in_tok = int(
                getattr(usage, "total_input_tokens", None)
                or getattr(usage, "prompt_token_count", None)
                or getattr(usage, "initial_input_tokens", None)
                or 0
            )
            out_tok = int(
                getattr(usage, "total_output_tokens", None)
                or getattr(usage, "response_token_count", None)
                or getattr(usage, "candidates_token_count", None)
                or 0
            )
            thought_tok = int(
                getattr(usage, "total_thought_tokens", None)
                or getattr(usage, "thoughts_token_count", None)
                or 0
            )
            cached_tok = int(
                getattr(usage, "total_cached_tokens", None)
                or getattr(usage, "cached_content_token_count", None)
                or 0
            )
            tot_tok = int(
                getattr(usage, "total_tokens", None)
                or getattr(usage, "total_token_count", None)
                or (in_tok + out_tok + thought_tok)
            )
            if in_tok > 0 or out_tok > 0 or tot_tok > 0:
                if out_tok == 0 and output_text:
                    out_tok = estimate_tokens(output_text)
                    tot_tok = max(tot_tok, in_tok + out_tok + thought_tok)
                return in_tok, out_tok, thought_tok, cached_tok, tot_tok, "api_usage"
        in_est = estimate_tokens(prompt_text)
        out_est = estimate_tokens(output_text)
        return in_est, out_est, 0, 0, in_est + out_est, "estimated"

    @staticmethod
    def _extract_openai_usage(
        resp_json: dict[str, Any], prompt_text: str, output_text: str
    ) -> tuple[int, int, int, int, int, str]:
        usage = resp_json.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        out_tok = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        tot_tok = int(usage.get("total_tokens") or (in_tok + out_tok))
        if in_tok > 0 or out_tok > 0:
            return in_tok, out_tok, 0, 0, tot_tok, "api_usage"
        in_est = estimate_tokens(prompt_text)
        out_est = estimate_tokens(output_text)
        return in_est, out_est, 0, 0, in_est + out_est, "estimated"

    @staticmethod
    def _extract_ollama_usage(
        resp_json: dict[str, Any], prompt_text: str, output_text: str
    ) -> tuple[int, int, int, int, int, str]:
        in_tok = int(resp_json.get("prompt_eval_count") or 0)
        out_tok = int(resp_json.get("eval_count") or 0)
        if in_tok > 0 or out_tok > 0:
            return in_tok, out_tok, 0, 0, in_tok + out_tok, "api_usage"
        in_est = estimate_tokens(prompt_text)
        out_est = estimate_tokens(output_text)
        return in_est, out_est, 0, 0, in_est + out_est, "estimated"

    # ------------------------------------------------------------------
    # Public High-Level Capabilities
    # ------------------------------------------------------------------

    def extract_candidates(
        self, title: str, content: str, existing_pages: dict[str, WikiPage]
    ) -> list[dict[str, Any]]:
        """
        Extract structured candidate wiki topics (primary topic + sub-concepts/entities)
        from a raw source or chat synthesis.
        """
        t0 = time.perf_counter()
        mode = self.active_mode()
        est_saved = estimate_tokens(content[:12000]) + 220

        if title.strip() or mode == "local_smart":
            items = self._local_extract_candidates(title, content, existing_pages)
            lat_ms = (time.perf_counter() - t0) * 1000.0
            exec_mode = "local_smart" if mode == "local_smart" else "local_dedup_prefilter"
            reason = (
                "Provider is local_smart (deterministic candidate extraction)"
                if mode == "local_smart"
                else "Explicit note title provided; deterministic candidate extraction used"
            )
            ev = self.telemetry.record_event(
                operation="extract_candidates",
                llm_used=False,
                execution_mode=exec_mode,
                provider=mode,
                model="local_smart" if mode == "local_smart" else self.active_model_name(),
                status="ok",
                estimated_tokens_saved=est_saved,
                latency_ms=lat_ms,
                target_slug=slugify(title) if title.strip() else "",
                reason=reason,
            )
            self._sync_stats_from_event(ev)
            return items

        try:
            catalog_hint = "\n".join(
                f"- {p.slug}: {p.title} (tags: {', '.join(p.tags[:4])})"
                for p in list(existing_pages.values())[:60]
            )
            schema = {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "category": {
                                    "type": "string",
                                    "enum": ["concepts", "entities", "sources", "syntheses"],
                                },
                                "aliases": {"type": "array", "items": {"type": "string"}},
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "summary": {"type": "string"},
                                "body": {"type": "string"},
                            },
                            "required": ["title", "category", "tags", "summary", "body"],
                        },
                    }
                },
                "required": ["items"],
            }
            prompt = (
                f"You are an expert knowledge base curator following Andrej Karpathy's LLM Wiki schema.\n"
                f"Analyze the incoming document and extract 1 to 3 cohesive wiki pages (a primary topic plus any distinct major sub-concepts).\n"
                f"Existing wiki catalog (reuse exact terminology when referring to existing concepts):\n{catalog_hint}\n\n"
                f"Incoming Title: {title}\n"
                f"Incoming Content:\n{content[:12000]}"
            )
            parsed = self._call_json_llm(
                prompt,
                schema,
                operation="extract_candidates",
                reason="Extracting candidate topics from untitled source via LLM",
            )
            items = parsed.get("items") or []
            if items:
                return items
        except Exception as exc:
            lat_ms = (time.perf_counter() - t0) * 1000.0
            ev = self.telemetry.record_event(
                operation="extract_candidates",
                llm_used=False,
                execution_mode="llm_fallback_to_local",
                provider=mode,
                model=self.active_model_name(),
                status="fallback",
                estimated_tokens_saved=est_saved,
                latency_ms=lat_ms,
                reason="LLM call failed; fell back to deterministic candidate extraction",
                error=f"{type(exc).__name__}: {str(exc)[:180]}",
            )
            self._sync_stats_from_event(ev)

        return self._local_extract_candidates(title, content, existing_pages)

    def synthesize_page_update(
        self,
        *,
        existing_page: WikiPage,
        new_title: str,
        new_content: str,
        source_name: str,
        new_tags: list[str],
        new_aliases: list[str],
        all_pages: dict[str, WikiPage],
    ) -> dict[str, Any]:
        """
        Merge new knowledge into an existing wiki page in-place instead of creating a duplicate.
        Preserves prior synthesis, integrates updates, flags contradictions, and weaves [[wikilinks]].
        """
        t0 = time.perf_counter()
        mode = self.active_mode()
        est_saved = (
            estimate_tokens(existing_page.body[:5000])
            + estimate_tokens(new_content[:6000])
            + 180
        )

        local_synth = self._local_synthesize_page_update(
            existing_page=existing_page,
            new_title=new_title,
            new_content=new_content,
            source_name=source_name,
            new_tags=new_tags,
            all_pages=all_pages,
        )
        local_lat_ms = (time.perf_counter() - t0) * 1000.0

        if local_synth.get("novel_added", 0) == 0:
            exec_mode = "local_dedup_prefilter" if mode != "local_smart" else "local_smart"
            ev = self.telemetry.record_event(
                operation="synthesize_page_update",
                llm_used=False,
                execution_mode=exec_mode,
                provider=mode,
                model=self.active_model_name() if mode != "local_smart" else "local_smart",
                status="ok",
                estimated_tokens_saved=est_saved,
                latency_ms=local_lat_ms,
                target_slug=existing_page.slug,
                reason=(
                    f"Pre-filter skipped {local_synth.get('redundant_skipped', 0)} redundant block(s) "
                    f"(0 novel sentences); avoided unnecessary LLM call"
                ),
            )
            self._sync_stats_from_event(ev)
            local_synth["telemetry"] = ev.to_dict()
            return local_synth

        if mode != "local_smart":
            try:
                schema = {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "change_note": {"type": "string"},
                        "contradictions_found": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary", "change_note", "contradictions_found"],
                }
                prompt = (
                    f"You are curating an existing LLM Wiki page after merging new source insights.\n"
                    f"Produce:\n"
                    f"1. `summary`: updated 1-2 sentence synthesis capturing both prior knowledge and the newly integrated facts.\n"
                    f"2. `change_note`: concise 1-sentence changelog entry citing specific newly integrated terms or revisions.\n"
                    f"3. `contradictions_found`: list of specific factual contradictions or parameter overrides introduced by the new source against existing claims (empty list if purely additive).\n\n"
                    f"EXISTING PAGE ([[{existing_page.slug}|{existing_page.title}]]):\n"
                    f"Current Summary: {existing_page.summary}\n"
                    f"{existing_page.body[:5000]}\n\n"
                    f"NEW SOURCE ({source_name} — {new_title}):\n{new_content[:6000]}"
                )
                parsed = self._call_json_llm(
                    prompt,
                    schema,
                    operation="synthesize_page_update",
                    target_slug=existing_page.slug,
                    reason=(
                        f"Synthesizing {local_synth.get('novel_added', 0)} novel block(s) "
                        f"from '{new_title}' into [[{existing_page.slug}]]"
                    ),
                )
                if parsed.get("summary"):
                    local_synth["summary"] = str(parsed["summary"]).strip()
                if parsed.get("change_note"):
                    local_synth["change_note"] = str(parsed["change_note"]).strip()

                llm_contradictions = [
                    str(c).strip() for c in (parsed.get("contradictions_found") or []) if str(c).strip()
                ]
                if llm_contradictions:
                    date_str = utc_now_iso()[:10]
                    updated_body = local_synth["updated_body"]
                    existing_lower = updated_body.lower()
                    new_bullets: list[str] = []
                    for note in llm_contradictions[:2]:
                        if note[:40].lower() not in existing_lower:
                            bullet = f"- **[{date_str} | {source_name}]** Gemini tension note: {note}"
                            new_bullets.append(bullet)
                    if new_bullets:
                        tension_header = "## Contradictions & Tensions"
                        joined = "\n\n".join(new_bullets)
                        if tension_header in updated_body:
                            updated_body = f"{updated_body}\n\n{joined}"
                        else:
                            updated_body = f"{updated_body}\n\n{tension_header}\n\n{joined}"
                        local_synth["updated_body"] = updated_body
                        local_synth["contradictions_found"] = [
                            *local_synth.get("contradictions_found", []),
                            *new_bullets,
                        ]
                if self.telemetry._all_events_list:
                    local_synth["telemetry"] = self.telemetry._all_events_list[-1].to_dict()
                return local_synth
            except Exception as exc:
                ev = self.telemetry.record_event(
                    operation="synthesize_page_update",
                    llm_used=False,
                    execution_mode="llm_fallback_to_local",
                    provider=mode,
                    model=self.active_model_name(),
                    status="fallback",
                    estimated_tokens_saved=est_saved,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    target_slug=existing_page.slug,
                    reason="LLM update synthesis failed; used deterministic local synthesis",
                    error=f"{type(exc).__name__}: {str(exc)[:180]}",
                )
                self._sync_stats_from_event(ev)
                local_synth["telemetry"] = ev.to_dict()
                return local_synth

        ev = self.telemetry.record_event(
            operation="synthesize_page_update",
            llm_used=False,
            execution_mode="local_smart",
            provider="local_smart",
            model="local_smart",
            status="ok",
            estimated_tokens_saved=est_saved,
            latency_ms=local_lat_ms,
            target_slug=existing_page.slug,
            reason=(
                f"Merged {local_synth.get('novel_added', 0)} novel block(s) deterministically "
                f"(skipped {local_synth.get('redundant_skipped', 0)} redundant)"
            ),
        )
        self._sync_stats_from_event(ev)
        local_synth["telemetry"] = ev.to_dict()
        return local_synth

    def answer_wiki_query(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
        retrieved_pages: list[tuple[WikiPage, float]],
        index_markdown: str,
    ) -> str:
        """Generate a grounded markdown answer citing wiki pages via [[slug|Title]]."""
        t0 = time.perf_counter()
        local_md = self._local_answer_query(question=question, retrieved_pages=retrieved_pages)
        local_lat_ms = (time.perf_counter() - t0) * 1000.0
        mode = self.active_mode()
        top_slug = retrieved_pages[0][0].slug if retrieved_pages else ""
        est_saved = (
            estimate_tokens(question)
            + sum(estimate_tokens(p.body[:6000]) for p, _ in retrieved_pages)
            + 300
        )

        if mode != "local_smart" and retrieved_pages:
            try:
                top_page, _ = retrieved_pages[0]
                citations = ", ".join(f"[[{p.slug}|{p.title}]]" for p, _ in retrieved_pages[:4])
                context_blocks = "\n\n---\n\n".join(
                    f"PAGE [[{p.slug}|{p.title}]] (category: {p.category}, score: {score:.2f}, tags: {', '.join(p.tags)}):\n{p.body[:6000]}"
                    for p, score in retrieved_pages
                )
                conv = "\n".join(
                    f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                    for msg in history[-6:]
                )
                sys_prompt = (
                    "You are the curator of a persistent, self-maintaining LLM Wiki. "
                    "Answer the user's question concisely (2-4 sentences) using ONLY the retrieved wiki pages. "
                    "Quote exact technical terms, specification identifiers, parameter values, numeric measurements, "
                    "and named entities verbatim when they answer the question, and cite pages using Obsidian wikilinks "
                    "like [[slug|Title]]. If the page records a newer revision or Contradictions & Tensions overriding older values, "
                    "explicitly state the updated/contradicting facts."
                )
                full_input = (
                    f"Wiki Index Summary:\n{index_markdown[:2500]}\n\n"
                    f"Retrieved Wiki Pages:\n{context_blocks}\n\n"
                    f"Recent Conversation:\n{conv}\n\n"
                    f"Question: {question}"
                )
                text = self._call_text_llm(
                    full_input,
                    system_instruction=sys_prompt,
                    operation="answer_wiki_query",
                    target_slug=top_slug,
                    reason=f"Grounded QA synthesis citing {len(retrieved_pages)} page(s)",
                )
                if text.strip():
                    local_direct = ""
                    if "### Direct Answer" in local_md:
                        after_h = local_md.split("### Direct Answer", 1)[1]
                        direct_body = "\n".join(after_h.splitlines()[1:])
                        local_direct = direct_body.split("\n### ", 1)[0].strip()

                    combined_direct = (
                        f"{text.strip()}\n\n> **Extractive Verbatim Span**: {local_direct}"
                        if local_direct
                        else text.strip()
                    )
                    header = f"Based on the compiled wiki ({citations}), here is the synthesized answer to **{question}**:"
                    parts = [
                        header,
                        "",
                        f"### Direct Answer ([[{top_page.slug}|{top_page.title}]])",
                        combined_direct,
                    ]
                    for marker in (
                        "### Key Evidence Across Wiki Pages",
                        "### Documented Tensions & Nuances",
                        "**Further associative trails**",
                    ):
                        if marker in local_md:
                            parts.extend(["", local_md[local_md.index(marker) :]])
                            break
                    return "\n".join(parts)
            except Exception as exc:
                ev = self.telemetry.record_event(
                    operation="answer_wiki_query",
                    llm_used=False,
                    execution_mode="llm_fallback_to_local",
                    provider=mode,
                    model=self.active_model_name(),
                    status="fallback",
                    estimated_tokens_saved=est_saved,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    target_slug=top_slug,
                    reason="LLM QA call failed; fell back to deterministic extractive answer",
                    error=f"{type(exc).__name__}: {str(exc)[:180]}",
                )
                self._sync_stats_from_event(ev)
                return local_md

        ev = self.telemetry.record_event(
            operation="answer_wiki_query",
            llm_used=False,
            execution_mode="local_smart",
            provider="local_smart",
            model="local_smart",
            status="ok",
            estimated_tokens_saved=est_saved,
            latency_ms=local_lat_ms,
            target_slug=top_slug,
            reason=f"Deterministic extractive QA over {len(retrieved_pages)} retrieved page(s)",
        )
        self._sync_stats_from_event(ev)
        return local_md

    # ------------------------------------------------------------------
    # External Provider Implementations
    # ------------------------------------------------------------------

    def _call_text_llm(
        self,
        prompt: str,
        *,
        system_instruction: str = "",
        operation: str = "llm_text_call",
        target_slug: str = "",
        reason: str = "",
    ) -> str:
        mode = self.active_mode()
        if mode == "local_smart":
            return ""
        self.stats["calls_attempted"] += 1
        t0 = time.perf_counter()
        full_prompt_for_est = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
        model_name = self.active_model_name()
        try:
            in_tok = out_tok = thought_tok = cached_tok = tot_tok = 0
            tok_source = "estimated"
            if mode == "gemini":
                client = self._get_gemini_client()
                model_name = self.settings.gemini_model or "gemini-3.5-flash-lite"
                self.stats["last_model"] = model_name
                kwargs: dict[str, Any] = {
                    "model": model_name,
                    "input": prompt,
                    "store": False,
                }
                if system_instruction:
                    kwargs["system_instruction"] = system_instruction
                interaction = client.interactions.create(**kwargs)
                out = interaction.output_text or ""
                in_tok, out_tok, thought_tok, cached_tok, tot_tok, tok_source = (
                    self._extract_gemini_usage(interaction, full_prompt_for_est, out)
                )
            elif mode == "openai":
                model_name = self.settings.openai_model
                self.stats["last_model"] = model_name
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})
                resp = httpx.post(
                    f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                    json={
                        "model": model_name,
                        "messages": messages,
                        "temperature": 0.3,
                    },
                    timeout=45.0,
                )
                resp.raise_for_status()
                r_json = resp.json()
                out = r_json["choices"][0]["message"]["content"]
                in_tok, out_tok, thought_tok, cached_tok, tot_tok, tok_source = (
                    self._extract_openai_usage(r_json, full_prompt_for_est, out)
                )
            elif mode == "ollama":
                model_name = self.settings.ollama_model
                self.stats["last_model"] = model_name
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})
                resp = httpx.post(
                    f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                    json={
                        "model": model_name,
                        "messages": messages,
                        "stream": False,
                    },
                    timeout=60.0,
                )
                resp.raise_for_status()
                r_json = resp.json()
                out = r_json["message"]["content"]
                in_tok, out_tok, thought_tok, cached_tok, tot_tok, tok_source = (
                    self._extract_ollama_usage(r_json, full_prompt_for_est, out)
                )
            else:
                out = ""

            elapsed_s = time.perf_counter() - t0
            self.stats["calls_succeeded"] += 1
            self.stats["total_latency_s"] = round(self.stats["total_latency_s"] + elapsed_s, 4)
            ev = self.telemetry.record_event(
                operation=operation,
                llm_used=True,
                execution_mode="llm_api",
                provider=mode,
                model=model_name,
                status="ok",
                input_tokens=in_tok,
                output_tokens=out_tok,
                thought_tokens=thought_tok,
                cached_tokens=cached_tok,
                total_tokens=tot_tok,
                token_source=tok_source,
                latency_ms=elapsed_s * 1000.0,
                target_slug=target_slug,
                reason=reason or "LLM text generation",
            )
            self._sync_stats_from_event(ev)
            return out
        except Exception as exc:
            elapsed_s = time.perf_counter() - t0
            self.stats["calls_failed"] += 1
            err_str = f"{type(exc).__name__}: {str(exc)[:220]}"
            self.stats["last_error"] = err_str
            self.stats["total_latency_s"] = round(self.stats["total_latency_s"] + elapsed_s, 4)
            ev = self.telemetry.record_event(
                operation=operation,
                llm_used=True,
                execution_mode="llm_api",
                provider=mode,
                model=model_name,
                status="error",
                input_tokens=estimate_tokens(full_prompt_for_est),
                output_tokens=0,
                token_source="estimated",
                latency_ms=elapsed_s * 1000.0,
                target_slug=target_slug,
                reason=reason or "LLM text call failed",
                error=err_str,
            )
            self._sync_stats_from_event(ev)
            raise

    def _call_json_llm(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        operation: str = "llm_json_call",
        target_slug: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        mode = self.active_mode()
        if mode == "local_smart":
            return {}
        self.stats["calls_attempted"] += 1
        t0 = time.perf_counter()
        model_name = self.active_model_name()
        try:
            in_tok = out_tok = thought_tok = cached_tok = tot_tok = 0
            tok_source = "estimated"
            if mode == "gemini":
                client = self._get_gemini_client()
                model_name = self.settings.gemini_model or "gemini-3.5-flash-lite"
                self.stats["last_model"] = model_name
                interaction = client.interactions.create(
                    model=model_name,
                    input=prompt,
                    store=False,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": schema,
                    },
                )
                raw = interaction.output_text or "{}"
                parsed = json.loads(raw)
                in_tok, out_tok, thought_tok, cached_tok, tot_tok, tok_source = (
                    self._extract_gemini_usage(interaction, prompt, raw)
                )
            elif mode == "openai":
                model_name = self.settings.openai_model
                self.stats["last_model"] = model_name
                resp = httpx.post(
                    f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": "Return valid JSON matching the requested structure."},
                            {"role": "user", "content": prompt},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.2,
                    },
                    timeout=45.0,
                )
                resp.raise_for_status()
                r_json = resp.json()
                raw = r_json["choices"][0]["message"]["content"]
                parsed = json.loads(raw)
                in_tok, out_tok, thought_tok, cached_tok, tot_tok, tok_source = (
                    self._extract_openai_usage(r_json, prompt, raw)
                )
            elif mode == "ollama":
                model_name = self.settings.ollama_model
                self.stats["last_model"] = model_name
                resp = httpx.post(
                    f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": "Respond ONLY with valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "format": "json",
                        "stream": False,
                    },
                    timeout=60.0,
                )
                resp.raise_for_status()
                r_json = resp.json()
                raw = r_json["message"]["content"]
                parsed = json.loads(raw)
                in_tok, out_tok, thought_tok, cached_tok, tot_tok, tok_source = (
                    self._extract_ollama_usage(r_json, prompt, raw)
                )
            else:
                parsed = {}

            elapsed_s = time.perf_counter() - t0
            self.stats["calls_succeeded"] += 1
            self.stats["total_latency_s"] = round(self.stats["total_latency_s"] + elapsed_s, 4)
            ev = self.telemetry.record_event(
                operation=operation,
                llm_used=True,
                execution_mode="llm_api",
                provider=mode,
                model=model_name,
                status="ok",
                input_tokens=in_tok,
                output_tokens=out_tok,
                thought_tokens=thought_tok,
                cached_tokens=cached_tok,
                total_tokens=tot_tok,
                token_source=tok_source,
                latency_ms=elapsed_s * 1000.0,
                target_slug=target_slug,
                reason=reason or "Structured JSON LLM synthesis",
            )
            self._sync_stats_from_event(ev)
            return parsed
        except Exception as exc:
            elapsed_s = time.perf_counter() - t0
            self.stats["calls_failed"] += 1
            err_str = f"{type(exc).__name__}: {str(exc)[:220]}"
            self.stats["last_error"] = err_str
            self.stats["total_latency_s"] = round(self.stats["total_latency_s"] + elapsed_s, 4)
            ev = self.telemetry.record_event(
                operation=operation,
                llm_used=True,
                execution_mode="llm_api",
                provider=mode,
                model=model_name,
                status="error",
                input_tokens=estimate_tokens(prompt),
                output_tokens=0,
                token_source="estimated",
                latency_ms=elapsed_s * 1000.0,
                target_slug=target_slug,
                reason=reason or "Structured JSON LLM call failed",
                error=err_str,
            )
            self._sync_stats_from_event(ev)
            raise

    # ------------------------------------------------------------------
    # Smart Offline Synthesis Fallback (Always Available)
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_category(title: str, content: str) -> str:
        lower = f"{title} {content[:500]}".lower()
        if title.lower().startswith("source:") or "author:" in lower or "published:" in lower:
            return "sources"
        if any(w in lower for w in ("comparison", "vs", "synthesis", "architecture", "overview")):
            if "vs" in title.lower() or "synthesis" in title.lower():
                return "syntheses"
        if any(w in lower for w in ("tool", "framework", "person", "library", "model", "memex", "obsidian", "agent")):
            # Heuristic: proper-noun heavy short titles often represent entities
            words = [w for w in title.split() if w[:1].isupper()]
            if len(words) == len(title.split()) and len(words) <= 3 and "pattern" not in lower:
                return "entities"
        return "concepts"

    @staticmethod
    def _extract_tags(title: str, content: str, existing_pages: dict[str, WikiPage]) -> list[str]:
        known_tags: set[str] = set()
        for p in existing_pages.values():
            known_tags.update(p.tags)
        toks = tokenize(f"{title} {content[:1500]}")
        freq: dict[str, int] = {}
        for t in toks:
            freq[t] = freq.get(t, 0) + 1
        # Prefer existing tags that appear in the text (sorted deterministically), then top frequent terms
        matched_known = sorted(
            [t for t in known_tags if t.replace("-", " ") in content.lower() or t in freq],
            key=lambda t: (-freq.get(t, 0), t),
        )
        top_terms = [
            k
            for k, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
            if (len(k) >= 2 if has_cjk(k) else len(k) > 3)
        ]
        combined = list(dict.fromkeys(matched_known[:4] + top_terms[:4]))
        return combined[:6] or ["knowledge-base"]

    def _weave_wikilinks(self, text: str, all_pages: dict[str, WikiPage], exclude_slug: str = "") -> str:
        result = text
        for slug, page in sorted(all_pages.items(), key=lambda kv: len(kv[1].title), reverse=True):
            if slug == exclude_slug:
                continue
            for term in [page.title, *page.aliases]:
                is_cjk = has_cjk(term)
                if len(term) < (2 if is_cjk else 4):
                    continue
                # Avoid replacing inside existing [[...]] or markdown headings
                if is_cjk:
                    pattern = re.compile(rf"(?<!\[)(?<!\|)({re.escape(term)})(?!\]|\|)", re.IGNORECASE)
                else:
                    pattern = re.compile(rf"(?<!\[)\b({re.escape(term)})\b(?!\]|\|)", re.IGNORECASE)
                if pattern.search(result):
                    result = pattern.sub(rf"[[{slug}|\1]]", result, count=1)
                    break
        return result

    def _local_extract_candidates(
        self, title: str, content: str, existing_pages: dict[str, WikiPage]
    ) -> list[dict[str, Any]]:
        clean_title = title.strip() or "Untitled Note"
        body_clean = content.strip()
        if not body_clean.startswith("#"):
            body_with_h1 = f"# {clean_title}\n\n{body_clean}"
        else:
            body_with_h1 = body_clean

        category = self._infer_category(clean_title, body_clean)
        tags = self._extract_tags(clean_title, body_clean, existing_pages)
        first_para = ""
        for para in body_clean.split("\n\n"):
            p = para.strip()
            if p and not p.startswith("#"):
                first_para = p.replace("\n", " ")
                break
        summary = (first_para[:177] + "...") if len(first_para) > 180 else (first_para or f"Knowledge note on {clean_title}.")

        woven_body = self._weave_wikilinks(body_with_h1, existing_pages, exclude_slug=slugify(clean_title))
        return [
            {
                "title": clean_title,
                "category": category,
                "aliases": [],
                "tags": tags,
                "summary": summary,
                "body": woven_body,
            }
        ]

    @staticmethod
    def _strip_wikilink_markup(text: str) -> str:
        """Convert [[slug|label]] -> label and [[slug]] -> slug for accurate text comparison."""
        s = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", text)
        s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
        return s

    @staticmethod
    def _split_technical_sentences(text: str) -> list[str]:
        """Split technical prose (English & Japanese/CJK) into clauses/sentences without breaking e.g./i.e./etc."""
        chunks: list[str] = []
        sent_re = re.compile(
            r"(?:(?<=[.!?])(?<!e\.g\.)(?<!i\.e\.)(?<!etc\.)(?<!fig\.)(?<!Fig\.)(?<!Dr\.)(?<!vs\.)\s+)|(?:(?<=[。！？])\s*)"
        )
        for line in text.splitlines():
            ln = line.strip()
            if not ln:
                continue
            for part in sent_re.split(ln):
                p = part.strip()
                if p:
                    chunks.append(p)
        return chunks

    @classmethod
    def _extract_comparable_segments(cls, markdown_body: str) -> tuple[str, list[set[str]]]:
        """Extract normalized lowercase body text plus per-paragraph and per-sentence token sets."""
        stripped = cls._strip_wikilink_markup(markdown_body)
        segments: list[set[str]] = []
        norm_lines: list[str] = []

        for raw_block in re.split(r"\n{2,}", stripped):
            block = raw_block.strip()
            if not block or re.match(r"^#{1,6}\s+", block) or block.startswith("|") or block == "---":
                continue
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            sub_items = lines if (len(lines) > 1 or any(ln.startswith("- ") for ln in lines)) else [" ".join(lines)]
            for item in sub_items:
                # Strip bullet prefixes and synthesized-update metadata headers
                clean = re.sub(
                    r"^[-*]\s+(?:\*\*\[[^\]]+\]\*\*\s*(?:\([^)]+\))?:\s*)?",
                    "",
                    item,
                ).strip()
                if not clean or clean.lower().startswith("related trail:"):
                    continue
                norm_lines.append(" ".join(clean.lower().split()))
                p_toks = set(tokenize(clean))
                if p_toks:
                    segments.append(p_toks)
                # Also index individual sentences/clauses so reordered/combined digests are caught
                for sent in cls._split_technical_sentences(clean):
                    s_toks = set(tokenize(sent))
                    if len(s_toks) >= 4:
                        segments.append(s_toks)

        return "\n".join(norm_lines), segments

    @classmethod
    def _is_redundant_unit(
        cls,
        text: str,
        existing_norm_body: str,
        existing_segments: list[set[str]],
        existing_numbers: set[str],
        existing_bigrams: set[str] | None = None,
    ) -> bool:
        clean = " ".join(cls._strip_wikilink_markup(text).lower().split())
        if not clean:
            return True
        min_sub_len = 8 if has_cjk(clean) else 20
        if len(clean) >= min_sub_len and clean in existing_norm_body:
            unit_nums = _extract_numbers(clean)
            if not (unit_nums - existing_numbers):
                return True

        unit_tok_list = tokenize(clean)
        unit_toks = set(unit_tok_list)
        if not unit_toks:
            return True

        # Preserve factual revisions or contradicting claims that introduce novel numbers/markers
        unit_nums = _extract_numbers(clean)
        if unit_nums - existing_numbers:
            return False

        max_overlap = max(
            (len(unit_toks & seg) / len(unit_toks) for seg in existing_segments if seg),
            default=0.0,
        )
        if max_overlap >= 0.78:
            return True

        if existing_bigrams and len(unit_toks) >= 5:
            unit_bigrams = set(word_ngrams(unit_tok_list, 2))
            if len(unit_bigrams) >= 4:
                bigram_containment = len(unit_bigrams & existing_bigrams) / len(unit_bigrams)
                if bigram_containment >= 0.75:
                    return True

        return False

    def _local_synthesize_page_update(
        self,
        *,
        existing_page: WikiPage,
        new_title: str,
        new_content: str,
        source_name: str,
        new_tags: list[str],
        all_pages: dict[str, WikiPage],
    ) -> dict[str, Any]:
        date_str = utc_now_iso()[:10]
        existing_stripped = self._strip_wikilink_markup(existing_page.body)
        existing_norm_body, existing_segments = self._extract_comparable_segments(existing_page.body)
        title_toks = set(tokenize(existing_page.title))
        if title_toks:
            existing_segments.append(title_toks)
        existing_numbers = _extract_numbers(existing_stripped) | _extract_numbers(existing_page.title)
        existing_bigrams = set(word_ngrams(tokenize(existing_norm_body), 2))

        # Split incoming content into candidate paragraphs / list bullets while skipping headings
        raw_paragraphs: list[str] = []
        for raw_p in re.split(r"\n{2,}", new_content.strip()):
            p = raw_p.strip()
            if not p or re.match(r"^#{1,6}\s+", p) or p.startswith("|"):
                continue
            lines = [ln.strip() for ln in p.splitlines() if ln.strip()]
            if len(lines) > 1 and all(ln.startswith("- ") for ln in lines):
                for ln in lines:
                    cleaned_ln = re.sub(
                        r"^[-*]\s+(?:\*\*\[[^\]]+\]\*\*\s*(?:\([^)]+\))?:\s*)?",
                        "",
                        ln,
                    ).strip()
                    if cleaned_ln and not cleaned_ln.lower().startswith("related trail:"):
                        raw_paragraphs.append(cleaned_ln)
            else:
                raw_paragraphs.append(p)

        novel_blocks: list[str] = []
        contradictions: list[str] = []
        redundant_blocks_skipped = 0

        for block in raw_paragraphs:
            if self._is_redundant_unit(
                block, existing_norm_body, existing_segments, existing_numbers, existing_bigrams
            ):
                redundant_blocks_skipped += 1
                continue

            # Filter out redundant sentences inside mixed paragraphs that combine old + new text
            sentences = self._split_technical_sentences(block)
            if len(sentences) >= 2:
                kept_sentences = [
                    s
                    for s in sentences
                    if not self._is_redundant_unit(
                        s, existing_norm_body, existing_segments, existing_numbers, existing_bigrams
                    )
                ]
                if not kept_sentences:
                    redundant_blocks_skipped += 1
                    continue
                if len(kept_sentences) < len(sentences):
                    redundant_blocks_skipped += 1
                candidate_text = " ".join(kept_sentences)
            else:
                candidate_text = block

            woven_block = self._weave_wikilinks(candidate_text, all_pages, exclude_slug=existing_page.slug)
            novel_blocks.append(woven_block)

            # Track newly accepted segments so duplicates within the same ingest payload are also skipped
            cand_norm = " ".join(self._strip_wikilink_markup(candidate_text).lower().split())
            existing_norm_body = f"{existing_norm_body}\n{cand_norm}".strip()
            cand_tok_list = tokenize(cand_norm)
            cand_toks = set(cand_tok_list)
            if cand_toks:
                existing_segments.append(cand_toks)
            existing_bigrams.update(word_ngrams(cand_tok_list, 2))
            for s in self._split_technical_sentences(cand_norm):
                s_toks = set(tokenize(s))
                if len(s_toks) >= 4:
                    existing_segments.append(s_toks)
            existing_numbers.update(_extract_numbers(cand_norm))

            lower_b = candidate_text.lower()
            if any(marker in lower_b for marker in CONTRADICTION_MARKERS):
                contradictions.append(
                    f"- **[{date_str} | {source_name}]** Potential tension/nuance noted: {woven_block}"
                )

        body = existing_page.body.strip()
        if novel_blocks:
            update_section_header = "## Evolution & Synthesized Updates"
            formatted_updates = "\n\n".join(
                f"- **[{date_str} | {source_name}]** ({new_title}): {blk}"
                for blk in novel_blocks[:6]
            )
            if update_section_header in body:
                body = f"{body}\n\n{formatted_updates}"
            else:
                body = f"{body}\n\n{update_section_header}\n\n{formatted_updates}"

            if contradictions:
                tension_header = "## Contradictions & Tensions"
                tension_text = "\n\n".join(contradictions[:3])
                if tension_header in body:
                    body = f"{body}\n\n{tension_text}"
                else:
                    body = f"{body}\n\n{tension_header}\n\n{tension_text}"

            change_note = (
                f"Merged {len(novel_blocks)} new insight(s) from '{new_title}' ({source_name}) "
                f"into existing page [[{existing_page.slug}]]"
                + (f" (skipped {redundant_blocks_skipped} redundant block(s))." if redundant_blocks_skipped else ".")
            )
        else:
            change_note = (
                f"Deduplicated {redundant_blocks_skipped} redundant block(s) from '{new_title}' "
                f"({source_name}); existing synthesis in [[{existing_page.slug}]] already covers it."
            )

        summary = existing_page.summary
        if not summary:
            summary = f"Compiled knowledge page covering {existing_page.title}."

        return {
            "updated_body": body,
            "summary": summary,
            "change_note": change_note,
            "contradictions_found": contradictions,
            "novel_added": len(novel_blocks),
            "redundant_skipped": redundant_blocks_skipped,
        }

    @staticmethod
    def _extract_passages(page: WikiPage) -> list[str]:
        """Split a wiki page into granular passages (paragraphs and individual update/tension bullets)."""
        passages: list[str] = []
        for raw_block in re.split(r"\n{2,}", page.body):
            block = raw_block.strip()
            if not block or block.startswith("#") or block.startswith("|"):
                continue
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if len(lines) > 1 and all(ln.startswith("- ") for ln in lines):
                passages.extend(ln for ln in lines)
            else:
                passages.append(" ".join(lines))
        return passages

    @staticmethod
    def _score_text_for_question(
        text: str,
        q_lower: str,
        q_tok_set: set[str],
        q_bigrams: set[str],
        token_idf: dict[str, float],
        q_acronyms: set[str] | None = None,
    ) -> float:
        toks = tokenize(text)
        if not toks:
            return 0.0
        t_set = set(toks)
        overlap = q_tok_set & t_set
        q_prefixes = {t[:5] for t in q_tok_set if len(t) >= 5}
        t_prefixes = {t[:5] for t in t_set if len(t) >= 5}
        stem_overlap = len((q_prefixes & t_prefixes) - {t[:5] for t in overlap if len(t) >= 5})
        if not overlap and stem_overlap == 0:
            return 0.0

        idf_score = sum(token_idf.get(t, 1.0) for t in overlap) / max(len(q_tok_set), 1)
        bigram_overlap = len(q_bigrams & set(word_ngrams(toks, 2)))
        stem_bonus = (stem_overlap / max(len(q_tok_set), 1)) * 0.9

        acronym_bonus = 0.0
        if q_acronyms:
            text_acronyms = set(re.findall(r"\b[A-Z0-9][A-Z0-9_-]{1,}\b", text))
            shared_acronyms = len(q_acronyms & text_acronyms)
            acronym_bonus = min(shared_acronyms * 0.35, 1.05)

        cue_boost = 0.0
        if any(
            w in q_lower
            for w in (
                "when",
                "what year",
                "how many",
                "how much",
                "how long",
                "what percentage",
                "what number",
                "いつ",
                "何年",
                "何月",
                "何日",
                "何人",
                "いくつ",
                "何メートル",
                "何パーセント",
                "どのくらい",
                "何歳",
                "何回",
            )
        ):
            if _extract_numbers(text):
                cue_boost += 0.35
        if any(w in q_lower for w in ("who", "which player", "which person", "whose", "assistant", "punter", "professor")):
            # Sentences containing multi-word capitalized names
            if re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text):
                cue_boost += 0.25
        if any(w in q_lower for w in ("where", "what city", "what country", "what stadium")):
            if re.search(r"\b(?:in|at|near|from)\s+[A-Z][a-z]+", text):
                cue_boost += 0.2

        return idf_score * 2.0 + bigram_overlap * 1.1 + stem_bonus + acronym_bonus + cue_boost

    def _local_answer_query(
        self,
        *,
        question: str,
        retrieved_pages: list[tuple[WikiPage, float]],
    ) -> str:
        if not retrieved_pages:
            return (
                "No closely matching pages were found in the compiled wiki yet. "
                "Try ingesting a source on this topic or broadening your question."
            )

        import math

        top_page, _ = retrieved_pages[0]
        citations = ", ".join(f"[[{p.slug}|{p.title}]]" for p, _ in retrieved_pages[:4])

        q_lower = question.lower()
        q_toks = tokenize(question)
        q_tok_set = set(q_toks)
        q_bigrams = set(word_ngrams(q_toks, 2))
        q_acronyms = set(re.findall(r"\b[A-Z0-9][A-Z0-9_-]{1,}\b", question))

        # Collect all passages across top retrieved pages and compute local IDF
        page_passages: list[tuple[WikiPage, float, list[str]]] = []
        all_passages: list[str] = []
        for page, score in retrieved_pages[:4]:
            ps = self._extract_passages(page)
            page_passages.append((page, score, ps))
            all_passages.extend(ps)

        df: dict[str, int] = {}
        for ps_text in all_passages:
            for t in set(tokenize(ps_text)):
                df[t] = df.get(t, 0) + 1
        n_passages = max(len(all_passages), 1)
        token_idf = {
            t: math.log((n_passages + 1.0) / (freq + 1.0)) + 1.0
            for t, freq in df.items()
        }

        # Rank passages and sentences across top retrieved pages
        ranked_sentences: list[tuple[float, WikiPage, str]] = []
        highlights: list[str] = []

        for p_idx, (page, page_score, ps) in enumerate(page_passages):
            scored_passages: list[tuple[float, str]] = []
            for para in ps:
                sc = self._score_text_for_question(para, q_lower, q_tok_set, q_bigrams, token_idf, q_acronyms)
                combined = sc + page_score * 0.4
                scored_passages.append((combined, para))

                # Also score individual technical sentences/clauses for pinpoint Direct Answer extraction
                for sent in self._split_technical_sentences(para):
                    if len(sent) < (5 if has_cjk(sent) else 12):
                        continue
                    s_sc = self._score_text_for_question(sent, q_lower, q_tok_set, q_bigrams, token_idf, q_acronyms)
                    ranked_sentences.append((s_sc + page_score * 0.65, page, sent))

            scored_passages.sort(key=lambda item: item[0], reverse=True)
            if scored_passages:
                highlights.append(
                    f"- **[[{page.slug}|{page.title}]]** *(relevance {int(page_score * 100)}%)*: {scored_passages[0][1]}"
                )
                if p_idx == 0 and len(scored_passages) > 1 and (scored_passages[1][0] - page_score * 0.4) > 0.35:
                    highlights.append(
                        f"- **[[{page.slug}|{page.title}]]** *(secondary section)*: {scored_passages[1][1]}"
                    )

        ranked_sentences.sort(key=lambda x: x[0], reverse=True)
        direct_answer_lines: list[str] = []
        seen_sents: set[str] = set()
        for _, s_page, sent_text in ranked_sentences[:5]:
            if sent_text not in seen_sents:
                seen_sents.add(sent_text)
                direct_answer_lines.append(f"{sent_text} *(source: [[{s_page.slug}|{s_page.title}]])*")
            if len(direct_answer_lines) >= 3:
                break

        sections: list[str] = [
            f"Based on the compiled wiki ({citations}), here is the synthesized answer to **{question}**:",
            "",
            f"### Direct Answer ([[{top_page.slug}|{top_page.title}]])",
            " ".join(direct_answer_lines) if direct_answer_lines else top_page.summary,
        ]

        if highlights:
            sections.extend(["", "### Key Evidence Across Wiki Pages", *highlights])

        # Surface any contradictions documented in cited pages
        tensions: list[str] = []
        for page, _ in retrieved_pages[:3]:
            if "## Contradictions & Tensions" in page.body:
                part = page.body.split("## Contradictions & Tensions", 1)[1].strip().splitlines()
                for line in part:
                    if line.strip().startswith("-"):
                        tensions.append(f"{line.strip()} *(from [[{page.slug}|{page.title}]])*")
                        if len(tensions) >= 4:
                            break
        if tensions:
            sections.extend(["", "### Documented Tensions & Nuances", *tensions])

        # Connected exploration trails
        related_slugs: list[str] = []
        cited_set = {p.slug for p, _ in retrieved_pages}
        for page, _ in retrieved_pages[:3]:
            for link in page.outbound_links + page.backlinks:
                if link not in cited_set and link not in related_slugs:
                    related_slugs.append(link)
        if related_slugs:
            trails = ", ".join(f"[[{s}]]" for s in related_slugs[:4])
            sections.extend(["", f"**Further associative trails**: {trails}"])

        return "\n".join(sections)

