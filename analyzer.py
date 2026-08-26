#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合分析引擎 v4.2
改进:
- 地缘评分从"简单加法"改为"加权融合"(归一化后参与总权重),
  避免 geo_score 过大时主导综合得分
- 执行层信号增加"基本面边际变化触发"(实际利率大幅改善/恶化)

优化点：
1. 多周期分层（日内/波段/趋势）
2. 信号引擎分层（方向层+执行层）
3. 输出升级（触发价/仓位/止损三要素）
"""

from typing import Dict, List, Optional
from indicators import calc_all_indicators, calc_ma, analyze_volume_price
from fundamental_analyzer import fundamental_analysis, format_fundamental_report
from sentiment_analyzer import sentiment_analysis, format_sentiment_report
from geopolitical import GeopoliticalMonitor, format_geopolitical_report
import logging
import json
import math
from datetime import datetime, timedelta, timezone
from app_paths import CONFIG_DIR, bundled_path

logger = logging.getLogger(__name__)
BEIJING_TZ = timezone(timedelta(hours=8), name='Asia/Shanghai')

# 默认权重
DEFAULT_WEIGHTS = {
    'technical': 0.40,
    'fundamental': 0.35,
    'sentiment': 0.25,
    'geopolitical_bonus': 0.15
}

def load_weights() -> Dict:
    """加载权重配置"""
    config_path = CONFIG_DIR / 'weights.json'
    if not config_path.exists():
        config_path = bundled_path('config/weights.json')
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('weights', DEFAULT_WEIGHTS)
    except Exception as e:
        logger.warning(f"加载权重配置失败，使用默认值: {e}")
    return DEFAULT_WEIGHTS


DEFAULT_FEE_CONFIG = {
    'long_only': True,
    'quantity_oz': 1.0,
    'buy_fixed_usd': 0.0,
    'sell_fixed_usd': 13.0,
    'buy_rate': 0.0,
    'sell_rate': 0.0,
    'slippage_points': 0.0,
    'min_rr_ratio': 1.5,
    'preferred_rr_ratio': 2.0,
    'stop_atr_multiplier': 1.0,
    'risk_pct': 0.01,
}


def load_fee_config() -> Dict:
    """加载做多成本与风控配置，兼容固定费用和按成交额费率。"""
    config = DEFAULT_FEE_CONFIG.copy()
    config_path = CONFIG_DIR / 'fees.json'
    if not config_path.exists():
        config_path = bundled_path('config/fees.json')
    try:
        if config_path.exists():
            with config_path.open('r', encoding='utf-8') as f:
                user = json.load(f).get('fees', {})
            config.update({k: user[k] for k in config if k in user})
    except (OSError, ValueError, TypeError) as e:
        logger.warning("加载费用配置失败，使用默认值: %s", e)

    numeric_keys = [k for k in config if k != 'long_only']
    for key in numeric_keys:
        try:
            config[key] = float(config[key])
        except (TypeError, ValueError):
            config[key] = DEFAULT_FEE_CONFIG[key]
    config['quantity_oz'] = max(config['quantity_oz'], 0.000001)
    config['min_rr_ratio'] = max(config['min_rr_ratio'], 0.1)
    config['preferred_rr_ratio'] = max(config['preferred_rr_ratio'], config['min_rr_ratio'])
    config['stop_atr_multiplier'] = max(config['stop_atr_multiplier'], 0.1)
    return config


def calculate_long_trade_metrics(entry: float, stop: float, target: float,
                                 fees: Dict) -> Dict:
    """按持仓数量计算做多净收益、净风险、净盈亏比和最低目标价。"""
    quantity = fees['quantity_oz']
    buy_cost = fees['buy_fixed_usd'] + entry * quantity * fees['buy_rate']
    target_sell_cost = fees['sell_fixed_usd'] + target * quantity * fees['sell_rate']
    stop_sell_cost = fees['sell_fixed_usd'] + stop * quantity * fees['sell_rate']
    slippage_cost = fees['slippage_points'] * quantity

    reward_net = (target - entry) * quantity - buy_cost - target_sell_cost - slippage_cost
    risk_net = (entry - stop) * quantity + buy_cost + stop_sell_cost + slippage_cost
    net_rr = reward_net / risk_net if risk_net > 0 else 0.0

    # 解 Reward_net >= min_rr * Risk_net，费率型退出成本也纳入目标。
    denominator = quantity * (1.0 - fees['sell_rate'])
    min_target = 0.0
    if denominator > 0:
        min_target = (
            entry * quantity + buy_cost + fees['sell_fixed_usd'] + slippage_cost
            + fees['min_rr_ratio'] * risk_net
        ) / denominator

    return {
        'reward_net_usd': round(reward_net, 2),
        'risk_net_usd': round(risk_net, 2),
        'net_rr': round(net_rr, 2),
        'min_target': round(min_target, 2),
        'cost_per_oz': round((buy_cost + target_sell_cost + slippage_cost) / quantity, 2),
    }


def calculate_friction_metrics(current_price: float, atr_dict: Dict, fees: Dict) -> Dict:
    """
    计算摩擦成本指标，量化手续费对不同周期的影响。
    
    核心逻辑：
    - 手续费 = 固定费用 + 费率型费用 + 滑点
    - 摩擦占比 = 手续费 / 周期波幅(ATR)
    - 摩擦占比越高，该周期越不适合交易
    
    周期适用性阈值：
    - 摩擦占比 < 5%: 适合（绿色）
    - 5% <= 摩擦占比 < 15%: 勉强（黄色）
    - 摩擦占比 >= 15%: 不适合（红色）
    """
    quantity = max(fees.get('quantity_oz', 1.0), 0.000001)
    
    # 计算单次往返总成本（买入 + 卖出）
    buy_fixed = fees.get('buy_fixed_usd', 0)
    sell_fixed = fees.get('sell_fixed_usd', 0)
    buy_rate = fees.get('buy_rate', 0)
    sell_rate = fees.get('sell_rate', 0)
    slippage = fees.get('slippage_points', 0)
    
    # 单次往返成本 = 固定费用 + 费率费用 + 滑点
    fixed_cost = buy_fixed + sell_fixed
    rate_cost = current_price * quantity * (buy_rate + sell_rate)
    slippage_cost = slippage * quantity
    total_cost = fixed_cost + rate_cost + slippage_cost
    
    # 每盎司成本
    cost_per_oz = total_cost / quantity
    
    # 计算各周期的摩擦占比
    period_friction = {}
    suitable_periods = []
    marginal_periods = []
    unsuitable_periods = []
    
    for period_name, atr_value in atr_dict.items():
        if atr_value is None or atr_value <= 0:
            continue
        
        # 摩擦占比 = 成本 / ATR（预期波幅）
        friction_ratio = cost_per_oz / atr_value
        friction_pct = friction_ratio * 100
        
        period_friction[period_name] = {
            'atr': round(atr_value, 2),
            'cost_per_oz': round(cost_per_oz, 2),
            'friction_pct': round(friction_pct, 1),
        }
        
        # 分类
        if friction_pct < 5:
            suitable_periods.append(period_name)
            period_friction[period_name]['suitability'] = '适合'
            period_friction[period_name]['color'] = 'green'
        elif friction_pct < 15:
            marginal_periods.append(period_name)
            period_friction[period_name]['suitability'] = '勉强'
            period_friction[period_name]['color'] = 'yellow'
        else:
            unsuitable_periods.append(period_name)
            period_friction[period_name]['suitability'] = '不适合'
            period_friction[period_name]['color'] = 'red'
    
    # 生成建议
    recommendation = _generate_fee_recommendation(
        suitable_periods, marginal_periods, unsuitable_periods, cost_per_oz
    )
    
    return {
        'total_cost_per_oz': round(cost_per_oz, 2),
        'fixed_cost': round(fixed_cost, 2),
        'rate_cost': round(rate_cost, 2),
        'slippage_cost': round(slippage_cost, 2),
        'period_friction': period_friction,
        'suitable_periods': suitable_periods,
        'marginal_periods': marginal_periods,
        'unsuitable_periods': unsuitable_periods,
        'recommendation': recommendation,
    }


def _generate_fee_recommendation(suitable: List, marginal: List, 
                                  unsuitable: List, cost_per_oz: float) -> str:
    """根据摩擦成本生成操作建议。"""
    if not suitable and not marginal:
        return f"当前费率过高（每盎司${cost_per_oz:.2f}），所有周期均不适合交易。建议降低费率或增大持仓量。"
    
    if suitable:
        return f"当前费率适合{', '.join(suitable)}交易。{'也可考虑' + ', '.join(marginal) + '（摩擦较高）。' if marginal else ''}"
    
    # 只有 marginal
    return f"当前费率偏高，仅{', '.join(marginal)}勉强可行（摩擦占比5-15%）。建议降低费率或仅在大波幅时交易。"


def filter_signals_by_friction(signals: Dict, period_friction: Dict, 
                                klines: Dict) -> Dict:
    """
    根据摩擦成本过滤信号。
    
    规则：
    - 不适合周期（摩擦>=15%）的信号被过滤
    - 勉强周期（5-15%）的信号强度降级
    - 适合周期（<5%）的信号保持不变
    """
    if not period_friction:
        return signals
    
    filtered_execution = []
    filtered_count = 0
    downgraded_count = 0
    
    for signal in signals.get('execution', []):
        timeframe = signal.get('timeframe', '')
        friction_info = period_friction.get(timeframe, {})
        suitability = friction_info.get('suitability', '适合')
        
        if suitability == '不适合':
            # 过滤掉不适合周期的信号
            filtered_count += 1
            continue
        elif suitability == '勉强':
            # 降级信号强度
            signal_copy = signal.copy()
            if signal_copy.get('strength') == '强':
                signal_copy['strength'] = '中'
            else:
                signal_copy['strength'] = '弱'
            signal_copy['friction_warning'] = f"摩擦占比{friction_info.get('friction_pct', 0):.1f}%"
            filtered_execution.append(signal_copy)
            downgraded_count += 1
        else:
            filtered_execution.append(signal)
    
    signals['execution'] = filtered_execution
    
    # 添加过滤统计
    if filtered_count > 0 or downgraded_count > 0:
        signals['friction_filter'] = {
            'filtered': filtered_count,
            'downgraded': downgraded_count,
            'reason': '手续费摩擦成本过高',
        }
    
    return signals


def _calculate_atr(candles: List[Dict], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        high, low = candles[i]['high'], candles[i]['low']
        previous_close = candles[i - 1]['close']
        trs.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    if len(trs) < period:
        return sum(trs) / len(trs)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def calculate_period_levels(candles: List[Dict], indicators: Dict,
                            swing: int = 3, lookback: int = 160) -> Dict:
    """计算单周期最近有效结构位；支撑必须低于当前价，阻力必须高于当前价。"""
    if len(candles) < swing * 2 + 1:
        return {'support': None, 'resistance': None, 'atr': 0.0, 'method': 'insufficient'}

    recent = candles[-lookback:]
    current = recent[-1]['close']
    atr = _calculate_atr(recent, 14)
    supports = []
    resistances = []

    for index in range(swing, len(recent) - swing):
        window = recent[index - swing:index + swing + 1]
        age = len(recent) - 1 - index
        if recent[index]['low'] == min(c['low'] for c in window) and recent[index]['low'] < current:
            supports.append((recent[index]['low'], age))
        if recent[index]['high'] == max(c['high'] for c in window) and recent[index]['high'] > current:
            resistances.append((recent[index]['high'], age))

    scale = max(atr, current * 0.001, 0.01)

    def choose(candidates):
        if not candidates:
            return None
        # 距离优先，同时轻度惩罚过旧结构，避免多年高低点主导执行层。
        return min(candidates, key=lambda item: abs(item[0] - current) / scale + item[1] * 0.01)[0]

    support = choose(supports)
    resistance = choose(resistances)
    method = 'swing'

    sr = indicators.get('support_resistance', {})
    if support is None:
        valid = [value for value in sr.get('supports', []) if value < current]
        support = max(valid) if valid else None
    if resistance is None:
        valid = [value for value in sr.get('resistances', []) if value > current]
        resistance = min(valid) if valid else None

    if support is None or resistance is None:
        last = recent[-1]
        pivot = (last['high'] + last['low'] + last['close']) / 3
        s1 = 2 * pivot - last['high']
        r1 = 2 * pivot - last['low']
        support = support or (s1 if s1 < current else None)
        resistance = resistance or (r1 if r1 > current else None)
        method = 'swing+pivot'

    return {
        'support': round(support, 2) if support is not None else None,
        'resistance': round(resistance, 2) if resistance is not None else None,
        'atr': round(atr, 2),
        'method': method,
    }


def _next_15m_watch_time() -> str:
    now = datetime.now(BEIJING_TZ)
    next_minute = ((now.minute // 15) + 1) * 15
    next_close = now.replace(second=0, microsecond=0)
    if next_minute >= 60:
        next_close = next_close.replace(minute=0) + timedelta(hours=1)
    else:
        next_close = next_close.replace(minute=next_minute)
    return next_close.strftime('%Y-%m-%d %H:%M 北京时间（15分钟收盘）')


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

            levels = calculate_period_levels(
                klines[key], analysis.get('indicators', {}),
                swing=2 if key in ('5min', '15min') else 3,
            )
            
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
                'raw_data': analysis.get('raw_data', []),  # 仅包含已收盘K线
                'support': levels['support'],
                'resistance': levels['resistance'],
                'atr': levels['atr'],
                'level_method': levels['method'],
                'bar_time': klines[key][-1].get('time', '') if klines[key] else '',
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
        'recommendation': {},  # 操作建议
        'period_table': [],    # 各周期独立结构位
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
    # geopolitical impact_score 的实际范围是 [-1, 1]。
    geo_direction = 'bullish' if geo_impact >= 0.15 else ('bearish' if geo_impact <= -0.15 else 'neutral')
    
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
    
    # ========== 多周期结构表与做多计划 ==========
    timeframes = technical.get('timeframes', [])
    by_label = {tf.get('label'): tf for tf in timeframes}
    for tf in timeframes:
        support = tf.get('support')
        resistance = tf.get('resistance')
        atr = tf.get('atr', 0)
        if support is None or resistance is None or atr <= 0:
            continue
        signals['period_table'].append({
            'label': tf.get('label', ''),
            'direction': 'bullish' if tf.get('score', 0) >= 1 else (
                'bearish' if tf.get('score', 0) <= -1 else 'neutral'
            ),
            'support': support,
            'resistance': resistance,
            'atr': atr,
            'bar_time': tf.get('bar_time', ''),
            'method': tf.get('level_method', ''),
        })

    # 15分钟负责执行，1小时/4小时提供上方结构目标；全部数据均已收盘。
    active = next((by_label[label] for label in ('15分钟', '1小时', '5分钟', '4小时', '日线')
                   if label in by_label and by_label[label].get('support') is not None), None)
    support_candidates = [tf.get('support') for tf in timeframes
                          if tf.get('support') is not None and tf.get('support') < current_price]
    entry_price = max(support_candidates) if support_candidates else None
    target_candidates = [tf.get('resistance') for tf in timeframes
                         if tf.get('resistance') is not None and tf.get('resistance') > current_price]
    target_price = min(target_candidates) if target_candidates else None
    atr_value = active.get('atr', 0) if active else 0

    fees = load_fee_config()
    stop_price = None
    metrics = None
    if entry_price is not None and target_price is not None and atr_value > 0:
        stop_price = entry_price - atr_value * fees['stop_atr_multiplier']
        metrics = calculate_long_trade_metrics(entry_price, stop_price, target_price, fees)

    confirm_tf = by_label.get('15分钟')
    confirmation_items = []
    confirmed = False
    if confirm_tf:
        indicators = confirm_tf.get('indicators', {})
        macd = indicators.get('macd', {})
        close_price = indicators.get('current', 0)
        confirmation_items = [
            ('15分钟方向转多', confirm_tf.get('score', 0) >= 1.0),
            ('收盘站上MA5', close_price > indicators.get('ma5', 0)),
            ('MACD位于信号线上方', macd.get('dif', 0) >= macd.get('dea', 0)),
            ('RSI(6)不低于50', indicators.get('rsi6', 0) >= 50),
        ]
        confirmed = all(value for _, value in confirmation_items)

    confirmation_text = '；'.join(
        f"{'✓' if value else '✗'}{name}" for name, value in confirmation_items
    ) or '等待有效15分钟收盘数据'
    next_watch = _next_15m_watch_time()
    conflict_info = signals['conflicts'][0] if signals['conflicts'] else None
    direction = signals['direction']

    status_code = 'NO_TRADE_DATA'
    action = '观望'
    strategy = '缺少有效结构位或ATR，不能生成交易计划'
    if conflict_info and conflict_info.get('resolution') == 'wait':
        status_code = 'WAIT_CONFLICT'
        strategy = f"信号冲突：{conflict_info['description']}"
    elif direction != 'bullish':
        status_code = 'WAIT_DIRECTION'
        strategy = f"当前主方向为{direction}；系统仅考虑做多，暂不交易"
    elif metrics is None:
        status_code = 'NO_TRADE_DATA'
    elif metrics['net_rr'] < fees['min_rr_ratio']:
        status_code = 'NO_TRADE_RR'
        action = '观望（盈亏比不足）'
        strategy = (
            f"计划净盈亏比{metrics['net_rr']:.2f}低于最低要求"
            f"{fees['min_rr_ratio']:.2f}，不允许入场"
        )
    elif entry_price is not None and current_price > entry_price + atr_value * 0.5:
        status_code = 'WAIT_PULLBACK'
        action = '等待回踩'
        strategy = '主方向看多，但价格尚未进入15分钟支撑执行区，不追多'
    elif not confirmed:
        status_code = 'WAIT_CONFIRMATION'
        action = '等待确认'
        strategy = '价格已接近执行区，等待已收盘15分钟K线完成转多确认'
    else:
        status_code = 'READY_LONG'
        action = '计划做多'
        strategy = '主方向、执行区和15分钟确认同时满足，按计划风险执行'

    can_enter = status_code == 'READY_LONG'
    fee_note = (
        f"买入固定${fees['buy_fixed_usd']:.2f}+{fees['buy_rate'] * 10000:.2f}bp，"
        f"卖出固定${fees['sell_fixed_usd']:.2f}+{fees['sell_rate'] * 10000:.2f}bp，"
        f"按{fees['quantity_oz']:.4g}盎司计算"
    )
    if metrics:
        fee_note += (
            f"；净盈亏比{metrics['net_rr']:.2f}，最低合格目标{metrics['min_target']:.2f}"
        )

    signals['recommendation'] = {
        'status_code': status_code,
        'action': action,
        'strategy': strategy,
        'entry': f'{entry_price:.2f}附近' if entry_price is not None else 'N/A',
        'position': f"单笔净风险不超过账户{fees['risk_pct'] * 100:.1f}%" if can_enter else '不入场',
        'stop_loss': f'{stop_price:.2f}' if stop_price is not None else 'N/A',
        'target': f'{target_price:.2f}' if target_price is not None else 'N/A',
        'condition': confirmation_text,
        'next_watch': next_watch,
        'cost_note': fee_note,
        'net_rr': metrics['net_rr'] if metrics else None,
        'reward_net_usd': metrics['reward_net_usd'] if metrics else None,
        'risk_net_usd': metrics['risk_net_usd'] if metrics else None,
        'min_target': metrics['min_target'] if metrics else None,
        'active_period': active.get('label', '') if active else '',
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
    logger.info("开始三体系综合分析 v4.2")
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
    w_geo = weights.get('geopolitical_bonus', 0.15)
    
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
    
    # 地缘分范围[-1,1]，作为有符号的小幅修正；0必须保持中性而不是产生正偏置。
    geo_score = max(-1.0, min(1.0, geo_score))
    base_w = w_tech + w_fund + w_sent
    base_score = tech_score * w_tech + fund_score * w_fund + sent_score * w_sent
    total_score = (base_score / base_w if base_w > 0 else 0.0) + geo_score * w_geo
    
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
    
    # 摩擦成本分析：量化手续费对不同周期的影响
    fees = load_fee_config()
    atr_dict = {}
    for tf_data in technical.get('timeframes', []):
        label = tf_data.get('label', '')
        indicators = tf_data.get('indicators', {})
        atr_val = indicators.get('atr')
        if atr_val is not None:
            atr_dict[label] = atr_val
    # 也加入日线 ATR
    daily_atr = technical.get('timeframes', [{}])[0].get('indicators', {}).get('atr')
    if daily_atr and '日线' not in atr_dict:
        atr_dict['日线'] = daily_atr
    
    friction = calculate_friction_metrics(current_price, atr_dict, fees)
    
    # 根据摩擦成本过滤信号
    signals = filter_signals_by_friction(signals, friction.get('period_friction', {}), klines)
    
    logger.info(f"主方向: {signals['direction']}")
    logger.info(f"执行信号: {len(signals['execution'])}个")
    if signals.get('friction_filter'):
        ff = signals['friction_filter']
        logger.warning(f"摩擦过滤: 过滤{ff['filtered']}个，降级{ff['downgraded']}个")
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
        'friction': friction,
        'current_price': current_price,
    }


def format_comprehensive_report(analysis: Dict, realtime: Dict, macro_data: Dict) -> str:
    """生成完整三体系分析报告 v3.0"""
    lines = []
    lines.append("=" * 70)
    lines.append("黄金三体系综合分析报告 v4.2")
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
            friction_tag = f" ⚠️{sig['friction_warning']}" if sig.get('friction_warning') else ''
            lines.append(f"    {emoji} {sig['type']} [{sig['layer']}-{sig['timeframe']}] {sig['reason']}{friction_tag}")
    
    friction_filter = signals.get('friction_filter', {})
    if friction_filter:
        lines.append(f"\n  🔇 摩擦过滤: 已过滤{friction_filter['filtered']}个信号，降级{friction_filter['downgraded']}个（{friction_filter['reason']}）")
    
    conflicts = signals.get('conflicts', [])
    if conflicts:
        lines.append(f"\n  ⚠️ 信号冲突 ({len(conflicts)}个):")
        for conflict in conflicts[:3]:
            lines.append(f"    - {conflict['description']}")

    period_table = signals.get('period_table', [])
    if period_table:
        lines.append(f"\n{'='*70}")
        lines.append("【已收盘K线周期点位】")
        lines.append(f"  {'周期':<7} {'方向':<8} {'支撑':>10} {'阻力':>10} {'ATR':>8}  最后收盘")
        for row in period_table:
            lines.append(
                f"  {row['label']:<7} {row['direction']:<8} "
                f"{row['support']:>10.2f} {row['resistance']:>10.2f} "
                f"{row['atr']:>8.2f}  {row.get('bar_time', '')}"
            )
    
    # 摩擦成本分析
    friction = analysis.get('friction', {})
    if friction:
        lines.append(f"\n{'='*70}")
        lines.append("【摩擦成本分析】")
        lines.append(f"  每盎司成本: ${friction.get('total_cost_per_oz', 0):.2f}")
        lines.append(f"  固定费用: ${friction.get('fixed_cost', 0):.2f}")
        lines.append(f"  费率费用: ${friction.get('rate_cost', 0):.2f}")
        lines.append(f"  滑点成本: ${friction.get('slippage_cost', 0):.2f}")
        
        period_friction = friction.get('period_friction', {})
        if period_friction:
            lines.append(f"\n  各周期摩擦占比:")
            lines.append(f"  {'周期':<8} {'ATR':>8} {'成本':>8} {'摩擦占比':>10} {'适用性':>8}")
            for period_name, info in period_friction.items():
                color = info.get('color', 'green')
                emoji = {'green': '✅', 'yellow': '⚠️', 'red': '❌'}.get(color, '⚪')
                lines.append(
                    f"  {period_name:<8} {info['atr']:>8.2f} {info['cost_per_oz']:>8.2f} "
                    f"{info['friction_pct']:>9.1f}% {emoji}{info['suitability']:>6}"
                )
        
        recommendation = friction.get('recommendation', '')
        if recommendation:
            lines.append(f"\n  💡 建议: {recommendation}")
        
        suitable = friction.get('suitable_periods', [])
        marginal = friction.get('marginal_periods', [])
        unsuitable = friction.get('unsuitable_periods', [])
        if suitable:
            lines.append(f"  ✅ 适合交易: {', '.join(suitable)}")
        if marginal:
            lines.append(f"  ⚠️ 勉强可行: {', '.join(marginal)}")
        if unsuitable:
            lines.append(f"  ❌ 不适合: {', '.join(unsuitable)}")
    
    # 操作建议（三要素）
    lines.append(f"\n{'='*70}")
    lines.append("【操作建议】")
    
    rec = signals.get('recommendation', {})
    if rec:
        lines.append(f"  状态: {rec.get('status_code', 'N/A')}")
        lines.append(f"  操作: {rec.get('action', 'N/A')}")
        lines.append(f"  策略: {rec.get('strategy', 'N/A')}")
        lines.append(f"  入场: {rec.get('entry', 'N/A')}")
        lines.append(f"  仓位: {rec.get('position', 'N/A')}")
        lines.append(f"  止损: {rec.get('stop_loss', 'N/A')}")
        lines.append(f"  目标: {rec.get('target', 'N/A')}")
        lines.append(f"  条件: {rec.get('condition', 'N/A')}")
        lines.append(f"  下次确认: {rec.get('next_watch', 'N/A')}")
        lines.append(f"  成本: {rec.get('cost_note', 'N/A')}")
        if rec.get('net_rr') is not None:
            lines.append(
                f"  净收益/风险: ${rec.get('reward_net_usd', 0):.2f} / "
                f"${rec.get('risk_net_usd', 0):.2f}，RR={rec['net_rr']:.2f}"
            )
    else:
        lines.append("  暂无明确建议")
    
    lines.append(f"\n{'='*70}")
    lines.append("⚠️ 以上分析仅供参考，不构成投资建议。市场有风险，投资需谨慎。")
    lines.append("=" * 70)
    
    return '\n'.join(lines)
