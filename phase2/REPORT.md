# XTIUSD PHASE II - DATA RECEIPT & DIGEST

Run: phase2_digest.py (python 3.12.14) at 2026-11-22 15:45:34 UTC. Input dir: `/workspace/XTIUSD`. Files found: 1.

## MANIFEST

| file | bytes | md5 | rows | first bar | last bar | tf | claimed | actual | symbol |
|---|---|---|---|---|---|---|---|---|---|
| CCMonthCapture XTIUSD t100 20260501-20261121.csv | 4130448 | 1abcfb10126fcf3f1f6bf11c9ca8c1e4 | 83308 | 2026-05-01 00:01:06 | 2026-11-20 21:54:37 | t100 | 2026 | 2026-05-01 00:01:06 .. 2026-11-20 21:54:37 | XTIUSD? |

- **t100**: 83308 rows (1 file), 2026-05-01 00:01:06 .. 2026-11-20 21:54:37; overlap 0/0 identical, 0 conflicts.

## FORMAT

- CCMonthCapture XTIUSD t100 20260501-20261121.csv: 7 fields date,time,O,H,L,C,V confirmed

## INTEGRITY

- **t100**: wrong-field-count 0; OHLC violations 0; duplicate ts 0; non-monotonic 0; zero-range 0; zero-volume 0.

## GAPS & SEAMS

Timezone evidence (finest timeframe t100): UTC: session-open days (first bar after a >6h gap) start at 21:00-23:59 in 100% of cases; the 21/22 split flips with US DST (EDT/EST), matching the 21:00/22:00 UTC session boundary (histogram in receipt.json).
- t100 (thr 6.0h): weekend 29, holiday 0, UNEXPLAINED 0.
- holiday gaps by name: 
- hole map **t100**: 0 zero-bar days: 
- weekend seams: 29 total across timeframes, mean |drift| 0.08%, worst 5:
  - [t100] 2026-05-29 20:53:04 -> 2026-05-31 22:00:21 close 90.190 reopen 90.990 drift +0.800 (0.89%)
  - [t100] 2026-10-30 20:51:18 -> 2026-11-01 23:00:26 close 103.513 reopen 103.012 drift -0.501 (-0.48%)
  - [t100] 2026-10-09 20:52:36 -> 2026-10-11 22:01:31 close 92.660 reopen 92.333 drift -0.327 (-0.35%)
  - [t100] 2026-05-22 20:56:01 -> 2026-05-24 22:00:42 close 95.340 reopen 95.440 drift +0.100 (0.10%)
  - [t100] 2026-07-17 20:55:33 -> 2026-07-19 22:00:34 close 84.080 reopen 84.160 drift +0.080 (0.10%)

## BAD TICKS

- **t100**: 21 flagged bars (delta_close x21; wick x11). Full rows in anomalies.csv.
  - CCMonthCapture XTIUSD t100 20260501-20261121.csv 2026-05-01 20:54:58 O=103.740 H=103.860 L=101.180 C=101.250 V=100 [delta_close 2.39%; wick 2.65%]
  - CCMonthCapture XTIUSD t100 20260501-20261121.csv 2026-05-05 22:50:19 O=103.290 H=103.320 L=100.250 C=100.340 V=100 [delta_close 2.87%; wick 3.06%]

## CROSS-VALIDATION

- same-timeframe overlaps: no same-timeframe overlaps (one file per timeframe)
- no cross-timeframe checks possible.

## CALIBRATION DIGEST

(per-year tables shown for 2021+; full history incl. pre-2021 in receipt.json. Cost tiers for XTIUSD: base 0.0200, stress 0.0400 per unit = 2.000/4.000 pips, as % of avg bar range.)

### t100 (reference bars/day ~750; ref ticks/day ~n/a (no tick file this run))

| year | bars | days | bars/day | ticks/day | min/bar | avg rng | med rng | avg rng % | base % | stress % |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026 | 83308 | 175 | 476.0 | 47605.0 | 1.8 | 0.156 | 0.14 | 0.17 | 12.82 | 25.64 |

**DEVIATION vs reference**: 2026: 476.0 bars/day vs ref ~750 (-37% off, BELOW ref - but 0 unexplained gaps / 0 hole days, so not missing data: real lower tick throughput)
- hourly bar density (00-24, printed hours): 00:1886 01:3705 02:2407 03:1829 04:1268 05:2373 06:3392 07:4041 08:5287 09:4245 10:3958 11:3999 12:4806 13:6518 14:6389 15:6358 16:5132 17:4498 18:4412 19:2844 20:1979 21:261 22:972 23:749
- dead hours: none; top hours: 13,14,15,08,16,12

