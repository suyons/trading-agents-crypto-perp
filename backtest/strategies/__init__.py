from .ema_cross import ema_cross
from .rsi_mr import rsi_mr
from .donchian import donchian_breakout
from .atr_renko import atr_renko

REGISTRY = {
    "ema_cross": ema_cross,
    "rsi_mr": rsi_mr,
    "donchian": donchian_breakout,
    "atr_renko": atr_renko,
}
