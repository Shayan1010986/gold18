"""Minimal smoke test for signal_engine — synthesizes M5 data, runs the engine,
checks it returns a Persian report without raising. Run: python3 bot/test_smoke.py"""
import os
import tempfile
import numpy as np
import pandas as pd

import signal_engine as se


def _make_csv(path, n=2500, trend=1.0, seed=0):
    rng = np.random.default_rng(seed)
    # 5-minute bars over trading hours 09:00-22:00
    start = pd.Timestamp("2026-06-01 09:00:00")
    idx = pd.date_range(start, periods=n, freq="5min")
    idx = idx[(idx.hour >= 9) & (idx.hour < 22)][:n]
    price = 18_000_000 + np.cumsum(rng.normal(trend * 200, 4000, len(idx)))
    o = price
    c = price + rng.normal(0, 3000, len(idx))
    h = np.maximum(o, c) + np.abs(rng.normal(0, 3000, len(idx)))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 3000, len(idx)))
    df = pd.DataFrame({
        "<DTYYYYMMDD>": idx.strftime("%Y%m%d"),
        "<TIME>": idx.strftime("%H%M%S").str.lstrip("0"),
        "<OPEN>": o.round().astype(int),
        "<HIGH>": h.round().astype(int),
        "<LOW>": l.round().astype(int),
        "<CLOSE>": c.round().astype(int),
        "<VOL>": rng.integers(1, 30, len(idx)),
    })
    df.to_csv(path, index=False)


def main():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "synth.csv")
        _make_csv(p)
        report = se.run(p)
        assert isinstance(report, str) and len(report) > 50, "empty report"
        assert "طلای ۱۸ عیار" in report, "missing Persian header"
        assert ("سیگنال" in report) or ("مناسب نیست" in report), "no verdict"
        # engine must never score on a forming bin: scores are ints in [-3,3]
        ctx, sigs = se.analyze(p)
        for k in ("s4", "s1", "s15"):
            assert -3 <= ctx[k] <= 3, f"bad score {k}={ctx[k]}"
        for sg in sigs:
            assert sg["net_rr"] >= se.MIN_NET_RR, "signal below min net RR"
    print("smoke test: PASS")


if __name__ == "__main__":
    main()
