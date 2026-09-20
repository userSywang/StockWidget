import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import NewsCache


def news_item(item_id, published_at, title="消息"):
    return {
        "id": item_id,
        "source": "新浪财经",
        "title": title,
        "summary": "正文",
        "published_at": published_at,
        "timestamp": int(datetime.strptime(published_at, "%Y-%m-%d %H:%M:%S").timestamp()),
        "important": False,
        "category": "市场",
        "stocks": [],
        "url": "",
    }


class NewsCacheTests(unittest.TestCase):
    def test_merge_keeps_three_days_deduplicated_and_newest_first(self):
        now = datetime(2026, 9, 20, 12, 0, 0)
        rows = NewsCache.merge_news_items(
            [news_item("sina:1", "2026-09-19 10:00:00", "旧标题")],
            [
                news_item("sina:2", "2026-09-20 11:00:00"),
                news_item("sina:1", "2026-09-19 10:00:00", "更新标题"),
                news_item("sina:0", "2026-09-16 10:00:00"),
            ],
            now=now,
        )

        self.assertEqual([row["id"] for row in rows], ["sina:2", "sina:1"])
        self.assertEqual(rows[1]["title"], "更新标题")

    def test_cache_round_trip_uses_separate_atomic_file(self):
        now = datetime(2026, 9, 20, 12, 0, 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = NewsCache.save_news_cache(
                [news_item("sina:2", "2026-09-20 11:00:00")],
                base_dir=tmp,
                now=now,
            )
            loaded = NewsCache.load_news_cache(base_dir=tmp, now=now)

            self.assertEqual([row["id"] for row in loaded], ["sina:2"])
            self.assertEqual(json.loads(Path(path).read_text(encoding="utf-8"))["version"], 2)
            self.assertFalse(Path(path + ".tmp").exists())

    def test_load_drops_expired_and_malformed_rows(self):
        now = datetime(2026, 9, 20, 12, 0, 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(NewsCache.news_cache_path(base_dir=tmp))
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"version": 2, "items": [
                news_item("sina:new", "2026-09-20 10:00:00"),
                news_item("sina:old", "2026-09-10 10:00:00"),
                {"title": "没有ID"},
            ]}), encoding="utf-8")

            loaded = NewsCache.load_news_cache(base_dir=tmp, now=now)

            self.assertEqual([row["id"] for row in loaded], ["sina:new"])

    def test_load_discards_old_importance_classification_cache(self):
        now = datetime(2026, 9, 20, 12, 0, 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(NewsCache.news_cache_path(base_dir=tmp))
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "version": 1,
                "items": [news_item("sina:legacy", "2026-09-20 10:00:00")],
            }), encoding="utf-8")

            self.assertEqual(NewsCache.load_news_cache(base_dir=tmp, now=now), [])


if __name__ == "__main__":
    unittest.main()
