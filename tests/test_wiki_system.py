from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import RuntimeSettings
from backend.linter import WikiLinter
from backend.similarity import HybridSimilarityEngine
from backend.vault_manager import VaultManager

SEED_VAULT = Path(__file__).resolve().parent / "fixtures" / "seed_vault"


def _make_isolated_client(tmp_path: Path) -> tuple[TestClient, Path]:
    vault_copy = tmp_path / "vault"
    shutil.copytree(SEED_VAULT, vault_copy)
    settings = RuntimeSettings(
        provider="local_smart",
        similarity_threshold=0.35,
        auto_maintain_after_ingest=True,
        periodic_maintain_seconds=0,
    )
    app = create_app(vault_dir=vault_copy, initial_settings=settings)
    return TestClient(app), vault_copy


def test_vault_initialization_and_seed_structure(tmp_path: Path) -> None:
    client, vault_dir = _make_isolated_client(tmp_path)
    assert (vault_dir / "SCHEMA.md").exists()
    assert (vault_dir / "index.md").exists()
    assert (vault_dir / "log.md").exists()
    assert (vault_dir / "raw").is_dir()
    assert (vault_dir / "wiki").is_dir()

    with client:
        resp = client.get("/api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_pages"] == 9
        assert data["total_raw_sources"] == 3


def test_hybrid_similarity_recommends_update_for_existing_topic(tmp_path: Path) -> None:
    _, vault_dir = _make_isolated_client(tmp_path)
    vm = VaultManager(vault_dir)
    pages = vm.load_all_pages()
    sim_engine = HybridSimilarityEngine(pages)

    res = sim_engine.find_similar_for_candidate(
        title="Karpathy LLM Wiki Pattern & Persistent Synthesis",
        content="Andrej Karpathy proposed compiling raw documents into a persistent interlinked markdown wiki instead of stateless RAG.",
        tags=["llm-wiki", "architecture"],
        threshold=0.35,
    )
    assert res["action"] == "update"
    assert res["target_slug"] == "llm-wiki-pattern"
    assert res["best_score"] >= 0.35


def test_ingest_updates_existing_page_instead_of_creating_duplicate(tmp_path: Path) -> None:
    client, vault_dir = _make_isolated_client(tmp_path)
    with client:
        before_pages = client.get("/api/pages").json()["pages"]
        before_count = len(before_pages)
        target_before = client.get("/api/pages/llm-wiki-pattern").json()["page"]

        preview = client.post(
            "/api/ingest/preview",
            json={
                "title": "LLM Wiki Pattern: Contradiction Auditing",
                "content": (
                    "When maintaining the LLM Wiki Pattern over many months, "
                    "explicitly flagging contradictions prevents silent knowledge drift. "
                    "However, keeping diffs in .history ensures full auditability."
                ),
            },
        ).json()
        assert preview["items"][0]["decision"] == "update"
        assert preview["items"][0]["target_slug"] == "llm-wiki-pattern"

        exec_res = client.post(
            "/api/ingest/execute",
            json={
                "title": "LLM Wiki Pattern: Contradiction Auditing",
                "content": (
                    "When maintaining the LLM Wiki Pattern over many months, "
                    "explicitly flagging contradictions prevents silent knowledge drift. "
                    "However, keeping diffs in .history ensures full auditability."
                ),
            },
        ).json()

        assert exec_res["updated_slugs"] == ["llm-wiki-pattern"]
        assert exec_res["created_slugs"] == []

        after_pages = client.get("/api/pages").json()["pages"]
        assert len(after_pages) == before_count

        target_after = client.get("/api/pages/llm-wiki-pattern").json()
        assert target_after["page"]["revision_count"] == target_before["revision_count"] + 1
        assert len(target_after["page"]["sources"]) > len(target_before["sources"])
        assert "Evolution & Synthesized Updates" in target_after["page"]["body"]
        assert "Contradictions & Tensions" in target_after["page"]["body"]
        assert len(target_after["history"]) >= 1
        assert "update |" in (vault_dir / "log.md").read_text(encoding="utf-8")


def test_ingest_creates_new_page_for_novel_topic(tmp_path: Path) -> None:
    client, _ = _make_isolated_client(tmp_path)
    with client:
        before_count = len(client.get("/api/pages").json()["pages"])
        res = client.post(
            "/api/ingest/execute",
            json={
                "title": "Spaced Repetition Flashcard Scheduling",
                "content": (
                    "Spaced repetition algorithms such as FSRS optimize long-term memory retention "
                    "by scheduling review intervals right before predicted forgetting."
                ),
            },
        ).json()
        assert len(res["created_slugs"]) == 1
        after_count = len(client.get("/api/pages").json()["pages"])
        assert after_count == before_count + 1


