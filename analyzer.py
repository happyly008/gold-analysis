#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合分析引擎 v3.1
改进:
- 地缘评分从"简单加法"改为"加权融合"(归一化后参与总权重),
  避免 geo_score 过大时主导综合得分
- 执行层信号增加"基本面边际变化触发"(实际利率大幅改善/恶化)

优化点：
1. 多周期分层（日内/波段/趋势）
2. 信号引擎分层（方向层+执行层）
3. 输出升级（触发价/仓位/止损三要素）
"""

from typing import Dict, List
from indicators import calc_all_indicators, calc_ma, analyze_volume_price
from fundamental_analyzer import fundamental_analysis, format_fundamental_report
from sentiment_analyzer import sentiment_analysis, format_sentiment_report
from geopolitical import GeopoliticalMonitor, format_geopolitical_report
import logging
import json
import os
import math

logger = logging.getLogger(__name__)

# 默认权重
DEFAULT_WEIGHTS = {
    'technical': 0.40,
    'fundamental': 0.35,
    'sentiment': 0.25,
    'geopolitical_bonus': 0.30
}

def load_weights() -> Dict:
    """加载权重配置"""
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'weights.json')
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('weights', DEFAULT_WEIGHTS)
    except Exception as e:
        logger.warning(f"加载权重配置失败，使用默认值: {e}")
    return DEFAULT_WEIGHTS


def analyze_single_timeframe(candles: List[Dict], label: str) -> Dict:
    """分析单个周期（技术面）"""
    if len(candles) < 30:
        return {'label': label, 'error': '数据不足'}
    
    indicators = calc_all_indicators(candles)
    current = indicators['current']
    
    # 评分系统
    score = 0.0
    reasons = []
    
    # 1. 均线排列 (±2分)
    if indicators['ma_alignment'] == 'bullish_aligned':
        score += 2.0
        reasons.append('均线多头排列')
    elif indicators['ma_alignment'] == 'bearish_aligned':
        score -= 2.0
        reasons.append('均线空头排列')
    
    # 2. 价格与均线关系 (±1.5分)
    if current > indicators['ma5'] > indicators['ma10'] > indicators['ma20']:
        score += 1.5
        reasons.append('价格在均线上方')
    elif current < indicators['ma5'] < indicators['ma10'] < indicators['ma20']:
        score -= 1.5
        reasons.append('价格在均线下方')
    
    # 3. MACD (±1.5分)
    macd = indicators['macd']
    if macd['cross'] == 'golden_cross':
        score += 1.5
        reasons.append('MACD金叉')
    elif macd['cross'] == 'death_cross':
        score -= 1.5
        reasons.append('MACD死叉')
    elif macd['dif'] > macd['dea'] and macd['hist'] > 0:
        score += 0.8
        reasons.append('MACD多头')
    elif macd['dif'] < macd['dea'] and macd['hist'] < 0:
        score -= 0.8
        reasons.append('MACD空头')
    
    # 4. RSI (±1分)
    rsi = indicators['rsi14']
    if rsi >= 70:
        score -= 0.5
        reasons.append(f'RSI超买({rsi:.1f})')
    elif rsi <= 30:
        score += 0.5
        reasons.append(f'RSI超卖({rsi:.1f})')
    elif rsi >= 55:
        score += 0.3
    elif rsi <= 45:
        score -= 0.3
    
    # 5. 布林带位置 (±0.5分)
    boll = indicators['bollinger']
    if current >= boll['upper']:
        score -= 0.3
        reasons.append('触及布林上轨')
    elif current <= boll['lower']:
        score += 0.3
        reasons.append('触及布林下轨')
    
    # 6. 斐波那契位置
    fib = indicators.get('support_resistance', {}).get('fibonacci', {})
    if fib:
        fib_supports = fib.get('supports', [])
        fib_resistances = fib.get('resistances', [])
        
        for fs in fib_supports[:2]:
            distance_pct = (current - fs['price']) / current * 100
            if 0 < distance_pct < 1.0:
                score += 0.3
                reasons.append(f'接近斐波那契支撑{fs["level"]}%')
                break
        
        for fr in fib_resistances[:2]:
            distance_pct = (fr['price'] - current) / current * 100
            if 0 < distance_pct < 1.0:
                score -= 0.2
                reasons.append(f'接近斐波那契阻力{fr["level"]}%')
                break
    
    # 7. KDJ指标 (±1分)
    kdj = indicators.get('kdj', {})
    if kdj:
        if kdj.get('cross') == 'golden_cross':
            score += 1.0
            reasons.append('KDJ金叉')
        elif kdj.get('cross') == 'death_cross':
            score -= 1.0
            reasons.append('KDJ死叉')
        else:
            k_val = kdj.get('k', 50)
            d_val = kdj.get('d', 50)
            j_val = kdj.get('j', 50)
            if k_val > 80 and d_val > 80:
                score -= 0.3
                reasons.append(f'KDJ超买(K:{k_val:.0f})')
            elif k_val < 20 and d_val < 20:
                score += 0.3
                reasons.append(f'KDJ超卖(K:{k_val:.0f})')
            elif k_val > d_val and j_val > k_val:
                score += 0.2
                reasons.append('KDJ多头排列')
            elif k_val < d_val and j_val < k_val:
                score -= 0.2
                reasons.append('KDJ空头排列')
    
    # 8. 量价关系 (±0.5分)
    volume_price = indicators.get('volume_price', {})
    if volume_price:
        vp_signal = volume_price.get('price_volume_signal', 'neutral')
        if vp_signal == 'bullish_breakout':
            score += 0.5
            reasons.append('放量突破')
        elif vp_signal == 'bearish_breakdown':
            score -= 0.5
            reasons.append('放量下跌')
        elif vp_signal == 'healthy_pullback':
            score += 0.2
            reasons.append('缩量回调(健康)')
        elif vp_signal == 'weak_uptrend':
            score -= 0.2
            reasons.append('缩量上涨(动能不足)')
    
    # 9. 道氏三级趋势 (±1.5分)
    dow = indicators.get('dow_trend', {})
    if dow:
        primary = dow.get('primary', 'unknown')
        secondary = dow.get('secondary', 'unknown')
        minor = dow.get('minor', 'unknown')
        
        if primary == 'uptrend':
            score += 1.0
            reasons.append('道氏长期趋势上涨')
        elif primary == 'downtrend':
            score -= 1.0
            reasons.append('道氏长期趋势下跌')
        
        if secondary == 'uptrend' and primary == 'uptrend':
            score += 0.3
            reasons.append('道氏中期趋势确认')
        elif secondary == 'downtrend' and primary == 'downtrend':
            score -= 0.3
            reasons.append('道氏中期趋势确认')
    
    # 10. ADX趋势强度过滤 (±0.5分 + 信号置信度调节)
    adx = indicators.get('adx', {})
    if adx:
        adx_val = adx.get('adx', 0)
        trend_strength = adx.get('trend_strength', 'unknown')
        plus_di = adx.get('plus_di', 0)
        minus_di = adx.get('minus_di', 0)
        
        if trend_strength == 'no_trend' or adx_val < 20:
            # 无趋势/震荡市：趋势信号打折，均值回归信号加分
            score *= 0.8
            reasons.append(f'ADX={adx_val:.0f}无趋势，信号衰减20%')
            # 震荡市中 RSI 超买超卖更有意义
            if rsi >= 65:
                score -= 0.3
                reasons.append('震荡市RSI偏高，回归预期')
            elif rsi <= 35:
                score += 0.3
                reasons.append('震荡市RSI偏低，反弹预期')
        elif trend_strength in ('strong', 'very_strong') and adx_val >= 25:
            # 强趋势市：趋势方向上的信号加分
            if plus_di > minus_di:
                score += 0.5
                reasons.append(f'ADX={adx_val:.0f}强趋势(+DI>{minus_di:.0f})，趋势可信')
            else:
                score -= 0.5
                reasons.append(f'ADX={adx_val:.0f}强趋势(-DI>{plus_di:.0f})，趋势可信')
    
    # 趋势判断
    if score >= 2.5:
        trend = '强势上涨'
    elif score >= 1.0:
        trend = '震荡偏多'
    elif score > -1.0:
        trend = '震荡整理'
    elif score > -2.5:
        trend = '震荡偏空'
    else:
        trend = '强势下跌'
    
    return {
        'label': label,
        'score': round(score, 2),
        'trend': trend,
        'indicators': indicators,
        'reasons': reasons,
        'raw_data': candles,  # 传递原始K线用于枢轴点计算
    }


def analyze_multi_timeframe_v2(klines: Dict) -> Dict:
    """
    多周期技术面分析 v2.0
    分层：日内(5/15min)、波段(1h/4h)、趋势(日线)
    """
    # 分层定义
    layers = {
        'intraday': {
            'name': '日内',
            'timeframes': [('5min', '5分钟'), ('15min', '15分钟')],
            'weight': 0.2
        },
        'swing': {
            'name': '波段',
            'timeframes': [('1hour', '1小时'), ('4hour', '4小时')],
            'weight': 0.4
        },
        'trend': {
            'name': '趋势',
            'timeframes': [('daily', '日线')],
            'weight': 0.4
        }
    }
    
    all_results = []
    layer_scores = {}
    
    # 分析每个周期
    for layer_key, layer_info in layers.items():
        layer_score = 0.0
        layer_weight_sum = 0
        layer_results = []
        
        for key, label in layer_info['timeframes']:
            if key not in klines:
                continue
            analysis = analyze_single_timeframe(klines[key], label)
            if 'error' in analysis:
                continue
            
            # 周期权重：同层内按时间长度
            tf_weight = {'5min': 0.3, '15min': 0.7, '1hour': 0.4, '4hour': 0.6, 'daily': 1.0}.get(key, 0.5)
            
            layer_results.append({
                'label': label,
                'score': analysis['score'],
                'trend': analysis['trend'],
                'weight': tf_weight,
                'reasons': analysis['reasons'],
                'indicators': analysis['indicators'],
                'layer': layer_info['name'],
                'raw_data': analysis.get('raw_data', [])  # 传递原始K线
            })
            
            layer_score += analysis['score'] * tf_weight
            layer_weight_sum += tf_weight
        
        if layer_weight_sum > 0:
            layer_scores[layer_key] = layer_score / layer_weight_sum
        else:
            layer_scores[layer_key] = 0
        
        all_results.extend(layer_results)
    
    # 计算各层方向
    layer_directions = {}
    for layer_key, score in layer_scores.items():
        if score >= 1.0:
            layer_directions[layer_key] = 'bullish'
        elif score <= -1.0:
            layer_directions[layer_key] = 'bearish'
        else:
            layer_directions[layer_key] = 'neutral'
    
    # 计算一致性
    bullish_count = sum(1 for d in layer_directions.values() if d == 'bullish')
    bearish_count = sum(1 for d in layer_directions.values() if d == 'bearish')
    total_layers = len(layer_directions)
    
    if bullish_count == total_layers:
        agreement = 100
        overall = '强烈看多'
    elif bearish_count == total_layers:
        agreement = 100
        overall = '强烈看空'
    elif bullish_count > bearish_count:
        agreement = bullish_count / total_layers * 100
        overall = '看多' if bullish_count >= 2 else '偏多'
    elif bearish_count > bullish_count:
        agreement = bearish_count / total_layers * 100
        overall = '看空' if bearish_count >= 2 else '偏空'
    else:
        agreement = 50
        overall = '中性震荡'
    
    # 一致性<60%时降级
    if agreement < 60:
        if '看多' in overall:
            overall = overall.replace('看多', '偏多').replace('强烈看多', '看多')
        elif '看空' in overall:
            overall = overall.replace('看空', '偏空').replace('强烈看空', '看空')
    
    # 综合得分（加权）
    # 波动率自适应权重：根据市场波动率动态调整各层权重
    # 高波动时趋势层权重增加（更看重长周期信号），低波动时日内层权重增加
    
    # 计算整体波动率（使用日线ATR/价格作为波动率指标）
    daily_volatility = 0
    for tf in all_results:
        if tf.get('label') == '日线':
            atr = tf.get('indicators', {}).get('atr', 0)
            current_price = tf.get('indicators', {}).get('current', 0)
            if current_price > 0:
                daily_volatility = atr / current_price * 100  # 百分比
            break
    
    # 根据波动率调整权重
    if daily_volatility > 2.0:  # 高波动
        layers['trend']['weight'] = 0.5  # 趋势层权重增加
        layers['swing']['weight'] = 0.35
        layers['intraday']['weight'] = 0.15  # 日内层权重减少
        vol_regime = 'high'
    elif daily_volatility < 0.8:  # 低波动
        layers['trend']['weight'] = 0.3
        layers['swing']['weight'] = 0.35
        layers['intraday']['weight'] = 0.35  # 日内层权重增加
        vol_regime = 'low'
    else:  # 正常波动
        vol_regime = 'normal'
    
    combined_score = sum(layer_scores[k] * layers[k]['weight'] for k in layers.keys())
    
    # 置信度
    confidence = min(95, 50 + abs(combined_score) * 8 + agreement * 0.3)
    
    return {
        'overall': overall,
        'combined_score': round(combined_score, 2),
        'confidence': round(confidence, 1),
        'timeframes': all_results,
        'agreement': round(agreement, 1),
        'layer_scores': {layers[k]['name']: round(v, 2) for k, v in layer_scores.items()},
        'layer_directions': {layers[k]['name']: v for k, v in layer_directions.items()},
    }


def generate_signals_v2(technical: Dict, fundamental: Dict, sentiment: Dict, 
                        geopolitical: Dict, current_price: float, klines: Dict) -> Dict:
    """
    信号引擎 v2.0
    分层：方向层（日/4小时/宏观）+ 执行层（1小时/15分/RSI/ATR）
    """
    signals = {
        'direction': None,  # 主方向
        'execution': [],    # 执行信号
        'conflicts': [],    # 冲突信号
        'recommendation': {}  # 操作建议
    }
    
    # ========== 方向层 ==========
    # 长周期技术方向
    trend_layer = technical.get('layer_directions', {}).get('趋势', 'neutral')
    swing_layer = technical.get('layer_directions', {}).get('波段', 'neutral')
    
    # 基本面方向
    fund_score = fundamental.get('combined_score', 0)
    fund_direction = 'bullish' if fund_score >= 0.5 else ('bearish' if fund_score <= -0.5 else 'neutral')
    
    # 资金面方向
    sent_score = sentiment.get('combined_score', 0)
    sent_direction = 'bullish' if sent_score >= 0.8 else ('bearish' if sent_score <= -0.8 else 'neutral')
    
    # 地缘政治方向
    geo_impact = geopolitical.get('impact_score', 0) if geopolitical else 0
    geo_direction = 'bullish' if geo_impact >= 1.5 else ('bearish' if geo_impact <= -0.5 else 'neutral')
    
    # 综合方向判断
    bullish_votes = sum(1 for d in [trend_layer, swing_layer, fund_direction, sent_direction, geo_direction] 
                        if d == 'bullish')
    bearish_votes = sum(1 for d in [trend_layer, swing_layer, fund_direction, sent_direction, geo_direction] 
                        if d == 'bearish')
    
    if bullish_votes >= 3:
        signals['direction'] = 'bullish'
    elif bearish_votes >= 3:
        signals['direction'] = 'bearish'
    else:
        signals['direction'] = 'neutral'
    
    # ========== 执行层 ==========
    intraday_layer = technical.get('layer_directions', {}).get('日内', 'neutral')
    swing_score = technical.get('layer_scores', {}).get('波段', 0)
    
    # 从技术面提取具体信号
    for tf in technical.get('timeframes', []):
        indicators = tf.get('indicators', {})
        if not indicators:
            continue
        
        layer = tf.get('layer', '')
        label = tf.get('label', '')
        
        # 只处理波段和日内周期作为执行信号
        if layer not in ['波段', '日内']:
            continue
        
        # MACD金叉/死叉
        macd = indicators.get('macd', {})
        if macd.get('cross') == 'golden_cross':
            signals['execution'].append({
                'type': 'BUY',
                'layer': layer,
                'timeframe': label,
                'reason': 'MACD金叉',
                'strength': '强' if tf['score'] > 1 else '中'
            })
        elif macd.get('cross') == 'death_cross':
            signals['execution'].append({
                'type': 'SELL',
                'layer': layer,
                'timeframe': label,
                'reason': 'MACD死叉',
                'strength': '强' if tf['score'] < -1 else '中'
            })
        
        # RSI超买超卖
        rsi = indicators.get('rsi14', 50)
        if rsi <= 30:
            signals['execution'].append({
                'type': 'BUY',
                'layer': layer,
                'timeframe': label,
                'reason': f'RSI超卖({rsi:.0f})',
                'strength': '中'
            })
        elif rsi >= 70:
            signals['execution'].append({
                'type': 'SELL',
                'layer': layer,
                'timeframe': label,
                'reason': f'RSI超买({rsi:.0f})',
                'strength': '中'
            })
        
        # KDJ金叉/死叉
        kdj = indicators.get('kdj', {})
        if kdj.get('cross') == 'golden_cross':
            signals['execution'].append({
                'type': 'BUY',
                'layer': layer,
                'timeframe': label,
                'reason': 'KDJ金叉',
                'strength': '中'
            })
        elif kdj.get('cross') == 'death_cross':
            signals['execution'].append({
                'type': 'SELL',
                'layer': layer,
                'timeframe': label,
                'reason': 'KDJ死叉',
                'strength': '中'
            })
    
    # ========== 冲突检测与解决 ==========
    buy_signals = [s for s in signals['execution'] if s['type'] == 'BUY']
    sell_signals = [s for s in signals['execution'] if s['type'] == 'SELL']
    
    has_conflict = len(buy_signals) > 0 and len(sell_signals) > 0
    
    if has_conflict:
        # 冲突解决机制：按优先级规则判断
        # 优先级：趋势层 > 波段层 > 日内层
        
        # 统计各层信号强度
        trend_buy_score = sum(1 for s in buy_signals if s['layer'] == '趋势')
        trend_sell_score = sum(1 for s in sell_signals if s['layer'] == '趋势')
        swing_buy_score = sum(1 for s in buy_signals if s['layer'] == '波段')
        swing_sell_score = sum(1 for s in sell_signals if s['layer'] == '波段')
        intraday_buy_score = sum(1 for s in buy_signals if s['layer'] == '日内')
        intraday_sell_score = sum(1 for s in sell_signals if s['layer'] == '日内')
        
        # 计算加权得分（趋势层权重最高）
        buy_weighted = trend_buy_score * 3 + swing_buy_score * 2 + intraday_buy_score * 1
        sell_weighted = trend_sell_score * 3 + swing_sell_score * 2 + intraday_sell_score * 1
        
        # 判断冲突严重程度
        conflict_severity = abs(buy_weighted - sell_weighted)
        
        if conflict_severity <= 2:
            # 轻度冲突：建议等待
            signals['conflicts'].append({
                'type': 'mild',
                'description': f'轻度冲突：{len(buy_signals)}个买入信号 vs {len(sell_signals)}个卖出信号，建议等待方向明确',
                'resolution': 'wait',
                'buy_signals': buy_signals[:3],
                'sell_signals': sell_signals[:3],
                'weighted_score': buy_weighted - sell_weighted
            })
        else:
            # 重度冲突：按权重高的方向为准
            dominant_direction = 'bullish' if buy_weighted > sell_weighted else 'bearish'
            signals['conflicts'].append({
                'type': 'severe',
                'description': f'重度冲突：{len(buy_signals)}个买入信号 vs {len(sell_signals)}个卖出信号，以{dominant_direction}方向为准',
                'resolution': 'follow_dominant',
                'dominant_direction': dominant_direction,
                'buy_signals': buy_signals[:3],
                'sell_signals': sell_signals[:3],
                'weighted_score': buy_weighted - sell_weighted
            })
    
    # ========== 操作建议 ==========
    direction = signals['direction']
    intraday_direction = intraday_layer
    agreement = technical.get('agreement', 50)
    
    # 检查是否有冲突
    conflict_info = signals['conflicts'][0] if signals['conflicts'] else None
    
    # 获取支撑阻力位（多源融合：枢轴点 + 布林带 + 斐波那契）
    support_price = None
    resistance_price = None
    current_price = current_price  # 函数参数已传入
    
    # 方法1: 经典枢轴点 (Pivot Point) - 基于昨日OHLC，每日更新
    for tf in technical.get('timeframes', []):
        if tf.get('label') == '日线':
            kline_data = tf.get('raw_data', [])
            if len(kline_data) >= 2:
                prev = kline_data[-2]  # 昨日K线
                pivot = (prev['high'] + prev['low'] + prev['close']) / 3
                s1 = 2 * pivot - prev['high']
                r1 = 2 * pivot - prev['low']
                s2 = pivot - (prev['high'] - prev['low'])
                r2 = pivot + (prev['high'] - prev['low'])
                # 取距当前价最近的支撑/阻力
                supports_pivot = sorted([s for s in [s1, s2] if s < current_price], reverse=True)
                resistances_pivot = sorted([r for r in [r1, r2] if r > current_price])
                if supports_pivot:
                    support_price = supports_pivot[0]
                if resistances_pivot:
                    resistance_price = resistances_pivot[0]
            break
    
    # 方法2: 布林带上下轨（仅当枢轴点不存在时使用）
    for tf in technical.get('timeframes', []):
        if tf.get('label') == '日线':
            bb = tf.get('indicators', {}).get('bollinger', {})
            bb_lower = bb.get('lower', 0)
            bb_upper = bb.get('upper', 0)
            if not support_price and bb_lower and bb_lower < current_price:
                support_price = bb_lower
            if not resistance_price and bb_upper and bb_upper > current_price:
                resistance_price = bb_upper
            break
    
    # 方法3: 如果以上都没有，回退到斐波那契
    if not support_price or not resistance_price:
        for tf in technical.get('timeframes', []):
            if tf.get('label') == '日线':
                sr = tf.get('indicators', {}).get('support_resistance', {})
                supports = sr.get('supports', [])
                resistances = sr.get('resistances', [])
                if not support_price and supports:
                    support_price = supports[0]
                if not resistance_price and resistances:
                    resistance_price = resistances[0]
                break
    
    # ATR动态止损计算
    # 从日线数据计算ATR
    atr_value = 0
    for tf in technical.get('timeframes', []):
        if tf.get('label') == '日线':
            kline_data = tf.get('raw_data', [])
            if len(kline_data) >= 15:
                # 计算14日ATR
                trs = []
                for i in range(1, len(kline_data)):
                    h = kline_data[i]['high']
                    l = kline_data[i]['low']
                    pc = kline_data[i-1]['close']
                    tr = max(h - l, abs(h - pc), abs(l - pc))
                    trs.append(tr)
                if len(trs) >= 14:
                    atr_value = sum(trs[:14]) / 14
                    for i in range(14, len(trs)):
                        atr_value = (atr_value * 13 + trs[i]) / 14
            break
    
    # 根据ATR计算动态止损
    # 规则：止损距离 = 2倍ATR（适应不同波动环境）
    # 高波动时止损更宽，低波动时止损更窄
    if atr_value > 0:
        atr_stop_distance = atr_value * 2
        stop_loss_price = (support_price - atr_stop_distance) if support_price else None
        stop_loss_price_short = (resistance_price + atr_stop_distance) if resistance_price else None
    else:
        # ATR计算失败时回退到固定3%
        stop_loss_price = support_price * 0.97 if support_price else None
        stop_loss_price_short = resistance_price * 1.03 if resistance_price else None
    
    # 生成建议（考虑冲突）
    if conflict_info and conflict_info.get('resolution') == 'wait':
        # 轻度冲突，建议等待
        signals['recommendation'] = {
            'action': '观望等待',
            'strategy': f"信号冲突（{conflict_info['description']}），建议等待方向明确",
            'entry': '等待冲突解决后再入场',
            'position': '暂不入场',
            'stop_loss': 'N/A',
            'target': 'N/A',
            'condition': '等待趋势层或波段层信号明确'
        }
    elif conflict_info and conflict_info.get('resolution') == 'follow_dominant':
        # 重度冲突，按主导方向
        dominant = conflict_info.get('dominant_direction')
        if dominant == 'bullish':
            signals['recommendation'] = {
                'action': '谨慎做多',
                'strategy': f"虽有冲突，但趋势层偏多，可轻仓试多",
                'entry': f'回调至{support_price:.0f}附近' if support_price else '回调至支撑位',
                'position': '总风险1% AUM，轻仓',
                'stop_loss': f'跌破{stop_loss_price:.0f}止损（支撑位下方{atr_stop_distance:.0f}，约2倍ATR）' if stop_loss_price and atr_value > 0 else ('跌破关键支撑止损' if stop_loss_price else 'N/A'),
                'target': f'目标{resistance_price:.0f}' if resistance_price else '上看阻力位',
                'condition': '严格止损，快进快出'
            }
        else:
            stop_loss_price_short = resistance_price * 1.03 if resistance_price else None
            signals['recommendation'] = {
                'action': '谨慎做空',
                'strategy': f"虽有冲突，但趋势层偏空，可轻仓试空",
                'entry': f'反弹至{resistance_price:.0f}附近' if resistance_price else '反弹至阻力位',
                'position': '总风险1% AUM，轻仓',
                'stop_loss': f'突破{stop_loss_price_short:.0f}止损（阻力位上方{atr_stop_distance:.0f}，约2倍ATR）' if stop_loss_price_short and atr_value > 0 else ('突破关键阻力止损' if stop_loss_price_short else 'N/A'),
                'target': f'下看{support_price:.0f}' if support_price else '下看支撑位',
                'condition': '严格止损，快进快出'
            }
    elif direction == 'bullish':
        if intraday_direction == 'bearish' or (sell_signals and not buy_signals):
            # 主多但短周期空
            signals['recommendation'] = {
                'action': '等待回调',
                'strategy': '主方向看多，但短周期偏空，不追多',
                'entry': f'等待回踩支撑位{support_price:.0f}' if support_price else '等待回调至支撑位',
                'position': '总风险1-2% AUM，首仓1/3',
                'stop_loss': f'跌破{stop_loss_price:.0f}止损（支撑位下方{atr_stop_distance:.0f}，约2倍ATR）' if stop_loss_price and atr_value > 0 else ('跌破关键支撑止损' if stop_loss_price else 'N/A'),
                'target': f'上看阻力位{resistance_price:.0f}' if resistance_price else '上看阻力位',
                'condition': '短周期转多确认后入场'
            }
        else:
            # 主多且短周期也多
            signals['recommendation'] = {
                'action': '逢低做多',
                'strategy': '多周期共振看多，可积极入场',
                'entry': f'回调至{support_price:.0f}附近' if support_price else '回调至支撑位',
                'position': '总风险2-3% AUM，可分2-3批建仓',
                'stop_loss': f'跌破{stop_loss_price:.0f}止损（支撑位下方{atr_stop_distance:.0f}，约2倍ATR）' if stop_loss_price and atr_value > 0 else ('跌破关键支撑止损' if stop_loss_price else 'N/A'),
                'target': f'目标{resistance_price:.0f}' if resistance_price else '上看阻力位',
                'condition': '直接入场或小幅回调后入场'
            }
    elif direction == 'bearish':
        # 止盈计算：阻力位上方2-3%
        stop_loss_price_short = resistance_price * 1.03 if resistance_price else None
        if intraday_direction == 'bullish' or (buy_signals and not sell_signals):
            # 主空但短周期多
            signals['recommendation'] = {
                'action': '观望或轻仓试空',
                'strategy': '主方向看空，但短周期偏多，谨慎操作',
                'entry': f'反弹至{resistance_price:.0f}附近' if resistance_price else '反弹至阻力位',
                'position': '总风险1% AUM，轻仓试空',
                'stop_loss': f'突破{stop_loss_price_short:.0f}止损（阻力位上方{atr_stop_distance:.0f}，约2倍ATR）' if stop_loss_price_short and atr_value > 0 else ('突破关键阻力止损' if stop_loss_price_short else 'N/A'),
                'target': f'下看{support_price:.0f}' if support_price else '下看支撑位',
                'condition': '短周期转空确认后入场'
            }
        else:
            # 主空且短周期也空
            signals['recommendation'] = {
                'action': '逢高做空',
                'strategy': '多周期共振看空，可积极入场',
                'entry': f'反弹至{resistance_price:.0f}附近' if resistance_price else '反弹至阻力位',
                'position': '总风险2-3% AUM，可分2-3批建仓',
                'stop_loss': f'突破{stop_loss_price_short:.0f}止损（阻力位上方{atr_stop_distance:.0f}，约2倍ATR）' if stop_loss_price_short and atr_value > 0 else ('突破关键阻力止损' if stop_loss_price_short else 'N/A'),
                'target': f'目标{support_price:.0f}' if support_price else '下看支撑位',
                'condition': '直接入场或小幅反弹后入场'
            }
    else:
        # 中性
        if agreement < 60:
            signals['recommendation'] = {
                'action': '观望',
                'strategy': '方向不明确，周期一致性低，建议观望',
                'entry': '等待方向明确',
                'position': '不建议入场',
                'stop_loss': 'N/A',
                'target': 'N/A',
                'condition': '等待至少2个周期方向一致'
            }
        else:
            signals['recommendation'] = {
                'action': '区间操作',
                'strategy': '方向中性，可区间高抛低吸',
                'entry': f'支撑位{support_price:.0f}附近做多，阻力位{resistance_price:.0f}附近做空' if support_price and resistance_price else '支撑位做多，阻力位做空',
                'position': '总风险1% AUM，轻仓',
                'stop_loss': '跌破支撑或突破阻力止损',
                'target': '区间内操作',
                'condition': '严格止损，快进快出'
            }
    
    return signals


def comprehensive_analysis(realtime: Dict, klines: Dict, macro_data: Dict, 
                          sentiment_data: Dict, geo_monitor: GeopoliticalMonitor = None,
                          correlations: Dict = None) -> Dict:
    """
    三套体系综合分析 + 地缘政治监控 v3.0
    
    Args:
        correlations: 相关性分析结果，用于动态调整技术面权重
    """
    logger.info("=" * 60)
    logger.info("开始三体系综合分析 v3.0")
    logger.info("=" * 60)
    
    # 1. 技术面分析
    logger.info("[1/4] 执行技术面分析...")
    technical = analyze_multi_timeframe_v2(klines)
    logger.info(f"技术面完成: 得分={technical.get('combined_score', 0):.2f}, 判断={technical.get('overall', 'N/A')}")
    
    # 2. 基本面分析
    logger.info("[2/4] 执行基本面分析...")
    fundamental = fundamental_analysis(macro_data, realtime)
    logger.info(f"基本面完成: 得分={fundamental.get('combined_score', 0):.2f}, 判断={fundamental.get('overall', 'N/A')}")
    
    # 3. 资金面分析
    logger.info("[3/4] 执行资金面分析...")
    sentiment = sentiment_analysis(sentiment_data, realtime)
    logger.info(f"资金面完成: 得分={sentiment.get('combined_score', 0):.2f}, 判断={sentiment.get('overall', 'N/A')}")
    
    # 4. 地缘政治分析
    geopolitical = None
    if geo_monitor:
        logger.info("[4/4] 执行地缘政治分析...")
        try:
            geo_monitor.fetch_all_news()
            # 使用新版接口
            geo_result = geo_monitor.get_geo_result()
            geo_risk = geo_monitor.score_geopolitical_risk()
            geopolitical = {
                'risk': geo_risk,
                'impact_score': geo_result.score,  # 新版：[-1, 1]标准化得分
                'geo_result': geo_result.to_dict(),
            }
            logger.info(f"地缘政治完成: 风险等级={geo_risk.get('level', 'N/A')}, 标准化得分={geo_result.score:+.2f}, 决策={geo_result.action}")
        except Exception as e:
            logger.error(f"地缘政治分析失败: {e}", exc_info=True)
    
    # 综合评分
    tech_score = technical.get('combined_score', 0)
    fund_score = fundamental.get('combined_score', 0)
    sent_score = sentiment.get('combined_score', 0)
    geo_score = geopolitical['impact_score'] if geopolitical else 0
    
    weights = load_weights()
    w_tech = weights.get('technical', 0.40)
    w_fund = weights.get('fundamental', 0.35)
    w_sent = weights.get('sentiment', 0.25)
    w_geo = weights.get('geopolitical_bonus', 0.30)
    
    # 相关性驱动的权重自适应调整
    if correlations:
        corr_overall = correlations.get('overall', '')
        if '不稳定' in corr_overall or '降低技术面权重' in corr_overall:
            w_tech *= 0.6  # 技术面权重从 0.40 降到 0.24
            logger.warning("相关性验证: 技术指标体系不稳定，技术面权重自动降至 %.2f", w_tech)
        elif '高度有效' in corr_overall:
            w_tech *= 1.1  # 置信度高时微提权重
            w_tech = min(w_tech, 0.50)  # 上限0.50
            logger.info("相关性验证: 技术指标高度有效，技术面权重提升至 %.2f", w_tech)
    
    # v3.1: 地缘加权融合（替代简单加法，避免geo_score过大主导综合得分）
    # 地缘分[-1,1]归一化到[0,1]后参与加权，再除以总权重归一化
    geo_norm = max(0.0, min(1.0, (geo_score + 1.0) / 2.0))
    total_w = w_tech + w_fund + w_sent + w_geo
    base_score = tech_score * w_tech + fund_score * w_fund + sent_score * w_sent
    total_score = (base_score + geo_norm * w_geo) / total_w
    
    # 综合判断
    if total_score >= 2.0:
        overall = '强烈看多'
    elif total_score >= 1.0:
        overall = '看多'
    elif total_score >= 0.3:
        overall = '偏多'
    elif total_score > -0.3:
        overall = '中性'
    elif total_score > -1.0:
        overall = '偏空'
    elif total_score > -2.0:
        overall = '看空'
    else:
        overall = '强烈看空'
    
    logger.info(f"综合判断: {overall} (得分={total_score:.2f})")
    
    # 生成信号 v2.0
    current_price = realtime.get('gold', {}).get('price', 0)
    signals = generate_signals_v2(technical, fundamental, sentiment, geopolitical, current_price, klines)
    
    logger.info(f"主方向: {signals['direction']}")
    logger.info(f"执行信号: {len(signals['execution'])}个")
    if signals['conflicts']:
        logger.warning(f"检测到信号冲突: {len(signals['conflicts'])}个")
    
    return {
        'overall': overall,
        'total_score': round(total_score, 2),
        'technical': technical,
        'fundamental': fundamental,
        'sentiment': sentiment,
        'geopolitical': geopolitical,
        'signals': signals,
        'current_price': current_price,
    }


def format_comprehensive_report(analysis: Dict, realtime: Dict, macro_data: Dict) -> str:
    """生成完整三体系分析报告 v3.0"""
    lines = []
    lines.append("=" * 70)
    lines.append("黄金三体系综合分析报告 v3.0")
    lines.append("=" * 70)
    
    # 实时行情
    gold = realtime.get('gold', {})
    usd = realtime.get('usd_index', {})
    oil = realtime.get('oil', {})
    silver = realtime.get('silver', {})
    
    lines.append("\n【实时行情】")
    if gold:
        lines.append(f"  伦敦金: {gold.get('price', 0):.2f}  "
                    f"高:{gold.get('high', 0):.2f}  低:{gold.get('low', 0):.2f}")
    if usd:
        lines.append(f"  美元指数: {usd.get('price', 0):.2f} (分位{usd.get('percentile', 'N/A')}%)")
    if oil:
        lines.append(f"  纽约原油: {oil.get('price', 0):.2f}")
    if silver:
        lines.append(f"  纽约白银: {silver.get('price', 0):.2f}")
    if 'gold_silver_ratio' in realtime:
        lines.append(f"  金银比: {realtime['gold_silver_ratio']:.2f}")
    
    # 宏观数据
    if macro_data:
        lines.append("\n【宏观数据】")
        if 'us10y' in macro_data:
            lines.append(f"  10Y国债: {macro_data['us10y'].get('value', 0):.2f}%")
        if 'real_rate' in macro_data:
            lines.append(f"  实际利率: {macro_data['real_rate'].get('value', 0):.2f}% (分位{macro_data['real_rate'].get('percentile', 'N/A')}%)")
        if 'inflation_expect' in macro_data:
            lines.append(f"  通胀预期: {macro_data['inflation_expect'].get('value', 0):.2f}%")
        if 'fed_rate' in macro_data:
            lines.append(f"  联邦基金利率: {macro_data['fed_rate'].get('value', 0):.2f}%")
        if 'nonfarm_change' in macro_data:
            lines.append(f"  非农就业变化: {macro_data['nonfarm_change']:+.0f}K")
        if 'unemployment_rate' in macro_data:
            lines.append(f"  失业率: {macro_data['unemployment_rate'].get('value', 0):.1f}%")
        if 'core_pce_yoy' in macro_data:
            lines.append(f"  核心PCE同比: {macro_data['core_pce_yoy'].get('value', 0):.1f}%")
        if 'gdp_growth' in macro_data:
            lines.append(f"  GDP增速: {macro_data['gdp_growth'].get('value', 0):.1f}%")
        if 'vix' in macro_data:
            lines.append(f"  VIX: {macro_data['vix'].get('value', 0):.2f} (分位{macro_data['vix'].get('percentile', 'N/A')}%)")
    
    # 综合判断
    lines.append(f"\n{'='*70}")
    lines.append(f"【综合判断】")
    lines.append(f"  总体方向: {analysis.get('overall', '无数据')}")
    lines.append(f"  综合得分: {analysis.get('total_score', 0):.2f}")
    lines.append(f"  技术面得分: {analysis.get('technical', {}).get('combined_score', 0):.2f} (权重40%)")
    lines.append(f"  基本面得分: {analysis.get('fundamental', {}).get('combined_score', 0):.2f} (权重35%)")
    lines.append(f"  资金面得分: {analysis.get('sentiment', {}).get('combined_score', 0):.2f} (权重25%)")
    
    # 技术面详情（分层展示）
    technical = analysis.get('technical', {})
    lines.append(f"\n{'='*70}")
    lines.append(f"【技术面分析】")
    lines.append(f"  总体判断: {technical.get('overall', '无数据')}")
    lines.append(f"  置信度: {technical.get('confidence', 0):.1f}%")
    lines.append(f"  周期一致性: {technical.get('agreement', 0):.1f}%")
    
    # 分层得分
    layer_scores = technical.get('layer_scores', {})
    if layer_scores:
        lines.append(f"  分层得分:")
        for layer_name, score in layer_scores.items():
            lines.append(f"    {layer_name}: {score:.2f}")
    
    # 各周期详情
    for tf in technical.get('timeframes', []):
        layer = tf.get('layer', '')
        lines.append(f"\n  [{layer}] {tf['label']}:")
        lines.append(f"    趋势: {tf['trend']} (得分: {tf['score']:.2f})")
        if tf['reasons']:
            lines.append(f"    原因: {', '.join(tf['reasons'][:3])}")
        
        sr = tf.get('indicators', {}).get('support_resistance', {})
        if sr:
            supports = sr.get('supports', [])
            resistances = sr.get('resistances', [])
            if supports:
                lines.append(f"    支撑位: {', '.join(f'{s:.2f}' for s in supports[:2])}")
            if resistances:
                lines.append(f"    阻力位: {', '.join(f'{r:.2f}' for r in resistances[:2])}")
    
    # 基本面详情
    fundamental = analysis.get('fundamental', {})
    lines.append(f"\n{'='*70}")
    lines.append(format_fundamental_report(fundamental, macro_data))
    
    # 资金面详情
    sentiment = analysis.get('sentiment', {})
    lines.append(f"\n{'='*70}")
    lines.append(format_sentiment_report(sentiment))
    
    # 地缘政治详情
    geopolitical = analysis.get('geopolitical')
    if geopolitical:
        lines.append(f"\n{'='*70}")
        lines.append(format_geopolitical_report(geopolitical.get('risk', {})))
        lines.append(f"  对金价影响: {geopolitical.get('impact_score', 0):.1f}分")
    
    # 交易信号（分层展示）
    signals = analysis.get('signals', {})
    lines.append(f"\n{'='*70}")
    lines.append("【交易信号】")
    
    direction = signals.get('direction', 'neutral')
    direction_emoji = {'bullish': '🟢', 'bearish': '🔴', 'neutral': '⚪'}.get(direction, '⚪')
    lines.append(f"  主方向: {direction_emoji} {direction}")
    
    execution = signals.get('execution', [])
    if execution:
        lines.append(f"\n  执行层信号 ({len(execution)}个):")
        for sig in execution[:10]:  # 最多显示10个
            emoji = '🟢' if sig['type'] == 'BUY' else '🔴'
            lines.append(f"    {emoji} {sig['type']} [{sig['layer']}-{sig['timeframe']}] {sig['reason']}")
    
    conflicts = signals.get('conflicts', [])
    if conflicts:
        lines.append(f"\n  ⚠️ 信号冲突 ({len(conflicts)}个):")
        for conflict in conflicts[:3]:
            lines.append(f"    - {conflict['description']}")
    
    # 操作建议（三要素）
    lines.append(f"\n{'='*70}")
    lines.append("【操作建议】")
    
    rec = signals.get('recommendation', {})
    if rec:
        lines.append(f"  操作: {rec.get('action', 'N/A')}")
        lines.append(f"  策略: {rec.get('strategy', 'N/A')}")
        lines.append(f"  入场: {rec.get('entry', 'N/A')}")
        lines.append(f"  仓位: {rec.get('position', 'N/A')}")
        lines.append(f"  止损: {rec.get('stop_loss', 'N/A')}")
        lines.append(f"  目标: {rec.get('target', 'N/A')}")
        lines.append(f"  条件: {rec.get('condition', 'N/A')}")
    else:
        lines.append("  暂无明确建议")
    
    lines.append(f"\n{'='*70}")
    lines.append("⚠️ 以上分析仅供参考，不构成投资建议。市场有风险，投资需谨慎。")
    lines.append("=" * 70)
    
    return '\n'.join(lines)
