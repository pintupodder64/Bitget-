# 🤖 Bitget Futures Signal Bot - Professional Edition

> **Advanced multi-factor trading signal generator for Bitget USDT-FUTURES**
> 
> Generates professional-grade signals with multiple take profit levels, detailed risk metrics, and optional automated order placement.

---

## 📋 Overview

A **signals-only** bot that:
- ✅ Scans top trading pairs every 15 minutes
- ✅ Generates **professional multi-TP signals** (TP1, TP2, TP3)
- ✅ Calculates precise **entry, SL, and TP levels** using ATR
- ✅ Shows **risk/reward ratios** for each TP level
- ✅ Provides **position sizing & leverage recommendations**
- ✅ Tracks **win rate & performance metrics**
- ✅ Sends alerts via **Telegram** with professional format
- ✅ Optional: **Auto-place orders** with API authentication

**Zero orders placed by default** — you execute manually or enable auto-orders.

---

## 🎯 Signal Quality

Every signal must pass **ALL 5 filters**:

1. **Higher-timeframe trend** (4H EMA crossover confirms direction)
2. **Lower-timeframe alignment** (1H EMA matches 4H trend)
3. **RSI filter** (not overbought/oversold — room to move)
4. **Breakout + volume spike** (above recent high/low with 1.5x volume)
5. **Funding rate check** (not overcrowded, risk-appropriate)

### Signal Confidence Score

0-100% based on:
- EMA alignment strength
- RSI neutrality (45-55 = best)
- Volume spike magnitude
- Funding rate favorability
- Breakout proximity to extremes

---

## 🚀 Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/Pintu64/Trade.git
cd Trade
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
python setup.py  # Interactive setup wizard
```

Minimum config:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
WHITELIST_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
```

### 3. Run
```bash
python main.py
```

Bot will:
- ✅ Validate all settings
- ✅ Initialize WebSocket for live tickers
- ✅ Start scanning on 15-minute intervals
- ✅ Send signals to Telegram when conditions align

---

## 📊 Professional Signal Format

Each signal includes:

### Price Levels
```
Entry Point    : $65,432.50
Stop Loss      : $64,500.25
```

### Multiple Take Profit Levels
```
TP1: $65,896.23 (30% position) → +1.42R [High confidence]
TP2: $66,743.75 (40% position) → +2.00R [Medium confidence]
TP3: $68,124.30 (30% position) → +4.11R [Lower confidence]
```

### Risk Metrics
```
Position Size  : 2.0% of account
Max Loss       : 1.5% if SL hit
ATR            : 145.67
Suggested Leverage: 3x (recommended)
```

### Market Context
```
RSI: 48.5 (neutral, room to move)
EMA Trend: LONG (aligned on both 4H and 1H)
Volume: Elevated (2.8x average)
Funding Rate: +0.045% (positive for longs)
```

### Confidence Analysis
```
✅ EMA20/50 aligned on both timeframes
✅ RSI neutral - room to move
✅ Breakout above 65000 with 1.6x volume
✅ Funding favorable
✅ Excellent setup - strong confluence (87% confidence)
```

---

## ⚙️ Configuration

### `.env` Parameters

#### Telegram (Required)
```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=-1001234567890
```

#### Trading Pairs
```env
WHITELIST_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT
MIN_24H_QUOTE_VOLUME_USDT=20000000
```

#### Timeframes
```env
TREND_TIMEFRAME=4H        # Higher timeframe for trend
SIGNAL_TIMEFRAME=1H       # Lower timeframe for entries
CANDLE_LIMIT=200          # Historical candles to fetch
```

#### Indicators
```env
EMA_FAST=20
EMA_SLOW=50
RSI_PERIOD=14
RSI_OVERBOUGHT=70
RSI_OVERSOLD=30
ATR_PERIOD=14
BREAKOUT_LOOKBACK=20
VOLUME_SPIKE_MULTIPLIER=1.5
```

#### Risk Management
```env
ATR_STOP_MULTIPLIER=1.5       # SL = entry ± 1.5×ATR
ATR_TARGET_MULTIPLIER=2.5     # TP = entry ± 2.5×ATR
ACCOUNT_RISK_PERCENT=1.0      # Risk per trade
MAX_ABS_FUNDING_RATE=0.0008    # Funding rate filter
```

#### Polling
```env
POLL_INTERVAL_SECONDS=900                    # Scan every 15min
MIN_MINUTES_BETWEEN_REPEAT_SIGNAL=240        # Same pair cooldown
SCAN_ERROR_BACKOFF_SECONDS=30                # Error retry delay
```

---

## 🔐 API Authentication (Optional)

To enable **automated order placement**, add credentials:

```env
BITGET_API_KEY=your_api_key
BITGET_API_SECRET=your_api_secret
BITGET_PASSPHRASE=your_passphrase
```

