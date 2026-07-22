#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
موتور سیگنال‌دهی بر پایه‌ی فایل CSV کندل‌ها (فرمت CHARTIX / متاتریدر).

ورودی: فایل CSV با ستون‌های
    <DTYYYYMMDD>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>

قیمت‌ها در فایل خام به‌صورت عدد صحیح و ضرب‌شده در ۱۰۰۰۰ ذخیره شده‌اند
(مثلاً 19033700 یعنی 1903.37).

خروجی: یک سیگنال معاملاتی فارسی شامل جهت (خرید/فروش/خنثی)،
نقطه ورود، حد ضرر و اهداف سود، به‌همراه دلایل بر پایه‌ی
اندیکاتورهای EMA، RSI، MACD و ATR.

اجرا:
    python bot/signal_engine.py <path/to/data.csv>
"""

import csv
import sys


PRICE_SCALE = 10000.0


def load_candles(path):
    """خواندن کندل‌ها از فایل CSV و برگرداندن لیستی از دیکشنری‌ها."""
    candles = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if not row or len(row) < 6:
                continue
            try:
                candles.append(
                    {
                        "date": row[0].strip(),
                        "time": row[1].strip(),
                        "open": float(row[2]) / PRICE_SCALE,
                        "high": float(row[3]) / PRICE_SCALE,
                        "low": float(row[4]) / PRICE_SCALE,
                        "close": float(row[5]) / PRICE_SCALE,
                        "vol": float(row[6]) if len(row) > 6 and row[6] else 0.0,
                    }
                )
            except ValueError:
                continue
    return candles


def ema(values, period):
    """میانگین متحرک نمایی."""
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def rsi(closes, period=14):
    """شاخص قدرت نسبی (RSI) به روش وایلدر."""
    if len(closes) <= period:
        return [None] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out = [None] * period
    for i in range(period, len(closes)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            out.append(100.0)
        else:
            rs = avg_gain / avg_loss
            out.append(100.0 - (100.0 / (1.0 + rs)))
    return out


def macd(closes, fast=12, slow=26, signal=9):
    """اندیکاتور MACD؛ برمی‌گرداند (خط مکدی، خط سیگنال، هیستوگرام)."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, hist


def atr(candles, period=14):
    """میانگین دامنه واقعی (ATR)."""
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    period = min(period, len(trs))
    return sum(trs[-period:]) / period


def generate_signal(candles):
    """تولید سیگنال بر پایه‌ی تلاقی EMA، RSI و MACD."""
    closes = [c["close"] for c in candles]
    ema_fast = ema(closes, 9)
    ema_slow = ema(closes, 21)
    rsi_vals = rsi(closes, 14)
    _, _, hist = macd(closes)
    atr_val = atr(candles, 14)

    price = closes[-1]
    ef = ema_fast[-1]
    es = ema_slow[-1]
    r = rsi_vals[-1]
    h = hist[-1]

    score = 0
    reasons = []

    # روند بر پایه‌ی EMA
    if ef > es:
        score += 1
        reasons.append("EMA9 بالای EMA21 (روند صعودی کوتاه‌مدت)")
    elif ef < es:
        score -= 1
        reasons.append("EMA9 زیر EMA21 (روند نزولی کوتاه‌مدت)")

    # مومنتوم بر پایه‌ی MACD
    if h > 0:
        score += 1
        reasons.append("هیستوگرام MACD مثبت (مومنتوم صعودی)")
    elif h < 0:
        score -= 1
        reasons.append("هیستوگرام MACD منفی (مومنتوم نزولی)")

    # RSI
    if r is not None:
        if r < 30:
            score += 1
            reasons.append("RSI در ناحیه اشباع فروش (%.1f)" % r)
        elif r > 70:
            score -= 1
            reasons.append("RSI در ناحیه اشباع خرید (%.1f)" % r)
        else:
            reasons.append("RSI خنثی (%.1f)" % r)

    if score >= 2:
        direction = "BUY"
    elif score <= -2:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    # محاسبه حد ضرر و اهداف بر پایه‌ی ATR
    sl = tp1 = tp2 = None
    if direction == "BUY":
        sl = price - 1.5 * atr_val
        tp1 = price + 1.5 * atr_val
        tp2 = price + 3.0 * atr_val
    elif direction == "SELL":
        sl = price + 1.5 * atr_val
        tp1 = price - 1.5 * atr_val
        tp2 = price - 3.0 * atr_val

    return {
        "direction": direction,
        "score": score,
        "price": price,
        "rsi": r,
        "atr": atr_val,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "reasons": reasons,
        "last_candle": candles[-1],
    }


def format_persian(sig):
    """قالب‌بندی خروجی سیگنال به‌صورت فارسی."""
    label = {
        "BUY": "🟢 خرید (BUY)",
        "SELL": "🔴 فروش (SELL)",
        "NEUTRAL": "⚪ خنثی (بدون موقعیت)",
    }[sig["direction"]]

    lc = sig["last_candle"]
    lines = []
    lines.append("📊 سیگنال معاملاتی — طلا (Gold)")
    lines.append("=" * 34)
    lines.append("⏱ آخرین کندل: %s %s" % (lc["date"], lc["time"]))
    lines.append("💰 قیمت فعلی: %.2f" % sig["price"])
    lines.append("📈 سیگنال: %s" % label)
    lines.append("")

    if sig["direction"] != "NEUTRAL":
        lines.append("🎯 نقطه ورود: %.2f" % sig["price"])
        lines.append("🛑 حد ضرر (SL): %.2f" % sig["sl"])
        lines.append("✅ هدف اول (TP1): %.2f" % sig["tp1"])
        lines.append("✅ هدف دوم (TP2): %.2f" % sig["tp2"])
    else:
        lines.append("در حال حاضر شرایط ورود به معامله فراهم نیست؛ منتظر تأیید بمانید.")

    lines.append("")
    lines.append("📌 دلایل:")
    for reason in sig["reasons"]:
        lines.append("   • " + reason)
    lines.append("")
    lines.append("ℹ️ RSI=%.1f | ATR=%.2f | امتیاز=%d" % (
        sig["rsi"] if sig["rsi"] is not None else 0.0,
        sig["atr"],
        sig["score"],
    ))
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("استفاده: python bot/signal_engine.py <path/to/data.csv>")
        sys.exit(1)

    candles = load_candles(sys.argv[1])
    if len(candles) < 30:
        print("داده کافی برای تحلیل وجود ندارد (حداقل ۳۰ کندل لازم است).")
        sys.exit(1)

    sig = generate_signal(candles)
    print(format_persian(sig))


if __name__ == "__main__":
    main()
