"""
Deterministic multi-timeframe signal engine for Iranian 18k gold (Etehadiye).
Mirrors signal_prompt.md. Pure Python + pandas — no LLM required.

Config via environment variables (all optional, sane defaults):
  FEE_PCT              round-trip commission        (default 0.0  = zero-commission venue)
  SPREAD_PCT           bid/ask spread + slippage     (default 0.10)
  MIN_TP_ATR_SWING     TP1 >= x*ATR for swing        (default 1.0)
  MIN_TP_ATR_SCALP     TP1 >= x*ATR for scalp        (default 1.5)
  MIN_NET_RR           minimum net risk:reward       (default 1.5)
  MAX_SIGNALS          cap on emitted signals        (default 3)
"""
import os
import pandas as pd
import numpy as np

FEE = float(os.getenv("FEE_PCT", "0.0"))
SPREAD = float(os.getenv("SPREAD_PCT", "0.10"))
COST = FEE + SPREAD
MIN_TP_ATR = {"SWING": float(os.getenv("MIN_TP_ATR_SWING", "1.0")),
              "SCALP": float(os.getenv("MIN_TP_ATR_SCALP", "1.5"))}
MIN_NET_RR = float(os.getenv("MIN_NET_RR", "1.5"))
MAX_SIGNALS = int(os.getenv("MAX_SIGNALS", "3"))

# ---------------------------------------------------------------- Persian helpers
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

def fa_num(x):
    return str(x).translate(_FA)

def fa_price(v):
    return fa_num(f"{int(round(v)):,}".replace(",", "٬"))

def fa_pct(v, d=2):
    return fa_num(f"{v:.{d}f}") + "٪"

# ---------------------------------------------------------------- indicators
def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def _rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)

def _macd(s):
    line = _ema(s, 12) - _ema(s, 26)
    sig = _ema(line, 9)
    return line, sig, line - sig

