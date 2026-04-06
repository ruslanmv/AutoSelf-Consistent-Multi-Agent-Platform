# autoself/stats.py
# -*- coding: utf-8 -*-
"""
Small statistical utilities for medians and confidence intervals.
"""
from __future__ import annotations
import numpy as np
from typing import Tuple

def median_iqr(x) -> Tuple[float, float, float]:
    x = np.asarray(x)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return (np.nan, np.nan, np.nan)
    return float(np.median(x)), float(np.percentile(x, 25)), float(np.percentile(x, 75))

def percentile_ci(x, alpha: float=0.05) -> Tuple[float, float]:
    x = np.asarray(x)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return (np.nan, np.nan)
    lo = np.percentile(x, 100*(alpha/2))
    hi = np.percentile(x, 100*(1 - alpha/2))
    return float(lo), float(hi)

def bootstrap_ci(x, n_boot: int=2000, alpha: float=0.05, seed: int=123) -> Tuple[float, float]:
    x = np.asarray(x)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    boots = []
    n = len(x)
    for _ in range(n_boot):
        samp = x[rng.integers(0, n, n)]
        boots.append(np.median(samp))
    lo = np.percentile(boots, 100*(alpha/2))
    hi = np.percentile(boots, 100*(1 - alpha/2))
    return float(lo), float(hi)
