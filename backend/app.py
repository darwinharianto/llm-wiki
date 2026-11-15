from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.config import BASE_DIR, DEFAULT_VAULT_DIR, RuntimeSettings
from backend.linter import WikiLinter
from backend.similarity import HybridSimilarityEngine
from backend.vault_manager import VALID_CATEGORIES, VaultManager
from backend.wiki_engine import WikiEngine

FRONTEND_DIR = BASE_DIR / "frontend"


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=50)


class IngestPreviewRequest(BaseModel):
    title: str
    content: str
    threshold: float | None = Field(default=None, ge=0.05, le=0.95)


class IngestExecuteRequest(BaseModel):
    title: str
    content: str
    source_name: str | None = None
    force_target_slug: str | None = None
    force_create: bool = False
    threshold: float | None = Field(default=None, ge=0.05, le=0.95)
    archive_raw: bool = True


class PageUpdateRequest(BaseModel):
    title: str
    category: str = "concepts"
    body: str
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence: str = "high"


class MergeRequest(BaseModel):
    source_slug: str
    target_slug: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = Field(default_factory=list)


class FileToWikiRequest(BaseModel):
    title: str
    answer_markdown: str
    question: str = ""
    threshold: float | None = Field(default=None, ge=0.05, le=0.95)


class SettingsUpdateRequest(BaseModel):
    provider: Literal["local_smart", "gemini", "openai", "ollama"] | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None
    openai_custom_headers: dict[str, str] | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    similarity_threshold: float | None = Field(default=None, ge=0.1, le=0.95)
    near_duplicate_threshold: float | None = Field(default=None, ge=0.2, le=0.95)
    auto_maintain_after_ingest: bool | None = None
    periodic_maintain_seconds: int | None = Field(default=None, ge=0)


class LintHealRequest(BaseModel):
    create_stubs_for_dangling: bool = True
    merge_near_duplicates: bool = True


