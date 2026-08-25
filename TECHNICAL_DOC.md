# 黄金综合分析系统 v3.1 - 技术文档

## 系统概述

基于三体系框架的黄金投资分析系统，整合技术面、基本面、资金面三大维度，辅以地缘政治监控，提供多维度量化评分和交易信号。

---

## 核心架构

### 三体系评分框架

```
综合得分 = 技术面(40%) + 基本面(35%) + 资金面(25%) + 地缘政治加分
```

- **技术面**：多周期分层（趋势40% + 波段40% + 日内20%）
- **基本面**：历史分位数 + 边际变化
- **资金面**：CFTC持仓 + ETF流向 + 央行购金
- **地缘政治**：风险事件监控，动态调整权重

---

## 功能模块详解

### 1. 数据获取模块 (`data_fetcher.py`)

#### 1.1 实时行情数据
**功能**：获取黄金、白银、原油、美元指数实时价格

**实现逻辑**：
```python
# 数据源：新浪财经API
URL = "https://hq.sinajs.cn/list=hf_XAU,hf_SI,hf_CL,DINIW"

# 返回字段：
# - 现价、开盘价、最高价、最低价
# - 前收盘价、买价、卖价
# - 更新时间
```

**关键函数**：
- `get_all_realtime()` → 返回所有资产实时数据
- `get_gold_klines()` → 返回多周期K线数据（5分钟/15分钟/1小时/4小时/日线）

#### 1.2 K线数据
**功能**：获取多周期历史K线数据

**实现逻辑**：
```python
# 数据源：新浪财经K线API
# 周期：5分钟、15分钟、1小时、4小时、日线
# 数据量：每个周期约200根K线

# 返回格式：
{
    '5min': [{'time': '...', 'open': ..., 'high': ..., 'low': ..., 'close': ...}, ...],
    '15min': [...],
    '1hour': [...],
    '4hour': [...],
    'daily': [...]
}
```

#### 1.3 宏观经济数据
**功能**：获取FRED宏观经济指标

**实现逻辑**：
```python
# 数据源：FRED API (CSV格式)
# 指标列表：
INDICATORS = {
    'real_rate': 'REAINTRATREAR01YE',      # 实际利率
    'us10y': 'DGS10',                       # 10年期国债收益率
    'inflation_expect': 'T5YIE',           # 通胀预期
    'fed_rate': 'FEDFUNDS',                # 联邦基金利率
    'vix': 'VIXCLS',                       # VIX恐慌指数
    'unemployment_rate': 'UNRATE',         # 失业率
    'cpi_yoy': 'CPIAUCSL',                 # CPI同比
    'core_pce_yoy': 'PCEPILFE',            # 核心PCE
    'gdp_growth': 'A191RL1Q225SBEA',       # GDP增速
    'dxy': 'DTWEXBGS',                     # 美元指数
    'nonfarm_payrolls': 'PAYEMS',          # 非农就业
    'retail_sales': 'RSAFS',               # 零售销售
    'ism_pmi': 'ISM',                      # ISM制造业PMI
    'consumer_sentiment': 'UMCSENT',       # 消费者信心指数
    'housing_starts': 'HOUST',             # 新屋开工
    'industrial_production': 'INDPRO'      # 工业生产
}

# 数据获取：
# 1. 构建FRED CSV URL
# 2. 下载最近90天数据
# 3. 解析CSV，取最新值
# 4. 计算同比/环比变化
```

#### 1.4 CFTC持仓数据
**功能**：获取COMEX黄金期货持仓报告

**实现逻辑**：
```python
# 数据源：CFTC每周持仓报告
URL = "https://www.cftc.gov/dea/newcot/deafut.txt"

# 解析逻辑：
# 1. 下载文本文件（固定宽度格式）
# 2. 定位"GOLD, COMEX"行
# 3. 提取字段：
#    - 管理资金多头 (Noncommercial Long)
#    - 管理资金空头 (Noncommercial Short)
#    - 管理资金净头寸 (Net Position)
#    - 商业多头/空头
#    - 未平仓合约数

# 返回格式：
{
    'noncommercial_long': 284711,
    'noncommercial_short': 135353,
    'net_long': 149358,
    'open_interest': 487654,
    'report_date': '2024-01-15'
}
```

#### 1.5 ETF持仓数据
**功能**：获取SPDR GLD黄金ETF资产规模

**实现逻辑**：
```python
# 数据源：SSGA官网
URL = "https://www.ssga.com/us/en/individual/etfs/funds/spdr-gold-shares-gld"

# 解析逻辑：
# 1. 请求HTML页面
# 2. 正则匹配"AUM"或"Net Assets"
# 3. 提取数值（单位：十亿美元）

# 返回：
{
    'aum': 157.33,  # 十亿美元
    'update_date': '2024-01-15'
}
```

#### 1.6 央行购金数据
**功能**：获取世界黄金协会央行购金数据

**实现逻辑**：
```python
# 数据源：世界黄金协会CSV
URL = "https://www.gold.org/goldhub/data/world-official-sector-gold-holdings-quarterly"

# 解析逻辑：
# 1. 下载季度CSV数据
# 2. 按国家分组统计
# 3. 计算季度净购买量
# 4. 识别主要买家（中国、印度、土耳其等）

# 返回：
{
    'quarter': '2024-Q3',
    'total_tonnes': 186,
    'top_buyers': [
        {'country': 'Poland', 'tonnes': 19},
        {'country': 'Turkey', 'tonnes': 16},
        {'country': 'India', 'tonnes': 14}
    ]
}
```

