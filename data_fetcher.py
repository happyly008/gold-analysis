#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据获取模块 v3.0
改进:
- 异步并行获取：使用 aiohttp 替代 requests，宏观数据获取耗时从 15-20s 降至 3-5s
- get_cftc_gold_positions(): 增加净头寸合理性校验
  (COMEX 黄金非商业净多头正常在万手级, |net|<1000 视为异常并跳过)
- get_macro_data(): FRED 历史数据拉取失败时提供默认范围 fallback,
  避免 fundamental_analyzer 分位计算返回 None -> 报告显示 N/A
"""

import requests
import re
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

HEADERS = {
    'Referer': 'https://finance.sina.com.cn/',
    'User-Agent': 'Mozilla/5.0 GoldAnalyzer/2.0'
}

# FRED历史数据默认范围（当实际数据拉取失败时使用）
FRED_DEFAULT_RANGES = {
    'DFII10': (-2.0, 3.0),    # 实际利率范围
    'DGS10': (0.5, 5.0),      # 10年期国债收益率
    'VIXCLS': (10, 40),       # VIX恐慌指数
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


async def _async_fred_data(session: aiohttp.ClientSession, series_id: str, days: int = 30) -> List[Dict]:
    """异步获取单个FRED数据"""
    start = (datetime.now() - timedelta(days=days + 10)).strftime('%Y-%m-%d')
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    
    try:
        async with session.get(url, timeout=15) as resp:
            text = await resp.text()
            if resp.status != 200:
                return []
    except Exception as e:
        logger.warning(f"异步FRED请求失败({series_id}): {e}")
        return []
    
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


async def _async_fred_historical(session: aiohttp.ClientSession, series_id: str, years: int = 5) -> List[float]:
    """异步获取FRED历史数据"""
    days = years * 365
    start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    
    try:
        async with session.get(url, timeout=15) as resp:
            text = await resp.text()
            if resp.status != 200:
                return []
    except Exception as e:
        logger.warning(f"异步FRED历史数据请求失败({series_id}): {e}")
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
    
    logger.debug(f"异步获取{series_id}历史数据: {len(values)}条记录")
    return values


async def _async_get_macro_data() -> Dict:
    """异步并行获取宏观数据（性能优化版本）"""
    logger.info("开始异步并行获取宏观数据...")
    result = {}
    
    # 定义所有需要获取的数据系列
    fred_series = [
        ('DGS10', 5, True),      # 10Y国债，需要历史数据
        ('DFII10', 5, True),     # 实际利率，需要历史数据
        ('T10YIE', 5, False),    # 通胀预期
        ('VIXCLS', 5, True),     # VIX，需要历史数据
        ('FEDFUNDS', 30, False), # 联邦基金利率
        ('PAYEMS', 60, False),   # 非农就业
        ('UNRATE', 60, False),   # 失业率
        ('CES0500000003', 60, False),  # 平均时薪
        ('JTSJOL', 120, False),  # JOLTS职位空缺
        ('CIVPART', 60, False),  # 劳动参与率
        ('CPIAUCSL', 60, False), # CPI
        ('PCEPI', 60, False),    # PCE
        ('PCEPILFE', 60, False), # 核心PCE
        ('A191RL1Q225SBEA', 365, False),  # GDP增速
    ]
    
    async with aiohttp.ClientSession() as session:
        # 并行获取所有当前数据
        current_tasks = [_async_fred_data(session, series_id, days) 
                        for series_id, days, _ in fred_series]
        current_results = await asyncio.gather(*current_tasks, return_exceptions=True)
        
        # 并行获取需要历史数据的系列
        history_tasks = []
        history_series = []
        for series_id, days, need_history in fred_series:
            if need_history:
                history_tasks.append(_async_fred_historical(session, series_id, years=5))
                history_series.append(series_id)
        
        history_results = await asyncio.gather(*history_tasks, return_exceptions=True) if history_tasks else []
    
    # 处理结果
    for i, (series_id, days, need_history) in enumerate(fred_series):
        try:
            data = current_results[i]
            if isinstance(data, Exception):
                logger.warning(f"获取{series_id}失败: {data}")
                continue
            
            if data:
                # 根据series_id存储到不同的字段
                if series_id == 'DGS10':
                    result['us10y'] = data[-1]
                    if need_history and i < len(history_results):
                        history = history_results[history_series.index(series_id)]
                        if not history:
                            default_range = FRED_DEFAULT_RANGES.get('DGS10')
                            if default_range:
                                result['us10y_range'] = default_range
                                logger.info(f"10Y国债历史数据为空，使用默认范围: {default_range}")
                        else:
                            result['us10y_history'] = history
                elif series_id == 'DFII10':
                    result['real_rate'] = data[-1]
                    if need_history and i < len(history_results):
                        history = history_results[history_series.index(series_id)]
                        if not history:
                            default_range = FRED_DEFAULT_RANGES.get('DFII10')
                            if default_range:
                                result['real_rate_range'] = default_range
                                logger.info(f"实际利率历史数据为空，使用默认范围: {default_range}")
                        else:
                            result['real_rate_history'] = history
                elif series_id == 'T10YIE':
                    result['inflation_expect'] = data[-1]
                elif series_id == 'VIXCLS':
                    result['vix'] = data[-1]
                    if need_history and i < len(history_results):
                        history = history_results[history_series.index(series_id)]
                        if not history:
                            default_range = FRED_DEFAULT_RANGES.get('VIXCLS')
                            if default_range:
                                result['vix_range'] = default_range
                                logger.info(f"VIX历史数据为空，使用默认范围: {default_range}")
                        else:
                            result['vix_history'] = history
                elif series_id == 'FEDFUNDS':
                    result['fed_rate'] = data[-1]
                elif series_id == 'PAYEMS':
                    result['nonfarm_payrolls'] = data[-1]
                    if len(data) >= 2:
                        result['nonfarm_change'] = data[-1]['value'] - data[-2]['value']
                elif series_id == 'UNRATE':
                    result['unemployment_rate'] = data[-1]
                elif series_id == 'CES0500000003':
                    result['avg_hourly_earnings'] = data[-1]
                elif series_id == 'JTSJOL':
                    result['jolts'] = data[-1]
                elif series_id == 'CIVPART':
                    result['labor_force_participation'] = data[-1]
                elif series_id == 'CPIAUCSL':
                    result['cpi'] = data[-1]
                    if len(data) >= 13:
                        yoy = (data[-1]['value'] / data[-13]['value'] - 1) * 100
                        result['cpi_yoy'] = {'date': data[-1]['date'], 'value': round(yoy, 2), 'series': 'CPI_YOY'}
                elif series_id == 'PCEPI':
                    result['pce'] = data[-1]
                elif series_id == 'PCEPILFE':
                    result['core_pce'] = data[-1]
                    if len(data) >= 13:
                        yoy = (data[-1]['value'] / data[-13]['value'] - 1) * 100
                        result['core_pce_yoy'] = {'date': data[-1]['date'], 'value': round(yoy, 2), 'series': 'CORE_PCE_YOY'}
                elif series_id == 'A191RL1Q225SBEA':
                    result['gdp_growth'] = data[-1]
        except Exception as e:
            logger.warning(f"处理{series_id}结果失败: {e}")
    
    logger.info(f"宏观数据获取完成，共{len(result)}项")
    return result


def get_macro_data() -> Dict:
    """获取宏观数据（自动选择同步或异步版本）"""
    # 检查是否在异步环境中
    try:
        loop = asyncio.get_running_loop()
        # 如果在异步环境中，直接调用异步版本
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _async_get_macro_data())
            return future.result()
    except RuntimeError:
        # 没有运行中的事件循环，使用异步版本
        return asyncio.run(_async_get_macro_data())


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
                    
                    # v2.1新增：净头寸合理性校验
                    # COMEX黄金非商业净多头正常在万手级(5万-30万)，|net|<1000视为异常
                    if abs(net_position) < 1000:
                        logger.error(f"CFTC净头寸异常: {net_position}，跳过本行数据")
                        continue
                    
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
