# TASK: Multi-Timeframe Signal Generation — Iranian 18-Karat Gold (Etehadiye)
# ENGINE: Run inside Claude Code with REAL Python (pandas). You are NOT a calculator —
#         every indicator MUST be computed in code, never estimated by eye.
# INPUT:  ONE CSV file — M5 (base) timeframe.

================================================================================
## CONFIG (set before you start)
================================================================================
MODE                = SWING          # SWING (default) | SCALP
# --- Cost model for Taline (طلاین), from platform cost research ---
# The advertised "5000 Toman flat fee" is MARKETING. The real cost is the SPREAD:
# ~0.4% per side ⇒ ~0.8% round-trip. The flat fee only bites on very small orders.
SPREAD_PER_SIDE_PCT = 0.4            # dashboard price vs reference, each side (from research)
FLAT_FEE_TOMAN      = 5000           # fixed commission per trade, each side
NOTIONAL_TOMAN      = 20000000       # your typical order value — SET THIS to your real size.
                                     #   Small orders make the flat fee huge in % terms.
SLIPPAGE_PCT        = 0.0            # optional extra execution buffer
COST_PCT            = 2*SPREAD_PER_SIDE_PCT + 2*FLAT_FEE_TOMAN/NOTIONAL_TOMAN*100 + SLIPPAGE_PCT
                                     #   ≈ 0.85% round-trip at defaults. THIS is the real hurdle,
                                     #   not the 5000-Toman flat fee. Scalping rarely clears it.
MIN_TP_ATR_MULT     = 1.0            # SWING TP1 ≥ this × entry-frame ATR. For SCALP use ≥ 1.5
MIN_NET_PROFIT_PCT  = 0.5            # TP1 must net at least this AFTER cost, else discard
DIRECTION_ALLOWED   = BOTH           # BOTH = long and short are equally valid
MAX_SIGNALS         = 3              # per run
MAX_SIGNALS_PER_DAY = 4              # hard cap across the day — zero commission is NOT a licence to
                                     #   overtrade; the hidden spread still compounds every trade.
ACCOUNT_CAN_SHORT   = TRUE           # user can both buy and sell/short

# --- Mode parameter sets ---
# SWING:  entry frame M15/H1, trend frame H4/H1, target holding hours-to-days
#         SL basis = ATR(14) on H1 × 1.5 | min SL 0.8% | max SL 3.0%
# SCALP:  entry frame M5/M15, trend frame H1/M15, target holding 1-6h
#         SL basis = ATR(14) on M15 × 1.5 | min SL 0.4% | max SL 1.0%

================================================================================
## ⚠️ TWO RULES THAT OVERRIDE EVERYTHING ELSE
================================================================================
RULE A — COST-AWARE PROFITABILITY (the flat fee is trivial; the SPREAD is the real cost):
    Use COST_PCT (≈0.85% round-trip at defaults) everywhere. Every candidate MUST satisfy:
      • net_R:R = (TP1_move% − COST_PCT) / (SL_move% + COST_PCT)  ≥ 1.5
      • Anti-noise floor: TP1_move% ≥ MIN_TP_ATR_MULT × (entry-frame ATR%)
      • Net profit floor: TP1_move% − COST_PCT ≥ MIN_NET_PROFIT_PCT
    If a candidate cannot reach a real key level that satisfies ALL THREE, DISCARD it.
    Do NOT shrink the stop or inflate the target to force a pass — use real levels only.
    Reality check: with a ~0.85% round-trip spread, SCALP targets (≈1–1.5×M15-ATR ≈
    0.4–0.6%) almost never clear the gate. Expect SWING moves ≥ ~3.5% to be the norm.

