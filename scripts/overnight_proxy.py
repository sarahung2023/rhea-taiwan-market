"""公開活躍股隔夜轉弱代理研究。只使用已完成交易日官方開高收與成交值。

本模型無法識別交易人、持有期間、券商分點或真正隔日沖成交占比。
前一交易日以成交值先選150檔，再對齊隔日同股開收；不依T日結果挑樣本。
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import json

POOL_SIZE = 150
MIN_VALID = 75
PAIR_GAP_LIMIT_DAYS = 7


def active_pool(quotes, limit=POOL_SIZE):
    rows = []
    for market in ('TWSE', 'TPEx'):
        for stock in quotes.get(market, {}).values():
            amount = stock.get('amount')
            price = stock.get('close')
            pct = stock.get('pct')
            if amount is None or amount <= 0 or price is None or price <= 0 or pct is None:
                continue
            rows.append({
                'market': market, 'code': stock['code'],
                'close': round(price, 4), 'pct': round(pct, 4),
                'amount': round(amount, 2),
            })
    rows.sort(key=lambda r: (-r['amount'], r['market'], r['code']))
    return rows[:limit]


def make_pair(previous_day, current_day, quotes):
    if not previous_day or not previous_day.get('active_candidates'):
        return None
    previous_date, current_date = previous_day.get('date'), current_day
    try:
        elapsed = (date.fromisoformat(current_date) - date.fromisoformat(previous_date)).days
    except (ValueError, TypeError):
        return None
    if elapsed < 1 or elapsed > PAIR_GAP_LIMIT_DAYS:
        return None

    matched = eligible = events = fades = continuations = 0
    examples = []
    for stock in previous_day['active_candidates']:
        fresh = quotes.get(stock['market'], {}).get(stock['code'])
        if not fresh:
            continue
        prev_close, opening, close = stock.get('close'), fresh.get('open'), fresh.get('close')
        if not all(isinstance(v, (int, float)) and v > 0 for v in (prev_close, opening, close)):
            continue
        gap = 100 * (opening / prev_close - 1)
        intraday = 100 * (close / opening - 1)
        # Coarse data-quality guard; does not fully eliminate ex-rights/dividend distortions.
        if not (-12 <= gap <= 12 and -12 <= intraday <= 12):
            continue
        matched += 1
        if gap >= 1 and intraday <= -1:
            fades += 1
        if stock['pct'] >= 2 and gap >= 1:
            eligible += 1
            if intraday <= -1:
                events += 1
                if len(examples) < 5:
                    examples.append({'code': stock['code'], 'market': stock['market'],
                                     'gap_pct': round(gap, 2), 'day_pct': round(intraday, 2)})
            if intraday >= 1:
                continuations += 1
    if matched < MIN_VALID:
        return {'date': current_date, 'previous_date': previous_date, 'status': 'insufficient',
                'matched': matched}
    return {
        'date': current_date, 'previous_date': previous_date, 'status': 'ok',
        'matched': matched, 'eligible': eligible, 'events': events,
        'fades': fades, 'continuations': continuations,
        'event_pct': round(100 * events / matched, 2),
        'conditional_pct': round(100 * events / eligible, 2) if eligible else None,
        'fade_pct': round(100 * fades / matched, 2),
        'examples': examples,
    }


def build_overview(daily_dir: Path):
    valid = []
    for path in sorted(daily_dir.glob('????-??-??.json'))[-60:]:
        try:
            day = json.loads(path.read_text(encoding='utf-8'))
            pair = day.get('overnight_pair')
            if day.get('date') == path.stem and pair and pair.get('date') == path.stem and pair.get('status') == 'ok':
                valid.append(pair)
        except (OSError, ValueError, TypeError):
            continue
    five = valid[-5:]
    n = sum(row['matched'] for row in five)
    events = sum(row['events'] for row in five)
    qualified = sum(row['eligible'] for row in five)
    fades = sum(row['fades'] for row in five)
    baseline = None
    if len(valid) >= 25:
        prior = valid[-25:-5]
        b_n = sum(r['matched'] for r in prior)
        baseline = round(100 * sum(r['events'] for r in prior) / b_n, 2) if b_n else None
    return {
        'status': 'ok' if len(five) == 5 else 'collecting',
        'days_observed': len(five), 'days_required': 5,
        'latest_date': five[-1]['date'] if five else None,
        'lookback': 'last five completed comparable trading-day pairs',
        'universe': 'prior trading day TWSE+TPEx top 150 stocks by traded value',
        'definition': 'previous day close gain >=2%; next open gap >=1% from previous close; same-day close <=-1% from open',
        'data_clock': 'T close and next completed T+1 open/close; never available before T+1 close',
        'matched': n, 'eligible': qualified, 'events': events,
        'fades': fades, 'event_days': sum(r['events'] > 0 for r in five),
        'event_pct': round(100 * events / n, 2) if n else None,
        'conditional_pct': round(100 * events / qualified, 2) if qualified else None,
        'fade_pct': round(100 * fades / n, 2) if n else None,
        'previous_20day_event_pct': baseline,
        'baseline_ready': baseline is not None,
        'days': five,
        'limitations': 'Price-pattern proxy only. Not actual overnight trader count, position share or causal evidence; corporate actions and market regimes can confound.',
    }
