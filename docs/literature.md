# Related work and positioning (checked 2026-11-07)

"Verified" means the bibliographic details and main finding were confirmed from an abstract or
the paper itself. "To read" means cited from memory and not yet confirmed.

## Verified

1. **Courteau, Kao & Richardson (2001)**, "Equity Valuation Employing the Ideal versus Ad Hoc
   Terminal Value Expressions," *Contemporary Accounting Research* 18(4), 625–661.
   - Closest prior work. With Value Line forecasts, DCF and residual-income models that use the
     forecasted **price** as terminal value have much lower errors (against current price) than
     models whose terminal value assumes an arbitrary growth rate.
   - **Relation to us:** their "price-based TV wins" matches our "exit multiple wins against
     market EV". Both are graded against market prices, which is exactly the circularity we flag.
     We add realized fundamentals (perfect foresight) and a non-market truth (deal prices).
     We also use 2015–2025 data and conditional rules.
2. **Kaplan & Ruback (1995)**, "The Valuation of Cash Flow Forecasts: An Empirical Analysis,"
   *Journal of Finance* 50(4), 1059–1093.
   - 51 highly leveraged transactions (1983–89), valued with management forecasts. DCF values
     are within about 10% of transaction values on average, and DCF does at least as well as
     comparable-company and comparable-transaction multiples.
   - **Relation to us:** they found DCF matches deal prices; we find Gordon unbiased against deal
     prices but biased against market prices (exploration). Their sample is small and special
     (HLTs, management forecasts). Ours is 1,400+ public-target deals with standard inputs.
3. **Heinrichs, Hess, Homburg, Lorenz & Sievers (2011)**, "Extended Dividend, Cash Flow and
   Residual Income Valuation Models – Accounting for Deviations from Ideal Conditions," CFR
   Working Paper 11-11, University of Cologne. Deviations from ideal conditions, including
   terminal-value and steady-state assumptions, drive large valuation errors. Extended models
   reduce them. Final publication venue not yet checked.

## To read (from memory, unverified)

- Penman & Sougiannis (1998); Francis, Olsson & Oswald (2000); Lundholm & O'Keefe (2001) and
  Penman (2001). These form the DCF-vs-residual-income accuracy debate, including terminal values.
- Levin & Olsson (2000), "Terminal Value Techniques in Equity Valuation," SSE working paper
  (title found; authors and content unchecked).
- Liu, Nissim & Thomas (2002): accuracy of multiples-based valuation.
- Gilson, Hotchkiss & Ruback (2000): DCF vs market value in bankruptcy reorganizations.
- Bradshaw (2002, 2004): which valuation models sell-side analysts use.

A practitioner search found no large-sample test of perpetuity-growth versus exit-multiple
accuracy against realized outcomes. Practitioner sources treat the two as cross-checks.

## Positioning (what is new here)

1. **Formula error isolated:** TV formulas get realized outcome-year fundamentals. Only the
   formula and its parameters are graded, not cash-flow forecasts. Prior work grades whole
   models with analyst forecasts.
2. **Two truths on the same firms:** market EV vs acquisition price, with fundamentals held
   fixed. This tests the circularity that makes price-based terminal values look good in
   Courteau et al.
3. **Mechanism:** r − g convexity explains where Gordon fails (low-WACC firms), which reverses
   the textbook "Gordon for stable industries".
4. **Conditional rules written by AI agents,** with random-search and GBM benchmarks (SignalLab
   design).
5. **Data:** recent US data (2015–2025) with point-in-time Damodaran WACC, survivorship handled
   through M&A exits.
