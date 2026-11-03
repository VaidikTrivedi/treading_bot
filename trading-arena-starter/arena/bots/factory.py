from arena.bots.mean_reversion import MeanReversionBot
from arena.bots.momentum import MomentumBot
from arena.bots.rotation import RotationBot

STRATEGIES = {"momentum": MomentumBot, "mean_reversion": MeanReversionBot, "rotation": RotationBot}


def make_bot(bot_id, strategy, genome, created_date):
    return STRATEGIES[strategy](bot_id, genome, created_date)