---

### 2. 技术分析模块 (`analyzer.py`)

#### 2.1 技术指标计算 (`indicators.py`)

**功能**：计算各类技术指标

**实现逻辑**：

##### 移动平均线 (MA)
```python
def calc_ma(prices, period):
    """
    简单移动平均线
    MA(N) = (P1 + P2 + ... + PN) / N
    """
    return [sum(prices[i:i+period]) / period for i in range(len(prices) - period + 1)]
```

##### 指数移动平均线 (EMA)
```python
def calc_ema(prices, period):
    """
    指数移动平均线
    EMA(t) = Price(t) * k + EMA(t-1) * (1-k)
    k = 2 / (N + 1)
    """
    k = 2 / (period + 1)
    ema = [prices[0]]
    for price in prices[1:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema
```

##### RSI (相对强弱指数)
```python
def calc_rsi(prices, period=14):
    """
    RSI = 100 - 100 / (1 + RS)
    RS = 平均上涨幅度 / 平均下跌幅度
    """
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi = 100 - 100 / (1 + rs)
    return rsi
```

##### MACD (指数平滑异同移动平均线)
```python
def calc_macd(prices, fast=12, slow=26, signal=9):
    """
    DIF = EMA(fast) - EMA(slow)
    DEA = EMA(DIF, signal)
    MACD柱 = 2 * (DIF - DEA)
    """
    ema_fast = calc_ema(prices, fast)
    ema_slow = calc_ema(prices, slow)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    dea = calc_ema(dif, signal)
    macd_hist = [2 * (d - e) for d, e in zip(dif, dea)]
    return dif[-1], dea[-1], macd_hist[-1]
```

##### 布林带 (Bollinger Bands)
```python
def calc_bollinger(prices, period=20, std_dev=2):
    """
    中轨 = MA(N)
    上轨 = 中轨 + K * 标准差
    下轨 = 中轨 - K * 标准差
    """
    ma = sum(prices[-period:]) / period
    std = (sum((p - ma)**2 for p in prices[-period:]) / period) ** 0.5
    upper = ma + std_dev * std
    lower = ma - std_dev * std
    return upper, ma, lower
```

##### KDJ (随机指标)
```python
def calc_kdj(highs, lows, closes, n=9, m1=3, m2=3):
    """
    RSV = (C - L) / (H - L) * 100
    K = SMA(RSV, m1)
    D = SMA(K, m2)
    J = 3K - 2D
    """
    rsv_list = []
    for i in range(len(closes) - n + 1):
        h = max(highs[i:i+n])
        l = min(lows[i:i+n])
        c = closes[i+n-1]
        rsv = (c - l) / (h - l) * 100 if h != l else 50
        rsv_list.append(rsv)
    
    k, d = 50, 50
    for rsv in rsv_list:
        k = (m1 - 1) / m1 * k + 1 / m1 * rsv
        d = (m2 - 1) / m2 * d + 1 / m2 * k
    j = 3 * k - 2 * d
    return k, d, j
```

##### ATR (平均真实波幅)
```python
def calc_atr(highs, lows, closes, period=14):
    """
    TR = max(H-L, |H-C(t-1)|, |L-C(t-1)|)
    ATR = MA(TR, N)
    """
    tr_list = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)
    atr = sum(tr_list[-period:]) / period
    return atr
```

##### 斐波那契回撤
```python
def calc_fibonacci(high, low):
    """
    计算斐波那契回撤位
    0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%
    """
    levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    diff = high - low
    return [low + diff * level for level in levels]
```

#### 2.2 多周期分层分析

**功能**：将技术面分为趋势层、波段层、日内层

**实现逻辑**：
```python
def analyze_multi_timeframe_v2(klines):
    """
    三层分析框架：
    - 趋势层 (Trend): 日线，权重40%
    - 波段层 (Swing): 1小时+4小时，权重40%
    - 日内层 (Intraday): 5分钟+15分钟，权重20%
    """
    layers = {
        'Trend': {
            'timeframes': ['daily'],
            'weight': 0.4,
            'indicators': ['MA20/60/120', 'MACD', 'RSI']
        },
        'Swing': {
            'timeframes': ['1hour', '4hour'],
            'weight': 0.4,
            'indicators': ['MA20/60', 'MACD', 'RSI', 'KDJ']
        },
        'Intraday': {
            'timeframes': ['5min', '15min'],
            'weight': 0.2,
            'indicators': ['MA20', 'MACD', 'RSI', 'KDJ', 'ATR']
        }
    }
    
    layer_scores = {}
    layer_directions = {}
    
    for layer_name, config in layers.items():
        scores = []
        for tf in config['timeframes']:
            kline_data = klines.get(tf, [])
            if not kline_data:
                continue
            
            # 计算该周期技术指标
            indicators = calc_all_indicators(kline_data)
            
            # 逐项评分
            tf_score = 0
            
            # MA排列评分
            ma_score = score_ma_alignment(indicators['ma'])
            tf_score += ma_score
            
            # MACD评分
            macd_score = score_macd(indicators['macd'])
            tf_score += macd_score
            
            # RSI评分
            rsi_score = score_rsi(indicators['rsi'])
            tf_score += rsi_score
            
            # KDJ评分（仅Swing和Intraday）
            if layer_name != 'Trend':
                kdj_score = score_kdj(indicators['kdj'])
                tf_score += kdj_score
            
            scores.append(tf_score)
        
        # 层内平均
        avg_score = sum(scores) / len(scores) if scores else 0
        layer_scores[layer_name] = avg_score
        
        # 判断方向
        if avg_score >= 0.5:
            layer_directions[layer_name] = 'bullish'
        elif avg_score <= -0.5:
            layer_directions[layer_name] = 'bearish'
        else:
            layer_directions[layer_name] = 'neutral'
    
    # 加权综合
    total_score = sum(
        layer_scores[name] * config['weight']
        for name, config in layers.items()
    )
    
    return {
        'combined_score': total_score,
        'layer_scores': layer_scores,
        'layer_directions': layer_directions,
        'agreement': calculate_agreement(layer_directions),
        'confidence': calculate_confidence(layer_scores)
    }
```

