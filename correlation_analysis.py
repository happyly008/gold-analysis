#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史相关性分析模块 v2.0
优化点：
- 用滚动窗口（60日）计算动态相关性，而非固定阈值
- 添加样本量检查，数据不足时降级
- 输出分位数而非二元判断
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def calculate_rolling_correlation(x: List[float], y: List[float], window: int = 60) -> Dict:
    """
    计算滚动窗口相关系数
    返回最新窗口的相关系数 + 历史分位
    """
    if len(x) != len(y) or len(x) < window:
        return {'error': f'数据不足(需要{window}条，实际{min(len(x), len(y))}条)'}
    
    correlations = []
    for i in range(len(x) - window + 1):
        x_w = x[i:i + window]
        y_w = y[i:i + window]
        n = len(x_w)
        sum_x = sum(x_w)
        sum_y = sum(y_w)
        sum_xy = sum(a * b for a, b in zip(x_w, y_w))
        sum_x2 = sum(a ** 2 for a in x_w)
        sum_y2 = sum(b ** 2 for b in y_w)
        denom = ((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2)) ** 0.5
        if denom == 0:
            correlations.append(0)
        else:
            correlations.append((n * sum_xy - sum_x * sum_y) / denom)
    
    if not correlations:
        return {'error': '无法计算相关系数'}
    
    current_corr = correlations[-1]
    sorted_corrs = sorted(correlations)
    rank = sum(1 for c in sorted_corrs if c <= current_corr)
    percentile = rank / len(sorted_corrs) * 100
    
    return {
        'current': round(current_corr, 3),
        'percentile': round(percentile, 1),
        'average': round(sum(correlations) / len(correlations), 3),
        'max': round(max(correlations), 3),
        'min': round(min(correlations), 3),
        'sample_size': len(correlations),
        'window': window,
    }


def validate_indicator_with_rolling(indicator_values: List[float], 
                                     future_returns: List[float],
                                     indicator_name: str,
                                     window: int = 60) -> Dict:
    """用滚动窗口验证指标有效性"""
    corr_result = calculate_rolling_correlation(indicator_values, future_returns, window)
    
    if 'error' in corr_result:
        return {'indicator': indicator_name, 'valid': False, 'reason': corr_result['error']}
    
    current_corr = corr_result['current']
    percentile = corr_result['percentile']
    
    if percentile >= 70:
        validity = 'strong_valid'
        reason = f'相关性{current_corr:+.3f}处于历史{percentile:.0f}%分位，强有效'
    elif percentile >= 55:
        validity = 'valid'
        reason = f'相关性{current_corr:+.3f}处于历史{percentile:.0f}%分位，有效'
    elif percentile <= 30:
        validity = 'inverse_valid'
        reason = f'相关性{current_corr:+.3f}处于历史{percentile:.0f}%分位，反向有效'
    elif percentile <= 45:
        validity = 'weak_inverse'
        reason = f'相关性{current_corr:+.3f}处于历史{percentile:.0f}%分位，弱反向'
    else:
        validity = 'unstable'
        reason = f'相关性{current_corr:+.3f}处于历史{percentile:.0f}%分位，不稳定'
    
    return {
        'indicator': indicator_name,
        'valid': True,
        'validity': validity,
        'reason': reason,
        'correlation': corr_result,
    }