def test_self_maintaining_linter_heals_unlinked_dangling_and_orphans(tmp_path: Path) -> None:
    client, vault_dir = _make_isolated_client(tmp_path)
    vm = VaultManager(vault_dir)

    # Create an orphan page with a dangling wikilink and unlinked mention, plus a pure orphan page
    vm.save_page(
        slug="isolated-quantum-note",
        title="Isolated Quantum Note",
        category="concepts",
        body=(
            "# Isolated Quantum Note\n\n"
            "This note discusses [[nonexistent-entanglement-bridge]] and mentions "
            "Vannevar Bush Memex without linking it."
        ),
        tags=["knowledge-base"],
    )
    vm.save_page(
        slug="pure-orphan-topic",
        title="Pure Orphan Topic",
        category="concepts",
        body="# Pure Orphan Topic\n\nNotes on compiled wiki synthesis and associative trails.",
        tags=["knowledge-base", "architecture"],
    )

    linter = WikiLinter(vm)
    before_audit = linter.audit()
    assert before_audit["summary"]["unlinked_mentions"] >= 1
    assert before_audit["summary"]["orphan_pages"] >= 2
    assert before_audit["summary"]["dangling_links"] >= 1

    with client:
        heal_res = client.post("/api/lint/heal", json={"create_stubs_for_dangling": True}).json()
        assert len(heal_res["actions_taken"]) >= 3
        after_audit = heal_res["audit"]
        assert after_audit["summary"]["unlinked_mentions"] == 0
        assert after_audit["summary"]["orphan_pages"] == 0
        assert after_audit["summary"]["dangling_links"] == 0
        assert after_audit["health_score"] > before_audit["health_score"]


def test_graph_chat_and_file_to_wiki_endpoints(tmp_path: Path) -> None:
    client, _ = _make_isolated_client(tmp_path)
    with client:
        graph = client.get("/api/graph").json()
        assert len(graph["nodes"]) == 9
        assert graph["stats"]["wikilink_edges"] >= 10

        chat_res = client.post(
            "/api/chat",
            json={"question": "Compare stateless RAG vs compiled LLM Wiki"},
        ).json()
        assert "[[rag-vs-compiled-wiki" in chat_res["answer"] or "RAG" in chat_res["answer"]
        assert len(chat_res["cited_pages"]) >= 1

        filed = client.post(
            "/api/chat/file-to-wiki",
            json={
                "title": "RAG vs Compiled Wiki Synthesis",
                "answer_markdown": chat_res["answer"],
                "question": "Compare stateless RAG vs compiled LLM Wiki",
            },
        ).json()
        assert "rag-vs-compiled-wiki" in filed["updated_slugs"]


def test_explicit_page_merge_redirects_links(tmp_path: Path) -> None:
    client, vault_dir = _make_isolated_client(tmp_path)
    vm = VaultManager(vault_dir)
    vm.save_page(
        slug="memex-notes",
        title="Memex Notes",
        category="entities",
        body="# Memex Notes\n\nExtra archival note on associative trails.",
    )
    vm.save_page(
        slug="trail-referrer",
        title="Trail Referrer",
        category="concepts",
        body="# Trail Referrer\n\nSee [[memex-notes|Memex Notes]] for context.",
    )

    with client:
        merge_res = client.post(
            "/api/merge",
            json={"source_slug": "memex-notes", "target_slug": "vannevar-bush-memex"},
        )
        assert merge_res.status_code == 200
        payload = merge_res.json()
        assert payload["removed_slug"] == "memex-notes"
        assert "trail-referrer" in payload["redirected_pages"]
        ref_page = client.get("/api/pages/trail-referrer").json()["page"]
        assert "[[vannevar-bush-memex|" in ref_page["body"]
        assert client.get("/api/pages/memex-notes").status_code == 404


def test_japanese_ingestion_deduplication_and_qa(tmp_path: Path) -> None:
    client, _ = _make_isolated_client(tmp_path)
    with client:
        # 1. Ingest a new Japanese article on Tokyo Tower
        res1 = client.post(
            "/api/ingest/execute",
            json={
                "title": "東京タワー",
                "source_name": "ja-wiki-1",
                "content": (
                    "東京タワー（とうきょうタワー）は、東京都港区芝公園にある総合電波塔である。"
                    "1958年12月23日に完工し、高さは333メートルである。設計は内藤多仲が手掛けた。"
                ),
            },
        )
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["created_slugs"] == ["東京タワー"]

        # 2. Ingest a redundant + extended Japanese note on the same topic (different title)
        res2 = client.post(
            "/api/ingest/execute",
            json={
                "title": "東京タワーの構造と2026年改訂記録",
                "source_name": "ja-wiki-2",
                "content": (
                    "東京タワー（とうきょうタワー）は、東京都港区芝公園にある総合電波塔である。"
                    "1958年12月23日に完工し、高さは333メートルである。"
                    "しかし、2026年の特別改訂記録では、試験用の量子アンテナ「CHRONO-JA9」が頂部に追加され、"
                    "実効高が341.5メートルに更新された。"
                ),
            },
        )
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["updated_slugs"] == ["東京タワー"]
        assert d2["created_slugs"] == []

        page_data = client.get("/api/pages/東京タワー").json()["page"]
        assert "CHRONO-JA9" in page_data["body"]
        assert "341.5メートル" in page_data["body"]
        assert "## Contradictions & Tensions" in page_data["body"]

        # 3. Query in Japanese and verify retrieval + direct answer extraction
        chat_res = client.post(
            "/api/chat",
            json={"question": "東京タワーの2026年の特別改訂記録で追加された量子アンテナと実効高は何メートルですか？"},
        ).json()
        assert chat_res["cited_pages"][0]["slug"] == "東京タワー"
        assert "CHRONO-JA9" in chat_res["answer"]
        assert "341.5" in chat_res["answer"]