#### 2.3 道氏理论趋势分析

**功能**：基于MA20/60/120判断趋势阶段

**实现逻辑**：
```python
def analyze_dow_trend(klines):
    """
    道氏理论三阶段：
    1. 积累阶段：MA20上穿MA60，价格在MA20上方
    2. 公众参与阶段：MA60上穿MA120，三线多头排列
    3. 派发阶段：MA20下穿MA60，价格跌破MA60
    """
    ma20 = indicators['ma20']
    ma60 = indicators['ma60']
    ma120 = indicators['ma120']
    price = klines[-1]['close']
    
    # 判断排列
    if ma20 > ma60 > ma120 and price > ma20:
        return '多头排列', '公众参与阶段（强势上涨）'
    elif ma20 > ma60 and price > ma20:
        return '上升趋势', '积累阶段（初期上涨）'
    elif ma20 < ma60 < ma120 and price < ma20:
        return '空头排列', '派发阶段（强势下跌）'
    elif ma20 < ma60 and price < ma20:
        return '下降趋势', '积累阶段（初期下跌）'
    else:
        return '横盘整理', '震荡区间'
```

#### 2.4 量价分析

**功能**：分析成交量与价格的配合关系

**实现逻辑**：
```python
def analyze_volume_price(klines):
    """
    量价关系判断：
    - 价涨量增：健康上涨
    - 价涨量缩：上涨乏力
    - 价跌量增：恐慌抛售
    - 价跌量缩：下跌动能减弱
    """
    price_change = klines[-1]['close'] - klines[-2]['close']
    volume_change = klines[-1]['volume'] - klines[-2]['volume']
    
    if price_change > 0 and volume_change > 0:
        return '价涨量增', 1.0, '健康上涨，多头强势'
    elif price_change > 0 and volume_change < 0:
        return '价涨量缩', 0.5, '上涨乏力，警惕回调'
    elif price_change < 0 and volume_change > 0:
        return '价跌量增', -1.0, '恐慌抛售，空头强势'
    elif price_change < 0 and volume_change < 0:
        return '价跌量缩', -0.5, '下跌动能减弱，可能企稳'
    else:
        return '量价平稳', 0.0, '无明显信号'
```

---

### 3. 基本面分析模块 (`fundamental_analyzer.py`)

#### 3.1 实际利率评分

**功能**：评估实际利率对黄金的影响

**实现逻辑**：
```python
def analyze_real_rate(macro_data):
    """
    实际利率 = 名义利率 - 通胀预期
    使用历史分位数而非固定阈值
    
    历史范围（2020-2024）：-1.5% ~ 2.5%
    """
    real_rate = macro_data['real_rate']['value']
    
    # 计算分位数
    historical_range = (-1.5, 2.5)
    percentile = (real_rate - historical_range[0]) / (historical_range[1] - historical_range[0])
    
    if percentile < 0.2:  # 极低（< -0.7%）
        return 2.0, '强烈看多'
    elif percentile < 0.4:  # 偏低
        return 1.0, '看多'
    elif percentile < 0.6:  # 中性
        return 0.0, '中性'
    elif percentile < 0.8:  # 偏高
        return -1.0, '看空'
    else:  # 极高（> 1.7%）
        return -2.0, '强烈看空'
```

#### 3.2 美元指数评分

**功能**：评估美元走势对黄金的影响

**实现逻辑**：
```python
def analyze_dxy(macro_data):
    """
    美元与黄金负相关
    历史范围（2020-2024）：89 ~ 114
    
    同时考虑边际变化（5日变化）
    """
    dxy = macro_data['dxy']['value']
    dxy_5d_change = macro_data['dxy'].get('5d_change', 0)
    
    # 绝对水平评分
    historical_range = (89, 114)
    percentile = (dxy - historical_range[0]) / (historical_range[1] - historical_range[0])
    
    if percentile < 0.2:  # 极弱（< 94）
        score = 2.0
    elif percentile < 0.4:  # 偏弱
        score = 1.0
    elif percentile < 0.6:  # 中性
        score = 0.0
    elif percentile < 0.8:  # 偏强
        score = -1.0
    else:  # 极强（> 109）
        score = -2.0
    
    # 边际调整（5日变化）
    if dxy_5d_change < -1.0:  # 美元急跌
        score += 0.5
    elif dxy_5d_change > 1.0:  # 美元急涨
        score -= 0.5
    
    return score, '看多' if score > 0 else ('看空' if score < 0 else '中性')
```

