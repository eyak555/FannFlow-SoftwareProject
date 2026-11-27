from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.db.models import Sum

from events_program.models import Event
from sponsors_finance.models import Budget


@dataclass(frozen=True)
class EventFinancialSummary:
    planned_budget: Optional[Decimal]
    total_expenses: Decimal
    remaining_budget: Optional[Decimal]


def calculate_event_finances(event: Event) -> EventFinancialSummary:
    try:
        planned_budget = event.budget.planned_amount
    except Budget.DoesNotExist:
        planned_budget = None

    total_expenses = event.expenses.aggregate(total=Sum("amount"))["total"]
    total_expenses = total_expenses or Decimal("0.00")
    remaining_budget = (
        planned_budget - total_expenses if planned_budget is not None else None
    )

    return EventFinancialSummary(
        planned_budget=planned_budget,
        total_expenses=total_expenses,
        remaining_budget=remaining_budget,
    )
