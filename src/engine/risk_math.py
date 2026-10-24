"""Shared arithmetic policies, independent of runtime configuration and I/O."""


def profit_factor(winning_pnls, losing_pnls):
    """Platform ratio of strictly positive/negative PnLs; no losses returns zero.

    Callers retain classification, units and result schemas. Do not use this for
    trainer metrics, whose no-loss result is infinity. Preserve native numeric
    behavior (including nonfinite values) without coercion or rounding.
    """
    return abs(sum(winning_pnls) / sum(losing_pnls)) if losing_pnls else 0