## PHASE II READINESS

- t500 ABSENT: MA layer not runnable; t500 exports required.
- t100 2026-05-01..2026-11-20: entry layer READY (83308 bars), but faithful-transpose cells NOT runnable - t500 MA layer absent, t500 exports required.
- not present in this run: t300, t500, t750. t300 would be derivable from t100 (groups of 3, phase calibrated by sweep) if t100 present; t750 from t1 ticks (groups of 750) where tick coverage exists; neither is derivable from a coarser bar file alone.
- No strategy backtest in this run - receipt and digest only; the strategy grid is a separate, later prompt.

## METHOD

- Tool: `phase2_digest.py` (python 3.12.14, stdlib only): `python3 phase2_digest.py <input_dir> [--instrument I --spread-base B --spread-stress S --pip P --synth-t500] [--out DIR]`; artifacts written next to the data; raw files read-only (in-memory copies).
- Parse: CSV, delimiter/header auto-detected; dates YYYY.MM.DD/YYYY-MM-DD/YYYY/MM/DD/YYYYMMDD; times HH:MM[:SS[.fff]]; bar files = 7 fields date,time,O,H,L,C,V (time,date auto-swapped); tick files = 4 fields date,time,bid,ask (ms timestamps) summarized as tick reference only. Bar timestamps are OPEN times, printed as-is; close-time = next bar open; last bar of each file open-ended.
- Symbol gate per file: median price outside the XTIUSD range (40-130) => SUSPECT wrong symbol, excluded from merge, both readings reported. Refs: XAUUSD ~1798->~4500s; GBPJPY ~124-220; EURUSD ~0.8-1.6; XTIUSD ~$63-114, ~75000 ticks/day.
- Merge per timeframe: dedupe by timestamp across files; overlaps compared bit-for-bit on printed OHLCV; conflicts reported with both readings (first file kept for stats, count disclosed). Integrity: field count != 7; H < max(O,C) or L > min(O,C); duplicate/non-monotonic timestamps; zero-range; zero-volume.
- Gap threshold per timeframe = max(6h, 2.5x median inter-bar gap). Class: weekend = Thu/Fri/Sat -> Sun/Mon 40-80h (intraday DST-adjusted 48-50h: 49h + Sun-Fri UTC offset, 4h EDT / 5h EST); holiday = span covers a computed US federal holiday 1998-2026 (Good Friday via computus, observance shifts, + 2025-01-09); else UNEXPLAINED (each listed). Hole map: zero-bar dates in [first,last] excl. Saturdays + listed holidays.
- Bad ticks (instrument-scaled, % of price): |dClose| > 1.5% of prev close (across_gap if gap > threshold), wick (H-L) > 2.5% of close, H or C == next session's reopen open (3dp) after such a gap (feed-contamination class). All flagged -> anomalies.csv; nothing deleted or fixed.
- Cross-validation: same-timeframe overlap equality; t500 = groups of 5 consecutive t100 (all 5 phases swept from file start, exact OHLCV + span); t300 = groups of 3; t100/t750 vs groups of 100/750 t1 ticks (mid and bid); daily H/L of finest frame vs h4/d1 under BOTH day definitions: printed date and DST-aware session day (open 22:00 UTC EDT / 23:00 UTC EST); --synth-t500 builds t500 from t100 groups of 5 phase 0, marked SYNTHETIC (on XAUUSD native t500 matched phase 3, 375380/375380 exact, so synthetic phase-0 grid is not bit-identical to the native chart).
- Digest: per-year bars/day, implied ticks/day = bars/day x tick size, median min/bar, avg/median range and % of close; cost ratio = spread / avg range (base 0.02, stress 0.04 per unit = 2.0/4.0 pips); hourly density on printed hours; Feb-Mar 2026 blowoff/crash metrics; weekend seam drift = reopen - prior close. Timezone: session-open first-bar hour histogram of finest timeframe vs the 21:00/22:00 UTC boundary (DST-shifting).
- Budget: REPORT.md hard-capped at 15 KB (long lists truncated here; full detail in receipt.json / anomalies.csv). Prices 3dp, percentages 2dp, timestamps full date+time as printed.
