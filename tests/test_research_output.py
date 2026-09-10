from __future__ import annotations

import json

from writing_agent.services.research import _coerce_deepagents_output


def test_deepagents_object_bullets_become_readable_text():
    raw = {
        "messages": [
            {
                "content": json.dumps(
                    [
                        {
                            "title": "产品能力边界",
                            "summary": "官方资料支持基础能力，但性能仍需实测。",
                            "bullets": [
                                {"status": "已确认", "point": "官网列出支持的数据库。"},
                                {"status": "待确认", "point": "性能和安全性需要实测。"},
                            ],
                            "source_urls": ["https://example.com/"],
                        }
                    ],
                    ensure_ascii=False,
                )
            }
        ]
    }

    notes = _coerce_deepagents_output(raw)

    assert len(notes) == 1
    assert notes[0].bullets == [
        "已确认：官网列出支持的数据库。",
        "待确认：性能和安全性需要实测。",
    ]
    assert notes[0].source_urls == ["https://example.com/"]
