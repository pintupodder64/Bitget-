"""
stats.py — CLI database inspector.

View signal history, open positions, and performance stats directly
from the terminal without writing raw SQL.

Usage:
    python stats.py recent              # last 20 signals across all pairs
    python stats.py recent BTCUSDT      # filter by symbol
    python stats.py recent BTCUSDT 50   # last 50 for that symbol
    python stats.py open                # all currently OPEN signals
    python stats.py performance         # win rate + avg R across closed signals
    python stats.py pairs               # per-symbol breakdown
    python stats.py events              # last 30 bot events (START/STOP/ERROR)
"""

import sys
import argparse

import database as db
from notifier import fmt_price


def _print_header(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def cmd_recent(args):
    _print_header(f"Recent Signals — {args.symbol or 'all pairs'} (limit {args.limit})")
    rows = db.get_recent_signals(limit=args.limit, symbol=args.symbol)
    if not rows:
        print("  No signals found.")
        return
    print(f"  {'#':<5} {'Time':<20} {'Symbol':<10} {'Dir':<6} {'Entry':<14} {'Status':<10} {'R'}")
    print(f"  {'─'*5} {'─'*20} {'─'*10} {'─'*6} {'─'*14} {'─'*10} {'─'*6}")
    for r in rows:
        r_val = f"{r['pnl_r_multiple']:.2f}R" if r["pnl_r_multiple"] is not None else "—"
        print(
            f"  #{r['id']:<4} {r['created_at']:<20} {r['symbol']:<10} "
            f"{r['direction']:<6} {fmt_price(r['entry']):<14} "
            f"{r['status']:<10} {r_val}"
        )


def cmd_open(args):
    _print_header("Open Signals")
    rows = db.get_open_signals()
    if not rows:
        print("  No open signals.")
        return
    print(f"  {'#':<5} {'Time':<20} {'Symbol':<10} {'Dir':<6} {'Entry':<14} {'SL':<14} {'TP'}")
    print(f"  {'─'*5} {'─'*20} {'─'*10} {'─'*6} {'─'*14} {'─'*14} {'─'*14}")
    for r in rows:
        print(
            f"  #{r['id']:<4} {r['created_at']:<20} {r['symbol']:<10} "
            f"{r['direction']:<6} {fmt_price(r['entry']):<14} "
            f"{fmt_price(r['stop_loss']):<14} {fmt_price(r['take_profit'])}"
        )


def cmd_performance(args):
    _print_header("Performance Summary (closed signals only)")
    rows = db.get_performance_summary()
    if not rows:
        print("  No closed signals yet.")
        return

    total    = sum(r["cnt"] for r in rows)
    tp_count = sum(r["cnt"] for r in rows if r["status"] == "TP_HIT")
    total_r  = sum(r["total_r"] or 0 for r in rows)
    win_rate = (tp_count / total * 100) if total else 0

    print(f"  {'Status':<12} {'Count':<8} {'Avg R':<10} {'Total R'}")
    print(f"  {'─'*12} {'─'*8} {'─'*10} {'─'*10}")
    for r in rows:
        avg_r   = f"{r['avg_r']:.2f}"   if r["avg_r"]   is not None else "—"
        total_rr = f"{r['total_r']:.2f}" if r["total_r"] is not None else "—"
        print(f"  {r['status']:<12} {r['cnt']:<8} {avg_r:<10} {total_rr}")

    print(f"\n  Total closed:  {total}")
    print(f"  Win rate:      {win_rate:.1f}%  ({tp_count} TP / {total - tp_count} SL+expired)")
    print(f"  Net R:         {total_r:.2f}R")


def cmd_pairs(args):
    _print_header("Per-Symbol Breakdown (closed signals)")
    rows = db.get_signals_by_symbol_summary()
    if not rows:
        print("  No closed signals yet.")
        return
    print(f"  {'Symbol':<12} {'Total':<8} {'TP':<6} {'SL':<6} {'Win%':<8} {'Avg R'}")
    print(f"  {'─'*12} {'─'*8} {'─'*6} {'─'*6} {'─'*8} {'─'*8}")
    for r in rows:
        win_pct = (r["tp_count"] / r["total"] * 100) if r["total"] else 0
        avg_r   = f"{r['avg_r']:.2f}" if r["avg_r"] is not None else "—"
        print(
            f"  {r['symbol']:<12} {r['total']:<8} {r['tp_count']:<6} "
            f"{r['sl_count']:<6} {win_pct:<8.1f} {avg_r}"
        )


def cmd_events(args):
    _print_header("Bot Events (last 30)")
    db.init_db()
    from database import _cursor
    with _cursor() as cur:
        cur.execute(
            "SELECT occurred_at, event_type, message FROM bot_events "
            "ORDER BY occurred_at DESC LIMIT 30"
        )
        rows = cur.fetchall()
    if not rows:
        print("  No events recorded.")
        return
    for r in rows:
        print(f"  [{r['occurred_at']}] {r['event_type']:<8}  {r['message']}")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect the Bitget signal bot database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # recent
    p_recent = sub.add_parser("recent", help="Show recent signals")
    p_recent.add_argument("symbol", nargs="?", default=None,
                          help="Filter by symbol, e.g. BTCUSDT")
    p_recent.add_argument("limit", nargs="?", type=int, default=20,
                          help="Max rows to show (default 20)")
    p_recent.set_defaults(func=cmd_recent)

    # open
    p_open = sub.add_parser("open", help="Show currently open signals")
    p_open.set_defaults(func=cmd_open)

    # performance
    p_perf = sub.add_parser("performance", help="Win rate and avg R")
    p_perf.set_defaults(func=cmd_performance)

    # pairs
    p_pairs = sub.add_parser("pairs", help="Per-symbol breakdown")
    p_pairs.set_defaults(func=cmd_pairs)

    # events
    p_events = sub.add_parser("events", help="Recent bot events")
    p_events.set_defaults(func=cmd_events)

    args = parser.parse_args()
    db.init_db()
    args.func(args)
    print()


if __name__ == "__main__":
    main()
