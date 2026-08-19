import unittest

import QuoteSource


def _sina_line(code, name, open_price, prev_close, current, high, low):
    fields = [name, str(open_price), str(prev_close), str(current), str(high), str(low)]
    fields.extend(["0"] * 24)
    fields.extend(["2026-08-19", "15:00:00", "00"])
    return f'var hq_str_{code}="{",".join(fields)}";\n'


class QuoteSourceTests(unittest.TestCase):
    def test_eastmoney_secid(self):
        self.assertEqual(QuoteSource.eastmoney_secid("sh600519"), "1.600519")
        self.assertEqual(QuoteSource.eastmoney_secid("sz000001"), "0.000001")
        self.assertEqual(QuoteSource.eastmoney_secid("bad-code"), "")

    def test_baostock_code(self):
        self.assertEqual(QuoteSource.baostock_code("sh600519"), "sh.600519")
        self.assertEqual(QuoteSource.baostock_code("sz000001"), "sz.000001")
        self.assertEqual(QuoteSource.baostock_code(""), "")

    def test_intraday_minute_index(self):
        self.assertEqual(QuoteSource.intraday_minute_index("09:30"), 0)
        self.assertEqual(QuoteSource.intraday_minute_index("11:30"), 120)
        self.assertEqual(QuoteSource.intraday_minute_index("13:00"), 121)
        self.assertEqual(QuoteSource.intraday_minute_index("15:00"), 241)
        self.assertIsNone(QuoteSource.intraday_minute_index("12:00"))
        self.assertIsNone(QuoteSource.intraday_minute_index("09:00"))
        self.assertIsNone(QuoteSource.intraday_minute_index(""))
        self.assertEqual(QuoteSource.intraday_minute_index("2026-08-19 10:00"), 30)

    def test_parse_sina_response(self):
        text = _sina_line("sh600519", "贵州茅台", 1700.0, 1690.0, 1710.5, 1720.0, 1695.0)
        text += 'garbage line without marker\n'
        text += 'var hq_str_szbad="only,few,fields";\n'

        result = QuoteSource.parse_sina_response(text)

        self.assertEqual(list(result.keys()), ["sh600519"])
        parts = result["sh600519"]
        self.assertEqual(parts[0], "贵州茅台")
        self.assertEqual(parts[3], "1710.5")
        self.assertEqual(parts[30], "2026-08-19")

    def test_fetch_sina_quotes_builds_url_and_parses(self):
        calls = []

        def fake_get(url, headers=None, timeout=None):
            calls.append((url, headers, timeout))

            class FakeResponse:
                encoding = None
                text = _sina_line("sh600519", "贵州茅台", 1700.0, 1690.0, 1710.5, 1720.0, 1695.0)

            return FakeResponse()

        result = QuoteSource.fetch_sina_quotes(["sh600519"], getter=fake_get)

        self.assertEqual(calls[0][0], "https://hq.sinajs.cn/list=sh600519")
        self.assertEqual(calls[0][1]["Referer"], "https://finance.sina.com.cn")
        self.assertEqual(result["sh600519"][0], "贵州茅台")

    def test_fetch_sina_quotes_empty_codes(self):
        self.assertEqual(QuoteSource.fetch_sina_quotes([], getter=lambda *a, **k: None), {})

    def test_parse_tencent_daily_payload(self):
        payload = {
            "data": {
                "sh600519": {
                    "qfqday": [
                        ["2026-08-01", "10.00", "10.20", "10.30", "9.90", "1000", "2000"],
                        ["bad", "x", "y"],
                    ]
                }
            }
        }

        rows = QuoteSource.parse_tencent_daily_payload("sh600519", payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-08-01")
        self.assertEqual(rows[0]["close"], 10.2)
        self.assertEqual(rows[0]["amount"], 2000.0)

    def test_parse_tencent_daily_payload_empty(self):
        self.assertEqual(QuoteSource.parse_tencent_daily_payload("sh600519", {}), [])
        self.assertEqual(QuoteSource.parse_tencent_daily_payload("sh600519", None), [])

    def test_parse_eastmoney_intraday_payload(self):
        payload = {
            "data": {
                "preClose": "10.00",
                "trends": [
                    "2026-08-19 09:30,1000,10.01,10.02,10.00,500,5010,10.005",
                    "2026-08-19 12:00,1000,10.50,10.60,10.40,500,5250,10.5",
                    "2026-08-19 13:00,1000,10.52,10.62,10.42,500,5260,10.52",
                ],
            }
        }

        trend = QuoteSource.parse_eastmoney_intraday_payload(payload)

        self.assertEqual(trend["prev_close"], 10.0)
        minutes = [point["minute"] for point in trend["points"]]
        self.assertEqual(minutes, [0, 121])  # 12:00 非交易时段被剔除
        self.assertEqual(trend["points"][0]["avg"], 10.005)

    def test_parse_eastmoney_intraday_payload_empty(self):
        trend = QuoteSource.parse_eastmoney_intraday_payload({})
        self.assertEqual(trend["points"], [])
        self.assertEqual(trend["prev_close"], 0.0)


if __name__ == "__main__":
    unittest.main()
