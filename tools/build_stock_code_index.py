# -*- coding: utf-8 -*-
"""生成全市场股票代码 -> 中文名称 索引文件（resources/stock_codes_list.json）。

数据源：baostock（项目 requirements 已包含）。
覆盖：沪深 A 股 + 场内基金（ETF/LOF），过滤指数与可转债。

用法：
    python tools/build_stock_code_index.py [--output resources/stock_codes_list.json]

输出格式（与 StockCodeSearch.load_stock_code_index / resolve_stock_code 兼容）：
    {
      "codes": {
        "sh600000": {"code": "600000", "market": "sh", "name": "浦发银行", "category": "沪A"},
        ...
      },
      "updated_at": "2026-08-18 12:00:00"
    }
"""
import argparse
import json
import os
import sys
from datetime import datetime

try:
    import baostock as bs
except Exception as exc:  # pragma: no cover
    sys.exit(f"需要安装 baostock：pip install baostock（当前导入失败：{exc}）")


# baostock type: 1=股票, 2=指数, 3=其它, 4=可转债, 5=ETF/基金
KEEP_TYPES = {"1", "5"}
# 仅保留上市状态（status=1）
KEEP_STATUS = {"1"}

CATEGORY_BY_TYPE = {"1": "A", "5": "基"}


def _to_prefixed(code):
    """sh.600000 -> sh600000；bj.xxxxxx -> bjxxxxxx"""
    text = str(code or "").strip().lower()
    for prefix in ("sh", "sz", "bj"):
        if text.startswith(prefix + "."):
            return prefix + text.split(".", 1)[1]
    return text


def fetch_entries():
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败：{lg.error_code} {lg.error_msg}")
    entries = []
    try:
        rs = bs.query_stock_basic()
        if rs.error_code != "0":
            raise RuntimeError(f"query_stock_basic 失败：{rs.error_code} {rs.error_msg}")
        while rs.next():
            row = rs.get_row_data()  # [code, code_name, ipoDate, outDate, type, status]
            code = _to_prefixed(row[0])
            name = str(row[1] or "").strip()
            stock_type = str(row[4] or "").strip()
            status = str(row[5] or "").strip()
            if not code or not name or stock_type not in KEEP_TYPES or status not in KEEP_STATUS:
                continue
            market = code[:2]
            category = {"sh": "沪", "sz": "深", "bj": "京"}.get(market, market.upper()) + CATEGORY_BY_TYPE.get(stock_type, "")
            entries.append({
                "code": code,
                "market": market,
                "name": name,
                "category": category,
            })
    finally:
        bs.logout()
    # 去重并排序
    merged = {item["code"]: item for item in entries}
    return [merged[key] for key in sorted(merged)]


def main():
    parser = argparse.ArgumentParser(description="生成全市场股票代码->名称索引")
    parser.add_argument("--output", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "resources", "stock_codes_list.json"))
    args = parser.parse_args()

    entries = fetch_entries()
    if not entries:
        sys.exit("未获取到任何数据，已中止（不覆盖已有索引文件）")

    payload = {
        "codes": {item["code"]: item for item in entries},
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    out_dir = os.path.dirname(args.output)
    os.makedirs(out_dir, exist_ok=True)
    tmp = args.output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=1)
    os.replace(tmp, args.output)
    print(f"已生成 {args.output}：{len(entries)} 条（股票+基金）")


if __name__ == "__main__":
    main()
