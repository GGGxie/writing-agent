from datetime import datetime, timezone

import httpx

from writing_agent.collectors.config import RssCollectorConfig, RssFeed
from writing_agent.collectors.rsshub import collect_rss_once
from writing_agent.collectors.store import CollectorStore
from writing_agent.config import get_settings
from writing_agent.models import SignalRecord, SourceTier

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test</title><item>
<guid>post-1</guid><title>New model</title><link>https://example.com/post-1</link>
<pubDate>Tue, 08 Sep 2026 02:00:00 GMT</pubDate><description>Details</description>
</item></channel></rss>"""


def test_rss_collection_and_deduplication(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("COLLECTOR_DATABASE_PATH", str(tmp_path / "collector.sqlite3"))
    get_settings.cache_clear()
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=RSS))
    client = httpx.Client(transport=transport)
    store = CollectorStore()
    config = RssCollectorConfig(
        max_item_age_hours=None,
        feeds=[
            RssFeed(
                id="test",
                name="Test Feed",
                url="https://example.com/rss",
                source_tier=SourceTier.A,
            )
        ],
    )
    try:
        first = collect_rss_once(config, store, client)
        second = collect_rss_once(config, store, client)
        assert first["saved"] == 1
        assert second["duplicates"] == 1
        assert len(store.list_signals()) == 1
    finally:
        client.close()
        store.close()


def test_x_signal_style_record_is_saved_as_idea(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("COLLECTOR_DATABASE_PATH", str(tmp_path / "collector.sqlite3"))
    get_settings.cache_clear()
    store = CollectorStore()
    try:
        saved = store.save_signal(
            SignalRecord(
                source_type="x",
                source_id="1",
                source_name="X @example",
                title="Unverified claim",
                content="A claim",
                url="https://x.com/example/status/1",
                discovered_at=datetime.now(timezone.utc),
                source_tier=SourceTier.C,
            )
        )
        assert saved
        markdown = next((tmp_path / "workspace" / "signals").glob("*.md")).read_text()
        assert 'status: "idea"' in markdown
        assert 'source_tier: "C"' in markdown
    finally:
        store.close()
