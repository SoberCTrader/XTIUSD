"""XAUUSD Phase II data receipt & digest. Usage: python3 phase2_digest.py [INPUT_DIR] [--out OUT_DIR]"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from statistics import median, mean
from collections import Counter

GOLD_TICK_REF = 104000
SPREAD_BASE = 0.065
SPREAD_STRESS = 0.30
REF_BARS_PER_DAY = {"t100": 1040, "t300": 347, "t500": 208, "t750": 139}
INSTRUMENT = "XAUUSD"
PIP_SIZE = 0.0001
DT_CLOSE_PCT = 0.015
WICK_PCT = 0.025
GAP_H = 6.0
REPORT_BUDGET = 15360
DIGEST_MIN_YEAR = 2021

def _easter(y):
    a = y % 19
    b, c = y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime(y, month, day)


def _nth_weekday(y, month, weekday, n):
    d = datetime(y, month, 1)
    return d + timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(y, month, weekday):
    d = (datetime(y, month + 1, 1) - timedelta(days=1)) if month < 12 else datetime(y, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _obs(d):
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _build_holidays():
    h = {}
    for y in range(1998, 2027):
        h[_obs(datetime(y, 1, 1)).strftime("%Y-%m-%d")] = "New Year's Day"
        h[_nth_weekday(y, 1, 0, 3).strftime("%Y-%m-%d")] = "MLK Day"
        h[_nth_weekday(y, 2, 0, 3).strftime("%Y-%m-%d")] = "Presidents Day"
        h[(_easter(y) - timedelta(days=2)).strftime("%Y-%m-%d")] = "Good Friday"
        h[_last_weekday(y, 5, 0).strftime("%Y-%m-%d")] = "Memorial Day"
        if y >= 2021:
            h[_obs(datetime(y, 6, 19)).strftime("%Y-%m-%d")] = "Juneteenth"
        h[_obs(datetime(y, 7, 4)).strftime("%Y-%m-%d")] = "Independence Day"
        h[_nth_weekday(y, 9, 0, 1).strftime("%Y-%m-%d")] = "Labor Day"
        h[_nth_weekday(y, 11, 3, 4).strftime("%Y-%m-%d")] = "Thanksgiving"
        h[_obs(datetime(y, 12, 25)).strftime("%Y-%m-%d")] = "Christmas"
    h["2025-01-09"] = "National Day of Mourning (Carter)"
    return h


HOLIDAYS = _build_holidays()


def parse_ts(d, t):
    d = d.strip()
    t = t.strip()
    dt = None
    for f in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            dt = datetime.strptime(d, f)
            break
        except ValueError:
            continue
    if dt is None:
        raise ValueError("bad date %r" % d)
    for f in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
        try:
            tm = datetime.strptime(t, f)
            return dt.replace(hour=tm.hour, minute=tm.minute, second=tm.second)
        except ValueError:
            continue
    raise ValueError("bad time %r" % t)


def infer_timeframe(name):
    n = name.lower()
    m = re.search(r"(?<![a-z0-9])t(\d+)(?![a-z0-9])", n)
    if m:
        return "t" + m.group(1), int(m.group(1))
    m = re.search(r"(?<![a-z0-9])h(\d+)(?![a-z0-9])", n)
    if m:
        return "h" + m.group(1), int(m.group(1)) * 3600
    m = re.search(r"(?<![a-z0-9])m(\d+)(?![a-z0-9])", n)
    if m:
        return "m" + m.group(1), int(m.group(1)) * 60
    m = re.search(r"(?<![a-z0-9])d(\d+)(?![a-z0-9])", n)
    if m:
        return "d" + m.group(1), int(m.group(1)) * 86400
    return "unknown", None


def claimed_coverage(name):
    n = name.lower()
    years = sorted(set(int(y) for y in re.findall(r"(19\d\d|20\d\d)", n)))
    dates8 = re.findall(r"(?<!\d)(\d{8})(?!\d)", n)
    ds = []
    for s in dates8:
        try:
            ds.append(datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d"))
        except ValueError:
            pass
    parts = []
    if len(years) >= 2:
        parts.append("%d-%d" % (years[0], years[-1]))
    elif len(years) == 1:
        parts.append(str(years[0]))
    if ds:
        parts.append("dates:" + ",".join(sorted(ds)))
    return " ".join(parts) if parts else "not stated in filename"


def infer_symbol(name, rows, ticks=None):
    n = name.lower()
    if re.search(r"gbpjpy", n):
        label, lo_ok, hi_ok = "GBPJPY", 100.0, 300.0
    elif re.search(r"xau|gold|gusd", n):
        label, lo_ok, hi_ok = "XAUUSD", 200.0, None
    elif re.search(r"xag|silver", n):
        label, lo_ok, hi_ok = "XAGUSD?", 15.0, 130.0
    elif re.search(r"xti|wti|oil|usoil", n):
        label, lo_ok, hi_ok = "XTIUSD?", 40.0, 130.0
    else:
        label = INSTRUMENT
        lo_ok = 100.0 if INSTRUMENT == "GBPJPY" else 200.0
        hi_ok = 300.0 if INSTRUMENT == "GBPJPY" else None
    vals = [r["c"] for r in rows] + [(t["bid"] + t["ask"]) / 2 for t in (ticks or [])]
    if not vals:
        return label + "?", "no rows"
    vals.sort()
    med = median(vals)
    lo, hi = vals[0], vals[-1]
    if med >= lo_ok and (hi_ok is None or med <= hi_ok):
        return label + "-consistent", "median %.3f in [%.3f..%.3f]" % (med, lo, hi)
    return "SUSPECT:" + label, "median %.3f in [%.3f..%.3f] outside expected range for %s" % (med, lo, hi, label)


def load_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    md5 = hashlib.md5(raw).hexdigest()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    rows = []
    ticks = []
    bad_nf = []
    header = None
    swapped = False
    delim = ","
    if lines:
        first = lines[0]
        if first.count(";") == 6 and first.count(",") < 6:
            delim = ";"
        elif first.count("\t") == 6:
            delim = "\t"
    for i, ln in enumerate(lines, 1):
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split(delim)
        if len(parts) == 7:
            if re.match(r"^\d{1,2}:\d{2}", parts[0]) and not re.match(r"^\d{1,2}:\d{2}", parts[1]):
                swapped = True
                parts = [parts[1], parts[0]] + parts[2:]
            try:
                ts = parse_ts(parts[0], parts[1])
                o, h, l, c = (float(parts[j]) for j in (2, 3, 4, 5))
                v = float(parts[6])
                v = int(v) if v == int(v) else v
                rows.append({"ts": ts, "o": o, "h": h, "l": l, "c": c, "v": v,
                             "nf": 7, "raw": ln, "line": i, "file": os.path.basename(path)})
            except Exception:
                if header is None and i == 1:
                    header = ln
                else:
                    bad_nf.append({"line": i, "nf": len(parts), "raw": ln[:120]})
        elif len(parts) == 4:
            try:
                ts = parse_ts(parts[0], parts[1])
                ticks.append({"ts": ts, "bid": float(parts[2]), "ask": float(parts[3]),
                              "line": i, "file": os.path.basename(path)})
            except Exception:
                if header is None and i == 1:
                    header = ln
                else:
                    bad_nf.append({"line": i, "nf": len(parts), "raw": ln[:120]})
        else:
            if header is None and i == 1:
                header = ln
            else:
                bad_nf.append({"line": i, "nf": len(parts), "raw": ln[:120]})
    return {"path": path, "name": os.path.basename(path), "bytes": len(raw), "md5": md5,
            "rows": rows, "ticks": ticks, "bad_nf": bad_nf, "header": header, "swapped": swapped, "delim": delim}


@lru_cache(maxsize=None)
def us_dst(d):
    y = d.year
    mar = datetime(y, 3, 1)
    start = mar + timedelta(days=(6 - mar.weekday()) % 7 + 7)
    nov = datetime(y, 11, 1)
    end = nov + timedelta(days=(6 - nov.weekday()) % 7)
    return start <= d < end


def session_day(ts):
    open_h = 22 if us_dst(ts) else 23
    return (ts - timedelta(hours=open_h)).date()


def expected_weekend_gap_h(fri):
    sun = fri + timedelta(days=2)
    off_fri = 4 if us_dst(fri) else 5
    off_sun = 4 if us_dst(sun) else 5
    return 49 + (off_sun - off_fri)


def classify_gap(t1, t2, med_gap_h):
    gh = (t2 - t1).total_seconds() / 3600.0
    d1, d2 = t1.date(), t2.date()
    if t1.weekday() in (3, 4, 5) and t2.weekday() in (6, 0) and 40 <= gh <= 80:
        if med_gap_h < 24:
            exp = expected_weekend_gap_h(t1)
            return "weekend", "%.1fh (DST-adjusted expected %.0fh)" % (gh, exp)
        note = "%.1fh (Thu->Sun: no Friday bars in this range)" % gh if t1.weekday() == 3 else "%.1fh" % gh
        return "weekend", note
    if t1.weekday() == 5 and t2.weekday() in (6, 0) and 12 <= gh <= 40:
        return "weekend", "%.1fh (Saturday stub)" % gh
    names = [HOLIDAYS.get((d1 + timedelta(days=k)).isoformat()) for k in range((d2 - d1).days + 1)]
    names = [n for n in names if n]
    if names and gh <= 110:
        return "holiday", "; ".join(sorted(set(names)))
    return "UNEXPLAINED", ""


def tf_gap_threshold(merged):
    gaps_h = [(merged[i + 1]["ts"] - merged[i]["ts"]).total_seconds() / 3600.0
              for i in range(len(merged) - 1)]
    med = median(gaps_h) if gaps_h else 24.0
    return max(GAP_H, 2.5 * med), med


def group_ranges(dates):
    out = []
    for d in sorted(dates):
        if out and (d - out[-1][1]).days == 1:
            out[-1][1] = d
        else:
            out.append([d, d])
    return ["%s..%s" % (a.isoformat(), b.isoformat()) if a != b else a.isoformat() for a, b in out]


def fmt_ts(ts):
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def merge_timeframe(files):
    by_ts = {}
    order = []
    conflicts = []
    agreements = 0
    overlap_pairs = 0
    for f in sorted(files, key=lambda x: x["name"]):
        for r in f["rows"]:
            if r["ts"] in by_ts:
                overlap_pairs += 1
                prev = by_ts[r["ts"]]
                if all(prev[k] == r[k] for k in ("o", "h", "l", "c", "v")):
                    agreements += 1
                else:
                    conflicts.append({"ts": fmt_ts(r["ts"]),
                                      "a": {"file": prev["file"], "o": prev["o"], "h": prev["h"], "l": prev["l"], "c": prev["c"], "v": prev["v"]},
                                      "b": {"file": r["file"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"]}})
            else:
                by_ts[r["ts"]] = r
                order.append(r["ts"])
    merged = [by_ts[t] for t in sorted(order)]
    return merged, agreements, overlap_pairs, conflicts


def integrity(merged, files):
    dup = 0
    nonmono = []
    ohlc = []
    zr = 0
    zv = 0
    for f in files:
        seen = set()
        prev = None
        for r in f["rows"]:
            if r["ts"] in seen:
                dup += 1
            seen.add(r["ts"])
            if prev is not None and r["ts"] <= prev:
                nonmono.append({"file": f["name"], "line": r["line"], "ts": fmt_ts(r["ts"])})
            prev = r["ts"]
    for r in merged:
        if r["h"] < max(r["o"], r["c"]) - 1e-9 or r["l"] > min(r["o"], r["c"]) + 1e-9:
            ohlc.append({"file": r["file"], "line": r["line"], "ts": fmt_ts(r["ts"]),
                         "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"]})
        if r["h"] == r["l"]:
            zr += 1
        if r["v"] == 0:
            zv += 1
    return {"duplicate_timestamps": dup, "non_monotonic": nonmono[:50], "non_monotonic_count": len(nonmono),
            "ohlc_violations": ohlc[:50], "ohlc_violation_count": len(ohlc),
            "zero_range": zr, "zero_volume": zv,
            "wrong_field_count_rows": sum(len(f["bad_nf"]) for f in files)}


def gaps_and_holes(merged, thr, med_gap_h):
    gaps = []
    for i in range(len(merged) - 1):
        t1, t2 = merged[i]["ts"], merged[i + 1]["ts"]
        gh = (t2 - t1).total_seconds() / 3600.0
        if gh > thr:
            cls, note = classify_gap(t1, t2, med_gap_h)
            gaps.append({"from": fmt_ts(t1), "to": fmt_ts(t2), "hours": round(gh, 2), "class": cls, "note": note})
    days_with = set(r["ts"].date() for r in merged)
    holes = []
    if merged:
        d = merged[0]["ts"].date()
        end = merged[-1]["ts"].date()
        while d <= end:
            if d not in days_with and d.weekday() != 5 and d.isoformat() not in HOLIDAYS:
                holes.append(d)
            d += timedelta(days=1)
    return gaps, holes


def weekend_seams(merged, thr):
    seams = []
    for i in range(1, len(merged)):
        t1, t2 = merged[i - 1]["ts"], merged[i]["ts"]
        gh = (t2 - t1).total_seconds() / 3600.0
        if gh > thr and t1.weekday() == 4 and t2.weekday() in (6, 0):
            drift = merged[i]["o"] - merged[i - 1]["c"]
            pct = drift / merged[i - 1]["c"] * 100 if merged[i - 1]["c"] else 0
            seams.append({"from": fmt_ts(t1), "to": fmt_ts(t2), "prev_close": merged[i - 1]["c"],
                          "reopen": merged[i]["o"], "drift": round(drift, 4), "drift_pct": round(pct, 4)})
    seams.sort(key=lambda s: -abs(s["drift_pct"]))
    return seams


def bad_ticks(merged, thr):
    flags = []
    for i, r in enumerate(merged):
        reasons = []
        if i > 0:
            pc = merged[i - 1]["c"]
            dc = abs(r["c"] - pc) / pc if pc else 0
            across = (r["ts"] - merged[i - 1]["ts"]).total_seconds() / 3600.0 > thr
            if dc > DT_CLOSE_PCT:
                reasons.append("delta_close %.2f%%%s" % (dc * 100, " across_gap" if across else ""))
        wick = (r["h"] - r["l"]) / r["c"] if r["c"] else 0
        if wick > WICK_PCT:
            reasons.append("wick %.2f%%" % (wick * 100))
        if i + 1 < len(merged):
            nt = merged[i + 1]["ts"]
            if (nt - r["ts"]).total_seconds() / 3600.0 > thr:
                no = merged[i + 1]["o"]
                if round(r["h"], 3) == round(no, 3):
                    reasons.append("H == next-session reopen %.3f" % no)
                if round(r["c"], 3) == round(no, 3):
                    reasons.append("C == next-session reopen %.3f" % no)
        if reasons:
            flags.append({"file": r["file"], "ts": fmt_ts(r["ts"]), "o": r["o"], "h": r["h"],
                          "l": r["l"], "c": r["c"], "v": r["v"], "reason": "; ".join(reasons)})
    return flags


def phase_sweep(fine, coarse, n):
    idx = {r["ts"]: r for r in coarse}
    results = []
    for p in range(n):
        total = 0
        matched = 0
        hits = []
        mism = []
        i = p
        while i + n <= len(fine):
            g = fine[i:i + n]
            key = g[0]["ts"]
            if key in idx:
                total += 1
                cb = idx[key]
                agg = (g[0]["o"], max(x["h"] for x in g), min(x["l"] for x in g), g[-1]["c"],
                       sum(x["v"] for x in g))
                ok = (round(agg[0], 3) == round(cb["o"], 3) and round(agg[1], 3) == round(cb["h"], 3)
                      and round(agg[2], 3) == round(cb["l"], 3) and round(agg[3], 3) == round(cb["c"], 3)
                      and agg[4] == cb["v"])
                if ok:
                    matched += 1
                    hits.append(key)
                elif len(mism) < 5:
                    mism.append({"ts": fmt_ts(key), "agg": [round(a, 3) for a in agg[:4]] + [agg[4]],
                                 "coarse": [cb["o"], cb["h"], cb["l"], cb["c"], cb["v"]]})
            i += n
        span = [fmt_ts(hits[0]), fmt_ts(hits[-1])] if hits else None
        results.append({"phase": p, "compared": total, "exact_match": matched, "span": span, "mismatches": mism})
    return results


def daily_reconcile(fine, daily, mode):
    by_day = {}
    for r in fine:
        d = r["ts"].date() if mode == "printed" else session_day(r["ts"])
        if d not in by_day:
            by_day[d] = [r["h"], r["l"]]
        else:
            by_day[d][0] = max(by_day[d][0], r["h"])
            by_day[d][1] = min(by_day[d][1], r["l"])
    didx = {r["ts"].date(): r for r in daily}
    total = 0
    h_ok = 0
    l_ok = 0
    mism = []
    for d, (h, l) in by_day.items():
        if d in didx:
            total += 1
            if round(h, 3) == round(didx[d]["h"], 3):
                h_ok += 1
            if round(l, 3) == round(didx[d]["l"], 3):
                l_ok += 1
            if round(h, 3) != round(didx[d]["h"], 3) or round(l, 3) != round(didx[d]["l"], 3):
                if len(mism) < 10:
                    mism.append({"day": d.isoformat(), "fine_H": round(h, 3), "fine_L": round(l, 3),
                                 "daily_H": didx[d]["h"], "daily_L": didx[d]["l"]})
    return {"mode": mode, "days_compared": total, "high_match": h_ok, "low_match": l_ok, "mismatches": mism}


def year_stats(merged, tick_size, thr_h):
    by_year = {}
    for r in merged:
        by_year.setdefault(r["ts"].year, []).append(r)
    out = []
    for y in sorted(by_year):
        rows = by_year[y]
        days = len(set(r["ts"].date() for r in rows))
        ranges = [r["h"] - r["l"] for r in rows]
        rpct = [(r["h"] - r["l"]) / r["c"] * 100 for r in rows if r["c"]]
        gaps_min = [(rows[i + 1]["ts"] - rows[i]["ts"]).total_seconds() / 60.0
                    for i in range(len(rows) - 1)
                    if (rows[i + 1]["ts"] - rows[i]["ts"]).total_seconds() / 3600.0 <= thr_h]
        avg_r = mean(ranges) if ranges else 0
        med_r = median(ranges) if ranges else 0
        avg_rp = mean(rpct) if rpct else 0
        med_rp = median(rpct) if rpct else 0
        out.append({"year": y, "bars": len(rows), "active_days": days,
                    "bars_per_day": round(len(rows) / days, 1) if days else 0,
                    "implied_ticks_per_day": round(len(rows) / days * tick_size, 0) if (days and tick_size) else None,
                    "median_min_per_bar": round(median(gaps_min), 2) if gaps_min else None,
                    "avg_range_usd": round(avg_r, 3), "median_range_usd": round(med_r, 3),
                    "avg_range_pct": round(avg_rp, 2), "median_range_pct": round(med_rp, 2),
                    "cost_base_pct_of_avg_range": round(SPREAD_BASE / avg_r * 100, 2) if avg_r else None,
                    "cost_stress_pct_of_avg_range": round(SPREAD_STRESS / avg_r * 100, 2) if avg_r else None})
    return out


def hourly_profile(merged):
    prof = [0] * 24
    first_hour = {}
    for r in merged:
        prof[r["ts"].hour] += 1
        d = r["ts"].date()
        if d not in first_hour or r["ts"] < first_hour[d]:
            first_hour[d] = r["ts"]
    fh = {}
    for d, ts in first_hour.items():
        fh[ts.hour] = fh.get(ts.hour, 0) + 1
    dead = [h for h in range(24) if prof[h] == 0]
    top = sorted(range(24), key=lambda h: -prof[h])[:6]
    return {"profile": prof, "dead_hours": dead, "top_hours": top,
            "first_bar_hour_histogram": dict(sorted(fh.items()))}


def feb_mar_2026(merged):
    rows = [r for r in merged if r["ts"].year == 2026 and r["ts"].month in (2, 3)]
    if not rows:
        return None
    peak = max(rows, key=lambda r: r["h"])
    hc = max(rows, key=lambda r: r["c"])
    big_range = max(rows, key=lambda r: r["h"] - r["l"])
    big_move = None
    for i in range(1, len(rows)):
        pc = rows[i - 1]["c"]
        dc = abs(rows[i]["c"] - pc) / pc * 100 if pc else 0
        if big_move is None or dc > big_move[0]:
            big_move = (dc, rows[i])
    march = [r for r in rows if r["ts"].month == 3]
    trough = min(march, key=lambda r: r["l"]) if march else None
    dd = (hc["c"] - trough["c"]) / hc["c"] * 100 if trough else None
    return {"bars": len(rows),
            "peak_high": peak["h"], "peak_high_ts": fmt_ts(peak["ts"]),
            "max_close": hc["c"], "max_close_ts": fmt_ts(hc["ts"]),
            "max_range_bar": round(big_range["h"] - big_range["l"], 3), "max_range_ts": fmt_ts(big_range["ts"]),
            "max_delta_close_pct": round(big_move[0], 2), "max_delta_close_ts": fmt_ts(big_move[1]["ts"]),
            "march_trough_close": trough["c"] if trough else None,
            "drawdown_from_max_close_pct": round(dd, 2) if dd is not None else None}


def tz_evidence(merged, thr_h):
    prof = hourly_profile(merged)
    fh = {}
    prev = None
    first_of_day = {}
    for r in merged:
        d = r["ts"].date()
        if d not in first_of_day:
            if prev is not None and (r["ts"] - prev).total_seconds() / 3600.0 > thr_h:
                fh[r["ts"].hour] = fh.get(r["ts"].hour, 0) + 1
            first_of_day[d] = r["ts"]
        prev = r["ts"]
    total = sum(fh.values()) or 1
    utc_hit = sum(v for h, v in fh.items() if h in (21, 22, 23))
    srv2_hit = sum(v for h, v in fh.items() if h in (0, 1))
    srv3_hit = sum(v for h, v in fh.items() if h in (1, 2))
    if utc_hit / total > 0.6:
        verdict = "UTC: session-open days (first bar after a >%.0fh gap) start at 21:00-23:59 in %.0f%% of cases; the 21/22 split flips with US DST (EDT/EST), matching the 21:00/22:00 UTC session boundary" % (thr_h, utc_hit / total * 100)
    elif srv2_hit / total > 0.6:
        verdict = "broker server time UTC+2 (session opens at 00:00-01:59 in %.0f%% of cases)" % (srv2_hit / total * 100)
    elif srv3_hit / total > 0.6:
        verdict = "broker server time UTC+3 (session opens at 01:00-02:59 in %.0f%% of cases)" % (srv3_hit / total * 100)
    else:
        verdict = "inconclusive (session-open first-bar hour histogram %s)" % fh
    return verdict, fh


def tick_stats(tick_files):
    all_ticks = []
    for f in tick_files:
        all_ticks.extend(f["ticks"])
    if not all_ticks:
        return None
    all_ticks.sort(key=lambda t: t["ts"])
    per_day = {}
    per_year = {}
    spreads = []
    mids = []
    for t in all_ticks:
        d = t["ts"].date()
        per_day[d] = per_day.get(d, 0) + 1
        per_year[d.year] = per_year.get(d.year, 0) + 1
        spreads.append((t["ask"] - t["bid"]) / PIP_SIZE)
        mids.append((t["ask"] + t["bid"]) / 2)
    spreads.sort()
    dense = sorted(d for d, c in per_day.items() if c > 1000)
    dense_counts = [per_day[d] for d in dense]

    def pct(a, p):
        return a[min(len(a) - 1, int(len(a) * p))]

    return {"files": [f["name"] for f in tick_files],
            "rows": len(all_ticks),
            "first": fmt_ts(all_ticks[0]["ts"]), "last": fmt_ts(all_ticks[-1]["ts"]),
            "days_covered": len(per_day),
            "ticks_per_year": {str(y): per_year[y] for y in sorted(per_year)},
            "dense_days": [d.isoformat() for d in dense],
            "ticks_per_day_dense_median": median(dense_counts) if dense_counts else None,
            "ticks_per_day_dense_max": max(dense_counts) if dense_counts else None,
            "spread_pips": {"min": round(spreads[0], 3), "p50": round(pct(spreads, 0.5), 3),
                            "p90": round(pct(spreads, 0.9), 3), "p99": round(pct(spreads, 0.99), 3),
                            "max": round(spreads[-1], 3)},
            "mid_price_min": round(min(mids), 3), "mid_price_max": round(max(mids), 3)}


def build_report(ctx):
    L = []
    ap = L.append
    synth_tfs = ctx.get("synthetic_tfs", [])
    entry_tf = "t500" if ("t500" in ctx["digest"] and "t500" not in synth_tfs) else "t100"
    ap("# %s PHASE II - DATA RECEIPT & DIGEST" % ctx["instrument"])
    ap("")
    ap("Run: phase2_digest.py (python %s) at %s. Input dir: `%s`. Files found: %d." % (
        ctx["pyver"], ctx["run_ts"], ctx["indir"], len(ctx["files"])))
    ap("")
    ap("## MANIFEST")
    ap("")
    ap("| file | bytes | md5 | rows | first bar | last bar | tf | claimed | actual | symbol |")
    ap("|---|---|---|---|---|---|---|---|---|---|")
    for m in ctx["manifest"]:
        ap("| %s | %d | %s | %d | %s | %s | %s | %s | %s | %s |" % (
            m["name"], m["bytes"], m["md5"], m["rows"], m["first"], m["last"], m["tf"] + (" (tick)" if m.get("kind") == "tick" else " (synth)" if m.get("kind") == "synthetic" else ""),
            m["claimed"].split(" dates:")[0], m["actual"], m["symbol"].replace("-consistent", "")))
    ap("")
    nfiles_tf = {}
    for m in ctx["manifest"]:
        if m.get("kind") in ("bar", "synthetic"):
            nfiles_tf[m["tf"]] = nfiles_tf.get(m["tf"], 0) + 1
    for tf, info in ctx["merged_info"].items():
        ap("- **%s**: %d rows (%d file%s), %s .. %s; overlap %d/%d identical, %d conflicts." % (
            tf, info["rows"], nfiles_tf.get(tf, 1), "s" if nfiles_tf.get(tf, 1) > 1 else "",
            info["first"], info["last"], info["agree"], info["overlap"], info["conflicts"]))
    for m in ctx["manifest"]:
        cy = re.findall(r"(19\d\d|20\d\d)", m["claimed"])
        if cy and m["actual"] != "-":
            cmin, cmax = int(cy[0]), int(cy[-1])
            ay = int(m["actual"][:4])
            if ay > cmin:
                ap("- **UNDER-DELIVERY vs filename**: %s claims %d-%d but actual coverage starts %s (head missing %d+ years)." % (
                    m["name"], cmin, cmax, m["actual"][:10], ay - cmin))
    ap("")
    ap("## FORMAT")
    ap("")
    for m in ctx["manifest"]:
        if m.get("kind") == "tick":
            ap("- %s: 4 fields date,time,bid,ask (raw ticks, ms-precision timestamps) - summarized as tick reference, not bar-scanned." % m["name"])
            continue
        notes = []
        if m["header"]:
            notes.append("header line present: `%s`" % m["header"][:60])
        if m["swapped"]:
            notes.append("field order is time,date (swapped vs expected date,time)")
        if m["delim"] != ",":
            notes.append("delimiter `%s`" % m["delim"])
        if m["bad_nf_count"]:
            notes.append("%d rows with wrong field count (receipt.json)" % m["bad_nf_count"])
        ap("- %s: 7 fields date,time,O,H,L,C,V %s" % (
            m["name"], "confirmed" if not notes else "DEVIATIONS: " + "; ".join(notes)))
    ap("")
    ap("## INTEGRITY")
    ap("")
    for tf, ig in ctx["integrity"].items():
        ap("- **%s**: wrong-field-count %d; OHLC violations %d; duplicate ts %d; non-monotonic %d; zero-range %d; zero-volume %d." % (
            tf, ig["wrong_field_count_rows"], ig["ohlc_violation_count"], ig["duplicate_timestamps"],
            ig["non_monotonic_count"], ig["zero_range"], ig["zero_volume"]))
        for c in ig["ohlc_violations"][:5]:
            ap("  - OHLC violation %s %s line %d O=%.3f H=%.3f L=%.3f C=%.3f V=%s" % (
                c["file"], c["ts"], c["line"], c["o"], c["h"], c["l"], c["c"], c["v"]))
    if ctx["conflicts_all"]:
        ap("- **overlap conflicts (both readings, none silently picked)**: %d" % len(ctx["conflicts_all"]))
        for c in ctx["conflicts_all"][:10]:
            ap("  - %s: %s O=%.3f H=%.3f L=%.3f C=%.3f V=%s vs %s O=%.3f H=%.3f L=%.3f C=%.3f V=%s" % (
                c["ts"], c["a"]["file"], c["a"]["o"], c["a"]["h"], c["a"]["l"], c["a"]["c"], c["a"]["v"],
                c["b"]["file"], c["b"]["o"], c["b"]["h"], c["b"]["l"], c["b"]["c"], c["b"]["v"]))
    ap("")
    ap("## GAPS & SEAMS")
    ap("")
    ap("Timezone evidence (finest timeframe %s): %s (histogram in receipt.json)." % (ctx["tz_tf"], ctx["tz"]))
    for tf, gc in ctx["gap_counts_tf"].items():
        ap("- %s (thr %.1fh): weekend %d, holiday %d, UNEXPLAINED %d." % (
            tf, ctx["thr"][tf], gc.get("weekend", 0), gc.get("holiday", 0), gc.get("UNEXPLAINED", 0)))
    un = [g for g in ctx["gaps"] if g["class"] == "UNEXPLAINED"]
    for g in un[:10]:
        ap("  - UNEXPLAINED %s -> %s (%.1fh)" % (g["from"], g["to"], g["hours"]))
    if len(un) > 10:
        ap("  - ... %d more unexplained gaps in receipt.json" % (len(un) - 10))
    hol_names = {}
    for g in ctx["gaps"]:
        if g["class"] == "holiday":
            for n in g["note"].split("; "):
                hol_names[n] = hol_names.get(n, 0) + 1
    ap("- holiday gaps by name: %s" % "; ".join("%s x%d" % (n, c) for n, c in sorted(hol_names.items(), key=lambda kv: -kv[1])[:8]))
    for tf, holes in ctx["holes_all_tf"].items():
        hd = [datetime.fromisoformat(d).date() for d in holes]
        gr = group_ranges(hd)
        fris = sum(1 for d in hd if d.weekday() == 4)
        note = " (incl. %d Fridays - this timeframe has no Friday bars in part of its range)" % fris if fris > 20 else ""
        ap("- hole map **%s**: %d zero-bar days%s: %s%s" % (
            tf, len(holes), note, ", ".join(gr[:2]), " ... (full map in receipt.json)" if len(gr) > 2 else ""))
    ap("- weekend seams: %d total across timeframes, mean |drift| %.2f%%, worst 5:" % (
        len(ctx["seams"]), mean([abs(s["drift_pct"]) for s in ctx["seams"]]) if ctx["seams"] else 0))
    for s in ctx["seams"][:5]:
        ap("  - [%s] %s -> %s close %.3f reopen %.3f drift %+.3f (%.2f%%)" % (
            s["tf"], s["from"], s["to"], s["prev_close"], s["reopen"], s["drift"], s["drift_pct"]))
    ap("")
    ap("## BAD TICKS")
    ap("")
    for tf, fl in ctx["flags"].items():
        reasons = {}
        for f in fl:
            for r in f["reason"].split("; "):
                key = r.split(" ")[0]
                reasons[key] = reasons.get(key, 0) + 1
        ap("- **%s**: %d flagged bars (%s). Full rows in anomalies.csv." % (
            tf, len(fl), "; ".join("%s x%d" % kv for kv in sorted(reasons.items(), key=lambda kv: -kv[1]))))
        if tf == entry_tf:
            for f in fl[:2]:
                ap("  - %s %s O=%.3f H=%.3f L=%.3f C=%.3f V=%s [%s]" % (
                    f["file"], f["ts"], f["o"], f["h"], f["l"], f["c"], f["v"], f["reason"]))
    ap("")
    ap("## CROSS-VALIDATION")
    ap("")
    ap("- same-timeframe overlaps: %s" % ("; ".join("%s %d/%d identical" % (tf, i["agree"], i["overlap"]) for tf, i in ctx["merged_info"].items() if i["overlap"]) or "no same-timeframe overlaps (one file per timeframe)"))
    for cv in ctx["crossval"]:
        ap("- %s" % cv)
    if not ctx["crossval"]:
        ap("- no cross-timeframe checks possible.")
    ap("")
    ap("## CALIBRATION DIGEST")
    ap("")

    ap("(per-year tables shown for %d+; full history incl. pre-%d in receipt.json. Cost tiers for %s: base %.4f, stress %.4f per unit = %.3f/%.3f pips, as %% of avg bar range.)" % (
        DIGEST_MIN_YEAR, DIGEST_MIN_YEAR, ctx["instrument"], SPREAD_BASE, SPREAD_STRESS, SPREAD_BASE / PIP_SIZE, SPREAD_STRESS / PIP_SIZE))
    ap("")
    ts = ctx.get("tick_stats")
    if ts:
        ap("### tick reference (%s)" % ", ".join(ts["files"]))
        ap("- %d raw ticks, %s .. %s, %d days covered; ticks/year (full in receipt.json): %s" % (
            ts["rows"], ts["first"], ts["last"], ts["days_covered"],
            "; ".join("%s:%d" % (y, c) for y, c in sorted(ts["ticks_per_year"].items())[-3:])))
        ap("- dense days (>1000 ticks): %s" % (", ".join(ts["dense_days"][:10]) + (" ..." if len(ts["dense_days"]) > 10 else "")))
        ap("- measured ticks/day on dense days: median %d, max %d (tick-rate reference); measured spread (ask-bid): min %.3f p50 %.3f p90 %.3f p99 %.3f max %.3f pips; mid price %.3f..%.3f" % (
            ts["ticks_per_day_dense_median"], ts["ticks_per_day_dense_max"],
            ts["spread_pips"]["min"], ts["spread_pips"]["p50"], ts["spread_pips"]["p90"], ts["spread_pips"]["p99"], ts["spread_pips"]["max"],
            ts["mid_price_min"], ts["mid_price_max"]))
        ap("")
    for tf, dg in ctx["digest"].items():
        ap("### %s (reference bars/day ~%s; ref ticks/day ~%s)" % (tf, REF_BARS_PER_DAY.get(tf, "n/a"), GOLD_TICK_REF if (INSTRUMENT == "XAUUSD" or ctx.get("tick_stats")) else "n/a (no tick file this run)"))
        ap("")
        if tf not in ("t100", "t500") or tf in synth_tfs:
            ys = [s for s in dg["years"] if s["year"] >= DIGEST_MIN_YEAR]
            if tf in synth_tfs:
                ap("- SYNTHETIC timeframe (derived from t100); per-year table omitted as redundant with t100 - see receipt.json.")
            ap("- %s: cross-validation/synthetic frame; per-year table and %d+ stats in receipt.json." % (tf, DIGEST_MIN_YEAR))
            ap("")
            continue
        ap("| year | bars | days | bars/day | ticks/day | min/bar | avg rng | med rng | avg rng % | base % | stress % |")
        ap("|---|---|---|---|---|---|---|---|---|---|---|")
        for s in dg["years"]:
            if s["year"] < DIGEST_MIN_YEAR:
                continue
            ap("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                s["year"], s["bars"], s["active_days"], s["bars_per_day"],
                s["implied_ticks_per_day"] if s["implied_ticks_per_day"] is not None else "-",
                s["median_min_per_bar"] if s["median_min_per_bar"] is not None else "-",
                s["avg_range_usd"], s["median_range_usd"], s["avg_range_pct"],
                s["cost_base_pct_of_avg_range"] if s["cost_base_pct_of_avg_range"] is not None else "-",
                s["cost_stress_pct_of_avg_range"] if s["cost_stress_pct_of_avg_range"] is not None else "-"))
        ap("")
        unexpl = ctx["gap_counts_tf"].get(tf, {}).get("UNEXPLAINED", 0)
        holes_n = len(ctx["holes_all_tf"].get(tf, []))
        dev = []
        for s in dg["years"]:
            ref = REF_BARS_PER_DAY.get(tf)
            if ref and s["active_days"] >= 100 and abs(s["bars_per_day"] - ref) / ref > 0.25:
                direction = "ABOVE ref - higher tick throughput (vol regime)" if s["bars_per_day"] > ref else "BELOW ref - but %d unexplained gaps / %d hole days, so not missing data: real lower tick throughput" % (unexpl, holes_n)
                dev.append("%d: %.1f bars/day vs ref ~%d (%.0f%% off, %s)" % (s["year"], s["bars_per_day"], ref, (s["bars_per_day"] / ref - 1) * 100, direction))
        if dev:
            ap("**DEVIATION vs reference**: " + "; ".join(dev))
        if tf == "t100" and ctx.get("tick_stats") and ctx["tick_stats"].get("ticks_per_day_dense_median"):
            s26 = [x for x in dg["years"] if x["year"] == 2026 and x["implied_ticks_per_day"]]
            if s26:
                ap("- implied ticks/day 2026 (t100 bars/day x 100): %d vs measured dense-day tick rate %d/day." % (
                    s26[0]["implied_ticks_per_day"], ctx["tick_stats"]["ticks_per_day_dense_median"]))
        if tf == entry_tf:
            ap("- hourly bar density (00-24, printed hours): %s" % " ".join("%02d:%d" % (h, c) for h, c in enumerate(dg["hourly"]["profile"]) if c))
            ap("- dead hours: %s; top hours: %s" % (
                ",".join("%02d" % h for h in dg["hourly"]["dead_hours"]) or "none",
                ",".join("%02d" % h for h in dg["hourly"]["top_hours"])))
        if dg["febmar"] and tf == entry_tf:
            f = dg["febmar"]
            ap("- Feb-Mar 2026: peak H %.3f @ %s; max close %.3f @ %s; max bar range %.3f @ %s; max |dC| %.2f%% @ %s; March trough close %.3f; drawdown from max close %.2f%%." % (
                f["peak_high"], f["peak_high_ts"], f["max_close"], f["max_close_ts"], f["max_range_bar"], f["max_range_ts"],
                f["max_delta_close_pct"], f["max_delta_close_ts"], f["march_trough_close"], f["drawdown_from_max_close_pct"]))
    ap("")
    ap("## PHASE II READINESS")
    ap("")
    for line in ctx["readiness"]:
        ap("- %s" % line)
    ap("")
    ap("## METHOD")
    ap("")
    ap("- Tool: `phase2_digest.py` (python %s, stdlib only): `python3 phase2_digest.py <input_dir> [--instrument I --spread-base B --spread-stress S --pip P --synth-t500] [--out DIR]`; artifacts written next to the data; raw files read-only (in-memory copies)." % ctx["pyver"])
    ap("- Parse: CSV, delimiter/header auto-detected; dates YYYY.MM.DD/YYYY-MM-DD/YYYY/MM/DD/YYYYMMDD; times HH:MM[:SS[.fff]]; bar files = 7 fields date,time,O,H,L,C,V (time,date auto-swapped); tick files = 4 fields date,time,bid,ask (ms timestamps) summarized as tick reference only. Bar timestamps are OPEN times, printed as-is; close-time = next bar open; last bar of each file open-ended.")
    ap("- Symbol gate per file: median price outside the " + INSTRUMENT + " range (" + {"GBPJPY": "100-300", "EURUSD": "0.5-2.0", "XTIUSD": "40-130"}.get(INSTRUMENT, ">=200") + ") => SUSPECT wrong symbol, excluded from merge, both readings reported. Refs: XAUUSD ~1798->~4500s; GBPJPY ~124-220; EURUSD ~0.8-1.6; XTIUSD ~$63-114, ~75000 ticks/day.")
    ap("- Merge per timeframe: dedupe by timestamp across files; overlaps compared bit-for-bit on printed OHLCV; conflicts reported with both readings (first file kept for stats, count disclosed). Integrity: field count != 7; H < max(O,C) or L > min(O,C); duplicate/non-monotonic timestamps; zero-range; zero-volume.")
    ap("- Gap threshold per timeframe = max(6h, 2.5x median inter-bar gap). Class: weekend = Thu/Fri/Sat -> Sun/Mon 40-80h (intraday DST-adjusted 48-50h: 49h + Sun-Fri UTC offset, 4h EDT / 5h EST); holiday = span covers a computed US federal holiday 1998-2026 (Good Friday via computus, observance shifts, + 2025-01-09); else UNEXPLAINED (each listed). Hole map: zero-bar dates in [first,last] excl. Saturdays + listed holidays.")
    ap("- Bad ticks (instrument-scaled, % of price): |dClose| > 1.5% of prev close (across_gap if gap > threshold), wick (H-L) > 2.5% of close, H or C == next session's reopen open (3dp) after such a gap (feed-contamination class). All flagged -> anomalies.csv; nothing deleted or fixed.")
    ap("- Cross-validation: same-timeframe overlap equality; t500 = groups of 5 consecutive t100 (all 5 phases swept from file start, exact OHLCV + span); t300 = groups of 3; t100/t750 vs groups of 100/750 t1 ticks (mid and bid); daily H/L of finest frame vs h4/d1 under BOTH day definitions: printed date and DST-aware session day (open 22:00 UTC EDT / 23:00 UTC EST); --synth-t500 builds t500 from t100 groups of 5 phase 0, marked SYNTHETIC (on XAUUSD native t500 matched phase 3, 375380/375380 exact, so synthetic phase-0 grid is not bit-identical to the native chart).")
    ap("- Digest: per-year bars/day, implied ticks/day = bars/day x tick size, median min/bar, avg/median range and % of close; cost ratio = spread / avg range (base " + str(SPREAD_BASE) + ", stress " + str(SPREAD_STRESS) + " per unit = " + str(round(SPREAD_BASE / PIP_SIZE, 2)) + "/" + str(round(SPREAD_STRESS / PIP_SIZE, 2)) + " pips); hourly density on printed hours; Feb-Mar 2026 blowoff/crash metrics; weekend seam drift = reopen - prior close. Timezone: session-open first-bar hour histogram of finest timeframe vs the 21:00/22:00 UTC boundary (DST-shifting).")
    ap("- Budget: REPORT.md hard-capped at 15 KB (long lists truncated here; full detail in receipt.json / anomalies.csv). Prices 3dp, percentages 2dp, timestamps full date+time as printed.")
    ap("")
    text = "\n".join(L)
    if len(text.encode("utf-8")) > REPORT_BUDGET:
        text = text[:REPORT_BUDGET] + "\n\n[truncated at 15 KB budget; full detail in receipt.json / anomalies.csv]\n"
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("indir", nargs="?", default=".")
    ap.add_argument("--out", default=None)
    ap.add_argument("--instrument", default="XAUUSD")
    ap.add_argument("--spread-base", type=float, default=0.065)
    ap.add_argument("--spread-stress", type=float, default=0.30)
    ap.add_argument("--pip", type=float, default=None)
    ap.add_argument("--synth-t500", action="store_true")
    args = ap.parse_args()
    global INSTRUMENT, SPREAD_BASE, SPREAD_STRESS, PIP_SIZE, REF_BARS_PER_DAY, GOLD_TICK_REF
    INSTRUMENT = args.instrument.upper()
    SPREAD_BASE = args.spread_base
    SPREAD_STRESS = args.spread_stress
    PIP_SIZE = args.pip if args.pip else (0.01 if "JPY" in INSTRUMENT else 0.0001)
    if INSTRUMENT == "XTIUSD":
        REF_BARS_PER_DAY = {"t50": 906, "t300": 234, "t100": 750}
        GOLD_TICK_REF = 75000
    elif INSTRUMENT != "XAUUSD":
        REF_BARS_PER_DAY = {}
    indir = os.path.abspath(args.indir)
    outdir = os.path.abspath(args.out) if args.out else indir
    os.makedirs(outdir, exist_ok=True)

    files = []
    for name in sorted(os.listdir(indir)):
        p = os.path.join(indir, name)
        if os.path.isfile(p) and name.lower().endswith(".csv") and name.lower() != "anomalies.csv":
            files.append(load_file(p))

    manifest = []
    for f in files:
        tf, tick = infer_timeframe(f["name"])
        sym, sym_note = infer_symbol(f["name"], f["rows"], f["ticks"])
        rows = f["rows"] if f["rows"] else f["ticks"]
        kind = "bar" if f["rows"] else ("tick" if f["ticks"] else "empty")
        first = fmt_ts(min(r["ts"] for r in rows)) if rows else "-"
        last = fmt_ts(max(r["ts"] for r in rows)) if rows else "-"
        manifest.append({"name": f["name"], "bytes": f["bytes"], "md5": f["md5"],
                         "rows": len(f["rows"]) if f["rows"] else len(f["ticks"]), "kind": kind,
                         "first": first, "last": last, "tf": tf, "claimed": claimed_coverage(f["name"]),
                         "actual": ("%s .. %s" % (first, last)) if rows else "-",
                         "symbol": sym, "symbol_note": sym_note, "header": f["header"],
                         "swapped": f["swapped"], "delim": f["delim"],
                         "bad_nf_count": len(f["bad_nf"]), "bad_nf": f["bad_nf"][:20],
                         "tick_size": tick})

    gold_files = [f for f, m in zip(files, manifest) if m["symbol"].startswith(INSTRUMENT)]
    gold_manifest = [m for m in manifest if m["symbol"].startswith(INSTRUMENT)]
    suspect_files = [(m["name"], m["symbol"], m["symbol_note"]) for m in manifest if not m["symbol"].startswith(INSTRUMENT)]
    tick_files = [f for f in gold_files if f["ticks"] and not f["rows"]]

    by_tf = {}
    for f, m in zip(gold_files, gold_manifest):
        if f["rows"]:
            by_tf.setdefault(m["tf"], []).append(f)

    synth_t500 = False
    if args.synth_t500 and "t100" in by_tf and "t500" not in by_tf:
        fine = merge_timeframe(by_tf["t100"])[0]
        synth_rows = []
        for i in range(0, len(fine) - 4, 5):
            g = fine[i:i + 5]
            synth_rows.append({"ts": g[0]["ts"], "o": g[0]["o"], "h": max(x["h"] for x in g),
                               "l": min(x["l"] for x in g), "c": g[-1]["c"], "v": sum(x["v"] for x in g),
                               "nf": 7, "raw": "", "line": 0, "file": "SYNTHETIC t500 (groups of 5 t100, phase 0)"})
        sf = {"name": "SYNTHETIC t500 from t100 (groups of 5, phase 0)", "bytes": 0, "md5": "synthetic",
              "rows": synth_rows, "ticks": [], "bad_nf": [], "header": None, "swapped": False, "delim": ","}
        by_tf["t500"] = [sf]
        manifest.append({"name": sf["name"], "bytes": 0, "md5": "synthetic", "rows": len(synth_rows), "kind": "synthetic",
                         "first": fmt_ts(synth_rows[0]["ts"]), "last": fmt_ts(synth_rows[-1]["ts"]), "tf": "t500",
                         "claimed": "synthetic from t100", "actual": "%s .. %s" % (fmt_ts(synth_rows[0]["ts"]), fmt_ts(synth_rows[-1]["ts"])),
                         "symbol": INSTRUMENT + "-consistent (derived)", "symbol_note": "derived from t100", "header": None,
                         "swapped": False, "delim": ",", "bad_nf_count": 0, "bad_nf": [], "tick_size": 500})
        gold_files = gold_files + [sf]
        gold_manifest = [m for m in manifest if m["symbol"].startswith(INSTRUMENT)]
        synth_t500 = True

    merged_info = {}
    integrity_res = {}
    gaps_all = []
    holes_all = {}
    seams_all = {}
    flags = {}
    conflicts_all = []
    merged_by_tf = {}
    thr = {}
    gap_counts_tf = {}
    for tf, flist in sorted(by_tf.items()):
        merged, agree, overlap, conflicts = merge_timeframe(flist)
        merged_by_tf[tf] = merged
        conflicts_all.extend(conflicts)
        t, med = tf_gap_threshold(merged)
        thr[tf] = round(t, 2)
        merged_info[tf] = {"rows": len(merged),
                           "first": fmt_ts(merged[0]["ts"]) if merged else "-",
                           "last": fmt_ts(merged[-1]["ts"]) if merged else "-",
                           "active_days": len(set(r["ts"].date() for r in merged)),
                           "agree": agree, "overlap": overlap, "conflicts": len(conflicts)}
        integrity_res[tf] = integrity(merged, flist)
        g, h = gaps_and_holes(merged, t, med)
        gc = {}
        for gg in g:
            gc[gg["class"]] = gc.get(gg["class"], 0) + 1
            gg["tf"] = tf
        gap_counts_tf[tf] = gc
        gaps_all.extend(g)
        holes_all[tf] = [d.isoformat() for d in h]
        seams_all[tf] = weekend_seams(merged, t)
        flags[tf] = bad_ticks(merged, t)

    crossval = []
    sweeps = {}
    tfs = set(merged_by_tf.keys())
    tf_tick = {m["tf"]: (m["tick_size"] or 10 ** 9) for m in gold_manifest}
    finetick = lambda excl: sorted([t for t in tfs if t not in excl], key=lambda t: (tf_tick.get(t, 10 ** 9), t))[0] if any(t not in excl for t in tfs) else None
    if "t100" in tfs and "t500" in tfs:
        sw = phase_sweep(merged_by_tf["t100"], merged_by_tf["t500"], 5)
        sweeps["t500_from_t100"] = sw
        tot_coarse = len(merged_by_tf["t500"])
        tot_match = 0
        for r in sw:
            if r["exact_match"]:
                span = " (%s .. %s)" % (r["span"][0], r["span"][1]) if r["span"] else ""
                crossval.append("t500 vs groups-of-5 t100, phase %d: %d/%d exact OHLCV matches%s" % (
                    r["phase"], r["exact_match"], r["compared"], span))
                tot_match += r["exact_match"]
        crossval.append("t500 bars reproducible from t100 overall: %d/%d (%.2f%%); remainder = t500 tail beyond t100 end + phase-boundary groups" % (
            tot_match, tot_coarse, tot_match / tot_coarse * 100))
    if "t100" in tfs and "t300" in tfs:
        sw = phase_sweep(merged_by_tf["t100"], merged_by_tf["t300"], 3)
        sweeps["t300_from_t100"] = sw
        for r in sw:
            crossval.append("t300 vs groups-of-3 t100, phase %d: %d/%d exact OHLCV matches" % (r["phase"], r["exact_match"], r["compared"]))
    tstats = tick_stats(tick_files) if tick_files else None
    if tstats and tstats.get("ticks_per_day_dense_median"):
        GOLD_TICK_REF = int(tstats["ticks_per_day_dense_median"])
    if tstats:
        all_ticks = []
        for f in tick_files:
            all_ticks.extend(f["ticks"])
        all_ticks.sort(key=lambda t: t["ts"])
        for basis in ("mid", "bid"):
            tb = []
            for t in all_ticks:
                px = (t["bid"] + t["ask"]) / 2 if basis == "mid" else t["bid"]
                tb.append({"ts": t["ts"], "o": px, "h": px, "l": px, "c": px, "v": 1})
            for coarse_tf, n in (("t100", 100), ("t750", 750)):
                if coarse_tf in tfs:
                    sw = phase_sweep(tb, merged_by_tf[coarse_tf], n)
                    sweeps["%s_from_t1_%s" % (coarse_tf, basis)] = sw
                    best = [r for r in sw if r["compared"] > 0]
                    best.sort(key=lambda r: -r["exact_match"])
                    for r in best[:2]:
                        crossval.append("%s vs groups-of-%d t1 ticks (%s), phase %d: %d/%d exact%s" % (
                            coarse_tf, n, basis, r["phase"], r["exact_match"], r["compared"],
                            " (%s .. %s)" % (r["span"][0], r["span"][1]) if r["span"] else ""))
        tick_sw = [c for c in crossval if "t1 ticks" in c]
        if tick_sw and all("0/" in c.split(": ")[1] for c in tick_sw):
            crossval = [c for c in crossval if "t1 ticks" not in c]
            for coarse_tf, n in (("t100", 100), ("t750", 750)):
                if coarse_tf in tfs:
                    crossval.append("%s vs groups-of-%d t1 ticks: 0 exact matches across all phases (mid+bid) - only sparse-tick false alignments; inconclusive, tick file not dense over %s range" % (coarse_tf, n, coarse_tf))
        for coarse_tf, n in (("t100", 100), ("t750", 750)):
            if coarse_tf in tfs and not any(c.startswith(coarse_tf + " vs groups-of-%d" % n) for c in crossval):
                crossval.append("%s vs groups-of-%d t1 ticks: no timestamp overlap (tick file sparse except dense days %s; check inconclusive)" % (
                    coarse_tf, n, ", ".join(tstats["dense_days"][:4])))
        if "t100" in tfs:
            t100_day = Counter(r["ts"].date() for r in merged_by_tf["t100"])
            per_day = Counter(t["ts"].date() for t in all_ticks)
            both = [d for d in tstats["dense_days"] if per_day.get(datetime.fromisoformat(d).date(), 0) and t100_day.get(datetime.fromisoformat(d).date(), 0)]
            if both:
                for d in both[:5]:
                    dd = datetime.fromisoformat(d).date()
                    measured = per_day.get(dd, 0)
                    implied = t100_day.get(dd, 0) * 100
                    crossval.append("day %s: t1 ticks %d vs t100 bars %d -> implied ticks %d, ratio implied/measured %.3f" % (
                        d, measured, t100_day.get(dd, 0), implied, implied / measured if measured else 0))
            else:
                crossval.append("no overlap between dense tick days (%s) and t100 coverage (t100 ends %s) - implied-vs-measured tick-rate check inconclusive; dense-day tick rate stands alone." % (
                    ", ".join(tstats["dense_days"][:4]), merged_info["t100"]["last"][:10] if "t100" in merged_info else "-"))
    recon = {}
    if "d1" in tfs:
        fine_tf = finetick({"d1"})
        if fine_tf:
            for mode in ("printed", "session"):
                rec = daily_reconcile(merged_by_tf[fine_tf], merged_by_tf["d1"], mode)
                recon["%s_vs_d1_%s" % (fine_tf, mode)] = rec
                crossval.append("daily H/L %s vs d1, %s-day: %d days, H match %d (%.1f%%), L match %d (%.1f%%)" % (
                    fine_tf, mode, rec["days_compared"], rec["high_match"], rec["high_match"] / rec["days_compared"] * 100 if rec["days_compared"] else 0,
                    rec["low_match"], rec["low_match"] / rec["days_compared"] * 100 if rec["days_compared"] else 0))
    if "h4" in tfs:
        fine_tf = finetick({"d1", "h4"})
        if fine_tf:
            for mode in ("printed", "session"):
                rec = daily_reconcile(merged_by_tf[fine_tf], merged_by_tf["h4"], mode)
                recon["%s_vs_h4_%s" % (fine_tf, mode)] = rec
                crossval.append("daily H/L %s vs h4, %s-day: %d days, H match %d, L match %d" % (
                    fine_tf, mode, rec["days_compared"], rec["high_match"], rec["low_match"]))
        if "d1" in tfs:
            rec = daily_reconcile(merged_by_tf["h4"], merged_by_tf["d1"], "session")
            recon["h4_vs_d1_session"] = rec
            crossval.append("daily H/L h4 vs d1, session-day: %d days, H match %d (%.1f%%), L match %d (%.1f%%) - h4 grid is offset from the d1 day stamp, both readings reported" % (
                rec["days_compared"], rec["high_match"], rec["high_match"] / rec["days_compared"] * 100 if rec["days_compared"] else 0,
                rec["low_match"], rec["low_match"] / rec["days_compared"] * 100 if rec["days_compared"] else 0))

    digest = {}
    for tf, merged in merged_by_tf.items():
        tick = next((m["tick_size"] for m in gold_manifest if m["tf"] == tf), None)
        digest[tf] = {"years": year_stats(merged, tick, thr[tf]), "hourly": hourly_profile(merged),
                      "febmar": feb_mar_2026(merged)}

    tz_tf = sorted(merged_by_tf.keys(), key=lambda t: (tf_tick.get(t, 10 ** 9), t))[0] if merged_by_tf else None
    tz = "no data"
    tz_hist = {}
    if tz_tf:
        tz, tz_hist = tz_evidence(merged_by_tf[tz_tf], thr[tz_tf])

    seams_flat = []
    for tf, s in seams_all.items():
        for x in s:
            x["tf"] = tf
        seams_flat.extend(s)
    seams_flat.sort(key=lambda s: -abs(s["drift_pct"]))

    present = sorted(merged_by_tf.keys())
    readiness = []
    cov = lambda t: "%s..%s" % (merged_info[t]["first"][:10], merged_info[t]["last"][:10]) if t in merged_info else "-"
    if "t500" in merged_by_tf:
        note = " (SYNTHETIC from t100, groups of 5 phase 0; native export preferred for chart parity)" if synth_t500 else ""
        readiness.append("t500 %s: MA layer READY (%d bars)%s." % (cov("t500"), merged_info["t500"]["rows"], note))
    else:
        readiness.append("t500 ABSENT: MA layer not runnable; t500 exports required.")
    if "t100" in merged_by_tf:
        if "t500" in merged_by_tf:
            readiness.append("t100 %s: entry layer READY (%d bars); faithful-transpose cells (entry t100 + MA t500, wall-time separation as the transposition key) runnable offline." % (cov("t100"), merged_info["t100"]["rows"]))
        else:
            readiness.append("t100 %s: entry layer READY (%d bars), but faithful-transpose cells NOT runnable - t500 MA layer absent, t500 exports required." % (cov("t100"), merged_info["t100"]["rows"]))
    else:
        readiness.append("t100 entry layer ABSENT - faithful-transpose cells not yet runnable offline; t100 exports still required. t300/t750 cells are not derivable from t500 alone.")
    if "t500" in merged_by_tf and "t100" in merged_by_tf:
        gap_n = len(merged_by_tf["t500"]) - sum(r["exact_match"] for r in sweeps.get("t500_from_t100", []))
        if gap_n > 0:
            readiness.append("coverage mismatch: t500 extends to %s, t100 only to %s - the last %d t500 bars have no t100 entry-layer coverage." % (
                merged_info["t500"]["last"][:10], merged_info["t100"]["last"][:10], gap_n))
    missing = [t for t in ("t300", "t500", "t750") if t not in merged_by_tf]
    if missing:
        readiness.append("not present in this run: %s. t300 would be derivable from t100 (groups of 3, phase calibrated by sweep) if t100 present; t750 from t1 ticks (groups of 750) where tick coverage exists; neither is derivable from a coarser bar file alone." % ", ".join(missing))
    extra = [t for t in ("t300", "t750", "h4", "d1") if t in merged_by_tf]
    if extra:
        missing = [t for t in ("t300", "t750") if t not in merged_by_tf]
        readiness.append("present extra timeframes enabling cross-validation: %s.%s" % (
            ", ".join(extra), " NOT present in this run: %s." % ", ".join(missing) if missing else ""))
    readiness.append("No strategy backtest in this run - receipt and digest only; the strategy grid is a separate, later prompt.")

    all_flags = [f for tf in flags for f in flags[tf]]
    with open(os.path.join(outdir, "anomalies.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "timestamp", "open", "high", "low", "close", "volume", "reason"])
        for f in all_flags:
            w.writerow([f["file"], f["ts"], "%.3f" % f["o"], "%.3f" % f["h"], "%.3f" % f["l"],
                        "%.3f" % f["c"], f["v"], f["reason"]])

    ctx = {"pyver": sys.version.split()[0],
           "run_ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), "indir": indir,
           "files": files, "manifest": manifest, "merged_info": merged_info,
           "integrity": integrity_res, "conflicts_all": conflicts_all, "gaps": gaps_all,
           "gap_counts_tf": gap_counts_tf, "thr": thr,
           "holes_all_tf": holes_all,
           "seams": seams_flat, "flags": flags, "crossval": crossval, "digest": digest,
           "tz": tz, "tz_tf": tz_tf or "-", "tz_hist": {str(k): v for k, v in tz_hist.items()},
           "readiness": readiness, "suspect_files": suspect_files,
           "instrument": INSTRUMENT, "tick_stats": tstats,
           "synthetic_tfs": ["t500"] if synth_t500 else []}
    report = build_report(ctx)
    with open(os.path.join(outdir, "REPORT.md"), "w") as fh:
        fh.write(report)

    receipt = {"run": ctx["run_ts"], "tool": "phase2_digest.py", "python": ctx["pyver"],
               "instrument": INSTRUMENT, "pip_size": PIP_SIZE, "tick_stats": tstats,
               "input_dir": indir, "files": manifest, "suspect_files": suspect_files,
               "merged": merged_info, "gap_thresholds_h": thr, "integrity": integrity_res,
               "conflicts": conflicts_all, "gaps": gaps_all, "gap_counts_per_tf": gap_counts_tf,
               "hole_map": holes_all, "weekend_seams": seams_all,
               "anomaly_counts": {tf: len(v) for tf, v in flags.items()},
               "cross_validation": crossval, "phase_sweeps": sweeps, "reconciliations": recon,
               "digest": digest, "timezone": tz, "timezone_timeframe": tz_tf,
               "first_bar_hour_histogram": ctx["tz_hist"], "readiness": readiness,
               "thresholds": {"delta_close_pct": DT_CLOSE_PCT, "wick_pct": WICK_PCT,
                              "gap_hours_floor": GAP_H, "gap_threshold_rule": "max(6h, 2.5x median inter-bar gap per timeframe)",
                              "spread_base": SPREAD_BASE, "spread_stress": SPREAD_STRESS,
                              "gold_tick_ref_per_day": GOLD_TICK_REF,
                              "session_day_open_utc": "22:00 EDT / 23:00 EST (DST-aware)"}}
    with open(os.path.join(outdir, "receipt.json"), "w") as fh:
        json.dump(receipt, fh, indent=1, default=str)

    print("files=%d timeframes=%s anomalies=%d report_bytes=%d" % (
        len(files), sorted(merged_by_tf.keys()), len(all_flags), len(report.encode("utf-8"))))
    print("outputs: %s" % outdir)


if __name__ == "__main__":
    main()