RULE B — NO DIRECTIONAL DEFAULT (kill the "always BUY" bias):
    • BUY and SELL are evaluated with IDENTICAL rigor. There is no default direction.
    • Trend is scored SYMMETRICALLY (see STEP 5). Bullish and bearish thresholds are mirrors.
    • Before emitting ANY signal you MUST complete the RED-TEAM step (STEP 6c):
      argue the OPPOSITE direction in ≥2 concrete sentences using the actual numbers.
      If the opposite case is nearly as strong → output NEUTRAL, not a forced trade.
    • NEUTRAL / no-trade is a correct, encouraged outcome. Silence beats a coin-flip.
    • Never let nominal price level ("gold always rises in Toman") justify a long. Judge
      direction ONLY from the symmetric trend score, momentum, and structure below.

================================================================================
## STEP 1 — LOAD & VALIDATE M5 DATA (in Python)
================================================================================
File format: <DTYYYYMMDD>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>

Parsing (mandatory, in code):
  - Strip angle brackets from headers (<DTYYYYMMDD> → DTYYYYMMDD …).
  - Zero-pad TIME to 6 digits (93000 → 093000).
  - Build a Tehran-time DatetimeIndex from DATE+TIME (format %Y%m%d%H%M%S).
  - pd.to_numeric(errors='coerce') on OPEN/HIGH/LOW/CLOSE/VOL.
  - Prices are Iranian Toman, source: Gold Union (اتحادیه).

Report BEFORE proceeding:
  1. Total M5 candles loaded
  2. Date range: first → last candle
  3. Most recent close (Toman)
  4. Count of NaN / missing values
  5. Intraday gaps > 30 min INSIDE the 09:00–22:00 session (exclude the normal
     overnight 22:00→09:00 gap and weekend gaps — those are expected, not errors)

⛔ STOP and wait for instructions if missing/NaN data exceeds 10%.

================================================================================
## STEP 2 — BUILD M15 / H1 / H4 FROM M5 (session-aware)
================================================================================
Resample with pandas: O=first, H=max, L=min, C=last, V=sum. Then DROP empty bins.
  M15 = '15min'  → keep last 500
  H1  = '1h'     → keep last 500
  H4  = '4h'     → keep last 300   (enough for SMA/EMA200)

Session note: the market trades ~09:00–22:00 Tehran. Fixed calendar bins therefore
produce partial candles at the first/last bin of each day. Flag (do not delete) any
H1/H4 candle built from < 50% of its expected M5 sub-candles, and do NOT treat such a
candle as a confirmed swing point in STEP 4.

⚠️ VOLUME is near-zero / unreliable for Etehadiye gold. Do NOT use volume for signal
confidence, breakout confirmation, or anything else. Ignore it.

Confirmation report: M15 / H1 / H4 candle counts, and H4 first→last date.

================================================================================
## STEP 3 — INDICATORS (compute in code for H4, H1, M15)
================================================================================
Trend:      SMA20/50/200, EMA50/200 (EMA = exponential, adjust=False)
Momentum:   RSI(14, Wilder) ; MACD(12,26,9) → line, signal, histogram, cross state
Volatility: ATR(14, Wilder) per timeframe ; Bollinger(20, 2σ) → upper/mid/lower, width%
EMA cross (last 300 candles each TF): Golden (EMA50↑EMA200) / Death (EMA50↓EMA200)
            → date + price of the most recent cross; current gap in Toman and %, and
            whether the gap is widening or narrowing.

Also compute, per timeframe, ATR% = ATR / Close × 100 (needed by the cost/ATR gate).

Mandatory verification block (print it):
  - Last 5 RSI(14) values for M15, all within 0–100
  - The exact Python snippet used for RSI
  - Confirm EMA used exponential weighting (adjust=False)
  - ATR(14) current value AND ATR% for H4, H1, M15 side by side

================================================================================
## STEP 4 — SUPPORT / RESISTANCE + FIBONACCI
================================================================================
Swing High/Low, lookback 10 candles each side, on H4 and H1 only (M15 too noisy).
Skip partial session-boundary candles (STEP 2) as swing points.
Per level: exact price, date formed, touch count, class (Strong 3+ / Moderate 2 / Weak 1).
Output: Top 3 resistances above price + Top 3 supports below price (sorted by proximity).

