Market-Impact-Aware Algorithmic Trading Agent
An adaptive execution strategy built on the ABIDES agent-based market simulator to minimize market footprint and reduce slippage compared to a standard Time-Weighted Average Price (TWAP) baseline.
📌 Executive Summary
When institutional investors execute large block orders, naive execution algorithms (such as TWAP) often suffer from significant adverse selection and self-induced market impact. By repeatedly walking thin order books, these baseline strategies drive prices against themselves, inflating execution costs.
This project implements a Market-Impact-Aware Trading Agent within the ABIDES framework. By dynamic self-impact measurement, order-book depth caps, and opportunistic price-tilt mechanisms, the agent dynamically paces order slices to measurably reduce slippage against the initial arrival price.
🛠 Strategy Architecture & Key Mechanics
The MarketImpactAwareAgent improves execution performance over TWAP using four core mechanisms:
Self-Impact Accounting (EMA Governor):
Measures execution cost relative to the mid-price at order transmission time.
Maintains an Exponential Moving Average (EMA) of temporary market footprint (my_temporary_impact).
Automatically shrinks subsequent slice sizes when recent fills show elevated market impact.
Book-Aware Depth Protection:
Constrains individual slice quantities based on visible ask volume up to book_depth levels.
Prevents walking thin books and over-penalizing execution during liquidity droughts.
Opportunistic Price Tilt:
Dynamically increases slice size when the prevailing mid-price dips below a reference level (arrival mid-price or short EMA).
Reduces slice size during temporary price spikes.
Schedule Band Enforcement:
Keeps cumulative execution within a strict percentage band (±band_pct) around the linear TWAP schedule.
Prevents premature budget exhaustion or excessive forced trading near the execution deadline.
📁 Repository Structure
.
├── MarketImpactAwareAgent.py  # Primary adaptive execution strategy class
├── TWAPAgent.py               # TWAP baseline agent implementation
├── run_execution_sim.py       # Multi-seed comparative simulation harness
└── README.md                  # Strategy documentation
​
🚀 Quickstart & Usage
Prerequisites
