from datetime import datetime, timezone

import httpx

from writing_agent.collectors import rsshub_instances
from writing_agent.collectors.config import RssCollectorConfig, RssFeed
from writing_agent.collectors.rsshub import collect_rss_once
from writing_agent.collectors.rsshub_instances import parse_instance_list
from writing_agent.collectors.store import CollectorStore
from writing_agent.config import get_settings
from writing_agent.models import SignalRecord, SourceTier

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test</title><item>
<guid>post-1</guid><title>New model</title><link>https://example.com/post-1</link>
<pubDate>Tue, 08 Sep 2026 02:00:00 GMT</pubDate><description>Details</description>
</item></channel></rss>"""

AUTO_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test</title><item>
<guid>post-auto-1</guid><title>Auto instance item</title><link>https://example.com/post-auto-1</link>
<pubDate>Tue, 08 Sep 2026 02:00:00 GMT</pubDate><description>Details</description>
</item></channel></rss>"""

HTML_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test</title><item>
<guid>post-html-1</guid><title>Tweet with markup</title>
<link>https://x.com/example/status/1</link>
<pubDate>Tue, 08 Sep 2026 02:00:00 GMT</pubDate>
<description>&lt;p&gt;Hello&lt;br&gt;World&lt;/p&gt;&lt;img src="https://example.com/a.jpg"&gt;&amp;ensp;Bye</description>
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


def test_rss_collection_strips_html_markup_from_content(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("COLLECTOR_DATABASE_PATH", str(tmp_path / "collector.sqlite3"))
    get_settings.cache_clear()
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=HTML_RSS))
    client = httpx.Client(transport=transport)
    store = CollectorStore()
    config = RssCollectorConfig(
        max_item_age_hours=None,
        feeds=[
            RssFeed(
                id="test-html",
                name="Test HTML Feed",
                url="https://example.com/rss",
                source_tier=SourceTier.C,
            )
        ],
    )
    try:
        result = collect_rss_once(config, store, client)
        assert result["saved"] == 1
        signals = store.list_signals()
        assert len(signals) == 1
        content = signals[0].content
        assert "<" not in content
        assert ">" not in content
        assert "Hello\nWorld\nBye" == content
    finally:
        client.close()
        store.close()


def test_auto_instance_falls_back_to_next_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("COLLECTOR_DATABASE_PATH", str(tmp_path / "collector.sqlite3"))
    get_settings.cache_clear()
    monkeypatch.setattr(
        rsshub_instances,
        "fetch_instance_candidates",
        lambda client: ["https://bad.example", "https://good.example"],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "bad.example":
            return httpx.Response(500)
        return httpx.Response(200, content=AUTO_RSS)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = CollectorStore()
    config = RssCollectorConfig(
        max_item_age_hours=None,
        feeds=[
            RssFeed(
                id="auto-feed",
                name="Auto Feed",
                url="/twitter/user/OpenAI",
                auto_instance=True,
                source_tier=SourceTier.C,
            )
        ],
    )
    try:
        result = collect_rss_once(config, store, client)
        assert result["saved"] == 1
        assert result["failed_feeds"] == 0
        assert store.get_feed_instance("auto-feed")["base_url"] == "https://good.example"
    finally:
        client.close()
        store.close()


def test_auto_instance_reuses_cached_instance(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("COLLECTOR_DATABASE_PATH", str(tmp_path / "collector.sqlite3"))
    get_settings.cache_clear()
    monkeypatch.setattr(
        rsshub_instances,
        "fetch_instance_candidates",
        lambda client: ["https://bad.example", "https://good.example"],
    )

    request_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_hosts.append(request.url.host)
        if request.url.host == "bad.example":
            return httpx.Response(500)
        return httpx.Response(200, content=AUTO_RSS)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = CollectorStore()
    config = RssCollectorConfig(
        max_item_age_hours=None,
        feeds=[
            RssFeed(
                id="auto-feed",
                name="Auto Feed",
                url="/twitter/user/OpenAI",
                auto_instance=True,
                source_tier=SourceTier.C,
            )
        ],
    )
    try:
        collect_rss_once(config, store, client)
        assert request_hosts.count("bad.example") == 1

        collect_rss_once(config, store, client)
        assert request_hosts.count("bad.example") == 1
        assert request_hosts[-1] == "good.example"
    finally:
        client.close()
        store.close()


def test_parse_instance_list():
    # 模拟真实页面结构：每行除了实例地址（第一列）外，维护者列（第三列）
    # 也是一个 https 链接，解析时必须只取每行第一个链接，否则会把维护者主页
    # 误当成 RSSHub 实例。两个表格之间还故意重复一个实例 URL 以验证去重。
    html = """
    <h2 id="official">Official</h2>
    <table><thead><tr><th>URL</th><th>Location</th><th>Maintainer</th><th>Online</th></tr></thead>
    <tbody>
    <tr><td><a href="https://rsshub.app" target="_blank" rel="noreferrer">rsshub.app</a></td>
    <td>US</td><td><a href="https://diygod.cc" target="_blank" rel="noreferrer">DIYgod</a></td>
    <td><img src="https://img.shields.io/website.svg?url=https://rsshub.app/test/cache"></td></tr>
    </tbody></table>
    <h2 id="public">Public</h2>
    <table><thead><tr><th>地址</th><th>位置</th><th>维护者</th><th>在线状态</th></tr></thead>
    <tbody>
    <tr data-v-x><td data-v-x>
    <a target="_blank" href="https://rsshub.rssforever.com" data-v-x>rsshub.rssforever.com</a>
    </td><td data-v-x>-</td><td data-v-x>
    <a target="_blank" href="https://maintainer-a.example" data-v-x>Someone</a>
    </td></tr>
    <tr data-v-x><td data-v-x>
    <a target="_blank" href="https://rsshub.app/" data-v-x>rsshub.app</a>
    </td><td data-v-x>-</td><td data-v-x>
    <a target="_blank" href="https://maintainer-b.example" data-v-x>Other</a>
    </td></tr>
    </tbody></table>
    """
    assert parse_instance_list(html) == [
        "https://rsshub.app",
        "https://rsshub.rssforever.com",
    ]


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