Fibonacci on H4: most recent significant swing (min 3% move). Report swing hi/lo + dates,
levels 0.236/0.382/0.500/0.618/0.786, and the closest level to current price.

These real levels are the ONLY allowed take-profit / stop anchors (see RULE A).

================================================================================
## STEP 5 — SYMMETRIC TREND SCORING (top-down: H4 → H1 → M15)
================================================================================
⚠️ LOOK-AHEAD / REPAINT GUARD (mandatory): the final resampled bin of H4/H1/M15 is
usually a STILL-FORMING candle (e.g. a 16:35 tick sits in a 16:00–20:00 H4 bin that is
only ~35 min old). Computing the trend score on it repaints — the score can flip when the
candle closes. Therefore score EMA/RSI/MACD/slope on the LAST CLOSED candle of each
timeframe (drop or exclude the forming bin). Use live price only as the entry reference,
never to compute a higher-timeframe indicator.

For EACH timeframe compute an integer directional score in [−3 … +3]:
  +1 / −1  : Close above / below EMA200
  +1 / −1  : EMA50 above / below EMA200
  +1 / −1  : EMA50 slope over last 20 candles rising / falling  (flat if |slope| tiny → 0)
  Bullish TF if score ≥ +2 · Bearish if score ≤ −2 · else RANGE.

Report per timeframe: the 3 components, the total score, RSI value+direction,
MACD cross state + histogram behaviour, Bollinger position + squeeze flag (width < 2%),
and (M15/H1 only) candlestick patterns in the last 5 candles
(Doji, Engulfing, Hammer, Shooting Star, Pin Bar, Inside Bar, Morning/Evening Star)
— name + date + implication, or "no significant pattern".

Print a compact SCORECARD table: TF | trend score | RSI | MACD | note.

================================================================================
## STEP 6 — SIGNAL SYNTHESIS
================================================================================
6a) ALIGNMENT (symmetric):
    SWING  BUY  needs H4 score ≥ +2 AND H1 score ≥ +1 AND an M15 long trigger.
    SWING  SELL needs H4 score ≤ −2 AND H1 score ≤ −1 AND an M15 short trigger.
    SCALP  BUY  needs H1 score ≥ +1 AND M15 score ≥ +2 AND an M5/M15 long trigger.
    SCALP  SELL needs H1 score ≤ −1 AND M15 score ≤ −2 AND an M5/M15 short trigger.
    Trigger = fresh momentum/pattern event (MACD cross, RSI cross of 50, engulfing,
    break/retest of a STEP-4 level). If timeframes conflict → NEUTRAL.

6b) QUALITY GATE — every box must be TRUE, else discard the candidate:
    □ 1  ≥ 2 of 3 agree on H1: {trend score sign, RSI vs 50, MACD histogram sign}
    □ 2  RULE A passes: net_R:R ≥ 1.5 AND TP1_move ≥ MIN_TP_ATR_MULT×ATR AND net ≥ MIN_NET_PROFIT_PCT
    □ 3  Volatility sane: entry-frame ATR ≤ 2× its own 20-period average (no vol spike)
    □ 4  Entry not trapped between two levels each < 0.3% away
    □ 5  SL distance within the mode's min/max band (SWING 0.8–3.0% · SCALP 0.4–1.0%)
    □ 6  Signal confirmed on a CLOSED candle (no intrabar / repainting triggers)
    □ 7  SWING only: if the venue charges overnight swap/holding cost, subtract an
         estimate of it from net profit for multi-session holds (physical Etehadiye = 0;
         a leveraged/futures venue ≠ 0). Zero-commission ≠ zero carry.

6c) RED-TEAM (mandatory anti-bias check — do this OUT LOUD before emitting):
    For each surviving candidate, write ≥2 sentences arguing the OPPOSITE direction
    using the real numbers (levels, scores, RSI, MACD). Then state why the chosen
    direction still wins. If it does not clearly win → downgrade to NEUTRAL.
    Also report the buy-vs-sell tally you evaluated, to prove both sides were tested.

