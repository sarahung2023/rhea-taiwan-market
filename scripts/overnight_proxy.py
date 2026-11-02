"""Public high-turnover stock and overnight price-pattern monitor.
No private pools, brokerage positions or day-trading signals.

The study cohort is frozen at T close (>=5% daily shares turnover), then
evaluated at T+1 close. Issued common shares are sourced from official company
rosters, and traded shares from official daily quotes. Not overnight trader %.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import json
import math

VERSION = 'high-turnover-v1-20261102'
HIGH = 5.0
VERY_HIGH = 10.0
PAIR_GAP_LIMIT_DAYS = 7
MIN_MARKET_COVERAGE = .70


def _valid(v):
    return isinstance(v, (int, float)) and math.isfinite(v) and v > 0


def active_pool(quotes, companies):
    """Select ALL stocks >=5% turnover, never an amount-ranked top-N slice."""
    selected = []
    coverage = {}
    totals = {}
    super_high = 0
    for market in ('TWSE', 'TPEx'):
        valid_rows = 0
        denominator = 0
        for code, stock in quotes.get(market, {}).items():
            company = companies.get(market, {}).get(code)
            if not company:
                continue
            denominator += 1
            issued = company.get('issued_shares')
            volume = stock.get('volume')
            close = stock.get('close')
            if not all(_valid(v) for v in (issued, volume, close)):
                continue
            ratio = 100 * volume / issued
            # Units or stale corporate action may distort extremes: quarantine, not fabricate.
            if ratio <= 0 or ratio > 100:
                continue
            valid_rows += 1
            if ratio < HIGH:
                continue
            row = {'market': market, 'code': code, 'close': round(close, 4),
                   'pct': stock.get('pct'), 'turnover_pct': round(ratio, 4)}
            if not isinstance(row['pct'], (int, float)):
                continue
            selected.append(row)
            if ratio >= VERY_HIGH:
                super_high += 1
        totals[market] = denominator
        coverage[market] = round(valid_rows / denominator, 4) if denominator else 0
    good = all(totals[m] >= 200 and coverage[m] >= MIN_MARKET_COVERAGE
               for m in ('TWSE', 'TPEx'))
    selected.sort(key=lambda r: (-r['turnover_pct'], r['market'], r['code']))
    return {'version': VERSION, 'status': 'ok' if good else 'insufficient',
            'coverage': coverage, 'universe_count': sum(totals.values()),
            'high_turnover_count': len(selected), 'very_high_count': super_high,
            'candidates': selected if good else []}


def make_pair(previous_day, current_day, quotes):
    study = (previous_day or {}).get('turnover_study') or {}
    if study.get('version') != VERSION or study.get('status') != 'ok':
        return None
    previous_date = previous_day.get('date')
    try:
        delta = (date.fromisoformat(current_day) - date.fromisoformat(previous_date)).days
    except (ValueError, TypeError):
        return None
    if not 1 <= delta <= PAIR_GAP_LIMIT_DAYS:
        return None

    candidates = study['candidates']
    matched = qualified = reversal = fade = continued = 0
    examples = []
    for stock in candidates:
        latest = quotes.get(stock['market'], {}).get(stock['code'])
        if not latest:
            continue
        prev_close, opening, close = stock.get('close'), latest.get('open'), latest.get('close')
        if not all(_valid(x) for x in (prev_close, opening, close)):
            continue
        gap = 100 * (opening / prev_close - 1)
        intraday = 100 * (close / opening - 1)
        # Corporate actions or malformed values are excluded, never auto-adjusted.
        if not (-12 <= gap <= 12 and -12 <= intraday <= 12):
            continue
        matched += 1
        if gap >= 1 and intraday <= -1:
            fade += 1
        if gap >= 1 and intraday >= 1:
            continued += 1
        if stock['pct'] >= 2 and gap >= 1:
            qualified += 1
            if intraday <= -1:
                reversal += 1
                if len(examples) < 5:
                    examples.append({'code': stock['code'], 'market': stock['market'],
                                     'gap_pct': round(gap, 2), 'intraday_pct': round(intraday, 2)})
    required = max(5, math.ceil(len(candidates) * .60)) if candidates else 0
    ok = matched >= required
    return {'model_version': VERSION, 'status': 'ok' if ok else 'insufficient',
            'date': current_day, 'previous_date': previous_date,
            'universe_count': study['universe_count'],
            'cohort_count': len(candidates), 'very_high_count': study['very_high_count'],
            'matched': matched, 'eligible': qualified, 'events': reversal,
            'fades': fade, 'continuations': continued,
            'event_pct': round(100 * reversal / matched, 2) if matched else None,
            'fade_pct': round(100 * fade / matched, 2) if matched else None,
            'continuation_pct': round(100 * continued / matched, 2) if matched else None,
            'examples': examples}


def build_overview(daily_dir: Path):
    snapshots = []
    for path in sorted(daily_dir.glob('????-??-??.json'))[-70:]:
        try:
            row = json.loads(path.read_text(encoding='utf-8'))
            if row.get('date') != path.stem:
                snapshots.append(None)
                continue
            pair = row.get('overnight_pair')
            valid = (isinstance(pair, dict) and pair.get('model_version') == VERSION
                     and pair.get('date') == path.stem and pair.get('status') == 'ok')
            snapshots.append(pair if valid else None)
        except (OSError, ValueError, TypeError):
            snapshots.append(None)
    last = snapshots[-5:]
    items = [p for p in last if p]
    ready = len(last) == 5 and len(items) == 5
    def pct(part, total):
        return round(100 * part / total, 2) if total else None
    total_universe = sum(p['universe_count'] for p in items)
    total_cohort = sum(p['cohort_count'] for p in items)
    total_matched = sum(p['matched'] for p in items)
    total_events = sum(p['events'] for p in items)
    total_fades = sum(p['fades'] for p in items)
    total_continue = sum(p['continuations'] for p in items)
    baseline = None
    if len(snapshots) >= 25 and all(snapshots[-25:-5]):
        prior = snapshots[-25:-5]
        base_n = sum(p['matched'] for p in prior)
        baseline = pct(sum(p['events'] for p in prior), base_n)
    return {
        'version': VERSION, 'status': 'ok' if ready else 'collecting',
        'days_observed': len(items), 'days_required': 5,
        'latest_date': items[-1]['date'] if items else None,
        'universe': 'All TWSE and TPEx ordinary stocks with verified daily turnover >=5%, not top 150 by value',
        'turnover_definition': 'Official traded shares divided by issued common shares',
        'universe_count': total_universe if ready else None,
        'cohort_count': total_cohort if ready else None,
        'very_high_count': sum(p['very_high_count'] for p in items) if ready else None,
        'high_density_pct': pct(total_cohort, total_universe) if ready else None,
        'matched': total_matched if ready else None,
        'eligible': sum(p['eligible'] for p in items) if ready else None,
        'events': total_events if ready else None,
        'fades': total_fades if ready else None,
        'continuations': total_continue if ready else None,
        'event_days': sum(p['events'] > 0 for p in items) if ready else None,
        'event_pct': pct(total_events, total_matched) if ready else None,
        'fade_pct': pct(total_fades, total_matched) if ready else None,
        'continuation_pct': pct(total_continue, total_matched) if ready else None,
        'previous_20day_event_pct': baseline,
        'baseline_ready': baseline is not None and ready,
        'days': items,
        'note': 'Five latest recorded sessions; missing or legacy selection days never backfilled. '
                'Price patterns cannot identify overnight traders or their volume.',
    }