#### 3.3 通胀评分

**功能**：评估通胀对黄金的影响

**实现逻辑**：
```python
def analyze_inflation(macro_data):
    """
    使用核心PCE偏离美联储2%目标的程度
    避免CPI和PCE重复计算
    """
    core_pce = macro_data['core_pce_yoy']['value']
    target = 2.0
    
    deviation = core_pce - target
    
    if deviation > 2.0:  # 严重超标（> 4%）
        return 2.0, '强烈看多'
    elif deviation > 1.0:  # 偏高（3-4%）
        return 1.0, '看多'
    elif deviation > 0:  # 略高（2-3%）
        return 0.5, '温和看多'
    elif deviation > -0.5:  # 接近目标（1.5-2%）
        return 0.0, '中性'
    else:  # 低于目标（< 1.5%）
        return -0.5, '温和看空'
```

#### 3.4 VIX恐慌指数评分

**功能**：评估市场恐慌情绪对黄金的影响

**实现逻辑**：
```python
def analyze_vix(macro_data):
    """
    VIX与黄金正相关（避险需求）
    历史范围：12 ~ 35
    """
    vix = macro_data['vix']['value']
    
    historical_range = (12, 35)
    percentile = (vix - historical_range[0]) / (historical_range[1] - historical_range[0])
    
    if percentile > 0.8:  # 极高恐慌（> 30）
        return 2.0, '强烈看多'
    elif percentile > 0.6:  # 高恐慌（25-30）
        return 1.0, '看多'
    elif percentile > 0.4:  # 中性偏高（20-25）
        return 0.5, '温和看多'
    elif percentile > 0.2:  # 中性偏低（15-20）
        return 0.0, '中性'
    else:  # 低恐慌（< 15）
        return -0.5, '温和看空'
```

#### 3.5 就业市场评分

**功能**：评估就业数据对黄金的影响

**实现逻辑**：
```python
def analyze_employment(macro_data):
    """
    失业率上升 → 经济衰退担忧 → 看多黄金
    同时考虑非农就业边际变化
    """
    unemployment = macro_data['unemployment_rate']['value']
    nonfarm_change = macro_data['nonfarm_payrolls'].get('1m_change', 0)
    
    # 失业率评分
    if unemployment > 5.0:  # 高失业率
        score = 1.5
    elif unemployment > 4.0:
        score = 0.5
    elif unemployment > 3.5:
        score = 0.0
    else:  # 低失业率
        score = -0.5
    
    # 非农边际调整
    if nonfarm_change < -100:  # 非农大幅减少（千人）
        score += 0.5
    elif nonfarm_change > 200:  # 非农大幅增加
        score -= 0.5
    
    return score, '看多' if score > 0 else ('看空' if score < 0 else '中性')
```

---

### 4. 资金面分析模块 (`sentiment_analyzer.py`)

#### 4.1 CFTC持仓分析

**功能**：评估期货持仓对黄金的影响

**实现逻辑**：
```python
def analyze_cftc_positions(cftc_data):
    """
    净多头占比 = 净多头 / 未平仓合约
    使用百分比而非绝对值，避免合约规模变化影响
    """
    net_long = cftc_data['net_long']
    open_interest = cftc_data['open_interest']
    
    net_pct = net_long / open_interest if open_interest > 0 else 0
    
    if net_pct > 0.3:  # 极度超买（> 30%）
        return 2.0, '强烈看多'
    elif net_pct > 0.15:  # 超买
        return 1.0, '看多'
    elif net_pct > -0.15:  # 中性
        return 0.0, '中性'
    elif net_pct > -0.3:  # 超卖
        return -1.0, '看空'
    else:  # 极度超卖（< -30%）
        return -2.0, '强烈看空'
```

#### 4.2 ETF持仓分析

**功能**：评估ETF资金流向对黄金的影响

**实现逻辑**：
```python
def analyze_etf_flows(etf_data):
    """
    GLD AUM规模判断
    > 150B：机构强烈配置
    100-150B：机构配置增加
    50-100B：中性
    < 50B：机构配置减少
    """
    aum = etf_data['aum']
    
    if aum > 150:
        return 2.0, '强烈看多'
    elif aum > 100:
        return 1.0, '看多'
    elif aum > 50:
        return 0.0, '中性'
    else:
        return -1.0, '看空'
```

#### 4.3 央行购金分析

**功能**：评估央行购金对黄金的影响

**实现逻辑**：
```python
def analyze_central_bank_purchases(cb_data):
    """
    季度购金量评分：
    > 300吨：强烈看多
    200-300吨：看多
    100-200吨：中性偏多
    50-100吨：中性
    < 50吨：中性偏空
    """
    tonnes = cb_data['total_tonnes']
    
    if tonnes > 300:
        return 2.0, '强烈看多'
    elif tonnes > 200:
        return 1.5, '看多'
    elif tonnes > 100:
        return 0.5, '温和看多'
    elif tonnes > 50:
        return 0.0, '中性'
    else:
        return -0.5, '温和看空'
```

