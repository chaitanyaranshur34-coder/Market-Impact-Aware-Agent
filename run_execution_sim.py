"""Market-impact-aware execution vs TWAP baseline (ABIDES).

Each agent executes an identical 5,000-share buy program in its own copy of
the same simulated market (same seed), so the comparison isolates strategy
quality instead of letting the two programs interfere with each other through
mutual market impact.
"""

import pandas as pd

from abides_markets.configs import rmsc04
from abides_core import abides

from TWAPAgent import TWAPAgent
from MarketImpactAwareAgent import MarketImpactAwareAgent

# --- experiment configuration ---
SEEDS = [12345, 7, 42, 1, 99, 123, 777, 2026]  # edit to add/remove trials
SYMBOL = "ABM"
START_TIME = pd.Timestamp("2021-02-05 09:35:00").value
END_TIME = pd.Timestamp("2021-02-05 10:35:00").value
TOTAL_SHARES = 5000
INTERVAL_SEC = 60
SIM_END = "16:00:00"  # market close for the background config


def run_agent(seed, cls, name, **kwargs):
    config = rmsc04.build_config(seed=seed, end_time=SIM_END)
    agent = cls(
        id=len(config["agents"]) - 1,
        name=name,
        type="ExecutionAgent",
        symbol=SYMBOL,
        starting_cash=10_000_000,
        total_shares=TOTAL_SHARES,
        start_time=START_TIME,
        end_time=END_TIME,
        interval_seconds=INTERVAL_SEC,
        **kwargs,
    )
    config["agents"][-1] = agent
    end_state = abides.run(config)
    return {a.id: a for a in end_state["agents"]}[agent.id]


def metrics(agent):
    if agent.total_shares_filled == 0:
        return None
    avg = agent.total_cost / agent.total_shares_filled
    slip = None
    if agent.arrival_price:
        slip = (avg - agent.arrival_price) / agent.arrival_price * 1e4
    return {
        "filled": agent.total_shares_filled,
        "notional": agent.total_cost / 100.0,
        "avg": avg / 100.0,
        "arrival": (agent.arrival_price or 0) / 100.0,
        "slip": slip,
    }


def print_metrics(name, m):
    print(f"--- {name} ---")
    if m is None:
        print("Status:            No shares were filled.\n")
        return
    fill_rate = m["filled"] / TOTAL_SHARES * 100.0
    print(f"Shares Filled:     {m['filled']:,} / {TOTAL_SHARES:,} ({fill_rate:.1f}%)")
    print(f"Total Notional:    ${m['notional']:,.2f}")
    print(f"Avg Exec Price:    ${m['avg']:.4f}")
    if m["slip"] is None:
        print("Arrival Price:     N/A")
        print("Slippage:          N/A\n")
    else:
        print(f"Arrival Price:     ${m['arrival']:.4f}")
        print(f"Slippage vs Arrv:  {m['slip']:+.2f} bps\n")


print("Running TWAP baseline and impact-aware agent in separate, identical markets")
print(f"({len(SEEDS)} seeds x 2 simulations)...\n")

rows = []
for seed in SEEDS:
    twap = run_agent(seed, TWAPAgent, "My_TWAP_Baseline")
    impact = run_agent(seed, MarketImpactAwareAgent, "My_Impact_Aware_Agent")

    mt, mi = metrics(twap), metrics(impact)
    print(f"=== SEED {seed} ===")
    print_metrics("TWAP BASELINE", mt)
    print_metrics("MARKET IMPACT AWARE AGENT", mi)

    if mt is None or mi is None or mt["slip"] is None or mi["slip"] is None:
        print("Improvement:       N/A\n")
        continue
    diff = mt["slip"] - mi["slip"]
    rows.append((seed, mt["slip"], mi["slip"], diff))
    print(f"Improvement:       {diff:+.2f} bps (positive = impact-aware agent better)\n")

print("=" * 60)
print("                 SUMMARY ACROSS SEEDS")
print("=" * 60)
print(f"{'seed':>8} {'twap':>9} {'impact':>9} {'diff':>9}")
for seed, ts, islip, diff in rows:
    print(f"{seed:>8} {ts:>+8.2f}b {islip:>+8.2f}b {diff:>+8.2f}b")

if rows:
    diffs = [d for _, _, _, d in rows]
    avg = sum(diffs) / len(diffs)
    wins = sum(1 for d in diffs if d > 0)
    print("-" * 60)
    print(f"Average improvement: {avg:+.2f} bps   (impact-aware wins {wins}/{len(diffs)} seeds)")
    print()
    if avg > 0 and wins > len(diffs) / 2:
        print("CONCLUSION: PASS - the impact-aware agent measurably beats the TWAP baseline.")
    else:
        print("CONCLUSION: FAIL - the impact-aware agent does not beat the TWAP baseline.")
else:
    print("CONCLUSION: N/A - no completed comparisons.")
print("=" * 60)
