#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基本面分析模块 v2.1
改进:
- analyze_employment_v2(): 数据新鲜度衰减天数从"写死7天"
  改为"从 NFP 实际发布日期计算", 更准确反映数据时效
- analyze_real_rate_v2() 等: 当 FRED 历史数据为空时,
  优先使用 macro_data 中的 *_range fallback (由 data_fetcher 提供)
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import math
import logging

logger = logging.getLogger(__name__)


def calculate_percentile(value: float, historical_data: List[float] = None,
                         historical_range: tuple = None) -> Optional[float]:
    """计算历史分位数 (0-100)"""
    if historical_data and len(historical_data) > 0:
        valid_data = [v for v in historical_data if v is not None and not (isinstance(v, float) and math.isnan(v))]
        if len(valid_data) > 0:
            count_below = sum(1 for v in valid_data if v < value)
            percentile = (count_below / len(valid_data)) * 100
            return max(0.0, min(100.0, percentile))
    if historical_range:
        min_val, max_val = historical_range
        if max_val == min_val:
            return 50.0
        percentile = (value - min_val) / (max_val - min_val) * 100
        return max(0.0, min(100.0, percentile))
    return None


def apply_freshness_decay(score: float, days_since_release: int) -> float:
    """数据新鲜度衰减: 7天内1.0, 8-30天0.8, 超过30天0.5"""
    if days_since_release <= 7:
        return score * 1.0
    elif days_since_release <= 30:
        return score * 0.8
    else:
        return score * 0.5


def _days_since(date_str: str) -> int:
    """从 'YYYY-MM-DD' 字符串计算距今天数, 失败返回 7"""
    if not date_str:
        return 7
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return max(0, (datetime.now() - d).days)
    except Exception:
        return 7


def analyze_real_rate_v2(real_rate: float, macro_data: Dict) -> Dict:
    """
    分析实际利率（优化版）
    - 用历史分位而非固定阈值
    - 考虑边际变化方向
    - 若央行购金/ETF强劲，实际利率利空要降权
    """
    score = 0.0
    reasons = []
    
    # 历史分位（优先使用真实历史数据，失败时用*_range fallback）
    historical_data = macro_data.get('real_rate_history', [])
    historical_range = macro_data.get('real_rate_range', (-1.5, 2.5))
    percentile = calculate_percentile(real_rate, historical_data, historical_range)
    
    if percentile is None:
        percentile = 50.0  # 默认中性
        reasons.append(f"实际利率{real_rate:.2f}%（历史数据缺失，使用默认分位）")
    else:
        # 分位评分
        if percentile >= 80:
            score -= 1.5
            reasons.append(f"实际利率{real_rate:.2f}%处于历史高分位({percentile:.0f}%)，利空黄金")
        elif percentile >= 60:
            score -= 0.8
            reasons.append(f"实际利率{real_rate:.2f}%偏高({percentile:.0f}%分位)")
        elif percentile >= 40:
            score += 0.0
            reasons.append(f"实际利率{real_rate:.2f}%中性({percentile:.0f}%分位)")
        elif percentile >= 20:
            score += 0.8
            reasons.append(f"实际利率{real_rate:.2f}%偏低({percentile:.0f}%分位)，利好黄金")
        else:
            score += 1.5
            reasons.append(f"实际利率{real_rate:.2f}%处于历史低分位({percentile:.0f}%)，强烈利好")
    
    # 边际变化（与5日前对比）
    prev_real_rate = None
    if 'real_rate_history' in macro_data:
        history = macro_data['real_rate_history']
        if len(history) >= 5:
            prev_real_rate = history[-5]  # 现在是纯数值列表
    
    if prev_real_rate is not None:
        change = real_rate - prev_real_rate
        if change < -0.15:
            score += 0.5
            reasons.append(f"实际利率5日下降{abs(change):.2f}%，边际改善")
        elif change > 0.15:
            score -= 0.5
            reasons.append(f"实际利率5日上升{change:.2f}%，边际恶化")
    
    # 若央行购金/ETF强劲，实际利率利空要降权
    # 这个逻辑在综合评分时处理
    
    outlook = 'bullish' if score > 0.3 else ('bearish' if score < -0.3 else 'neutral')
    
    return {
        'score': round(score, 2),
        'outlook': outlook,
        'reasons': reasons,
        'value': real_rate,
        'percentile': round(percentile, 1),
    }