def correlation_analysis(klines: Dict) -> Dict:
    """综合分析各技术指标与未来收益的相关性（滚动窗口60日）"""
    results = {}
    
    daily = klines.get('daily', [])
    if len(daily) < 70:
        return {'error': f'日线数据不足(需要70条，实际{len(daily)}条)'}
    
    closes = [c['close'] for c in daily]
    
    # 未来5日收益率
    future_returns = []
    for i in range(len(closes) - 5):
        ret = (closes[i + 5] - closes[i]) / closes[i] * 100
        future_returns.append(ret)
    
    aligned_length = min(len(future_returns), len(closes) - 5)
    future_returns = future_returns[:aligned_length]
    closes_aligned = closes[:aligned_length]
    
    # 1. RSI
    rsi_values = []
    for i in range(aligned_length):
        if i < 14:
            rsi_values.append(50)
            continue
        gains, losses = [], []
        for j in range(i - 13, i + 1):
            change = closes_aligned[j] - closes_aligned[j - 1]
            if change > 0:
                gains.append(change); losses.append(0)
            else:
                gains.append(0); losses.append(abs(change))
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        if avg_loss == 0:
            rsi_values.append(100)
        else:
            rsi_values.append(100 - 100 / (1 + avg_gain / avg_loss))
    
    results['rsi'] = validate_indicator_with_rolling(rsi_values, future_returns, 'RSI(14)', 60)
    
    # 2. MACD柱
    macd_hist = []
    ema12 = ema26 = closes_aligned[0]
    dea = 0
    for i in range(len(closes_aligned)):
        ema12 = ema12 * 11/13 + closes_aligned[i] * 2/13
        ema26 = ema26 * 25/27 + closes_aligned[i] * 2/27
        dif = ema12 - ema26
        dea = dea * 8/10 + dif * 2/10 if i > 0 else dif
        macd_hist.append((dif - dea) * 2)
    
    results['macd'] = validate_indicator_with_rolling(macd_hist, future_returns, 'MACD柱', 60)
    
    # 3. 5日动量
    momentum = []
    for i in range(len(closes_aligned)):
        if i < 5:
            momentum.append(0)
        else:
            momentum.append((closes_aligned[i] - closes_aligned[i-5]) / closes_aligned[i-5] * 100)
    
    results['momentum'] = validate_indicator_with_rolling(momentum, future_returns, '5日动量', 60)
    
    # 4. 布林带宽 → 未来波动
    boll_width = []
    for i in range(len(closes_aligned)):
        if i < 20:
            boll_width.append(0); continue
        w = closes_aligned[i-19:i+1]
        ma = sum(w) / 20
        std = (sum((c - ma)**2 for c in w) / 20) ** 0.5
        boll_width.append(std * 4 / ma * 100)
    
    future_vol = []
    for i in range(len(closes_aligned) - 5):
        fc = closes_aligned[i:i+6]
        rets = [(fc[j+1]-fc[j])/fc[j]*100 for j in range(len(fc)-1)]
        future_vol.append((sum(r**2 for r in rets)/len(rets))**0.5)
    
    al = min(len(boll_width), len(future_vol))
    results['boll_width'] = validate_indicator_with_rolling(
        boll_width[:al], future_vol[:al], '布林带宽→未来波动', 60)
    
    # 综合评估
    valid = [r for r in results.values() if r.get('valid')]
    strong = sum(1 for r in valid if r.get('validity') in ['strong_valid', 'valid'])
    inverse = sum(1 for r in valid if r.get('validity') in ['inverse_valid', 'weak_inverse'])
    
    if strong >= 3:
        overall = '指标体系高度有效，可信赖技术信号'
    elif strong >= 2:
        overall = '指标体系部分有效，结合使用'
    elif inverse >= 2:
        overall = '部分指标反向有效，可反向参考'
    else:
        overall = '指标体系不稳定，降低技术面权重'
    
    return {
        'overall': overall,
        'indicators': results,
        'valid_count': len(valid),
        'strong_valid_count': strong,
    }


def format_correlation_report(result: Dict) -> str:
    """格式化相关性分析报告"""
    lines = ["\n【历史相关性验证】"]
    lines.append(f"  总体评估: {result.get('overall', 'N/A')}")
    lines.append(f"  有效指标: {result.get('valid_count', 0)}个 / 强有效: {result.get('strong_valid_count', 0)}个")
    
    for name, data in result.get('indicators', {}).items():
        if not data.get('valid'):
            lines.append(f"\n  {data.get('indicator', name)}: {data.get('reason', '数据不足')}")
            continue
        corr = data.get('correlation', {})
        lines.append(f"\n  {data.get('indicator', name)}:")
        lines.append(f"    当前相关性: {corr.get('current', 0):+.3f} (分位{corr.get('percentile', 0):.0f}%)")
        lines.append(f"    历史均值: {corr.get('average', 0):+.3f} | 范围: [{corr.get('min', 0):+.3f}, {corr.get('max', 0):+.3f}]")
        lines.append(f"    判定: {data.get('reason', '')}")
    
    return '\n'.join(lines)
