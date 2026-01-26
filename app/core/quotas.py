# default free tier
DEFAULT_QUOTAS = {
    "max_runs_per_month": 1_000,
    "max_cost_cents_per_month": 10_00,  # $10.00
}

PLAN_QUOTAS = {
    "free": {
        "max_runs_per_month": 1_000,
        "max_cost_cents_per_month": 10_00,   # $10.00
    },
    "pro": {
        "max_runs_per_month": 50_000,
        "max_cost_cents_per_month": 500_00,  # $500.00
    },
    "team": {
        "max_runs_per_month": 200_000,
        "max_cost_cents_per_month": 2_000_00,  # $2,000.00
    },
}

DEFAULT_PLAN = "free"