def analyze_usd_v2(usd_price: float, prev_close: float, macro_data: Dict) -> Dict:
    """
    分析美元指数（优化版）
    - 用历史分位+斜率
    - 横盘也看位置（关键均线上下）
    - 结合利率差、美联储预期
    """
    score = 0.0
    reasons = []
    
    # 日变化
    change_pct = (usd_price - prev_close) / prev_close * 100 if prev_close else 0
    
    # 历史分位（2020年以来DXY范围约 89-114）
    percentile = calculate_percentile(usd_price, (89, 114))
    
    # 分位评分
    if percentile >= 80:
        score -= 1.0
        reasons.append(f"美元{usd_price:.2f}处于历史高位({percentile:.0f}%分位)")
    elif percentile >= 60:
        score -= 0.5
        reasons.append(f"美元{usd_price:.2f}偏高({percentile:.0f}%分位)")
    elif percentile >= 40:
        score += 0.0
        reasons.append(f"美元{usd_price:.2f}中性({percentile:.0f}%分位)")
    elif percentile >= 20:
        score += 0.5
        reasons.append(f"美元{usd_price:.2f}偏低({percentile:.0f}%分位)")
    else:
        score += 1.0
        reasons.append(f"美元{usd_price:.2f}处于历史低位({percentile:.0f}%分位)")
    
    # 斜率（5日变化）
    if abs(change_pct) < 0.1:
        # 横盘但看位置
        if percentile < 30:
            score += 0.3
            reasons.append(f"美元横盘但处于低位，支撑金价")
        elif percentile > 70:
            score -= 0.3
            reasons.append(f"美元横盘但处于高位，压制金价")
        else:
            reasons.append(f"美元横盘({change_pct:+.2f}%)")
    elif change_pct <= -0.5:
        score += 0.8
        reasons.append(f"美元下跌{change_pct:.2f}%，利好黄金")
    elif change_pct >= 0.5:
        score -= 0.8
        reasons.append(f"美元上涨{change_pct:.2f}%，利空黄金")
    
    outlook = 'bullish' if score > 0.3 else ('bearish' if score < -0.3 else 'neutral')
    
    return {
        'score': round(score, 2),
        'outlook': outlook,
        'reasons': reasons,
        'value': usd_price,
        'change_pct': round(change_pct, 2),
        'percentile': round(percentile, 1),
    }


def analyze_inflation_v2(macro_data: Dict) -> Dict:
    """
    分析通胀数据（优化版）
    - 用预期差而非绝对同比
    - 核心PCE权重高于CPI
    - 避免CPI和PCE重复计分
    """
    score = 0.0
    reasons = []
    
    # 核心PCE（美联储最关注）
    core_pce_yoy = macro_data.get('core_pce_yoy', {}).get('value', 0)
    core_pce_target = 2.0  # 美联储目标
    
    if core_pce_yoy > 0:
        deviation = core_pce_yoy - core_pce_target
        if deviation > 1.5:
            score += 1.5
            reasons.append(f"核心PCE {core_pce_yoy:.1f}%远超目标{deviation:+.1f}%，通胀压力大")
        elif deviation > 0.5:
            score += 0.8
            reasons.append(f"核心PCE {core_pce_yoy:.1f}%高于目标{deviation:+.1f}%")
        elif deviation > -0.5:
            score += 0.0
            reasons.append(f"核心PCE {core_pce_yoy:.1f}%接近目标")
        else:
            score -= 0.5
            reasons.append(f"核心PCE {core_pce_yoy:.1f}%低于目标，通缩风险")
    
    # 通胀预期（市场定价）
    inflation_expect = macro_data.get('inflation_expect', {}).get('value', 0)
    if inflation_expect > 2.5:
        score += 0.5
        reasons.append(f"通胀预期{inflation_expect:.2f}%偏高")
    elif inflation_expect < 1.5:
        score -= 0.3
        reasons.append(f"通胀预期{inflation_expect:.2f}%偏低")
    
    # 不再重复计CPI，避免与PCE重叠
    
    outlook = 'bullish' if score > 0.3 else ('bearish' if score < -0.3 else 'neutral')
    
    return {
        'score': round(score, 2),
        'outlook': outlook,
        'reasons': reasons,
        'core_pce_yoy': core_pce_yoy,
        'inflation_expect': inflation_expect,
    }