#### 4.4 金银比分析

**功能**：评估金银比对黄金的指示作用

**实现逻辑**：
```python
def analyze_gold_silver_ratio(gold_price, silver_price):
    """
    金银比 = 黄金价格 / 白银价格
    历史中位数：60-80
    > 80：黄金相对低估
    < 60：黄金相对高估
    """
    ratio = gold_price / silver_price
    
    if ratio > 85:
        return 1.0, '看多'
    elif ratio > 80:
        return 0.5, '温和看多'
    elif ratio > 60:
        return 0.0, '中性'
    elif ratio > 50:
        return -0.5, '温和看空'
    else:
        return -1.0, '看空'
```

---

### 5. 地缘政治监控模块 (`geopolitical.py`)

#### 5.1 新闻抓取

**功能**：从多个新闻源抓取地缘政治新闻

**实现逻辑**：
```python
def fetch_news():
    """
    数据源：
    1. 观察者网国际新闻
    2. 新浪国际新闻API
    
    关键词过滤：
    KEYWORDS = ['战争', '冲突', '制裁', '导弹', '军事', '地缘', 
                '俄罗斯', '乌克兰', '以色列', '巴勒斯坦', '伊朗', 
                '朝鲜', '台海', '南海', '中东', '恐怖', '核武']
    """
    news_list = []
    
    # 观察者网
    observer_news = fetch_guancha_news()
    news_list.extend(observer_news)
    
    # 新浪
    sina_news = fetch_sina_news()
    news_list.extend(sina_news)
    
    # 关键词过滤
    filtered = [n for n in news_list if match_keywords(n['title'])]
    
    return filtered
```

#### 5.2 风险评估

**功能**：评估地缘政治风险等级

**实现逻辑**：
```python
def assess_risk(news_list):
    """
    风险评分 = 新闻数量 * 0.1 + 热点地区权重
    
    热点地区权重：
    - 中东（以色列、伊朗）：1.5
    - 俄乌：1.3
    - 台海/南海：1.4
    - 朝鲜：1.2
    - 其他：1.0
    
    风险等级：
    - 0-3：低风险
    - 3-6：中风险
    - 6-8：高风险
    - 8-10：极高风险
    """
    score = len(news_list) * 0.1
    
    for news in news_list:
        for region, weight in HOTSPOTS.items():
            if region in news['title']:
                score += weight
    
    score = min(score, 10)  # 上限10
    
    if score >= 8:
        return '极高风险 🔴', score
    elif score >= 6:
        return '高风险 🟠', score
    elif score >= 3:
        return '中风险 🟡', score
    else:
        return '低风险 🟢', score
```

#### 5.3 对金价影响评分

**功能**：将地缘政治风险转化为金价影响分数

**实现逻辑**：
```python
def calculate_impact_score(risk_level, risk_score):
    """
    风险等级 → 金价影响分
    极高风险：+3.0
    高风险：+2.0
    中风险：+1.0
    低风险：0.0
    """
    if risk_score >= 8:
        return 3.0
    elif risk_score >= 6:
        return 2.0
    elif risk_score >= 3:
        return 1.0
    else:
        return 0.0
```

---

### 6. 信号引擎模块 (`analyzer.py`)

#### 6.1 方向层

**功能**：确定主交易方向

**实现逻辑**：
```python
def determine_direction(technical, fundamental, sentiment, geopolitical):
    """
    综合多周期技术方向、基本面、资金面、地缘政治
    判断主方向：bullish / bearish / neutral
    """
    # 技术面方向（多周期加权）
    trend_dir = technical['layer_directions']['趋势']
    swing_dir = technical['layer_directions']['波段']
    intraday_dir = technical['layer_directions']['日内']
    
    tech_score = (
        (1 if trend_dir == 'bullish' else -1 if trend_dir == 'bearish' else 0) * 0.4 +
        (1 if swing_dir == 'bullish' else -1 if swing_dir == 'bearish' else 0) * 0.4 +
        (1 if intraday_dir == 'bullish' else -1 if intraday_dir == 'bearish' else 0) * 0.2
    )
    
    # 基本面方向
    fund_score = fundamental['combined_score']
    fund_dir = 1 if fund_score >= 0.5 else (-1 if fund_score <= -0.5 else 0)
    
    # 资金面方向
    sent_score = sentiment['combined_score']
    sent_dir = 1 if sent_score >= 0.8 else (-1 if sent_score <= -0.8 else 0)
    
    # 地缘政治方向
    geo_impact = geopolitical.get('impact_score', 0)
    geo_dir = 1 if geo_impact >= 1.5 else 0
    
    # 综合评分
    total = tech_score * 0.4 + fund_dir * 0.3 + sent_dir * 0.2 + geo_dir * 0.1
    
    if total >= 0.3:
        return 'bullish'
    elif total <= -0.3:
        return 'bearish'
    else:
        return 'neutral'
```

#### 6.2 执行层

**功能**：生成具体交易信号

