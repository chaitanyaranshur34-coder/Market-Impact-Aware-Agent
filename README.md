# Market-Impact-Aware Algorithmic Trading Agent

> An adaptive execution strategy built on the ABIDES agent-based market simulator to minimize market footprint and reduce slippage compared to a standard Time-Weighted Average Price (TWAP) baseline.

---

## 📌 Executive Summary

When institutional investors execute large block orders, naive execution algorithms (such as TWAP) often suffer from significant adverse selection and self-induced market impact. By repeatedly walking thin order books, these baseline strategies drive prices against themselves, inflating execution costs.

This project implements a **Market-Impact-Aware Trading Agent** within the [ABIDES]([https://github.com/abides-sim/abides-core](https://github.com/jpmorganchase/abides-jpmc-public.git)) framework. By dynamic self-impact measurement, order-book depth caps, and opportunistic price-tilt mechanisms, the agent dynamically paces order slices to measurably reduce slippage against the initial arrival price.

---

## 🛠 Strategy Architecture & Key Mechanics

The `MarketImpactAwareAgent` improves execution performance over TWAP using four core mechanisms:

1. **Self-Impact Accounting (EMA Governor):**
   * Measures execution cost relative to the mid-price at order transmission time.
   * Maintains an Exponential Moving Average (EMA) of temporary market footprint (`my_temporary_impact`).
   * Automatically shrinks subsequent slice sizes when recent fills show elevated market impact.

2. **Book-Aware Depth Protection:**
   * Constrains individual slice quantities based on visible ask volume up to `book_depth` levels.
   * Prevents walking thin books and over-penalizing execution during liquidity droughts.

3. **Opportunistic Price Tilt:**
   * Dynamically increases slice size when the prevailing mid-price dips below a reference level (arrival mid-price or short EMA).
   * Reduces slice size during temporary price spikes.

4. **Schedule Band Enforcement:**
   * Keeps cumulative execution within a strict percentage band (`±band_pct`) around the linear TWAP schedule.
   * Prevents premature budget exhaustion or excessive forced trading near the execution deadline.

---

## 📁 Repository Structure

```text
.
├── MarketImpactAwareAgent.py  # Primary adaptive execution strategy class
├── TWAPAgent.py               # TWAP baseline agent implementation
├── run_execution_sim.py       # Multi-seed comparative simulation harness
└── README.md                  # Strategy documentation
```

---

## 🚀 Quickstart & Usage

### Prerequisites
Ensure you have Python 3.8+ installed along with the standard data stack and ABIDES market simulation framework:

```bash
pip install pandas numpy
# Ensure ABIDES (abides-core and abides-markets) is installed in your environment
```

### Running the Comparison Harness
The simulation runner executes identical 5,000-share buy programs across independent, identical market instances (using matching random seeds) to isolate strategy quality from mutual market interference:

```bash
python run_execution_sim.py
```

### Example Simulation Output

```text
Running TWAP baseline and impact-aware agent in separate, identical markets
(8 seeds x 2 simulations)...

============================================================
                 SUMMARY ACROSS SEEDS
============================================================
    seed      twap    impact      diff
   12345    +12.40b   +8.15b    +4.25b
       7     +9.80b   +6.10b    +3.70b
      42    +14.10b   +9.30b    +4.80b
...
------------------------------------------------------------
Average improvement: +4.25 bps   (impact-aware wins 8/8 seeds)

CONCLUSION: PASS - the impact-aware agent measurably beats the TWAP baseline.
============================================================
```

---

## 📊 Key Metrics Tracked

* **Fill Rate (%):** Executed volume vs. targeted total order size.
* **Effective Price ($):** Total notional cost divided by total shares filled.
* **Slippage (bps):** Percentage deviation between final execution price and arrival mid-price:
  $$\text{Slippage (bps)} = \frac{\bar{P}_{\text{exec}} - P_{\text{arrival}}}{P_{\text{arrival}}} \times 10^4$$

---

## 🏷 Proposed Resume Bullet Points

* **Adaptive Execution Agent (ABIDES):** Engineered a market-impact-aware execution agent in Python using ABIDES to optimize 5,000-share block orders, reducing execution slippage vs. a TWAP baseline across multi-seed market simulations.
* **Market Microstructure Controls:** Implemented real-time self-impact accounting (EMA filter), visible ask-depth volume capping, and schedule-constrained opportunistic price tilting to protect order placement in thin order books.
