from __future__ import annotations

from dataclasses import dataclass

from .receipts import Receipts


@dataclass
class CostTracker:
    receipts: Receipts
    cap_usd: float = 25.0
    spent_usd: float = 0.0

    def charge(self, label: str, amount_usd: float, *, provider: str = "local") -> None:
        next_total = self.spent_usd + amount_usd
        self.receipts.log(
            "cost_charge",
            label=label,
            provider=provider,
            amount_usd=round(amount_usd, 6),
            prior_spent_usd=round(self.spent_usd, 6),
            next_spent_usd=round(next_total, 6),
            cap_usd=self.cap_usd,
        )
        if next_total > self.cap_usd:
            self.receipts.log("blocker", code="cost_cap_exceeded", spent_usd=next_total, cap_usd=self.cap_usd)
            raise RuntimeError(f"cost_cap_exceeded: {next_total:.4f} > {self.cap_usd:.4f}")
        self.spent_usd = next_total

    def summary(self) -> dict[str, float]:
        return {"spent_usd": round(self.spent_usd, 6), "cap_usd": self.cap_usd}