**实现逻辑**：
```python
def generate_execution_signals(klines, technical):
    """
    扫描短周期（1小时/15分钟）的交叉信号：
    - MACD金叉/死叉
    - KDJ金叉/死叉
    - RSI超买/超卖
    """
    signals = []
    
    # 1小时MACD
    h1 = klines['1hour']
    if h1:
        macd_prev = calc_macd([k['close'] for k in h1[:-1]])
        macd_curr = calc_macd([k['close'] for k in h1])
        
        if macd_prev[0] < macd_prev[1] and macd_curr[0] >= macd_curr[1]:
            signals.append({
                'type': 'BUY',
                'layer': '波段',
                'timeframe': '1小时',
                'reason': 'MACD金叉',
                'strength': '中'
            })
        elif macd_prev[0] > macd_prev[1] and macd_curr[0] <= macd_curr[1]:
            signals.append({
                'type': 'SELL',
                'layer': '波段',
                'timeframe': '1小时',
                'reason': 'MACD死叉',
                'strength': '中'
            })
    
    # 15分钟KDJ
    m15 = klines['15min']
    if m15:
        kdj = calc_kdj([k['high'] for k in m15], [k['low'] for k in m15], [k['close'] for k in m15])
        if kdj[0] < 20 and kdj[2] < 0:  # K<20且J<0，超卖
            signals.append({
                'type': 'BUY',
                'layer': '日内',
                'timeframe': '15分钟',
                'reason': 'KDJ超卖',
                'strength': '弱'
            })
        elif kdj[0] > 80 and kdj[2] > 100:  # K>80且J>100，超买
            signals.append({
                'type': 'SELL',
                'layer': '日内',
                'timeframe': '15分钟',
                'reason': 'KDJ超买',
                'strength': '弱'
            })
    
    return signals
```

#### 6.3 冲突检测

**功能**：检测信号冲突

**实现逻辑**：
```python
def detect_conflicts(execution_signals):
    """
    如果同时存在BUY和SELL信号，标记冲突
    """
    buy_signals = [s for s in execution_signals if s['type'] == 'BUY']
    sell_signals = [s for s in execution_signals if s['type'] == 'SELL']
    
    conflicts = []
    if buy_signals and sell_signals:
        conflicts.append({
            'description': f'存在{len(buy_signals)}个买入信号和{len(sell_signals)}个卖出信号冲突',
            'buy_signals': buy_signals,
            'sell_signals': sell_signals
        })
    
    return conflicts
```

#### 6.4 操作建议生成

**功能**：生成具体操作建议（入场/止损/目标）

**实现逻辑**：
```python
def generate_recommendation(direction, execution_signals, conflicts, klines):
    """
    根据主方向和执行信号生成操作建议
    包含：操作、策略、入场、仓位、止损、目标、条件
    """
    # 计算支撑位和阻力位
    daily = klines['daily']
    supports, resistances = find_support_resistance(daily)
    support_price = supports[0] if supports else None
    resistance_price = resistances[0] if resistances else None
    
    # 止损计算：支撑位下方3%
    stop_loss_price = support_price * 0.97 if support_price else None
    
    if direction == 'bullish':
        if has_conflict(conflicts):
            return {
                'action': '等待回调',
                'strategy': '主方向看多，但短周期偏空，不追多',
                'entry': f'等待回踩支撑位{support_price:.0f}' if support_price else '等待回调至支撑位',
                'position': '总风险1-2% AUM，首仓1/3',
                'stop_loss': f'跌破{stop_loss_price:.0f}止损（支撑位下方3%）' if stop_loss_price else '跌破关键支撑止损',
                'target': f'上看阻力位{resistance_price:.0f}' if resistance_price else '上看阻力位',
                'condition': '短周期转多确认后入场'
            }
        else:
            return {
                'action': '逢低做多',
                'strategy': '多周期共振看多，可积极入场',
                'entry': f'回调至{support_price:.0f}附近' if support_price else '回调至支撑位',
                'position': '总风险2-3% AUM，可分2-3批建仓',
                'stop_loss': f'跌破{stop_loss_price:.0f}止损（支撑位下方3%）' if stop_loss_price else '跌破关键支撑止损',
                'target': f'目标{resistance_price:.0f}' if resistance_price else '上看阻力位',
                'condition': '直接入场或小幅回调后入场'
            }
    
    elif direction == 'bearish':
        stop_loss_price_short = resistance_price * 1.03 if resistance_price else None
        if has_conflict(conflicts):
            return {
                'action': '观望或轻仓试空',
                'strategy': '主方向看空，但短周期偏多，谨慎操作',
                'entry': f'反弹至{resistance_price:.0f}附近' if resistance_price else '反弹至阻力位',
                'position': '总风险1% AUM，轻仓试空',
                'stop_loss': f'突破{stop_loss_price_short:.0f}止损（阻力位上方3%）' if stop_loss_price_short else '突破关键阻力止损',
                'target': f'下看{support_price:.0f}' if support_price else '下看支撑位',
                'condition': '短周期转空确认后入场'
            }
        else:
            return {
                'action': '逢高做空',
                'strategy': '多周期共振看空，可积极入场',
                'entry': f'反弹至{resistance_price:.0f}附近' if resistance_price else '反弹至阻力位',
                'position': '总风险2-3% AUM，可分2-3批建仓',
                'stop_loss': f'突破{stop_loss_price_short:.0f}止损（阻力位上方3%）' if stop_loss_price_short else '突破关键阻力止损',
                'target': f'目标{support_price:.0f}' if support_price else '下看支撑位',
                'condition': '直接入场或小幅反弹后入场'
            }
    
    else:  # neutral
        return {
            'action': '观望',
            'strategy': '方向不明确，建议观望等待明确信号',
            'entry': '等待方向明确',
            'position': '暂不建仓',
            'stop_loss': 'N/A',
            'target': 'N/A',
            'condition': '等待技术面或基本面出现明确方向'
        }
```