def test_telemetry_observability_tokens_cost_and_dedup_savings(tmp_path: Path) -> None:
    client, vault_dir = _make_isolated_client(tmp_path)
    with client:
        # 1. Ingest in local_smart mode -> llm_used=False, cost=0, estimated_tokens_saved > 0
        ingest_res = client.post(
            "/api/ingest/execute",
            json={
                "title": "LLM Wiki Pattern: Telemetry Test",
                "content": "Keeping a deterministic pre-filter prevents redundant LLM calls during wiki updates.",
            },
        ).json()
        tel = ingest_res["telemetry"]
        assert tel["llm_used"] is False
        assert tel["llm_calls"] == 0
        assert tel["local_operations"] >= 2
        assert tel["cost_usd"] == 0.0
        assert tel["estimated_tokens_saved"] > 0
        assert tel["estimated_cost_saved_usd"] > 0.0

        # 2. Chat in local_smart mode
        chat_res = client.post("/api/chat", json={"question": "How does LLM Wiki work?"}).json()
        assert chat_res["telemetry"]["llm_used"] is False
        assert chat_res["telemetry"]["local_operations"] >= 2

        # 3. Check /api/telemetry endpoint & persistent telemetry.jsonl
        t_summary = client.get("/api/telemetry").json()
        assert t_summary["totals"]["local_smart_executions"] >= 4
        assert t_summary["totals"]["llm_calls_total"] == 0
        assert t_summary["totals"]["total_cost_usd"] == 0.0
        assert t_summary["totals"]["estimated_tokens_saved"] > 0
        assert (vault_dir / "telemetry.jsonl").exists()

        # 4. Simulate a live Gemini provider call via _call_text_llm / synthesize_page_update
        engine = client.app.state.engine
        engine.update_settings(
            RuntimeSettings(
                provider="gemini",
                gemini_api_key="test-key",
                gemini_model="gemini-3.5-flash-lite",
            )
        )

        class _FakeUsage:
            total_input_tokens = 1200
            total_output_tokens = 300
            total_thought_tokens = 0
            total_cached_tokens = 0
            total_tokens = 1500

        class _FakeInteraction:
            output_text = '{"summary": "Updated synthesis.", "change_note": "Merged telemetry fact.", "contradictions_found": []}'
            usage = _FakeUsage()

        class _FakeInteractions:
            @staticmethod
            def create(**_kwargs):
                return _FakeInteraction()

        class _FakeClient:
            interactions = _FakeInteractions()

        engine.llm._gemini_client = _FakeClient()

        # 4a. Novel update -> triggers real LLM call with exact token & USD cost logging
        upd1 = client.post(
            "/api/ingest/execute",
            json={
                "title": "LLM Wiki Pattern: Telemetry Novel Fact 9981",
                "content": "A brand new benchmark recorded 9981 operations per second in 2026.",
            },
        ).json()
        assert upd1["telemetry"]["llm_used"] is True
        assert upd1["telemetry"]["llm_calls"] == 1
        assert upd1["telemetry"]["total_tokens"] == 1500
        assert upd1["telemetry"]["cost_usd"] > 0.0
        assert "gemini-3.5-flash-lite" in upd1["telemetry"]["models"]

        # 4b. Duplicate update -> pre-filter skips the LLM call completely
        upd2 = client.post(
            "/api/ingest/execute",
            json={
                "title": "LLM Wiki Pattern: Telemetry Novel Fact 9981",
                "content": "A brand new benchmark recorded 9981 operations per second in 2026.",
            },
        ).json()
        assert upd2["telemetry"]["llm_used"] is False
        assert upd2["telemetry"]["llm_calls"] == 0
        assert upd2["telemetry"]["estimated_tokens_saved"] > 0

        # 5. Reset telemetry
        reset_res = client.post("/api/telemetry/reset").json()
        assert reset_res["totals"]["total_events"] == 0



