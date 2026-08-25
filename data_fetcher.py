#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据获取模块 v2.0
三套体系数据源：
- 实时行情: 新浪 (伦敦金/美元/原油/白银)
- 宏观数据: FRED (利率/通胀/VIX) + 新浪 (美元指数)
- 资金数据: CFTC持仓 + SSGA(GLD ETF)
"""

import requests
import re
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    'Referer': 'https://finance.sina.com.cn/',
    'User-Agent': 'Mozilla/5.0 GoldAnalyzer/2.0'
}

# ============================================================
# 新浪财经 - 实时行情
# ============================================================

def sina_quote(codes: List[str]) -> Dict[str, Dict]:
    """批量获取新浪实时行情"""
    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.encoding = 'gbk'
        text = resp.text
    except Exception as e:
        raise Exception(f"新浪行情请求失败: {e}")
    
    results = {}
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'var hq_str_(\w+)="(.*)";', line)
        if not m:
            continue
        code = m.group(1)
        data = m.group(2)
        if not data:
            continue
        results[code] = data
    return results


def parse_gold_quote(raw: str) -> Dict:
    """解析伦敦金行情"""
    fields = raw.split(',')
    if len(fields) < 13:
        raise Exception(f"伦敦金数据格式异常: {raw}")
    return {
        'name': '伦敦金',
        'price': float(fields[0]),
        'prev_close': float(fields[1]),
        'open': float(fields[2]) if fields[2] else 0,
        'high': float(fields[4]) if fields[4] else 0,
        'low': float(fields[5]) if fields[5] else 0,
        'time': fields[6] if len(fields) > 6 else '',
        'date': fields[12] if len(fields) > 12 else '',
    }


def parse_usd_index(raw: str) -> Dict:
    """解析美元指数"""
    fields = raw.split(',')
    if len(fields) < 10:
        raise Exception(f"美元指数格式异常: {raw}")
    return {
        'name': '美元指数',
        'price': float(fields[1]),
        'prev_close': float(fields[5]) if fields[5] else 0,
        'high': float(fields[6]) if fields[6] else 0,
        'low': float(fields[7]) if fields[7] else 0,
        'open': float(fields[8]) if fields[8] else 0,
        'time': fields[0],
        'date': fields[10] if len(fields) > 10 else '',
    }


def parse_oil_quote(raw: str) -> Dict:
    """解析纽约原油行情"""
    fields = raw.split(',')
    if len(fields) < 13:
        raise Exception(f"原油数据格式异常: {raw}")
    return {
        'name': '纽约原油',
        'price': float(fields[0]),
        'prev_close': float(fields[7]) if fields[7] else 0,
        'open': float(fields[8]) if fields[8] else 0,
        'high': float(fields[4]) if fields[4] else 0,
        'low': float(fields[5]) if fields[5] else 0,
        'time': fields[6] if fields[6] else '',
        'date': fields[12] if len(fields) > 12 else '',
    }


def parse_silver_quote(raw: str) -> Dict:
    """解析白银行情"""
    fields = raw.split(',')
    if len(fields) < 13:
        raise Exception(f"白银数据格式异常: {raw}")
    return {
        'name': '纽约白银',
        'price': float(fields[0]),
        'prev_close': float(fields[7]) if fields[7] else 0,
        'open': float(fields[8]) if fields[8] else 0,
        'high': float(fields[4]) if fields[4] else 0,
        'low': float(fields[5]) if fields[5] else 0,
        'time': fields[6] if fields[6] else '',
        'date': fields[12] if len(fields) > 12 else '',
    }


# ============================================================
# 新浪 K 线数据
# ============================================================

def sina_kline(symbol: str, ktype: int) -> List[Dict]:
    """获取新浪 K 线"""
    url = f"https://gu.sina.cn/ft/api/jsonp.php/var_{symbol}=/GlobalService.getMink?symbol={symbol}&type={ktype}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        text = resp.text
    except Exception as e:
        raise Exception(f"新浪K线请求失败: {e}")
    
    candles = []
    pattern = r'\{[^{}]+\}'
    for match in re.finditer(pattern, text):
        obj = match.group(0)
        time_m = re.search(r'"d"\s*:\s*"([^"]*)"', obj)
        open_m = re.search(r'"o"\s*:\s*"([^"]*)"', obj)
        high_m = re.search(r'"h"\s*:\s*"([^"]*)"', obj)
        low_m = re.search(r'"l"\s*:\s*"([^"]*)"', obj)
        close_m = re.search(r'"c"\s*:\s*"([^"]*)"', obj)
        
        if not all([time_m, open_m, high_m, low_m, close_m]):
            continue
        try:
            candles.append({
                'time': time_m.group(1),
                'open': float(open_m.group(1)),
                'high': float(high_m.group(1)),
                'low': float(low_m.group(1)),
                'close': float(close_m.group(1)),
            })
        except ValueError:
            continue
    
    return candles


def sina_daily_kline(symbol: str) -> List[Dict]:
    """获取新浪日线 K 线"""
    url = f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var_{symbol}_D=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={symbol}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        text = resp.text
    except Exception as e:
        raise Exception(f"新浪日线请求失败: {e}")
    
    candles = []
    pattern = r'\{[^{}]+\}'
    for match in re.finditer(pattern, text):
        obj = match.group(0)
        date_m = re.search(r'"date"\s*:\s*"([^"]*)"', obj)
        open_m = re.search(r'"open"\s*:\s*"([^"]*)"', obj)
        high_m = re.search(r'"high"\s*:\s*"([^"]*)"', obj)
        low_m = re.search(r'"low"\s*:\s*"([^"]*)"', obj)
        close_m = re.search(r'"close"\s*:\s*"([^"]*)"', obj)
        
        if not all([date_m, open_m, high_m, low_m, close_m]):
            continue
        try:
            candles.append({
                'time': date_m.group(1),
                'open': float(open_m.group(1)),
                'high': float(high_m.group(1)),
                'low': float(low_m.group(1)),
                'close': float(close_m.group(1)),
            })
        except ValueError:
            continue
    
    return candles


# ============================================================
# FRED - 宏观数据
# ============================================================

def fred_data(series_id: str, days: int = 30) -> List[Dict]:
    """获取 FRED 数据"""
    start = (datetime.now() - timedelta(days=days + 10)).strftime('%Y-%m-%d')
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        text = resp.text
    except Exception as e:
        raise Exception(f"FRED请求失败: {e}")
    
    results = []
    reader = csv.DictReader(text.strip().split('\n'))
    for row in reader:
        date = row.get('observation_date', '')
        value = row.get(series_id, '')
        if date and value and value != '.':
            try:
                results.append({
                    'date': date,
                    'value': float(value),
                    'series': series_id,
                })
            except ValueError:
                continue
    
    return results[-days:]


def fred_historical_data(series_id: str, years: int = 5) -> List[float]:
    """
    获取FRED历史数据（用于分位数计算）
    
    Args:
        series_id: FRED数据系列ID
        years: 获取多少年的历史数据，默认5年
    
    Returns:
        List[float]: 历史数值列表
    """
    days = years * 365
    start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        text = resp.text
    except Exception as e:
        logger.warning(f"FRED历史数据请求失败({series_id}): {e}")
        return []
    
    values = []
    reader = csv.DictReader(text.strip().split('\n'))
    for row in reader:
        value = row.get(series_id, '')
        if value and value != '.':
            try:
                values.append(float(value))
            except ValueError:
                continue
    
    logger.debug(f"获取{series_id}历史数据: {len(values)}条记录")
    return values


def get_macro_data() -> Dict:
    """获取宏观数据"""
    logger.info("开始获取宏观数据...")
    result = {}
    
    # 美国10Y国债收益率
    try:
        data = fred_data('DGS10', days=5)
        if data:
            result['us10y'] = data[-1]
            # 获取历史数据用于分位数计算
            result['us10y_history'] = fred_historical_data('DGS10', years=5)
            logger.debug(f"10Y国债: {data[-1]['value']:.2f}%")
    except Exception as e:
        logger.warning(f"获取10Y国债失败: {e}")
    
    # 美国10Y TIPS (实际利率)
    try:
        data = fred_data('DFII10', days=5)
        if data:
            result['real_rate'] = data[-1]
            # 获取历史数据用于分位数计算
            result['real_rate_history'] = fred_historical_data('DFII10', years=5)
            logger.debug(f"实际利率: {data[-1]['value']:.2f}%")
    except Exception as e:
        logger.warning(f"获取实际利率失败: {e}")
    
    # 10Y通胀预期
    try:
        data = fred_data('T10YIE', days=5)
        if data:
            result['inflation_expect'] = data[-1]
            logger.debug(f"通胀预期: {data[-1]['value']:.2f}%")
    except Exception as e:
        logger.warning(f"获取通胀预期失败: {e}")
    
    # VIX恐慌指数
    try:
        data = fred_data('VIXCLS', days=5)
        if data:
            result['vix'] = data[-1]
            # 获取历史数据用于分位数计算
            result['vix_history'] = fred_historical_data('VIXCLS', years=5)
            logger.debug(f"VIX: {data[-1]['value']:.2f}")
    except Exception as e:
        logger.warning(f"获取VIX失败: {e}")
    
    # 联邦基金利率
    try:
        data = fred_data('FEDFUNDS', days=30)
        if data:
            result['fed_rate'] = data[-1]
            logger.debug(f"联邦基金利率: {data[-1]['value']:.2f}%")
    except Exception as e:
        logger.warning(f"获取联邦基金利率失败: {e}")
    
    # ========== 就业数据 ==========
    # 非农就业 (千人)
    try:
        data = fred_data('PAYEMS', days=60)
        if data:
            result['nonfarm_payrolls'] = data[-1]
            if len(data) >= 2:
                result['nonfarm_change'] = data[-1]['value'] - data[-2]['value']
                logger.debug(f"非农就业变化: {result['nonfarm_change']:+.0f}K")
    except Exception as e:
        logger.warning(f"获取非农就业失败: {e}")
    
    # 失业率 (%)
    try:
        data = fred_data('UNRATE', days=60)
        if data:
            result['unemployment_rate'] = data[-1]
            logger.debug(f"失业率: {data[-1]['value']:.1f}%")
    except Exception as e:
        logger.warning(f"获取失业率失败: {e}")
    
    # 平均时薪
    try:
        data = fred_data('CES0500000003', days=60)
        if data:
            result['avg_hourly_earnings'] = data[-1]
            logger.debug(f"平均时薪: ${data[-1]['value']:.2f}")
    except Exception as e:
        logger.warning(f"获取时薪失败: {e}")
    
    # JOLTS职位空缺
    try:
        data = fred_data('JTSJOL', days=120)
        if data:
            result['jolts'] = data[-1]
            logger.debug(f"JOLTS职位空缺: {data[-1]['value']:.0f}K")
    except Exception as e:
        logger.warning(f"获取JOLTS失败: {e}")
    
    # 劳动参与率
    try:
        data = fred_data('CIVPART', days=60)
        if data:
            result['labor_force_participation'] = data[-1]
            logger.debug(f"劳动参与率: {data[-1]['value']:.1f}%")
    except Exception as e:
        logger.warning(f"获取劳动参与率失败: {e}")
    
    # ========== 通胀数据 ==========
    # CPI
    try:
        data = fred_data('CPIAUCSL', days=60)
        if data:
            result['cpi'] = data[-1]
            if len(data) >= 13:  # 12个月数据计算同比
                yoy = (data[-1]['value'] / data[-13]['value'] - 1) * 100
                result['cpi_yoy'] = {'date': data[-1]['date'], 'value': round(yoy, 2), 'series': 'CPI_YOY'}
                logger.debug(f"CPI同比: {yoy:.1f}%")
    except Exception as e:
        logger.warning(f"获取CPI失败: {e}")
    
    # PCE价格指数
    try:
        data = fred_data('PCEPI', days=60)
        if data:
            result['pce'] = data[-1]
            logger.debug(f"PCE: {data[-1]['value']:.3f}")
    except Exception as e:
        logger.warning(f"获取PCE失败: {e}")
    
    # 核心PCE
    try:
        data = fred_data('PCEPILFE', days=60)
        if data:
            result['core_pce'] = data[-1]
            if len(data) >= 13:
                yoy = (data[-1]['value'] / data[-13]['value'] - 1) * 100
                result['core_pce_yoy'] = {'date': data[-1]['date'], 'value': round(yoy, 2), 'series': 'CORE_PCE_YOY'}
                logger.debug(f"核心PCE同比: {yoy:.1f}%")
    except Exception as e:
        logger.warning(f"获取核心PCE失败: {e}")
    
    # ========== GDP数据 ==========
    # GDP增速 (季度环比年化)
    try:
        data = fred_data('A191RL1Q225SBEA', days=365)
        if data:
            result['gdp_growth'] = data[-1]
            logger.debug(f"GDP增速: {data[-1]['value']:.1f}%")
    except Exception as e:
        logger.warning(f"获取GDP增速失败: {e}")
    
    logger.info(f"宏观数据获取完成，共{len(result)}项")
    return result


# ============================================================
# CFTC 持仓数据
# ============================================================

def get_cftc_gold_positions() -> Dict:
    """获取CFTC黄金期货持仓数据（修正版）"""
    url = "https://www.cftc.gov/dea/newcot/deafut.txt"
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        text = resp.text
    except Exception as e:
        raise Exception(f"CFTC请求失败: {e}")
    
    # 查找GOLD数据行（排除MICRO GOLD）
    for line in text.split('\n'):
        if 'GOLD' in line.upper() and 'COMMODITY EXCHANGE' in line and 'MICRO' not in line:
            fields = line.split(',')
            if len(fields) >= 15:
                try:
                    # CFTC字段索引（修正版）
                    # [0] 合约名称, [2] 报告日期
                    # [7] 非商业多头, [8] 非商业空头, [9] 非商业套利
                    # [10] 商业多头, [11] 商业空头
                    # [13] 总多头, [14] 总空头
                    report_date = fields[2].strip()
                    noncommercial_long = int(fields[7].strip())
                    noncommercial_short = int(fields[8].strip())
                    noncommercial_spread = int(fields[9].strip()) if fields[9].strip() else 0
                    commercial_long = int(fields[10].strip())
                    commercial_short = int(fields[11].strip())
                    total_long = int(fields[13].strip())
                    total_short = int(fields[14].strip())
                    
                    # 计算衍生指标
                    net_position = noncommercial_long - noncommercial_short
                    long_short_ratio = noncommercial_long / noncommercial_short if noncommercial_short > 0 else 0
                    total_open_interest = total_long + total_short
                    net_position_pct = (net_position / total_open_interest * 100) if total_open_interest > 0 else 0
                    
                    return {
                        'date': report_date,
                        'noncommercial_long': noncommercial_long,
                        'noncommercial_short': noncommercial_short,
                        'noncommercial_spread': noncommercial_spread,
                        'commercial_long': commercial_long,
                        'commercial_short': commercial_short,
                        'total_long': total_long,
                        'total_short': total_short,
                        'net_position': net_position,
                        'long_short_ratio': round(long_short_ratio, 2),
                        'net_position_pct': round(net_position_pct, 2),
                        'total_open_interest': total_open_interest,
                        'source': 'CFTC'
                    }
                except (ValueError, IndexError) as e:
                    logger.warning(f"解析CFTC数据失败: {e}")
                    continue
    
    return {}


# ============================================================
# ETF 持仓数据 (GLD)
# ============================================================

def get_gld_etf_data() -> Dict:
    """获取SPDR Gold Shares ETF数据"""
    url = "https://www.ssga.com/us/en/individual/etfs/funds/spdr-gold-shares-gld"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html = response.text
        
        # 提取 NAV
        nav_match = re.search(r'NAV.*?\$([0-9,]+\.[0-9]+).*?as of ([A-Za-z]+ \d+ \d+)', html, re.DOTALL)
        nav = None
        nav_date = None
        if nav_match:
            nav = float(nav_match.group(1).replace(',', ''))
            nav_date = nav_match.group(2)
        
        # 提取 AUM
        aum_match = re.search(r'Assets Under Management.*?\$([0-9,]+\.[0-9]+)\s*M.*?as of ([A-Za-z]+ \d+ \d+)', html, re.DOTALL)
        aum = None
        aum_date = None
        if aum_match:
            aum = float(aum_match.group(1).replace(',', ''))
            aum_date = aum_match.group(2)
        
        return {
            'nav': nav,
            'nav_date': nav_date,
            'aum_million': aum,
            'aum_billion': aum / 1000 if aum else None,
            'aum_date': aum_date,
            'source': 'SSGA',
            'update_time': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取GLD ETF数据失败: {e}")
        return {}


# ============================================================
# 统一获取接口
# ============================================================

def get_all_realtime() -> Dict:
    """获取所有实时行情"""
    raw = sina_quote(['hf_XAU', 'DINIW', 'hf_CL', 'hf_SI'])
    
    result = {}
    if 'hf_XAU' in raw:
        result['gold'] = parse_gold_quote(raw['hf_XAU'])
    if 'DINIW' in raw:
        result['usd_index'] = parse_usd_index(raw['DINIW'])
    if 'hf_CL' in raw:
        result['oil'] = parse_oil_quote(raw['hf_CL'])
    if 'hf_SI' in raw:
        result['silver'] = parse_silver_quote(raw['hf_SI'])
    
    # 计算金银比
    if 'gold' in result and 'silver' in result:
        gold_price = result['gold']['price']
        silver_price = result['silver']['price']
        if silver_price > 0:
            result['gold_silver_ratio'] = gold_price / silver_price
    
    return result


def get_treasury_yields() -> Dict:
    """获取美债收益率"""
    result = {}
    for series, label in [('DGS2', '2Y'), ('DGS10', '10Y'), ('DGS30', '30Y')]:
        try:
            data = fred_data(series, days=5)
            if data:
                result[label] = data[-1]
        except Exception as e:
            logger.warning(f"获取{label}美债失败: {e}")
    return result


def get_gold_klines() -> Dict:
    """获取黄金多周期 K 线"""
    result = {}
    for label, ktype in [('5min', 5), ('15min', 15), ('1hour', 60), ('4hour', 240)]:
        try:
            candles = sina_kline('XAU', ktype)
            result[label] = candles
        except Exception as e:
            logger.warning(f"获取黄金{label}K线失败: {e}")
    
    try:
        result['daily'] = sina_daily_kline('XAU')
    except Exception as e:
        logger.warning(f"获取黄金日线失败: {e}")
    
    return result


def get_all_sentiment_data() -> Dict:
    """获取资金/情绪面数据"""
    result = {}
    
    # CFTC持仓
    try:
        cftc = get_cftc_gold_positions()
        if cftc:
            result['cftc'] = cftc
    except Exception as e:
        logger.warning(f"获取CFTC数据失败: {e}")
    
    # GLD ETF
    try:
        gld = get_gld_etf_data()
        if gld:
            result['gld_etf'] = gld
    except Exception as e:
        logger.warning(f"获取ETF数据失败: {e}")
    
    return result


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    print("=" * 60)
    print("实时行情")
    print("=" * 60)
    rt = get_all_realtime()
    for key, data in rt.items():
        if isinstance(data, dict) and 'name' in data:
            print(f"\n{data.get('name', key)}:")
            for k, v in data.items():
                if k != 'name':
                    print(f"  {k}: {v}")
        else:
            print(f"\n{key}: {data}")
    
    print("\n" + "=" * 60)
    print("宏观数据")
    print("=" * 60)
    macro = get_macro_data()
    for key, data in macro.items():
        print(f"  {key}: {data.get('value', 'N/A')} ({data.get('date', '')})")
    
    print("\n" + "=" * 60)
    print("资金/情绪面数据")
    print("=" * 60)
    sentiment = get_all_sentiment_data()
    if 'cftc' in sentiment:
        c = sentiment['cftc']
        print(f"  CFTC净多头: {c.get('net_position', 'N/A')} ({c.get('date', '')})")
    if 'gld_etf' in sentiment:
        g = sentiment['gld_etf']
        print(f"  GLD AUM: ${g.get('aum_billion', 'N/A')}B ({g.get('aum_date', '')})")
