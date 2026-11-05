"""Black–Scholes pricing, Greeks, implied volatility and an American binomial tree (Python port of the
app's options lab, used by the MCP server). Rates, yields and volatilities are fractions, T in years."""

from __future__ import annotations

import math

SQRT2PI = math.sqrt(2 * math.pi)


def _cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT2PI


def _validate(S: float, K: float, T: float, sigma: float) -> None:
    if not (S > 0 and K > 0 and T > 0 and sigma > 0):
        raise ValueError("spot, strike, time and volatility must all be positive")


def black_scholes(kind: str, S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    _validate(S, K, T, sigma)
    vt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vt
    d2 = d1 - vt
    if kind == "call":
        return S * math.exp(-q * T) * _cdf(d1) - K * math.exp(-r * T) * _cdf(d2)
    if kind == "put":
        return K * math.exp(-r * T) * _cdf(-d2) - S * math.exp(-q * T) * _cdf(-d1)
    raise ValueError("kind must be 'call' or 'put'")


def greeks(kind: str, S: float, K: float, T: float, r: float, q: float, sigma: float) -> dict:
    _validate(S, K, T, sigma)
    vt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vt
    d2 = d1 - vt
    dq, df = math.exp(-q * T), math.exp(-r * T)
    call = kind == "call"
    common = -(S * dq * _pdf(d1) * sigma) / (2 * math.sqrt(T))
    theta = (common - r * K * df * _cdf(d2) + q * S * dq * _cdf(d1)) if call else (common + r * K * df * _cdf(-d2) - q * S * dq * _cdf(-d1))
    return {
        "delta": dq * _cdf(d1) if call else dq * (_cdf(d1) - 1),
        "gamma": dq * _pdf(d1) / (S * vt),
        "vega_per_vol_point": S * dq * _pdf(d1) * math.sqrt(T) / 100,
        "theta_per_day": theta / 365,
        "rho_per_rate_point": (K * T * df * _cdf(d2) if call else -K * T * df * _cdf(-d2)) / 100,
    }


def binomial(kind: str, S: float, K: float, T: float, r: float, q: float, sigma: float, steps: int = 400, american: bool = True) -> float:
    _validate(S, K, T, sigma)
    dt = T / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not 0 < p < 1:
        raise ValueError("binomial tree unstable for these inputs")
    disc = math.exp(-r * dt)

    def pay(s: float) -> float:
        return max(s - K, 0.0) if kind == "call" else max(K - s, 0.0)

    v = [pay(S * u ** (steps - i) * d**i) for i in range(steps + 1)]
    for n in range(steps - 1, -1, -1):
        for i in range(n + 1):
            cont = disc * (p * v[i] + (1 - p) * v[i + 1])
            v[i] = max(cont, pay(S * u ** (n - i) * d**i)) if american else cont
    return v[0]


def implied_vol(price: float, kind: str, S: float, K: float, T: float, r: float, q: float) -> float | None:
    """Volatility that reproduces `price`, or None if the price breaks no-arbitrage bounds."""
    fwd, pvk = S * math.exp(-q * T), K * math.exp(-r * T)
    lower, upper = (max(fwd - pvk, 0), fwd) if kind == "call" else (max(pvk - fwd, 0), pvk)
    if not lower + 1e-12 < price < upper - 1e-12:
        return None
    lo, hi = 1e-6, 5.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if black_scholes(kind, S, K, T, r, q, mid) > price:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)