---

### 7. 相关性验证模块 (`correlation_analysis.py`)

#### 7.1 滚动相关性计算

**功能**：计算黄金与其他资产的滚动相关性

**实现逻辑**：
```python
def calculate_rolling_correlation(x, y, window=60):
    """
    使用60日滚动窗口计算动态相关性
    避免固定阈值，使用历史分位数判断
    """
    if len(x) != len(y) or len(x) < window:
        return None
    
    correlations = []
    for i in range(window, len(x)):
        x_window = x[i-window:i]
        y_window = y[i-window:i]
        
        corr = np.corrcoef(x_window, y_window)[0, 1]
        correlations.append(corr)
    
    # 计算统计指标
    current_corr = correlations[-1]
    avg_corr = np.mean(correlations)
    std_corr = np.std(correlations)
    
    # 判断是否异常（超过2倍标准差）
    is_anomaly = abs(current_corr - avg_corr) > 2 * std_corr
    
    return {
        'current': current_corr,
        'average': avg_corr,
        'std': std_corr,
        'is_anomaly': is_anomaly,
        'history': correlations
    }
```

#### 7.2 相关性验证

**功能**：验证技术指标与价格的相关性

**实现逻辑**：
```python
def validate_indicator_with_rolling(indicator_values, prices, window=60):
    """
    验证技术指标（如RSI、MACD）与价格的相关性
    判断指标是否失效
    """
    result = calculate_rolling_correlation(indicator_values, prices, window)
    
    if result:
        # 如果当前相关性显著偏离历史均值，指标可能失效
        if result['is_anomaly']:
            return '指标可能失效', result
        else:
            return '指标有效', result
    
    return '数据不足', None
```

---

### 8. GUI界面模块 (`gui.py`)

#### 8.1 界面布局

**功能**：提供图形化操作界面

**实现逻辑**：
```python
# 使用tkinter构建
# 10个Tab页：
# 1. 实时行情
# 2. 综合报告
# 3. 信号面板（新增）
# 4. 基本面
# 5. 资金面
# 6. 地缘政治
# 7. 相关性验证
# 8. 经济日历
# 9. 价格提醒
# 10. 邮件配置

# 顶部控制栏：
# - 立即分析按钮（防重复点击）
# - 启动定时按钮
# - 停止定时按钮
# - HTML报告按钮
# - 间隔设置
# - 状态显示
```

#### 8.2 信号面板

**功能**：分层显示方向层、执行层、操作建议

**实现逻辑**：
```python
def update_signal_display(self, analysis):
    """
    信号面板显示：
    1. 方向层：主方向 + 各层状态
    2. 执行层：具体交易信号
    3. 冲突警告
    4. 操作建议（入场/止损/目标）
    """
    signals = analysis['signals']
    
    # 方向层
    direction = signals['direction']
    layer_scores = analysis['technical']['layer_scores']
    layer_dirs = analysis['technical']['layer_directions']
    
    # 执行层
    execution = signals['execution']
    
    # 冲突
    conflicts = signals['conflicts']
    
    # 操作建议
    rec = signals['recommendation']
    
    # 格式化显示
    display_text = f"""
方向层
  主方向: {direction}
  趋势层: {layer_dirs['趋势']} ({layer_scores['趋势']:+.2f})
  波段层: {layer_dirs['波段']} ({layer_scores['波段']:+.2f})
  日内层: {layer_dirs['日内']} ({layer_scores['日内']:+.2f})

执行层 ({len(execution)}个信号)
"""
    for sig in execution:
        display_text += f"  {sig['type']} [{sig['layer']}-{sig['timeframe']}] {sig['reason']}\n"
    
    if conflicts:
        display_text += f"\n⚠️ 冲突警告\n"
        for c in conflicts:
            display_text += f"  {c['description']}\n"
    
    display_text += f"""
操作建议
  操作: {rec['action']}
  策略: {rec['strategy']}
  入场: {rec['entry']}
  仓位: {rec['position']}
  止损: {rec['stop_loss']}
  目标: {rec['target']}
  条件: {rec['condition']}
"""
    
    self.signal_text.delete(1.0, tk.END)
    self.signal_text.insert(tk.END, display_text)
```

#### 8.3 防重复点击

**功能**：防止分析过程中重复点击

**实现逻辑**：
```python
def run_analysis(self):
    if self.analyzing:
        self.log("分析正在进行中，请稍候...")
        return
    
    self.analyzing = True
    self.btn_analyze.config(state=tk.DISABLED)  # 禁用按钮
    
    try:
        # 执行分析
        ...
    finally:
        self.analyzing = False
        self.btn_analyze.config(state=tk.NORMAL)  # 恢复按钮
```

---

### 9. 邮件通知模块 (`notifier.py`)

#### 9.1 邮件发送

**功能**：发送分析报告和价格提醒

