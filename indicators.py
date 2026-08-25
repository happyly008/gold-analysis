#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术指标计算模块
MA / EMA / MACD / RSI / 布林带 / 支撑阻力位
"""

from typing import List, Dict, Tuple
import math


def calc_ma(closes: List[float], period: int) -> float:
    """简单移动平均线"""
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period


def calc_ema_series(values: List[float], period: int) -> List[float]:
    """指数移动平均线序列"""
    if not values:
        return []
    multiplier = 2.0 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        ema = (v - result[-1]) * multiplier + result[-1]
        result.append(ema)
    return result


def calc_macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
    """
    MACD 指标
    返回: dif, dea, macd_hist, 以及前一根的值(用于判断金叉死叉)
    """
    if len(closes) < slow + signal:
        return {'dif': 0, 'dea': 0, 'macd': 0, 'dif_prev': 0, 'dea_prev': 0}
    
    ema_fast = calc_ema_series(closes, fast)
    ema_slow = calc_ema_series(closes, slow)
    
    dif_series = [f - s for f, s in zip(ema_fast, ema_slow)]
    dea_series = calc_ema_series(dif_series, signal)
    
    dif = dif_series[-1]
    dea = dea_series[-1]
    macd = 2 * (dif - dea)
    
    dif_prev = dif_series[-2] if len(dif_series) >= 2 else dif
    dea_prev = dea_series[-2] if len(dea_series) >= 2 else dea
    
    return {
        'dif': dif,
        'dea': dea,
        'macd': macd,
        'dif_prev': dif_prev,
        'dea_prev': dea_prev,
    }


def calc_rsi(closes: List[float], period: int = 14) -> float:
    """Wilder RSI"""
    if len(closes) <= period:
        return 50.0
    
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_bollinger(closes: List[float], period: int = 20, num_std: float = 2.0) -> Dict:
    """布林带"""
    if len(closes) < period:
        return {'upper': 0, 'middle': 0, 'lower': 0, 'width': 0}
    
    recent = closes[-period:]
    middle = sum(recent) / period
    variance = sum((x - middle) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    
    return {
        'upper': middle + num_std * std,
        'middle': middle,
        'lower': middle - num_std * std,
        'width': (num_std * 2 * std) / middle * 100 if middle else 0,
    }


def analyze_dow_trend(candles: List[Dict]) -> Dict:
    """
    道氏三级趋势分析
    长期趋势(Primary): 6个月以上，使用120日均线
    中期趋势(Secondary): 3周到3个月，使用60日均线
    短期趋势(Minor): 3周以内，使用20日均线
    """
    if len(candles) < 120:
        return {'primary': 'unknown', 'secondary': 'unknown', 'minor': 'unknown'}
    
    closes = [c['close'] for c in candles]
    current = closes[-1]
    
    # 计算各周期均线
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)
    ma120 = calc_ma(closes, 120)
    
    # 分析趋势（基于价格与均线关系 + 均线斜率）
    def determine_trend(ma_short: float, ma_long: float, lookback: int = 20) -> str:
        """判断趋势方向"""
        if ma_short == 0 or ma_long == 0:
            return 'unknown'
        
        # 计算均线斜率
        ma_series = []
        for i in range(len(closes) - lookback, len(closes)):
            if i >= 0:
                ma_series.append(calc_ma(closes[:i+1], 20))
        
        if len(ma_series) < 2:
            return 'unknown'
        
        slope = (ma_series[-1] - ma_series[0]) / len(ma_series) if ma_series[0] != 0 else 0
        
        # 判断趋势
        if current > ma_short > ma_long and slope > 0:
            return 'uptrend'
        elif current < ma_short < ma_long and slope < 0:
            return 'downtrend'
        else:
            return 'sideways'
    
    # 长期趋势：价格 vs 120日均线 + 均线斜率（不需要双均线排列）
    def determine_primary_trend() -> str:
        """判断长期趋势：价格位置 + 120日均线斜率"""
        if ma120 == 0:
            return 'unknown'
        
        # 计算120日均线斜率（20日变化）
        if len(closes) > 140:
            ma120_20ago = calc_ma(closes[:-20], 120)
        else:
            ma120_20ago = ma120
        
        slope = ma120 - ma120_20ago
        
        # 判断趋势：价格在均线上方且均线上升 = 上涨趋势
        if current > ma120 and slope > 0:
            return 'uptrend'
        elif current < ma120 and slope < 0:
            return 'downtrend'
        else:
            return 'sideways'
    
    # 三级趋势
    primary_trend = determine_primary_trend()  # 长期：价格 vs 120日均线 + 斜率
    secondary_trend = determine_trend(ma60, ma120, 30)  # 中期：60日 vs 120日
    minor_trend = determine_trend(ma20, ma60, 10)  # 短期：20日 vs 60日
    
    return {
        'primary': primary_trend,
        'secondary': secondary_trend,
        'minor': minor_trend,
        'ma20': round(ma20, 2),
        'ma60': round(ma60, 2),
        'ma120': round(ma120, 2),
    }


def calc_atr(candles: List[Dict], period: int = 14) -> float:
    """平均真实波幅 ATR"""
    if len(candles) < period + 1:
        return 0.0
    
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]['high']
        l = candles[i]['low']
        pc = candles[i-1]['close']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    
    if len(trs) < period:
        return 0.0
    
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return atr


def calc_adx(candles: List[Dict], period: int = 14) -> Dict:
    """
    平均趋向指标 ADX (Average Directional Index)
    用于判断趋势强度：
    - ADX < 20: 无趋势/震荡
    - 20 <= ADX < 25: 弱趋势
    - 25 <= ADX < 50: 强趋势
    - ADX >= 50: 极强趋势
    
    返回: adx, +di, -di, trend_strength
    """
    if len(candles) < period * 2 + 1:
        return {'adx': 0, 'plus_di': 0, 'minus_di': 0, 'trend_strength': 'unknown'}
    
    # 计算 +DM, -DM, TR
    plus_dm = []
    minus_dm = []
    trs = []
    
    for i in range(1, len(candles)):
        h = candles[i]['high']
        l = candles[i]['low']
        ph = candles[i-1]['high']
        pl = candles[i-1]['low']
        pc = candles[i-1]['close']
        
        # True Range
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
        
        # +DM, -DM
        up_move = h - ph
        down_move = pl - l
        
        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0)
        
        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0)
    
    if len(trs) < period:
        return {'adx': 0, 'plus_di': 0, 'minus_di': 0, 'trend_strength': 'unknown'}
    
    # 平滑计算 (Wilder's smoothing)
    atr_val = sum(trs[:period]) / period
    plus_dm_smooth = sum(plus_dm[:period]) / period
    minus_dm_smooth = sum(minus_dm[:period]) / period
    
    plus_di_list = []
    minus_di_list = []
    dx_list = []
    
    # 计算前 period 个 +DI, -DI
    for i in range(period):
        if atr_val > 0:
            pdi = (plus_dm_smooth / atr_val) * 100
            mdi = (minus_dm_smooth / atr_val) * 100
        else:
            pdi = 0
            mdi = 0
        plus_di_list.append(pdi)
        minus_di_list.append(mdi)
        
        # DX = |+DI - -DI| / (+DI + -DI) * 100
        di_sum = pdi + mdi
        if di_sum > 0:
            dx = abs(pdi - mdi) / di_sum * 100
        else:
            dx = 0
        dx_list.append(dx)
        
        # 更新平滑值
        if i + period < len(trs):
            atr_val = (atr_val * (period - 1) + trs[i + period]) / period
            plus_dm_smooth = (plus_dm_smooth * (period - 1) + plus_dm[i + period]) / period
            minus_dm_smooth = (minus_dm_smooth * (period - 1) + minus_dm[i + period]) / period
    
    # 计算 ADX (DX 的 period 周期平均)
    if len(dx_list) < period:
        adx = sum(dx_list) / len(dx_list) if dx_list else 0
    else:
        adx = sum(dx_list[:period]) / period
        for i in range(period, len(dx_list)):
            adx = (adx * (period - 1) + dx_list[i]) / period
    
    # 当前 +DI, -DI
    plus_di = plus_di_list[-1] if plus_di_list else 0
    minus_di = minus_di_list[-1] if minus_di_list else 0
    
    # 趋势强度判断
    if adx < 20:
        trend_strength = 'no_trend'
    elif adx < 25:
        trend_strength = 'weak'
    elif adx < 50:
        trend_strength = 'strong'
    else:
        trend_strength = 'very_strong'
    
    return {
        'adx': round(adx, 2),
        'plus_di': round(plus_di, 2),
        'minus_di': round(minus_di, 2),
        'trend_strength': trend_strength,
    }


def calc_kdj(candles: List[Dict], n: int = 9, m1: int = 3, m2: int = 3) -> Dict:
    """
    KDJ 随机指标
    n: RSV周期
    m1: K的平滑因子
    m2: D的平滑因子
    返回: k, d, j, 以及前一根的值(用于判断金叉死叉)
    """
    if len(candles) < n:
        return {'k': 50, 'd': 50, 'j': 50, 'k_prev': 50, 'd_prev': 50}
    
    k_values = []
    d_values = []
    
    # 初始K、D值
    k = 50.0
    d = 50.0
    
    for i in range(n - 1, len(candles)):
        # 计算n周期内的最高价和最低价
        recent = candles[i - n + 1:i + 1]
        high_n = max(c['high'] for c in recent)
        low_n = min(c['low'] for c in recent)
        
        # 计算RSV
        if high_n == low_n:
            rsv = 50.0
        else:
            rsv = (candles[i]['close'] - low_n) / (high_n - low_n) * 100
        
        # 计算K、D
        k = (m1 - 1) / m1 * k + 1 / m1 * rsv
        d = (m2 - 1) / m2 * d + 1 / m2 * k
        
        k_values.append(k)
        d_values.append(d)
    
    if not k_values:
        return {'k': 50, 'd': 50, 'j': 50, 'k_prev': 50, 'd_prev': 50}
    
    k_curr = k_values[-1]
    d_curr = d_values[-1]
    j_curr = 3 * k_curr - 2 * d_curr
    
    k_prev = k_values[-2] if len(k_values) >= 2 else k_curr
    d_prev = d_values[-2] if len(d_values) >= 2 else d_curr
    
    return {
        'k': k_curr,
        'd': d_curr,
        'j': j_curr,
        'k_prev': k_prev,
        'd_prev': d_prev,
    }


def analyze_volume_price(candles: List[Dict], period: int = 20) -> Dict:
    """
    量价关系分析
    - 放量突破：价格上涨且成交量放大
    - 缩量回调：价格下跌但成交量萎缩（健康回调）
    - 放量下跌：价格下跌且成交量放大（危险信号）
    - 缩量上涨：价格上涨但成交量萎缩（上涨乏力）
    """
    if len(candles) < period + 1:
        return {
            'volume_trend': 'unknown',
            'price_volume_signal': 'neutral',
            'volume_ratio': 1.0,
            'description': '数据不足'
        }
    
    # 计算平均成交量
    recent_volumes = [c.get('volume', 0) for c in candles[-period:]]
    avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 1
    
    # 当前成交量
    current_volume = candles[-1].get('volume', 0)
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
    
    # 价格变化
    current_close = candles[-1]['close']
    prev_close = candles[-2]['close']
    price_change_pct = (current_close - prev_close) / prev_close * 100 if prev_close > 0 else 0
    
    # 量价信号判断
    volume_trend = 'normal'
    if volume_ratio > 1.5:
        volume_trend = 'high_volume'
    elif volume_ratio < 0.7:
        volume_trend = 'low_volume'
    
    price_volume_signal = 'neutral'
    description = ''
    
    if price_change_pct > 0.5 and volume_ratio > 1.3:
        price_volume_signal = 'bullish_breakout'
        description = f'放量上涨({price_change_pct:.2f}%)，成交量是均量的{volume_ratio:.1f}倍'
    elif price_change_pct > 0.5 and volume_ratio < 0.8:
        price_volume_signal = 'weak_uptrend'
        description = f'缩量上涨({price_change_pct:.2f}%)，上涨动能不足'
    elif price_change_pct < -0.5 and volume_ratio > 1.3:
        price_volume_signal = 'bearish_breakdown'
        description = f'放量下跌({price_change_pct:.2f}%)，成交量是均量的{volume_ratio:.1f}倍'
    elif price_change_pct < -0.5 and volume_ratio < 0.8:
        price_volume_signal = 'healthy_pullback'
        description = f'缩量回调({price_change_pct:.2f}%)，健康调整'
    elif abs(price_change_pct) < 0.5:
        price_volume_signal = 'consolidation'
        description = f'横盘整理({price_change_pct:.2f}%)'
    else:
        description = f'价格变化{price_change_pct:.2f}%，成交量{volume_ratio:.1f}倍均量'
    
    return {
        'volume_trend': volume_trend,
        'price_volume_signal': price_volume_signal,
        'volume_ratio': round(volume_ratio, 2),
        'price_change_pct': round(price_change_pct, 2),
        'description': description
    }


def calc_fibonacci_levels(high: float, low: float) -> Dict:
    """
    计算斐波那契回撤位
    用于找支撑和阻力
    """
    diff = high - low
    return {
        '0.0': round(high, 2),      # 高点
        '23.6': round(high - diff * 0.236, 2),
        '38.2': round(high - diff * 0.382, 2),
        '50.0': round(high - diff * 0.500, 2),
        '61.8': round(high - diff * 0.618, 2),
        '78.6': round(high - diff * 0.786, 2),
        '100.0': round(low, 2),     # 低点
    }


def find_fibonacci_support_resistance(candles: List[Dict], lookback: int = 100) -> Dict:
    """
    基于斐波那契回撤找支撑阻力
    """
    if len(candles) < lookback:
        lookback = len(candles)
    
    recent = candles[-lookback:]
    
    # 找近期高低点
    high = max(c['high'] for c in recent)
    low = min(c['low'] for c in recent)
    current = candles[-1]['close']
    
    fib_levels = calc_fibonacci_levels(high, low)
    
    # 分类支撑和阻力
    supports = []
    resistances = []
    
    for level, price in fib_levels.items():
        if price < current:
            supports.append({'level': level, 'price': price})
        elif price > current:
            resistances.append({'level': level, 'price': price})
    
    # 按距离排序
    supports.sort(key=lambda x: x['price'], reverse=True)
    resistances.sort(key=lambda x: x['price'])
    
    return {
        'supports': supports[:3],
        'resistances': resistances[:3],
        'high': round(high, 2),
        'low': round(low, 2),
        'fib_levels': fib_levels,
    }


def find_support_resistance(candles: List[Dict], lookback: int = 50) -> Dict:
    """
    支撑阻力位分析
    使用近期高低点 + 布林带 + 斐波那契
    """
    if len(candles) < 10:
        return {'supports': [], 'resistances': []}
    
    recent = candles[-lookback:] if len(candles) > lookback else candles
    closes = [c['close'] for c in recent]
    current = closes[-1]
    
    # 近期高低点
    highs = sorted([c['high'] for c in recent], reverse=True)
    lows = sorted([c['low'] for c in recent])
    
    # 布林带
    boll = calc_bollinger(closes)
    
    # 斐波那契
    fib = find_fibonacci_support_resistance(candles, lookback)
    
    # 支撑位: 近期低点 + 布林下轨 + 斐波那契支撑
    supports = []
    s1 = lows[1] if len(lows) > 1 else lows[0]
    s2 = boll['lower']
    s3 = fib['supports'][0]['price'] if fib['supports'] else 0
    
    for s in [s1, s2, s3]:
        if s < current and s not in supports:
            supports.append(round(s, 2))
    supports.sort(reverse=True)
    
    # 阻力位: 近期高点 + 布林上轨 + 斐波那契阻力
    resistances = []
    r1 = highs[1] if len(highs) > 1 else highs[0]
    r2 = boll['upper']
    r3 = fib['resistances'][0]['price'] if fib['resistances'] else 0
    
    for r in [r1, r2, r3]:
        if r > current and r not in resistances:
            resistances.append(round(r, 2))
    resistances.sort()
    
    return {
        'supports': supports[:3],
        'resistances': resistances[:3],
        'current': round(current, 2),
        'fibonacci': fib,
    }


def calc_all_indicators(candles: List[Dict]) -> Dict:
    """计算所有技术指标"""
    if len(candles) < 30:
        return {}
    
    closes = [c['close'] for c in candles]
    current = closes[-1]
    
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    ma30 = calc_ma(closes, 30)
    
    macd = calc_macd(closes)
    rsi6 = calc_rsi(closes, 6)
    rsi14 = calc_rsi(closes, 14)
    boll = calc_bollinger(closes)
    atr = calc_atr(candles)
    adx = calc_adx(candles)
    kdj = calc_kdj(candles)
    sr = find_support_resistance(candles)
    
    # MACD 金叉/死叉判断
    macd_cross = ''
    if macd['dif'] > macd['dea'] and macd['dif_prev'] <= macd['dea_prev']:
        macd_cross = 'golden_cross'  # 金叉
    elif macd['dif'] < macd['dea'] and macd['dif_prev'] >= macd['dea_prev']:
        macd_cross = 'death_cross'  # 死叉
    
    # KDJ 金叉/死叉判断
    kdj_cross = ''
    if kdj['k'] > kdj['d'] and kdj['k_prev'] <= kdj['d_prev']:
        kdj_cross = 'golden_cross'  # 金叉
    elif kdj['k'] < kdj['d'] and kdj['k_prev'] >= kdj['d_prev']:
        kdj_cross = 'death_cross'  # 死叉
    
    # 均线排列
    ma_alignment = 'neutral'
    if ma5 > ma10 > ma20 > ma30:
        ma_alignment = 'bullish_aligned'  # 多头排列
    elif ma5 < ma10 < ma20 < ma30:
        ma_alignment = 'bearish_aligned'  # 空头排列
    
    return {
        'current': current,
        'ma5': round(ma5, 2),
        'ma10': round(ma10, 2),
        'ma20': round(ma20, 2),
        'ma30': round(ma30, 2),
        'ma_alignment': ma_alignment,
        'macd': {
            'dif': round(macd['dif'], 4),
            'dea': round(macd['dea'], 4),
            'hist': round(macd['macd'], 4),
            'cross': macd_cross,
        },
        'kdj': {
            'k': round(kdj['k'], 2),
            'd': round(kdj['d'], 2),
            'j': round(kdj['j'], 2),
            'cross': kdj_cross,
        },
        'rsi6': round(rsi6, 2),
        'rsi14': round(rsi14, 2),
        'bollinger': {
            'upper': round(boll['upper'], 2),
            'middle': round(boll['middle'], 2),
            'lower': round(boll['lower'], 2),
            'width': round(boll['width'], 2),
        },
        'atr': round(atr, 2),
        'adx': adx,
        'support_resistance': sr,
        'volume_price': analyze_volume_price(candles),
        'dow_trend': analyze_dow_trend(candles),
    }
