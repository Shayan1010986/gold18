#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Signal Engine — CSV-based trading signal generator (Gold / XAUUSD, M5).

Reads an OHLCV CSV exported in the CHARTIX/MetaTrader format:

    <DTYYYYMMDD>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>

Prices are integer-scaled (e.g. 18283400 == 1828.34). The engine computes a
small set of classic indicators (EMA trend, RSI, MACD, ATR) and produces a
single actionable signal (BUY / SELL / NEUTRAL) printed in Persian.

Usage:
    python bot/signal_engine.py path/to/data.csv
"""

import csv
import sys

# Price scale used by the CHARTIX export (integer prices -> real price).
PRICE_SCALE = 10000.0

# Indicator settings.
EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ATR_PERIOD = 14

# Risk model (ATR multiples).
SL_ATR_MULT = 1.5
TP_ATR_MULT = 3.0


def load_candles(path):
    """Load OHLCV candles from a CHARTIX-format CSV file."""
    candles = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
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
                        "volume": float(row[6]) if len(row) > 6 and row[6] else 0.0,
                    }
                )
            except ValueError:
                # Skip malformed rows.
                continue
    return candles


def ema(values, period):
    """Exponential moving average; returns a list aligned with `values`."""
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def rsi(closes, period=RSI_PERIOD):
    """Wilder's RSI; returns a list aligned with `closes` (None until warm)."""
    if len(closes) <= period:
        return [None] * len(closes)
    out = [None] * len(closes)
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def macd(closes):
    """MACD line, signal line and histogram (last values)."""
    fast = ema(closes, MACD_FAST)
    slow = ema(closes, MACD_SLOW)
    macd_line = [f - s for f, s in zip(fast, slow)]
    signal_line = ema(macd_line, MACD_SIGNAL)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, hist


def atr(candles, period=ATR_PERIOD):
    """Average True Range (Wilder). Returns last ATR value."""
    if len(candles) <= period:
        return None
    trs = []
    for i in range(1, len(candles)):
        h, l = candles[i]["high"], candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


def generate_signal(candles):
    """Analyse candles and return a signal dict."""
    closes = [c["close"] for c in candles]
    price = closes[-1]

    ema_fast = ema(closes, EMA_FAST)[-1]
    ema_slow = ema(closes, EMA_SLOW)[-1]
    ema_trend = ema(closes, EMA_TREND)[-1]
    rsi_val = rsi(closes)[-1]
    _, _, hist = macd(closes)
    macd_hist = hist[-1]
    atr_val = atr(candles) or 0.0

    # Score-based decision: aggregate directional votes.
    score = 0
    if ema_fast > ema_slow:
        score += 1
    else:
        score -= 1
    if price > ema_trend:
        score += 1
    else:
        score -= 1
    if macd_hist > 0:
        score += 1
    else:
        score -= 1
    if rsi_val is not None:
        if rsi_val > 55:
            score += 1
        elif rsi_val < 45:
            score -= 1

    if score >= 2:
        direction = "BUY"
    elif score <= -2:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    # Confidence as a share of the maximum possible |score| (=4).
    confidence = min(100, int(abs(score) / 4.0 * 100))

    if direction == "BUY":
        entry = price
        sl = price - SL_ATR_MULT * atr_val
        tp = price + TP_ATR_MULT * atr_val
    elif direction == "SELL":
        entry = price
        sl = price + SL_ATR_MULT * atr_val
        tp = price - TP_ATR_MULT * atr_val
    else:
        entry = sl = tp = None

    return {
        "direction": direction,
        "confidence": confidence,
        "price": price,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rsi": rsi_val,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "ema_trend": ema_trend,
        "atr": atr_val,
        "last_time": f"{candles[-1]['date']} {candles[-1]['time']}",
    }


def format_persian(sig):
    """Render the signal as a Persian-language report."""
    label = {
        "BUY": "خرید (BUY) \U0001f7e2",
        "SELL": "فروش (SELL) \U0001f534",
        "NEUTRAL": "بدون موقعیت / خنثی (NEUTRAL) ⚪",
    }[sig["direction"]]

    lines = []
    lines.append("سیگنال معاملاتی طلا (XAUUSD — م 5)")
    lines.append("=" * 38)
    lines.append(f"زمان کندل آخر: {sig['last_time']}")
    lines.append(f"قیمت فعلی: {sig['price']:.2f}")
    lines.append(f"سیگنال: {label}")
    lines.append(f"میزان اطمینان: {sig['confidence']}٪")

    if sig["direction"] != "NEUTRAL":
        lines.append(f"نقطه ورود: {sig['entry']:.2f}")
        lines.append(f"حد ضرر (SL): {sig['sl']:.2f}")
        lines.append(f"حد سود (TP): {sig['tp']:.2f}")

    lines.append("-" * 38)
    rsi_txt = f"{sig['rsi']:.1f}" if sig["rsi"] is not None else "—"
    lines.append(f"RSI(14): {rsi_txt}")
    lines.append(f"EMA9: {sig['ema_fast']:.2f} | EMA21: {sig['ema_slow']:.2f} | EMA50: {sig['ema_trend']:.2f}")
    lines.append(f"ATR(14): {sig['atr']:.2f}")
    return "\n".join(lines)


def main(argv):
    if len(argv) < 2:
        print("خطا: مسیر فایل CSV را وارد کنید.")
        print("روش استفاده: python bot/signal_engine.py <file.csv>")
        return 1
    candles = load_candles(argv[1])
    if len(candles) < EMA_TREND + 1:
        print("خطا: داده کافی برای محاسبه وجود ندارد.")
        return 1
    sig = generate_signal(candles)
    print(format_persian(sig))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