def _atr(d, n=14):
    tr = pd.concat([d.HIGH - d.LOW,
                    (d.HIGH - d.CLOSE.shift()).abs(),
                    (d.LOW - d.CLOSE.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

# ---------------------------------------------------------------- load / resample
class DataError(Exception):
    pass

def load_m5(path):
    df = pd.read_csv(path)
    df.columns = [c.strip("<>").strip() for c in df.columns]
    if "TIME" not in df.columns or "DTYYYYMMDD" not in df.columns:
        raise DataError("ساختار فایل شناخته نشد. ستون‌های DTYYYYMMDD و TIME لازم است.")
    df["TIME"] = df["TIME"].astype(str).str.zfill(6)
    idx = pd.to_datetime(df["DTYYYYMMDD"].astype(str) + df["TIME"],
                         format="%Y%m%d%H%M%S", errors="coerce")
    df = df.set_index(idx)
    for c in ["OPEN", "HIGH", "LOW", "CLOSE", "VOL"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[["OPEN", "HIGH", "LOW", "CLOSE"]].sort_index()
    df = df[~df.index.isna()]
    miss = df[["OPEN", "HIGH", "LOW", "CLOSE"]].isna().sum().sum()
    total = df.size if df.size else 1
    if miss / total > 0.10:
        raise DataError(f"داده ناقص بیش از ۱۰٪ است ({miss} مقدار). لطفاً فایل سالم بفرست.")
    df = df.dropna()
    if len(df) < 250:
        raise DataError(f"تعداد کندل کم است ({len(df)}). حداقل ~۲۵۰ کندل M5 لازم است.")
    return df

def _resample(df, rule, expected_sub):
    x = pd.DataFrame({
        "OPEN": df.OPEN.resample(rule).first(),
        "HIGH": df.HIGH.resample(rule).max(),
        "LOW": df.LOW.resample(rule).min(),
        "CLOSE": df.CLOSE.resample(rule).last(),
        "N": df.CLOSE.resample(rule).count(),
    }).dropna(subset=["CLOSE"])
    x["partial"] = x["N"] < 0.9 * expected_sub
    x["ema50"] = _ema(x.CLOSE, 50)
    x["ema200"] = _ema(x.CLOSE, 200)
    x["rsi"] = _rsi(x.CLOSE)
    x["macd"], x["sig"], x["hist"] = _macd(x.CLOSE)
    x["atr"] = _atr(x)
    x["atrpct"] = x["atr"] / x.CLOSE * 100
    x["slope"] = x["ema50"].diff(20)
    return x

def _last_closed(x):
    # LOOK-AHEAD GUARD: never score on a still-forming bin
    return x[~x["partial"]] if bool(x["partial"].iloc[-1]) else x

def _score(row):
    s = 1 if row.CLOSE > row.ema200 else -1
    s += 1 if row.ema50 > row.ema200 else -1
    if not pd.isna(row.slope) and abs(row.slope) > 1e-9:
        s += 1 if row.slope > 0 else -1
    return int(s)

def _swings(x, lb=10):
    hi, lo = [], []
    H, L = x.HIGH.values, x.LOW.values
    for i in range(lb, len(x) - lb):
        if bool(x["partial"].iloc[i]):
            continue
        if H[i] == max(H[i-lb:i+lb+1]):
            hi.append(H[i])
        if L[i] == min(L[i-lb:i+lb+1]):
            lo.append(L[i])
    return hi, lo

def _round100(v):
    return int(round(v / 100.0) * 100)

# ---------------------------------------------------------------- core
def analyze(path):
    df = load_m5(path)
    price = float(df.CLOSE.iloc[-1])
    M15 = _resample(df, "15min", 3).iloc[-500:]
    H1 = _resample(df, "1h", 12).iloc[-500:]
    H4 = _resample(df, "4h", 48).iloc[-300:]

    c15, c1, c4 = _last_closed(M15).iloc[-1], _last_closed(H1).iloc[-1], _last_closed(H4).iloc[-1]
    s15, s1, s4 = _score(c15), _score(c1), _score(c4)

    hiH1, loH1 = _swings(H1)
    hiH4, loH4 = _swings(H4)
    res = sorted({p for p in hiH1 + hiH4 if p > price})
    sup = sorted({p for p in loH1 + loH4 if p < price}, reverse=True)

    def trend_word(s):
        return "صعودی" if s >= 2 else ("نزولی" if s <= -2 else "رنج")

    ctx = dict(price=price, last_time=df.index[-1], candles=len(df),
               s4=s4, s1=s1, s15=s15,
               ema50_h4=c4.ema50, ema200_h4=c4.ema200,
               ema50_h1=c1.ema50, ema200_h1=c1.ema200,
               rsi_h1=c1.rsi, res=res, sup=sup,
               trend_h4=trend_word(s4), trend_h1=trend_word(s1), trend_m15=trend_word(s15),
               atr_m15=c15.atrpct, atr_h1=c1.atrpct)

    signals = []
    tested = {"BUY": 0, "SELL": 0}
    for mode in ("SWING", "SCALP"):
        if mode == "SWING":
            buy, sell = (s4 >= 2 and s1 >= 1), (s4 <= -2 and s1 <= -1)
            slpct = min(max(c1.atrpct * 1.5, 0.8), 3.0)
        else:
            buy, sell = (s1 >= 1 and s15 >= 2), (s1 <= -1 and s15 <= -2)
            slpct = min(max(c15.atrpct * 1.5, 0.4), 1.0)
        direction = "BUY" if buy else ("SELL" if sell else None)
        if direction is None:
            continue
        tested[direction] += 1
        min_tp = MIN_TP_ATR[mode] * c15.atrpct
        levels = res if direction == "BUY" else sup
        passing = []
        for tp in (levels if direction == "BUY" else levels):
            move = abs(tp - price) / price * 100
            net = move - COST
            rr = (move - COST) / (slpct + COST)
            if rr >= MIN_NET_RR and move >= min_tp and SPREAD <= 0.20 * move:
                passing.append((tp, move, net, rr))
        if not passing:
            continue
        tp1 = passing[0]
        tp2 = next((p for p in passing if p[3] >= 2.5 and p[0] != tp1[0]), None)
        sl = _round100(price * (1 - slpct/100) if direction == "BUY" else price * (1 + slpct/100))
        signals.append(dict(mode=mode, direction=direction, entry=_round100(price),
                            sl=sl, sl_pct=slpct,
                            tp1=_round100(tp1[0]), tp1_pct=tp1[1], tp1_net=tp1[2], net_rr=tp1[3],
                            tp2=(_round100(tp2[0]) if tp2 else None),
                            tp2_pct=(tp2[1] if tp2 else None),
                            tp2_net=(tp2[2] if tp2 else None)))
    ctx["tested"] = tested
    return ctx, signals[:MAX_SIGNALS]

# ---------------------------------------------------------------- Persian report
def format_report(ctx, signals):
    dt = ctx["last_time"]
    res0 = ctx["res"][0] if ctx["res"] else None
    sup0 = ctx["sup"][0] if ctx["sup"] else None
    L = []
    L.append("📋 خلاصه بازار | طلای ۱۸ عیار اتحادیه")
    L.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    L.append(f"🕐 آخرین کندل: {fa_num(dt.strftime('%Y-%m-%d %H:%M'))}")
    L.append(f"💰 آخرین قیمت: {fa_price(ctx['price'])} تومان")
    L.append("─────────────")
    L.append(f"📈 روند H4: {ctx['trend_h4']} (امتیاز {fa_num(f'{ctx[\"s4\"]:+d}')})")
    L.append(f"   EMA50: {fa_price(ctx['ema50_h4'])} | EMA200: {fa_price(ctx['ema200_h4'])}")
    L.append(f"📊 روند H1: {ctx['trend_h1']} (امتیاز {fa_num(f'{ctx[\"s1\"]:+d}')}) | روند M15: {ctx['trend_m15']}")
    L.append(f"   EMA50: {fa_price(ctx['ema50_h1'])} | EMA200: {fa_price(ctx['ema200_h1'])}")
    L.append("─────────────")
    if res0:
        L.append(f"🔴 مقاومت کلیدی: {fa_price(res0)} تومان")
    if sup0:
        L.append(f"🟢 حمایت کلیدی: {fa_price(sup0)} تومان")
    t = ctx["tested"]
    L.append(f"🧭 سناریوهای بررسی‌شده — خرید: {fa_num(t['BUY'])} | فروش: {fa_num(t['SELL'])}")
    L.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if not signals:
        L.append("")
        L.append("⛔️ شرایط بازار برای ورود مناسب نیست")
        reason = "هیچ هدفی بعد از هزینه به حد نصاب R:R خالص ۱٫۵ یا کف ATR نرسید."
        if not ctx["res"] and t["BUY"]:
            reason = "قیمت روی سقف دامنه است و هدف سودآوری بالای آن وجود ندارد."
        L.append("دلیل: " + reason)
        return "\n".join(L)

    mode_fa = {"SWING": "سویینگ", "SCALP": "اسکالپ"}
    dir_fa = {"BUY": "خرید 📈", "SELL": "فروش 📉"}
    for sg in signals:
        L.append("")
        L.append("═════════════════════")
        L.append(f"🔔 سیگنال | طلای ۱۸ عیار ({mode_fa[sg['mode']]})")
        L.append(f"📊 نوع معامله: {dir_fa[sg['direction']]}")
        L.append(f"💰 نقطه ورود: {fa_price(sg['entry'])} تومان")
        L.append(f"🛡️ حد ضرر: {fa_price(sg['sl'])} تومان (فاصله {fa_pct(sg['sl_pct'])})")
        L.append(f"🎯 حد سود اول: {fa_price(sg['tp1'])} تومان (فاصله {fa_pct(sg['tp1_pct'])})")
        if sg["tp2"]:
            L.append(f"🎯 حد سود دوم: {fa_price(sg['tp2'])} تومان (فاصله {fa_pct(sg['tp2_pct'])})")
        else:
            L.append("🎯 حد سود دوم: تعریف‌نشده (در هدف اول خروج/کاهش حجم)")
        L.append(f"💵 سود خالص بعد از هزینه (هدف اول): {fa_pct(sg['tp1_net'])}")
        L.append(f"⚖️ نسبت ریسک‌به‌ریوارد خالص: {fa_num(f'{sg[\"net_rr\"]:.2f}')}")
        L.append(f"⏱️ بازه زمانی: {'چند ساعت تا چند روز' if sg['mode']=='SWING' else '۱ تا ۶ ساعت'}")
        L.append(f"⭕️ شرط ابطال: بسته‌شدن آن‌سوی {fa_price(sg['sl'])} تومان")
        L.append("═════════════════════")
    L.append("")
    L.append("⚠️ ریسک گپ شبانه (بازار ۲۲–۹ بسته) و اسپرد واقعی پلتفرم را در نظر بگیر.")
    return "\n".join(L)

def run(path):
    ctx, signals = analyze(path)
    return format_report(ctx, signals)

if __name__ == "__main__":
    import sys
    print(run(sys.argv[1]))