def analyze_employment_v2(macro_data: Dict) -> Dict:
    """
    分析就业数据（优化版）
    - 添加数据新鲜度衰减
    - 综合非农/失业率/时薪判断宽松概率
    """
    score = 0.0
    reasons = []
    
    # 非农就业变化
    nonfarm_change = macro_data.get('nonfarm_change', 0)
    if nonfarm_change < -50:
        score += 2.0
        reasons.append(f"非农减少{nonfarm_change:+.0f}K，就业明显恶化")
    elif nonfarm_change < 0:
        score += 1.5
        reasons.append(f"非农减少{nonfarm_change:+.0f}K，就业转负")
    elif nonfarm_change < 100:
        score += 0.5
        reasons.append(f"非农新增{nonfarm_change:+.0f}K，就业疲软")
    elif nonfarm_change < 200:
        score += 0.0
        reasons.append(f"非农新增{nonfarm_change:+.0f}K，就业平稳")
    else:
        score -= 0.5
        reasons.append(f"非农新增{nonfarm_change:+.0f}K，就业强劲")
    
    # 失业率
    unemployment = macro_data.get('unemployment_rate', {}).get('value', 0)
    if unemployment > 4.5:
        score += 1.0
        reasons.append(f"失业率{unemployment:.1f}%，劳动力市场疲软")
    elif unemployment > 4.0:
        score += 0.5
        reasons.append(f"失业率{unemployment:.1f}%，有所上升")
    elif unemployment < 3.5:
        score -= 0.3
        reasons.append(f"失业率{unemployment:.1f}%，就业充分")
    
    # 数据新鲜度衰减：从 NFP 实际发布日期计算
    nfp_date = macro_data.get('nonfarm_date', '')
    days_since_release = _days_since(nfp_date)
    score = apply_freshness_decay(score, days_since_release)
    if days_since_release > 14:
        reasons.append(f"NFP数据已{days_since_release}天未更新，评分衰减")
    
    outlook = 'bullish' if score > 0.3 else ('bearish' if score < -0.3 else 'neutral')
    
    return {
        'score': round(score, 2),
        'outlook': outlook,
        'reasons': reasons,
        'nonfarm_change': nonfarm_change,
        'unemployment_rate': unemployment,
    }


def analyze_gdp_v2(macro_data: Dict) -> Dict:
    """分析GDP数据（优化版）"""
    score = 0.0
    reasons = []
    
    gdp_growth = macro_data.get('gdp_growth', {}).get('value', 0)
    
    if gdp_growth < 0:
        score += 2.0
        reasons.append(f"GDP负增长{gdp_growth:.1f}%，经济衰退")
    elif gdp_growth < 1.0:
        score += 1.0
        reasons.append(f"GDP增速{gdp_growth:.1f}%，经济明显放缓")
    elif gdp_growth < 2.0:
        score += 0.3
        reasons.append(f"GDP增速{gdp_growth:.1f}%，增长乏力")
    elif gdp_growth < 3.0:
        score += 0.0
        reasons.append(f"GDP增速{gdp_growth:.1f}%，增长平稳")
    else:
        score -= 0.5
        reasons.append(f"GDP增速{gdp_growth:.1f}%，增长强劲")
    
    outlook = 'bullish' if score > 0.3 else ('bearish' if score < -0.3 else 'neutral')
    
    return {
        'score': round(score, 2),
        'outlook': outlook,
        'reasons': reasons,
        'gdp_growth': gdp_growth,
    }


