# ADR-0018: Reward points replace kWh credit

**Supersedes:** [ADR-0015](0015-rewards-are-data-not-points.md)

**Status:** Accepted in prototype (`web/milestones.js`, 2026-09-27)
**Date:** 2026-09-27

## Context

ADR-0015 set reward amounts in kWh of member energy, on the reasoning that a kWh credit costs Base its marginal cost rather than retail cash. Judges and members read a kWh reward as an energy promise sitting next to real ERCOT and battery numbers on the same pages, which blurs the line between measured energy facts and a proposed loyalty mechanic.

## Decision

Rewards keep their amounts and rules from ADR-0015, but the unit changes from kWh to points ("pts"), a currency clearly not energy:

| Event | Reward |
|---|---|
| Member confirms one open field | 10 pts |
| Member takes the panel photo | 20 pts |
| Every open task done | 30 pts bonus |
| A neighbour joins from the member's link | 50 pts per join |
| Cap per home | 100 pts |

Every reward line carries the label "Base Fleet points (proposal)" instead of "proposed credit," to keep it plainly a proposal, not an energy figure.

Redeem options (proposal, not a Base offer):
- 100 pts = $10 bill credit
- 150 pts = priority engineering review slot
- Give points to a neighbour's first month

Real energy numbers — battery kWh, backup hours, the energy page, ERCOT prices, grid data — are unaffected and stay in kWh. Only the reward/credit currency changes.

## Consequences

- No page can read as promising energy the member has not been billed or credited for; points are visibly a proposal.
- `web/milestones.js` is the single source of the points table and label; pages that show rewards read from it rather than hardcoding kWh strings.
- Redeem options give the points a concrete, discussable value without Base having committed to any of them.