6d) STOPS & TARGETS (use ONLY real STEP-4 levels; never invent a level to pass a gate):
    SL   = mode ATR basis, clamped to the mode band. Place just beyond a real level.
    TP1  = nearest opposing H1 key level giving net_R:R ≥ 1.5 after cost AND ≥ 1×ATR.
    TP2  = next H4 key level or matching Fib giving net_R:R ≥ 2.5 after cost.
    If price sits at a range extreme with NO real level ahead (no overhead target for a
    long / no target below for a short), there is no defined objective → output NEUTRAL.
    Do not chase a breakout without a measured target.
    Expected time-to-TP from average entry-frame ATR velocity; SWING may span hours–days,
    SCALP should resolve within ~1–6h (flag if unlikely).

If NOTHING passes: output ⛔ "شرایط بازار برای ورود مناسب نیست" and name the exact
failed condition(s) and the direction(s) you tested.

6e) OPERATIONAL CAUTIONS (state them when relevant, do not silently ignore):
    • Overnight gap risk: the market is closed ~22:00→09:00 Tehran. A stop cannot fill
      while closed; a rial/USD or global-gold move overnight can gap PAST the stop. For
      SWING positions held overnight, size for a possible gap, not just the stop distance.
    • Etehadiye price is ≈ (USD/Toman × global gold) + local premium (حباب). In a premium
      spike/collapse or an administrative price freeze, technical levels stop working —
      prefer NEUTRAL when price detaches from its normal behaviour.
    • KEEP A JOURNAL: log every signal's outcome (hit TP / hit SL / timed out) so the real
      post-spread win rate is measured. Without it you are flying blind on whether an edge exists.

================================================================================
## STEP 7 — FINAL OUTPUT (Persian; Persian digits ۰۱۲۳; max 3 signals)
================================================================================
### بخش اول — خلاصه بازار
📋 خلاصه بازار | طلای ۱۸ عیار اتحادیه
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🕐 آخرین کندل: [تاریخ و ساعت]   💰 آخرین قیمت: [عدد] تومان
📈 روند H4: [صعودی/نزولی/رنج] (امتیاز [±n]) | 📊 روند H1: [..] (امتیاز [±n]) | روند M15: [..]
🔴 مقاومت کلیدی: [قیمت] ([قدرت]|[TF])   🟢 حمایت کلیدی: [قیمت] ([قدرت]|[TF])
🧭 جمع‌بندی جهت: خرید/فروش/خنثی  ←  (تعداد سناریوی خرید بررسی‌شده: n | فروش: n)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### بخش دوم — سیگنال‌ها (اگر هیچ سیگنالی نبود: ⛔️ شرایط بازار برای ورود مناسب نیست)
═════════════════════
🔔 سیگنال | طلای ۱۸ عیار ([اسکالپ/سویینگ])
📊 نوع معامله: [خرید 📈 / فروش 📉]
💰 نقطه ورود: [عدد فارسی] تومان
🛡️ حد ضرر: [عدد فارسی] تومان  (فاصله: [٪])
🎯 حد سود اول: [عدد فارسی] تومان  (فاصله: [٪])
🎯 حد سود دوم: [عدد فارسی] تومان  (فاصله: [٪])
💵 سود خالص تخمینی بعد از هزینه (اسپرد) — هدف اول: [٪] | هدف دوم: [٪]
⚖️ نسبت ریسک‌به‌ریوارد خالص (بعد از هزینه): [عدد]
⏱️ بازه زمانی تخمینی: [عدد فارسی] ([ساعت/روز])
✅ دلیل اصلی: [یک جمله]
🔎 چرا جهت مخالف رد شد: [یک جمله از مرحله red-team]
⭕️ شرط ابطال: [قیمت فارسی] تومان
═════════════════════

### Output rules
- All numeric outputs in Persian digits.
- Every signal MUST show net-after-cost profit and net R:R. A signal without them is invalid.
- Max 3 signals. Prefer fewer, higher-quality signals over filling the quota.
- Honesty over action: if the honest answer is "no trade", say it.
