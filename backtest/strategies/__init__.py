from .ema_cross import ema_cross
from .rsi_mr import rsi_mr
from .donchian import donchian_breakout

REGISTRY = {
    "ema_cross": ema_cross,
    "rsi_mr": rsi_mr,
    "donchian": donchian_breakout,
}
