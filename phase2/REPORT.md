# XTIUSD PHASE II - DATA RECEIPT & DIGEST

Run: phase2_digest.py (python 3.12.14) at 2026-11-26 09:11:32 UTC. Input dir: `/workspace/XTIUSD`. Files found: 2.

## MANIFEST

| file | bytes | md5 | rows | first bar | last bar | tf | claimed | actual | symbol |
|---|---|---|---|---|---|---|---|---|---|
| CCMonthCapture XTIUSD t100 20220101-20221123.csv | 4890297 | 3a28062b32699cbed7d8a7a46e844738 | 99276 | 2022-01-02 23:04:03 | 2022-11-23 23:27:51 | t100 | 2022 | 2022-01-02 23:04:03 .. 2022-11-23 23:27:51 | XTIUSD? |
| CCMonthCapture XTIUSD t100 20260501-20261121.csv | 4130448 | 1abcfb10126fcf3f1f6bf11c9ca8c1e4 | 83308 | 2026-05-01 00:01:06 | 2026-11-20 21:54:37 | t100 | 2026 | 2026-05-01 00:01:06 .. 2026-11-20 21:54:37 | XTIUSD? |

- **t100**: 182584 rows (2 files), 2022-01-02 23:04:03 .. 2026-11-20 21:54:37; overlap 0/0 identical, 0 conflicts.

## FORMAT

- CCMonthCapture XTIUSD t100 20220101-20221123.csv: 7 fields date,time,O,H,L,C,V confirmed
- CCMonthCapture XTIUSD t100 20260501-20261121.csv: 7 fields date,time,O,H,L,C,V confirmed

## INTEGRITY

- **t100**: wrong-field-count 0; OHLC violations 0; duplicate ts 0; non-monotonic 0; zero-range 0; zero-volume 0.

## GAPS & SEAMS

Timezone evidence (finest timeframe t100): UTC: session-open days (first bar after a >6h gap) start at 21:00-23:59 in 99% of cases; the 21/22 split flips with US DST (EDT/EST), matching the 21:00/22:00 UTC session boundary (histogram in receipt.json).
- t100 (thr 6.0h): weekend 75, holiday 0, UNEXPLAINED 1.
  - UNEXPLAINED 2022-11-23 23:27:51 -> 2026-05-01 00:01:06 (30096.5h)
- holiday gaps by name: 
- hole map **t100**: 1038 zero-bar days (incl. 174 Fridays - this timeframe has no Friday bars in part of its range): 2022-11-25, 2022-11-27..2022-12-02 ... (full map in receipt.json)
- weekend seams: 74 total across timeframes, mean |drift| 0.05%, worst 5:
  - [t100] 2026-05-29 20:53:04 -> 2026-05-31 22:00:21 close 90.190 reopen 90.990 drift +0.800 (0.89%)
  - [t100] 2026-10-30 20:51:18 -> 2026-11-01 23:00:26 close 103.513 reopen 103.012 drift -0.501 (-0.48%)
  - [t100] 2026-10-09 20:52:36 -> 2026-10-11 22:01:31 close 92.660 reopen 92.333 drift -0.327 (-0.35%)
  - [t100] 2022-03-04 21:54:58 -> 2022-03-06 23:03:29 close 129.860 reopen 129.620 drift -0.240 (-0.18%)
  - [t100] 2026-05-22 20:56:01 -> 2026-05-24 22:00:42 close 95.340 reopen 95.440 drift +0.100 (0.10%)

## BAD TICKS

- **t100**: 33 flagged bars (delta_close x32; wick x16). Full rows in anomalies.csv.
  - CCMonthCapture XTIUSD t100 20220101-20221123.csv 2022-02-25 21:56:49 O=93.230 H=98.920 L=93.220 C=98.830 V=100 [delta_close 6.03%; wick 5.77%]
  - CCMonthCapture XTIUSD t100 20220101-20221123.csv 2022-03-04 21:54:58 O=116.050 H=131.110 L=115.790 C=129.860 V=100 [delta_close 11.89%; wick 11.80%]

## CROSS-VALIDATION

- same-timeframe overlaps: no same-timeframe overlaps (one file per timeframe)
- no cross-timeframe checks possible.

## CALIBRATION DIGEST

(per-year tables shown for 2021+; full history incl. pre-2021 in receipt.json. Cost tiers for XTIUSD: base 0.0200, stress 0.0400 per unit = 2.000/4.000 pips, as % of avg bar range.)

### t100 (reference bars/day ~750; ref ticks/day ~n/a (no tick file this run))

| year | bars | days | bars/day | ticks/day | min/bar | avg rng | med rng | avg rng % | base % | stress % |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | 99276 | 279 | 355.8 | 35583.0 | 2.35 | 0.204 | 0.18 | 0.21 | 9.8 | 19.61 |
| 2026 | 83308 | 175 | 476.0 | 47605.0 | 1.8 | 0.156 | 0.14 | 0.17 | 12.82 | 25.64 |

**DEVIATION vs reference**: 2022: 355.8 bars/day vs ref ~750 (-53% off, BELOW ref - but 1 unexplained gaps / 1038 hole days, so not missing data: real lower tick throughput); 2026: 476.0 bars/day vs ref ~750 (-37% off, BELOW ref - but 1 unexplained gaps / 1038 hole days, so not missing data: real lower tick throughput)
- hourly bar density (00-24, printed hours): 00:4046 01:7953 02:5348 03:3978 04:2587 05:4843 06:6837 07:8483 08:10864 09:8722 10:8054 11:8271 12:10093 13:15357 14:15597 15:14721 16:11660 17:10273 18:10377 19:6417 20:3818 21:649 22:1791 23:1845
- dead hours: none; top hours: 14,13,15,16,08,18

## PHASE II READINESS

- t500 ABSENT: MA layer not runnable; t500 exports required.
- t100 2022-01-02..2026-11-20: entry layer READY (182584 bars), but faithful-transpose cells NOT runnable - t500 MA layer absent, t500 exports required.
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