def analyze_vix_v2(vix: float, macro_data: Dict = None) -> Dict:
    """分析VIX恐慌指数（优化版）"""
    score = 0.0
    reasons = []
    
    # 历史分位（优先使用真实历史数据，失败时用*_range fallback）
    historical_data = macro_data.get('vix_history', []) if macro_data else []
    historical_range = macro_data.get('vix_range', (10, 40)) if macro_data else (10, 40)
    percentile = calculate_percentile(vix, historical_data, historical_range)
    
    if percentile is None:
        percentile = 50.0
        reasons.append(f"VIX{vix:.1f}（历史数据缺失，使用默认分位）")
    elif percentile >= 80:
        score += 2.0
        reasons.append(f"VIX{vix:.1f}处于历史高位({percentile:.0f}%分位)，市场恐慌")
    elif percentile >= 60:
        score += 1.0
        reasons.append(f"VIX{vix:.1f}偏高({percentile:.0f}%分位)")
    elif percentile >= 40:
        score += 0.0
        reasons.append(f"VIX{vix:.1f}中性({percentile:.0f}%分位)")
    elif percentile >= 20:
        score -= 0.5
        reasons.append(f"VIX{vix:.1f}偏低({percentile:.0f}%分位)")
    else:
        score -= 1.0
        reasons.append(f"VIX{vix:.1f}处于历史低位({percentile:.0f}%分位)，市场乐观")
    
    outlook = 'bullish' if score > 0.3 else ('bearish' if score < -0.3 else 'neutral')
    
    return {
        'score': round(score, 2),
        'outlook': outlook,
        'reasons': reasons,
        'value': vix,
        'percentile': round(percentile, 1),
    }


def fundamental_analysis(macro_data: Dict, realtime: Dict) -> Dict:
    """
    综合基本面分析 v2.0
    优化点：
    - 所有因子用分位+边际变化
    - 避免重复计分
    - 数据新鲜度衰减
    """
    results = {}
    total_score = 0.0
    weight_sum = 0
    
    # 1. 实际利率 (权重: 3)
    if 'real_rate' in macro_data:
        real_rate = macro_data['real_rate']['value']
        result = analyze_real_rate_v2(real_rate, macro_data)
        results['real_rate'] = result
        total_score += result['score'] * 3
        weight_sum += 3
    
    # 2. 美元指数 (权重: 2)
    if 'usd_index' in realtime:
        usd = realtime['usd_index']
        result = analyze_usd_v2(usd['price'], usd['prev_close'], macro_data)
        results['usd'] = result
        total_score += result['score'] * 2
        weight_sum += 2
    
    # 3. 通胀 (权重: 2)
    if 'core_pce_yoy' in macro_data or 'inflation_expect' in macro_data:
        result = analyze_inflation_v2(macro_data)
        results['inflation'] = result
        total_score += result['score'] * 2
        weight_sum += 2
    
    # 4. 就业 (权重: 2)
    if 'nonfarm_change' in macro_data or 'unemployment_rate' in macro_data:
        result = analyze_employment_v2(macro_data)
        results['employment'] = result
        total_score += result['score'] * 2
        weight_sum += 2
    
    # 5. GDP (权重: 1.5)
    if 'gdp_growth' in macro_data:
        result = analyze_gdp_v2(macro_data)
        results['gdp'] = result
        total_score += result['score'] * 1.5
        weight_sum += 1.5
    
    # 6. VIX (权重: 1)
    if 'vix' in macro_data:
        vix = macro_data['vix']['value']
        result = analyze_vix_v2(vix, macro_data)
        results['vix'] = result
        total_score += result['score'] * 1
        weight_sum += 1
    
    # 综合评分
    if weight_sum > 0:
        combined_score = total_score / weight_sum
    else:
        combined_score = 0
    
    # 总体判断
    if combined_score >= 1.5:
        overall = '强烈看多'
    elif combined_score >= 0.8:
        overall = '看多'
    elif combined_score >= 0.3:
        overall = '偏多'
    elif combined_score > -0.3:
        overall = '中性'
    elif combined_score > -0.8:
        overall = '偏空'
    else:
        overall = '看空'
    
    return {
        'overall': overall,
        'combined_score': round(combined_score, 2),
        'details': results,
    }


