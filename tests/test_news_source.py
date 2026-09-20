import unittest
from datetime import datetime

import NewsSource


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class NewsSourceTests(unittest.TestCase):
    def test_parse_sina_payload_normalizes_timeline_message(self):
        payload = {
            "result": {
                "data": {
                    "feed": {
                        "list": [{
                            "id": 5103630,
                            "rich_text": "<b>【深蓝航天完成试车】</b> 发动机完成测试。",
                            "create_time": "2026-09-20 09:49:01",
                            "is_focus": 1,
                            "tag": [{"name": "公司"}],
                            "docurl": "https://finance.sina.cn/example.html",
                            "ext": '{"stocks":[{"symbol":"sh600519"}]}',
                        }]
                    }
                }
            }
        }

        rows = NewsSource.parse_sina_payload(payload)

        self.assertEqual(rows[0]["id"], "sina:5103630")
        self.assertEqual(rows[0]["source"], "新浪财经")
        self.assertEqual(rows[0]["title"], "深蓝航天完成试车")
        self.assertEqual(rows[0]["summary"], "发动机完成测试。")
        self.assertEqual(rows[0]["category"], "公司")
        self.assertTrue(rows[0]["important"])
        self.assertEqual(rows[0]["stocks"], ["600519"])

    def test_sina_importance_uses_source_flag_not_keyword_guessing(self):
        payload = {"result": {"data": {"feed": {"list": [{
            "id": 5103631,
            "rich_text": "【突发重磅】正文",
            "create_time": "2026-09-20 09:50:01",
            "is_focus": 0,
            "top_value": 0,
        }]}}}}

        rows = NewsSource.parse_sina_payload(payload)

        self.assertFalse(rows[0]["important"])

    def test_parse_cls_payload_normalizes_message(self):
        payload = {
            "data": {
                "roll_data": [{
                    "id": 123,
                    "title": "重大事项",
                    "content": "消息正文",
                    "ctime": 1789552896,
                    "level": "A",
                    "shareurl": "https://example.test/123",
                    "stock_list": [{"StockID": "600519", "name": "贵州茅台"}],
                }]
            }
        }

        rows = NewsSource.parse_cls_payload(payload)

        self.assertEqual(rows[0]["id"], "cls:123")
        self.assertEqual(rows[0]["source"], "财联社")
        self.assertEqual(rows[0]["title"], "重大事项")
        self.assertTrue(rows[0]["important"])
        self.assertEqual(rows[0]["stocks"], ["600519"])

    def test_parse_eastmoney_payload_normalizes_message(self):
        payload = {
            "data": {
                "fastNewsList": [{
                    "code": "20260916001",
                    "title": "市场快讯",
                    "summary": "快讯正文",
                    "showTime": "2026-09-16 17:54:23",
                    "titleColor": 1,
                    "stockList": ["1.603259", "90.BK0001"],
                }]
            }
        }

        rows = NewsSource.parse_eastmoney_payload(payload)

        self.assertEqual(rows[0]["id"], "eastmoney:20260916001")
        self.assertEqual(rows[0]["source"], "东方财富")
        self.assertTrue(rows[0]["important"])
        self.assertEqual(rows[0]["stocks"], ["603259"])

    def test_fetch_fast_news_falls_back_to_eastmoney(self):
        session = FakeSession([
            RuntimeError("CLS unavailable"),
            RuntimeError("Sina unavailable"),
            FakeResponse({
                "data": {
                    "fastNewsList": [{
                        "code": "fallback-1",
                        "title": "备用消息",
                        "summary": "",
                        "showTime": "2026-09-16 18:00:00",
                        "titleColor": 0,
                        "stockList": [],
                    }]
                }
            }),
        ])

        rows = NewsSource.fetch_fast_news(session=session, page_size=10)

        self.assertEqual(rows[0]["source"], "东方财富")
        self.assertEqual(len(session.calls), 3)

    def test_fetch_sina_news_uses_public_feed_parameters(self):
        session = FakeSession([FakeResponse({
            "result": {"data": {"feed": {"list": [{
                "id": 1,
                "rich_text": "【市场快讯】正文",
                "create_time": "2026-09-20 10:00:00",
            }]}}}
        })])

        rows = NewsSource.fetch_sina_news(session=session, page_size=10)

        self.assertEqual(rows[0]["source"], "新浪财经")
        self.assertEqual(session.calls[0][1]["params"]["zhibo_id"], 152)
        self.assertEqual(session.calls[0][1]["params"]["page_size"], 10)

    def test_fetch_sina_recent_news_stops_after_reaching_three_day_cutoff(self):
        session = FakeSession([
            FakeResponse({"result": {"data": {"feed": {"list": [
                {"id": 3, "rich_text": "【今天】正文", "create_time": "2026-09-20 10:00:00"},
                {"id": 2, "rich_text": "【昨天】正文", "create_time": "2026-09-19 10:00:00"},
            ]}}}}),
            FakeResponse({"result": {"data": {"feed": {"list": [
                {"id": 1, "rich_text": "【过期】正文", "create_time": "2026-09-16 09:00:00"},
            ]}}}}),
        ])

        rows = NewsSource.fetch_sina_recent_news(
            session=session,
            days=3,
            page_size=2,
            max_pages=10,
            now=datetime(2026, 9, 20, 12, 0, 0),
        )

        self.assertEqual([row["id"] for row in rows], ["sina:3", "sina:2"])
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1][1]["params"]["page"], 2)


if __name__ == "__main__":
    unittest.main()