**实现逻辑**：
```python
def send_email(subject, body, config):
    """
    使用SMTP发送邮件
    支持QQ邮箱、163邮箱等
    """
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = config['from']
    msg['To'] = ', '.join(config['to'])
    
    try:
        if config['ssl']:
            server = smtplib.SMTP_SSL(config['server'], config['port'])
        else:
            server = smtplib.SMTP(config['server'], config['port'])
            server.starttls()
        
        server.login(config['user'], config['password'])
        server.sendmail(config['from'], config['to'], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False
```

---

### 10. 价格提醒模块 (`alerts.py`)

#### 10.1 提醒规则

**功能**：设置价格突破/跌破提醒

**实现逻辑**：
```python
class AlertManager:
    def __init__(self):
        self.alerts = []
    
    def add_alert(self, name, condition, threshold):
        """
        添加提醒规则
        condition: 'above' / 'below' / 'change_pct'
        """
        self.alerts.append({
            'name': name,
            'condition': condition,
            'threshold': threshold,
            'triggered': False
        })
    
    def check_price(self, current_price):
        """
        检查价格是否触发提醒
        """
        triggered = []
        for alert in self.alerts:
            if alert['condition'] == 'above' and current_price > alert['threshold']:
                if not alert['triggered']:
                    triggered.append(alert)
                    alert['triggered'] = True
            elif alert['condition'] == 'below' and current_price < alert['threshold']:
                if not alert['triggered']:
                    triggered.append(alert)
                    alert['triggered'] = True
        
        return triggered
```

---

## 配置文件

### config/weights.json
```json
{
  "technical": 0.40,
  "fundamental": 0.35,
  "sentiment": 0.25,
  "geopolitical_bonus": 0.30
}
```

### config/email.ini
```ini
[smtp]
server = smtp.qq.com
port = 465
user = your_email@qq.com
password = your_auth_code
ssl = true
recipients = recipient1@example.com,recipient2@example.com
```

### config/alerts.json
```json
[
  {"name": "金价突破3500", "condition": "above", "threshold": 3500},
  {"name": "金价跌破3000", "condition": "below", "threshold": 3000}
]
```

---

## 数据流

```
1. 数据获取层
   ├─ 实时行情 (Sina)
   ├─ K线数据 (Sina)
   ├─ 宏观数据 (FRED)
   ├─ CFTC持仓 (CFTC)
   ├─ ETF持仓 (SSGA)
   ├─ 央行购金 (WGC)
   └─ 地缘新闻 (观察者网/新浪)

2. 分析层
   ├─ 技术分析 (多周期分层)
   ├─ 基本面分析 (分位数+边际)
   ├─ 资金面分析 (CFTC+ETF+央行)
   ├─ 地缘政治评估 (新闻+风险)
   └─ 相关性验证 (滚动窗口)

3. 信号层
   ├─ 方向层 (综合判断)
   ├─ 执行层 (交叉信号)
   ├─ 冲突检测
   └─ 操作建议 (入场/止损/目标)

4. 输出层
   ├─ GUI显示 (10个Tab)
   ├─ HTML报告 (图表+文本)
   ├─ 邮件通知 (报告+提醒)
   └─ 日志记录 (运行日志+错误日志)
```

---

## 系统依赖

```
Python 3.8+
- requests (HTTP请求)
- pandas (数据处理)
- numpy (数值计算)
- matplotlib (图表生成)
- beautifulsoup4 (HTML解析)
- lxml (XML解析)
- tkinter (GUI，Python内置)
- smtplib (邮件发送，Python内置)
```

---

## 性能指标

- **数据获取**：约10-15秒（取决于网络）
- **分析计算**：约2-3秒
- **总耗时**：约15-20秒
- **内存占用**：约100-150MB
- **CPU占用**：分析时约20-30%

---

## 扩展性

### 可扩展模块
1. **数据源**：可添加更多数据源（如Bloomberg、Reuters）
2. **技术指标**：可添加更多指标（如Ichimoku、Williams %R）
3. **分析维度**：可添加季节性分析、周期分析
4. **输出格式**：可添加PDF报告、Excel导出
5. **通知渠道**：可添加微信、钉钉、短信通知

### 优化方向
1. **性能优化**：使用异步IO加速数据获取
2. **缓存机制**：缓存历史数据，减少重复请求
3. **机器学习**：引入ML模型预测价格走势
4. **回测系统**：添加历史回测功能
5. **风险管理**：添加VaR、最大回撤等风险指标

---

## 版本历史

- **v3.1** (2024-08-25)
  - 新增信号面板Tab
  - 修复入场/止损价格相同问题
  - 添加防重复点击功能
  - 修复HTML报告信号格式兼容性

- **v3.0** (2024-08-25)
  - 重构为三体系框架
  - 多周期分层分析
  - 信号引擎分层（方向层+执行层）
  - 相关性模块使用滚动窗口
  - 基本面使用历史分位数

- **v2.0** (2024-08-24)
  - 添加地缘政治监控
  - 添加经济日历
  - 添加HTML报告
  - 添加邮件通知

- **v1.0** (2024-08-23)
  - 基础技术分析
  - 基本面分析
  - GUI界面

---

## 免责声明

本系统仅供学习和研究使用，不构成任何投资建议。投资有风险，入市需谨慎。使用者需自行承担投资风险，系统开发者不承担任何法律责任。

---

**文档版本**：v3.1  
**最后更新**：2024-08-25  
**维护者**：OpenClaw AI Assistant
