# Claude Code — Trading / Technical Analysis Setup

اسکیل‌ها و پلاگین‌های نصب‌شده برای پروژه‌ی تحلیل تکنیکال و تولید سیگنال خرید/فروش
(دیتای OHLCV، اندیکاتورهای RSI/MACD/Bollinger/Ichimoku، و Smart Money Concepts).

## پلاگین‌های مارکت‌پلیس (در `settings.json`)

با باز کردن پروژه در Claude Code این مارکت‌پلیس‌ها شناخته می‌شن و پلاگین‌ها فعال می‌شن
(اولین بار ممکنه Claude Code برای trust پرامپت بده):

| پلاگین | مارکت‌پلیس (ریپو) | کاربرد |
|--------|-------------------|--------|
| `trading-skills` | [`agiprolabs/claude-trading-skills`](https://github.com/agiprolabs/claude-trading-skills) | ۶۷ اسکیل ترید/کوانت: `pandas-ta` (RSI/MACD/Bollinger/Ichimoku/SuperTrend)، `ta-lib`، `ohlcv-processing`، `signal-classification`، `trading-visualization` |
| `tvremix` | [`tvremix/claude-plugin`](https://github.com/tvremix/claude-plugin) | Smart Money Concepts: BOS، CHoCH، Order Blocks، FVG، Premium/Discount، ساختار سوینگ. دستورات `/tvremix:*` (نیاز به اتصال TradingView/MCP) |
| `trading-ideas` | [`quant-sentiment-ai/claude-equity-research`](https://github.com/quant-sentiment-ai/claude-equity-research) | ریتینگ BUY/SELL/HOLD با تارگت قیمت و position sizing. دستور `/trading-ideas:research <TICKER>` |

## اسکیل‌های محلی (در `.claude/skills/`)

از [`shakeebshaan/claude-code-quant-skills`](https://github.com/shakeebshaan/claude-code-quant-skills)
(مارکت‌پلیس نداشت، مستقیم داخل ریپو کپی شد):

- `indicator-design` — طراحی اندیکاتور کاستوم با pandas وکتورایز از یک ایده‌ی معاملاتی
- `backtest-review` — بررسی بک‌تست برای look-ahead/overfitting/هزینه‌ها
- `risk-report` — متریک‌های ریسک: Sharpe/Sortino/MaxDD/CVaR
- `strategy-critique` — نقد ریسک‌محور استراتژی
- `hedge-lab` — روش‌های هجینگ (delta hedge / basis trade)
- `data-scrub` — اعتبارسنجی دیتای بازار (بارهای گم‌شده، تایم‌زون، تکراری)

## نکته
همه‌ی این‌ها برای اهداف آموزشی/پژوهشی هستن و توصیه‌ی مالی محسوب نمی‌شن.
