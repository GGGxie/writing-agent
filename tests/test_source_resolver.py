from writing_agent.editorial.evidence import infer_source_tier
from writing_agent.models import SourceTier
from writing_agent.services.source_resolver import MetadataParser


def test_metadata_parser_keeps_headings_paragraphs_and_lists():
    parser = MetadataParser()
    parser.feed(
        """
        <html><head><title>产品页</title></head><body>
          <h2>Requirements</h2>
          <p>这是产品的基本说明。</p>
          <ul><li>支持 PostgreSQL</li><li>支持 Redis 插件</li></ul>
        </body></html>
        """
    )

    assert parser.blocks == [
        "Requirements",
        "这是产品的基本说明。",
        "支持 PostgreSQL",
        "支持 Redis 插件",
    ]


def test_root_product_homepage_is_primary_but_subpage_stays_unverified():
    root_tier, root_reason = infer_source_tier(
        url="https://product.example/",
        kind="article",
    )
    subpage_tier, _ = infer_source_tier(
        url="https://publisher.example/articles/product",
        kind="article",
    )

    assert root_tier == SourceTier.A
    assert "官网" in root_reason
    assert subpage_tier == SourceTier.B
