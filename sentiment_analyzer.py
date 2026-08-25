#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金面分析模块
分析市场情绪和资金流向：
- CFTC持仓（投机资金动向）
- GLD ETF持仓（机构配置）
- 金银比（市场情绪指标）
- 央行购金（官方需求）
"""

from typing import Dict, List
import logging
from central_bank_gold import get_latest_central_bank_data, get_central_bank_trend, calculate_central_bank_score

logger = logging.getLogger(__name__)


def analyze_cftc_positions(cftc_data: Dict) -> Dict:
    """
    分析CFTC持仓数据（修正版）
    
    评分逻辑：
    - 净多头占比 > 20%: 强烈看多 (+2.0)
    - 净多头占比 10-20%: 看多 (+1.0)
    - 净多头占比 0-10%: 中性偏多 (+0.5)
    - 净多头占比 -10-0%: 中性偏空 (-0.5)
    - 净多头占比 -20--10%: 看空 (-1.0)
    - 净多头占比 < -20%: 强烈看空 (-2.0)
    
    极端值警告：
    - 净多占比 > 40%: 过度拥挤，反转风险高
    - 净多占比 < -30%: 过度看空，反弹风险高
    """
    score = 0.0
    reasons = []
    
    if not cftc_data:
        return {
            'score': 0.0,
            'reasons': ['CFTC数据不可用'],
            'outlook': 'neutral'
        }
    
    # 使用修正后的字段名
    net_position = cftc_data.get('net_position', 0)
    net_position_pct = cftc_data.get('net_position_pct', 0)
    long_short_ratio = cftc_data.get('long_short_ratio', 1.0)
    noncommercial_long = cftc_data.get('noncommercial_long', 0)
    noncommercial_short = cftc_data.get('noncommercial_short', 0)
    
    # 基于净多头占比评分（而非绝对值）
    if net_position_pct > 40:
        score = 1.0  # 过度拥挤，反转风险
        reasons.append(f"净多占比{net_position_pct:.1f}%，过度拥挤，反转风险高")
    elif net_position_pct > 20:
        score = 2.0
        reasons.append(f"净多占比{net_position_pct:.1f}%，投机资金强烈看多")
    elif net_position_pct > 10:
        score = 1.0
        reasons.append(f"净多占比{net_position_pct:.1f}%，投机资金看多")
    elif net_position_pct > 0:
        score = 0.5
        reasons.append(f"净多占比{net_position_pct:.1f}%，投机资金偏多")
    elif net_position_pct > -10:
        score = -0.5
        reasons.append(f"净多占比{net_position_pct:.1f}%，投机资金偏空")
    elif net_position_pct > -20:
        score = -1.0
        reasons.append(f"净多占比{net_position_pct:.1f}%，投机资金看空")
    elif net_position_pct > -30:
        score = -2.0
        reasons.append(f"净多占比{net_position_pct:.1f}%，投机资金强烈看空")
    else:
        score = -1.0  # 过度看空，反弹风险
        reasons.append(f"净多占比{net_position_pct:.1f}%，过度看空，反弹风险高")
    
    # 多空比辅助判断
    if long_short_ratio > 2.0:
        reasons.append(f"多空比{long_short_ratio:.2f}，多头占绝对优势")
    elif long_short_ratio > 1.5:
        reasons.append(f"多空比{long_short_ratio:.2f}，多头占优")
    elif long_short_ratio < 0.5:
        reasons.append(f"多空比{long_short_ratio:.2f}，空头占绝对优势")
    elif long_short_ratio < 0.7:
        reasons.append(f"多空比{long_short_ratio:.2f}，空头占优")
    
    # 总体判断
    if score >= 1.5:
        outlook = 'strongly_bullish'
    elif score >= 0.8:
        outlook = 'bullish'
    elif score >= 0.3:
        outlook = 'slightly_bullish'
    elif score > -0.3:
        outlook = 'neutral'
    elif score > -0.8:
        outlook = 'slightly_bearish'
    else:
        outlook = 'bearish'
    
    return {
        'score': round(score, 2),
        'reasons': reasons,
        'outlook': outlook,
        'net_position': net_position,
        'net_position_pct': net_position_pct,
        'long_short_ratio': long_short_ratio,
        'noncommercial_long': noncommercial_long,
        'noncommercial_short': noncommercial_short
    }


def analyze_gld_etf(gld_data: Dict) -> Dict:
    """
    分析GLD ETF持仓
    AUM增加 = 机构配置增加
    """
    score = 0.0
    reasons = []
    
    if not gld_data:
        return {'score': 0, 'outlook': 'neutral', 'reasons': ['GLD ETF数据不可用']}
    
    aum_billion = gld_data.get('aum_billion', 0)
    
    # AUM水平判断（简化版，实际应该对比历史数据）
    if aum_billion > 150:
        score += 2.0
        reasons.append(f"GLD AUM极高(${aum_billion:.1f}B)，机构强烈配置")
    elif aum_billion > 120:
        score += 1.5
        reasons.append(f"GLD AUM较高(${aum_billion:.1f}B)，机构配置增加")
    elif aum_billion > 100:
        score += 0.5
        reasons.append(f"GLD AUM中性(${aum_billion:.1f}B)")
    elif aum_billion > 80:
        score += 0.0
        reasons.append(f"GLD AUM较低(${aum_billion:.1f}B)")
    else:
        score -= 1.0
        reasons.append(f"GLD AUM低(${aum_billion:.1f}B)，机构配置减少")
    
    outlook = 'bullish' if score > 0.5 else ('bearish' if score < -0.5 else 'neutral')
    
    return {
        'score': round(score, 2),
        'outlook': outlook,
        'reasons': reasons,
        'aum_billion': aum_billion,
        'nav': gld_data.get('nav', 0),
        'date': gld_data.get('aum_date', ''),
    }


def analyze_gold_silver_ratio(ratio: float) -> Dict:
    """
    分析金银比
    高金银比 = 避险情绪高（经济担忧）
    低金银比 = 风险偏好高（经济乐观）
    """
    score = 0.0
    reasons = []
    
    if ratio > 90:
        score += 1.5
        reasons.append(f"金银比极高({ratio:.1f})，避险情绪强烈")
    elif ratio > 80:
        score += 1.0
        reasons.append(f"金银比偏高({ratio:.1f})，避险情绪较高")
    elif ratio > 70:
        score += 0.5
        reasons.append(f"金银比中性偏高({ratio:.1f})")
    elif ratio > 60:
        score += 0.0
        reasons.append(f"金银比中性({ratio:.1f})")
    else:
        score -= 0.5
        reasons.append(f"金银比偏低({ratio:.1f})，风险偏好较高")
    
    outlook = 'bullish' if score > 0.5 else ('bearish' if score < -0.5 else 'neutral')
    
    return {
        'score': round(score, 2),
        'outlook': outlook,
        'reasons': reasons,
        'ratio': round(ratio, 2),
    }


def sentiment_analysis(sentiment_data: Dict, realtime: Dict) -> Dict:
    """
    综合资金面/情绪面分析
    """
    logger.info("开始资金面分析...")
    results = {}
    total_score = 0.0
    weight_sum = 0
    
    # 1. CFTC持仓分析 (权重: 3)
    if 'cftc' in sentiment_data:
        result = analyze_cftc_positions(sentiment_data['cftc'])
        results['cftc'] = result
        total_score += result['score'] * 3
        weight_sum += 3
        logger.info(f"CFTC分析完成: 净多头={sentiment_data['cftc'].get('net_position', 'N/A')}, 得分={result['score']:.2f}")
    
    # 2. GLD ETF分析 (权重: 2)
    if 'gld_etf' in sentiment_data:
        result = analyze_gld_etf(sentiment_data['gld_etf'])
        results['gld_etf'] = result
        total_score += result['score'] * 2
        weight_sum += 2
        logger.info(f"GLD ETF分析完成: AUM=${sentiment_data['gld_etf'].get('aum_billion', 'N/A')}B, 得分={result['score']:.2f}")
    
    # 3. 金银比分析 (权重: 1)
    if 'gold_silver_ratio' in realtime:
        ratio = realtime['gold_silver_ratio']
        result = analyze_gold_silver_ratio(ratio)
        results['gold_silver_ratio'] = result
        total_score += result['score'] * 1
        weight_sum += 1
        logger.info(f"金银比分析完成: 比值={ratio:.2f}, 得分={result['score']:.2f}")
    
    # 4. 央行购金分析 (权重: 2)
    try:
        cb_data = get_latest_central_bank_data()
        cb_trend = get_central_bank_trend(4)
        cb_result = calculate_central_bank_score(cb_data, cb_trend)
        results['central_bank'] = cb_result
        total_score += cb_result['score'] * 2
        weight_sum += 2
        logger.info(f"央行购金分析完成: 购金量={cb_data.get('total_purchases', 'N/A')}吨, 得分={cb_result['score']:.2f}")
    except Exception as e:
        logger.error(f"央行购金分析失败: {e}")
    
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
    
    logger.info(f"资金面综合: 得分={combined_score:.2f}, 判断={overall}")
    
    return {
        'overall': overall,
        'combined_score': round(combined_score, 2),
        'details': results,
    }


def format_sentiment_report(sentiment: Dict) -> str:
    """生成资金面/情绪面分析报告"""
    lines = []
    lines.append("\n【资金面/情绪面分析】")
    lines.append(f"  总体判断: {sentiment.get('overall', '无数据')}")
    lines.append(f"  综合得分: {sentiment.get('combined_score', 0):.2f}")
    
    details = sentiment.get('details', {})
    
    if 'cftc' in details:
        c = details['cftc']
        lines.append(f"\n  CFTC持仓:")
        lines.append(f"    净多头: {c.get('net_position', 'N/A'):,}")
        lines.append(f"    评分: {c.get('score', 0):.2f} ({c.get('outlook', '')})")
        for reason in c.get('reasons', [])[:2]:
            lines.append(f"    - {reason}")
    
    if 'gld_etf' in details:
        g = details['gld_etf']
        lines.append(f"\n  GLD ETF:")
        lines.append(f"    AUM: ${g.get('aum_billion', 'N/A'):.2f}B")
        lines.append(f"    评分: {g.get('score', 0):.2f} ({g.get('outlook', '')})")
        for reason in g.get('reasons', [])[:2]:
            lines.append(f"    - {reason}")
    
    if 'gold_silver_ratio' in details:
        r = details['gold_silver_ratio']
        lines.append(f"\n  金银比: {r.get('ratio', 'N/A')}")
        lines.append(f"    评分: {r.get('score', 0):.2f} ({r.get('outlook', '')})")
        for reason in r.get('reasons', [])[:2]:
            lines.append(f"    - {reason}")
    
    if 'central_bank' in details:
        cb = details['central_bank']
        lines.append(f"\n  央行购金:")
        lines.append(f"    最新季度: {cb.get('quarter', 'N/A')}")
        lines.append(f"    购金量: {cb.get('total_purchases', 'N/A')}吨")
        lines.append(f"    评分: {cb.get('score', 0):.2f} ({cb.get('outlook', '')})")
        for reason in cb.get('reasons', [])[:3]:
            lines.append(f"    - {reason}")
        top_buyers = cb.get('top_buyers', [])
        if top_buyers:
            buyers_str = ', '.join([f"{b['country']}({b['purchases']}吨)" for b in top_buyers[:3]])
            lines.append(f"    主要买家: {buyers_str}")
    
    return '\n'.join(lines)