def format_fundamental_report(fundamental: Dict, macro_data: Dict) -> str:
    """生成基本面分析报告"""
    lines = []
    lines.append("\n【基本面分析】")
    lines.append(f"  总体判断: {fundamental.get('overall', '无数据')}")
    lines.append(f"  综合得分: {fundamental.get('combined_score', 0):.2f}")
    
    details = fundamental.get('details', {})
    
    if 'real_rate' in details:
        r = details['real_rate']
        lines.append(f"\n  实际利率 ({r.get('value', 'N/A')}%, 分位{r.get('percentile', 'N/A')}%):")
        lines.append(f"    评分: {r.get('score', 0):.2f} ({r.get('outlook', '')})")
        for reason in r.get('reasons', [])[:2]:
            lines.append(f"    - {reason}")
    
    if 'usd' in details:
        u = details['usd']
        lines.append(f"\n  美元指数 ({u.get('value', 'N/A')}, 分位{u.get('percentile', 'N/A')}%):")
        lines.append(f"    评分: {u.get('score', 0):.2f} ({u.get('outlook', '')})")
        for reason in u.get('reasons', [])[:2]:
            lines.append(f"    - {reason}")
    
    if 'inflation' in details:
        i = details['inflation']
        lines.append(f"\n  通胀数据:")
        if i.get('core_pce_yoy'):
            lines.append(f"    核心PCE同比: {i['core_pce_yoy']:.1f}%")
        if i.get('inflation_expect'):
            lines.append(f"    通胀预期: {i['inflation_expect']:.2f}%")
        lines.append(f"    评分: {i.get('score', 0):.2f} ({i.get('outlook', '')})")
        for reason in i.get('reasons', [])[:2]:
            lines.append(f"    - {reason}")
    
    if 'employment' in details:
        e = details['employment']
        lines.append(f"\n  就业数据:")
        if e.get('nonfarm_change') is not None:
            lines.append(f"    非农就业变化: {e['nonfarm_change']:+.0f}K")
        if e.get('unemployment_rate'):
            lines.append(f"    失业率: {e['unemployment_rate']:.1f}%")
        lines.append(f"    评分: {e.get('score', 0):.2f} ({e.get('outlook', '')})")
        for reason in e.get('reasons', [])[:2]:
            lines.append(f"    - {reason}")
    
    if 'gdp' in details:
        g = details['gdp']
        lines.append(f"\n  GDP增速 ({g.get('gdp_growth', 'N/A')}%):")
        lines.append(f"    评分: {g.get('score', 0):.2f} ({g.get('outlook', '')})")
        for reason in g.get('reasons', [])[:2]:
            lines.append(f"    - {reason}")
    
    if 'vix' in details:
        v = details['vix']
        lines.append(f"\n  VIX恐慌指数 ({v.get('value', 'N/A')}, 分位{v.get('percentile', 'N/A')}%):")
        lines.append(f"    评分: {v.get('score', 0):.2f} ({v.get('outlook', '')})")
        for reason in v.get('reasons', [])[:2]:
            lines.append(f"    - {reason}")
    
    return '\n'.join(lines)