def create_app(
    vault_dir: Path | None = None,
    initial_settings: RuntimeSettings | None = None,
) -> FastAPI:
    settings = initial_settings or RuntimeSettings.from_env()
    vault = VaultManager(vault_dir or DEFAULT_VAULT_DIR)
    engine = WikiEngine(vault, settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop_event = asyncio.Event()

        async def periodic_maintainer() -> None:
            while not stop_event.is_set():
                interval = engine.settings.periodic_maintain_seconds
                wait_for = interval if interval > 0 else 60
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=wait_for)
                    break
                except asyncio.TimeoutError:
                    if engine.settings.periodic_maintain_seconds > 0:
                        try:
                            linter = WikiLinter(
                                vault,
                                near_duplicate_threshold=engine.settings.near_duplicate_threshold,
                            )
                            audit = linter.audit()
                            # Only auto-heal silently when drift or unlinked mentions appear
                            if (
                                audit["summary"]["unlinked_mentions"] > 0
                                or audit["summary"]["missing_from_index"] > 0
                            ):
                                linter.auto_maintain(create_stubs_for_dangling=False)
                        except Exception:
                            pass

        bg_task = asyncio.create_task(periodic_maintainer())
        try:
            yield
        finally:
            stop_event.set()
            bg_task.cancel()
            try:
                await bg_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="LLM Wiki — Self-Maintaining Knowledge Base", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Expose state for tests
    app.state.vault = vault
    app.state.engine = engine

    @app.get("/api/overview")
    def get_overview() -> dict[str, Any]:
        pages = vault.load_all_pages()
        by_cat = {c: 0 for c in VALID_CATEGORIES}
        for p in pages.values():
            by_cat[p.category] = by_cat.get(p.category, 0) + 1
        linter = WikiLinter(vault, near_duplicate_threshold=engine.settings.near_duplicate_threshold)
        audit = linter.audit()
        return {
            "total_pages": len(pages),
            "total_raw_sources": len(vault.list_raw_sources()),
            "categories": by_cat,
            "health_score": audit["health_score"],
            "lint_summary": audit["summary"],
            "recent_log": vault.read_log_entries(limit=12),
            "recent_history": vault.get_recent_history(limit=12),
            "provider_mode": engine.llm.active_mode(),
            "model_name": engine.llm.active_model_name(),
            "similarity_threshold": engine.settings.similarity_threshold,
            "telemetry": engine.telemetry.summary(limit_recent=25),
        }

    @app.get("/api/pages")
    def list_pages() -> dict[str, Any]:
        pages = vault.load_all_pages()
        items = [p.to_summary_dict() for p in pages.values()]
        items.sort(key=lambda x: (x["category"], x["title"].lower()))
        return {"pages": items}

    @app.get("/api/pages/{slug}")
    def get_page(slug: str) -> dict[str, Any]:
        pages = vault.load_all_pages()
        page = vault.get_page(slug)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page '{slug}' not found")
        sim_engine = HybridSimilarityEngine(pages)
        similar = [
            m.to_dict()
            for m in sim_engine.search(
                f"{page.title} {page.summary} {' '.join(page.tags)}",
                top_k=5,
                query_tags=page.tags,
                query_links=page.outbound_links,
                exclude_slug=page.slug,
            )
        ]
        return {
            "page": page.to_detail_dict(),
            "similar_pages": similar,
            "history": vault.get_page_history(page.slug),
        }

    @app.put("/api/pages/{slug}")
    def update_page(slug: str, req: PageUpdateRequest) -> dict[str, Any]:
        existing = vault.get_page(slug)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Page '{slug}' not found")
        saved, diff_text = vault.save_page(
            slug=existing.slug,
            title=req.title,
            category=req.category,
            body=req.body,
            aliases=req.aliases,
            tags=req.tags,
            summary=req.summary,
            confidence=req.confidence,
            operation="manual-edit",
            change_note="Edited directly in Wiki Reader/Editor",
        )
        vault.append_log("update", saved.title, [f"Manual edit to `[[{saved.slug}]]`"])
        return {"page": saved.to_detail_dict(), "diff": diff_text}

    @app.post("/api/search")
    def search_wiki(req: SearchRequest) -> dict[str, Any]:
        return {"results": engine.search(req.query, top_k=req.top_k)}

    @app.post("/api/ingest/preview")
    def preview_ingest(req: IngestPreviewRequest) -> dict[str, Any]:
        if not req.content.strip():
            raise HTTPException(status_code=400, detail="Content cannot be empty")
        return engine.preview_ingest(
            title=req.title or "Untitled Note",
            content=req.content,
            threshold=req.threshold,
        )

    @app.post("/api/ingest/execute")
    def execute_ingest(req: IngestExecuteRequest) -> dict[str, Any]:
        if not req.content.strip():
            raise HTTPException(status_code=400, detail="Content cannot be empty")
        return engine.execute_ingest(
            title=req.title or "Untitled Note",
            content=req.content,
            source_name=req.source_name,
            force_target_slug=req.force_target_slug,
            force_create=req.force_create,
            threshold=req.threshold,
            archive_raw=req.archive_raw,
        )

    @app.post("/api/merge")
    def merge_pages(req: MergeRequest) -> dict[str, Any]:
        try:
            return engine.merge_pages(req.source_slug, req.target_slug)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/graph")
    def get_graph(include_semantic: bool = Query(default=True)) -> dict[str, Any]:
        return engine.build_graph(include_semantic_edges=include_semantic)

    @app.post("/api/chat")
    def chat_wiki(req: ChatRequest) -> dict[str, Any]:
        if not req.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        return engine.chat(
            question=req.question,
            history=[m.model_dump() for m in req.history],
        )

    @app.post("/api/chat/file-to-wiki")
    def file_to_wiki(req: FileToWikiRequest) -> dict[str, Any]:
        if not req.answer_markdown.strip():
            raise HTTPException(status_code=400, detail="Answer markdown cannot be empty")
        return engine.file_answer_to_wiki(
            title=req.title or "Synthesized Exploration",
            answer_markdown=req.answer_markdown,
            question=req.question,
            threshold=req.threshold,
        )

    @app.get("/api/lint")
    def run_lint_audit() -> dict[str, Any]:
        linter = WikiLinter(vault, near_duplicate_threshold=engine.settings.near_duplicate_threshold)
        return linter.audit()

    @app.post("/api/lint/heal")
    def run_lint_heal(req: LintHealRequest | None = None) -> dict[str, Any]:
        linter = WikiLinter(vault, near_duplicate_threshold=engine.settings.near_duplicate_threshold)
        create_stubs = req.create_stubs_for_dangling if req else True
        merge_dupes = req.merge_near_duplicates if req else True
        return linter.auto_maintain(
            create_stubs_for_dangling=create_stubs,
            merge_near_duplicates=merge_dupes,
        )

    @app.get("/api/raw")
    def get_raw_sources() -> dict[str, Any]:
        return {"raw_sources": vault.list_raw_sources()}

    @app.get("/api/index-log")
    def get_index_and_log() -> dict[str, Any]:
        return {
            "schema_md": vault.schema_path.read_text(encoding="utf-8") if vault.schema_path.exists() else "",
            "index_md": vault.index_path.read_text(encoding="utf-8") if vault.index_path.exists() else "",
            "log_md": vault.log_path.read_text(encoding="utf-8") if vault.log_path.exists() else "",
            "log_entries": vault.read_log_entries(limit=40),
            "history_events": vault.get_recent_history(limit=30),
        }

    def _masked_settings() -> dict[str, Any]:
        data = engine.settings.model_dump()
        data["active_mode"] = engine.llm.active_mode()
        data["active_model"] = engine.llm.active_model_name()
        data["has_gemini_key"] = bool(engine.settings.gemini_api_key)
        data["has_openai_key"] = bool(engine.settings.openai_api_key)
        data["has_openai_custom_headers"] = bool(engine.settings.openai_custom_headers)
        data["gemini_api_key"] = "••••" + engine.settings.gemini_api_key[-4:] if engine.settings.gemini_api_key else ""
        data["openai_api_key"] = "••••" + engine.settings.openai_api_key[-4:] if engine.settings.openai_api_key else ""
        data["llm_stats"] = dict(engine.llm.stats)
        data["telemetry_totals"] = engine.telemetry.summary(limit_recent=5)["totals"]
        return data

    @app.get("/api/telemetry")
    def get_telemetry(limit: int = Query(default=80, ge=1, le=500)) -> dict[str, Any]:
        summary = engine.telemetry.summary(limit_recent=limit)
        summary["active_provider"] = engine.llm.active_mode()
        summary["active_model"] = engine.llm.active_model_name()
        return summary

    @app.post("/api/telemetry/reset")
    def reset_telemetry() -> dict[str, Any]:
        engine.telemetry.reset()
        summary = engine.telemetry.summary(limit_recent=20)
        summary["active_provider"] = engine.llm.active_mode()
        summary["active_model"] = engine.llm.active_model_name()
        return summary

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return _masked_settings()

    @app.post("/api/settings")
    def update_settings(req: SettingsUpdateRequest) -> dict[str, Any]:
        current = engine.settings.model_dump()
        updates = req.model_dump(exclude_none=True)
        # Preserve existing secret keys if user submitted masked placeholder or empty string
        for secret_field in ("gemini_api_key", "openai_api_key"):
            if secret_field in updates and updates[secret_field].startswith("••••"):
                updates.pop(secret_field)
        current.update(updates)
        new_cfg = RuntimeSettings(**current)
        engine.update_settings(new_cfg)
        return _masked_settings()

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

        @app.get("/")
        def serve_index() -> FileResponse:
            return FileResponse(str(FRONTEND_DIR / "index.html"))

        @app.get("/guide")
        def serve_architecture_guide() -> FileResponse:
            return FileResponse(str(FRONTEND_DIR.parent / "architecture_guide.html"))

    return app


app = create_app()