### Get Credentials
1. Log in to [Bitget](https://www.bitget.com/)
2. Account → API Management
3. Create new API with permissions:
   - Read: Account, Position, Order
   - Trade: Create/Cancel Orders, Modify Leverage/Margin
4. Enable **IP whitelist** for security

### Enable Auto-Orders
```env
ENABLE_AUTO_ORDERS=true
AUTO_ORDER_TYPE=limit           # or "market"
AUTO_ORDER_LEVERAGE=3           # 1-20x
AUTO_ORDER_MARGIN_MODE=isolated # or "crossed"
POSITION_SIZE_PERCENT=2.0       # % of account per trade
```

⚠️ **WARNING**: Only enable after testing!

---

## 📈 Viewing Performance

### Recent Signals
```bash
python stats.py recent BTCUSDT 20
```

Output:
```
─────────────────────────────────────────────────
  Recent Signals — BTCUSDT (limit 20)
─────────────────────────────────────────────────
  #  Time                 Symbol     Dir    Entry          Status      R
  ──────────────────────────────────────────────
  #42 2026-07-02 15:32:10 BTCUSDT   LONG   65432.50       TP_HIT      +2.15R
  #41 2026-07-02 14:15:23 ETHUSDT   SHORT  3245.30        OPEN        —
  #40 2026-07-02 13:00:45 SOLUSDT   LONG   145.32         SL_HIT      -1.00R
```

### Open Signals
```bash
python stats.py open
```

### Performance Summary
```bash
python stats.py performance
```

Output:
```
────────────────────────────────────────────────
  Performance Summary (closed signals only)
────────────────────────────────────────────────
  Status      Count    Avg R      Total R
  ────────────────────────────────────
  TP_HIT      28       +1.68      +47.04R
  SL_HIT      12       -1.00      -12.00R
  EXPIRED     2        -0.00      -0.00R

  Total closed: 42
  Win rate: 66.7% (28 TP / 14 SL+expired)
  Net R: +35.04R
```

### Per-Symbol Breakdown
```bash
python stats.py pairs
```

---

## 🐳 Docker Deployment

### Build Image
```bash
docker build -t bitget-signal-bot .
```

### Run Container
```bash
docker run -d \
  --name bitget-bot \
  -e TELEGRAM_BOT_TOKEN=your_token \
  -e TELEGRAM_CHAT_ID=your_chat \
  -e WHITELIST_SYMBOLS=BTCUSDT,ETHUSDT \
  -v $(pwd)/signal_bot.db:/app/signal_bot.db \
  -v $(pwd)/signal_bot.log:/app/signal_bot.log \
  bitget-signal-bot
```

---

## 🖥️ Systemd Service (Linux)

### Install
```bash
sudo cp bitget-signal-bot.service.txt /etc/systemd/system/bitget-signal-bot.service
sudo systemctl daemon-reload
sudo systemctl enable bitget-signal-bot
sudo systemctl start bitget-signal-bot
```

### View Logs
```bash
sudo journalctl -u bitget-signal-bot -f
```

### Manage
```bash
sudo systemctl stop bitget-signal-bot
sudo systemctl restart bitget-signal-bot
sudo systemctl status bitget-signal-bot
```

---

## 📁 Project Structure

```
Trade/
├── main.py                 # Main bot loop
├── signal_engine.py        # Signal generation logic
├── signal_formatter.py     # Professional signal formatting
├── notifier.py             # Telegram notifications
├── bitget_client.py        # Public API (candles, tickers, funding)
├── bitget_websocket.py     # Real-time ticker updates
├── bitget_auth_client.py   # Authenticated API (orders, positions)
├── indicators.py           # EMA, RSI, ATR calculations
├── database.py             # SQLite signal tracking
├── outcome_tracker.py      # TP/SL outcome detection
├── config.py               # Configuration management
├── stats.py                # CLI stats inspector
├── setup.py                # Interactive setup wizard
├── example_signals.py      # Demo signal examples
├── .env.example            # Configuration template
├── .env                    # Your secrets (git-ignored)
└── signal_bot.db           # Signal history database
```

---

## 🔒 Security Notes

- **Never commit `.env`** to version control
- Use **API IP whitelist** on Bitget account
- **Rotate API keys** periodically
- The bot **never reads incoming messages** (signals-only)
- Store credentials in environment or `.env`, never hardcoded
- Use **systemd service** with limited user permissions

---

## 🐛 Troubleshooting

### Bot won't start: `ConfigError: TELEGRAM_BOT_TOKEN not found`
**Solution**: Run `python setup.py` and set your Telegram credentials in `.env`

### No signals generated
**Checklist**:
- ✓ Is bot running? Check logs: `tail -f signal_bot.log`
- ✓ Are symbols in whitelist? Check: `python stats.py recent`
- ✓ Is market active? Check: `curl https://api.bitget.com/api/v2/mix/market/ticker?symbol=BTCUSDT`
- ✓ Did indicators warm up? Bot needs 60+ candles before signals

### WebSocket connection failing
**Solution**: Check internet connection and Bitget API status. Bot auto-reconnects with backoff.

### Database locked
**Solution**: Only one process can run at a time. Kill existing: `pkill -f "python main.py"`

---

## 📊 How Signals Are Generated

### Multi-Timeframe Analysis
1. **Fetch candles** from Bitget (1H for signals, 4H for trend)
2. **Calculate indicators**: EMA, RSI, ATR on both timeframes
3. **Check higher-TF trend** (4H EMA20/50 crossover)
4. **Verify lower-TF alignment** (1H EMA must match 4H trend)
5. **Filter RSI** (not overbought/oversold for the direction)
6. **Detect breakout** (above recent high/low + volume spike)
7. **Check funding rate** (within safe range)

### Risk Calculation
- **Entry** = current close price
- **Stop Loss** = entry ± (ATR × 1.5)
- **TP1** = entry ± (ATR × 1.5) → 30% position
- **TP2** = entry ± (ATR × 2.5) → 40% position
- **TP3** = entry ± (ATR × 4.0) → 30% position
- **Position Size** = (account_balance × risk_percent) / (entry - SL)

### Confidence Score
Ranges 0-100% based on:
- EMA alignment on both timeframes (+20)
- RSI neutrality at entry (+15)
- Volume spike magnitude (+15)
- Funding rate favorability (+10)
- Breakout strength (+25)

---

## 📚 API Reference

### `signal_engine.py`
```python
from signal_engine import evaluate_symbol

signal = evaluate_symbol(
    symbol="BTCUSDT",
    signal_df=df_1h,
    trend_df=df_4h,
    funding_rate=0.00045,
    account_balance=10000,
)

if signal:
    print(f"SIGNAL: {signal.direction} {signal.symbol}")
    print(f"Entry: {signal.entry}, SL: {signal.stop_loss}")
    for tp in signal.tp_levels:
        print(f"TP{tp.level}: {tp.price} (+{tp.reward_risk:.2f}R)")
```

### `signal_formatter.py`
```python
from signal_formatter import build_professional_signal, format_professional_signal_text

signal = build_professional_signal(
    symbol="BTCUSDT",
    direction="LONG",
    entry=65432.50,
    stop_loss=64500.25,
    atr=145.67,
    rsi=48.5,
    ema_direction="LONG",
    volume_spike=True,
    funding_rate=0.00045,
    account_balance=10000,
)

message = format_professional_signal_text(signal)
print(message)
```

### `bitget_auth_client.py` (Optional)
```python
from bitget_auth_client import place_limit_order, set_leverage, close_position

# Place order
order = place_limit_order(
    symbol="BTCUSDT",
    side="buy",
    quantity=0.01,
    price=65432.50,
)

# Set leverage
leverage = set_leverage(symbol="BTCUSDT", leverage=3)

# Close position
close = close_position(symbol="BTCUSDT", close_percentage=100.0)
```

### `notifier.py`
```python
from notifier import send_professional_signal, send_trade_outcome

send_professional_signal(signal)

send_trade_outcome(
    symbol="BTCUSDT",
    direction="LONG",
    entry=65432.50,
    exit_price=67123.75,
    tp_or_sl="TP_HIT",
    pnl_r=1.67,
)
```

---

## 📈 Performance Tips

- **Wider timeframes** (4H trend + 1H signals) = fewer, higher-quality signals
- **Narrower timeframes** (1H trend + 15m signals) = more signals, faster trades
- **Higher volume multiplier** = fewer but stronger signals
- **Lower RSI bands** = more signals, more whipsaws
- **Shorter CANDLE_LIMIT** = faster startup (but less warmup)

**Recommended for beginners**: 4H + 1H, default settings

---

## 📝 License

MIT License — Feel free to fork and modify

---

## ⚠️ Disclaimer

**TRADING INVOLVES RISK OF LOSS.** This bot:
- 🚫 Is NOT financial advice
- 🚫 Does NOT guarantee profit
- 🚫 Is PROVIDED AS-IS without warranty
- 📋 Is for **educational purposes only**
- ⚖️ Requires YOU to execute trades manually (or enable auto-orders at your own risk)

**You are responsible for:**
- ✓ Understanding all trades you execute
- ✓ Setting appropriate stop losses
- ✓ Position sizing
- ✓ Risk management
- ✓ All trades and outcomes

**Futures trading can result in rapid account liquidation.** Start small and never risk more than you can afford to lose.

---

## 🙋 Support & Contribution

Found a bug? Have a feature request?

- 📝 Open an issue on GitHub
- 🔀 Submit a pull request
- 💬 Discuss in Telegram

---

## 🚀 Next Steps

1. **Setup**: Run `python setup.py`
2. **Test**: Start with 1-2 pairs and default settings
3. **Monitor**: Watch signals for 1-2 weeks
4. **Analyze**: Review performance with `python stats.py performance`
5. **Optimize**: Adjust indicators if needed
6. **Scale**: Add more pairs or expand allocation

Happy trading! 📊🚀
