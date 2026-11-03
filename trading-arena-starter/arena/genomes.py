"""Gene definitions: (type, initial, min, max). Source of truth for initial bots, bounds and mutation."""
GENES = {
    "momentum": {
        "lookback_days":      ("int",   20,   5,     60),
        "entry_threshold":    ("float", 0.03, 0.005, 0.15),
        "stop_loss":          ("float", 0.05, 0.01,  0.20),
        "take_profit":        ("float", 0.08, 0.02,  0.40),
        "max_position_pct":   ("float", 0.50, 0.10,  1.00),
        "max_open_positions": ("int",   2,    1,     4),
    },
    "mean_reversion": {
        "ma_days":            ("int",   20,   5,     60),
        "entry_z":            ("float", 1.5,  0.5,   3.0),
        "exit_z":             ("float", 0.0,  -0.5,  1.0),
        "stop_loss":          ("float", 0.06, 0.01,  0.20),
        "max_position_pct":   ("float", 0.50, 0.10,  1.00),
        "max_open_positions": ("int",   2,    1,     4),
    },
    "rotation": {
        "lookback_days":      ("int",   30,   10,    90),
        "rebalance_days":     ("int",   5,    1,     20),
        "top_n":              ("int",   1,    1,     3),
        "min_return_to_hold": ("float", 0.0,  -0.05, 0.05),
    },
}

INITIAL_BOTS = [("bot_001", "momentum"), ("bot_002", "mean_reversion"), ("bot_003", "rotation")]


def initial_genome(strategy: str) -> dict:
    return {name: spec[1] for name, spec in GENES[strategy].items()}
