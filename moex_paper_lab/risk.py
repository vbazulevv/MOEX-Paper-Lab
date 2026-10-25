"""Simple educational risk alerts; not financial advice."""
from __future__ import annotations

from decimal import Decimal
from .models import RiskFlag, Snapshot, money


def assess_risk(
    snapshot: Snapshot,
    max_position_weight: str = "0.40",
    loss_warning: str = "0.10",
) -> list[RiskFlag]:
    max_weight = money(max_position_weight, "concentration threshold")
    max_loss = money(loss_warning, "loss threshold")
    if not 0 < max_weight <= 1 or not 0 < max_loss <= 1:
        raise ValueError("risk thresholds must be greater than 0 and at most 1")
    flags: list[RiskFlag] = []
    for row in snapshot.positions:
        if snapshot.market_value > 0:
            weight = row.market_value / snapshot.market_value
            if weight > max_weight:
                flags.append(RiskFlag(
                    row.ticker, "concentration",
                    f"position weight {weight:.1%} exceeds {max_weight:.0%}",
                ))
        if row.average_cost > 0:
            decline = (row.average_cost - row.market_price) / row.average_cost
            if decline > max_loss:
                flags.append(RiskFlag(
                    row.ticker, "paper_loss",
                    f"price {decline:.1%} below average cost (alert: {max_loss:.0%})",
                ))
    return flags
