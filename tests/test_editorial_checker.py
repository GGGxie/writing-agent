from writing_agent.editorial.checker import has_template_placeholder


def test_normal_url_word_is_not_a_template_placeholder():
    assert not has_template_placeholder("谁能访问这个 URL？")


def test_markdown_url_placeholder_is_detected():
    assert has_template_placeholder("- [官方来源](URL)")
    assert has_template_placeholder("核查时间：YYYY-MM-DD")
