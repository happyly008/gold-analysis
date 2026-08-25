#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
地缘政治风险因子量化模块 v2.0
基于四层框架：GPR边际 → 资产确认 → 时间衰减 → 宏观通道

核心公式：
    GeoScore = tanh( (ΔGPR/100) × 0.025 × C × exp(-λt) × SCALE ) × geo_weight

数据源：
- 观察者网/新浪国际新闻（关键词代理分，降级方案）
- GPR指数（优先，需外部数据源）
- 实时行情（黄金/美元/美债/原油，用于资产确认）

输出：
- score: [-1, 1] 标准化得分
- impact_pct: 对金价的估计%影响
- action: bullish/bearish/neutral/caution
"""

import requests
import re
import json
import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple
from pathlib import Path
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# ============================================================
# 数据类：模块输出
# ============================================================
@dataclass
class GeoRiskResult:
    """地缘政治因子量化结果"""
    score: float = 0.0           # 标准化得分 [-1, 1]
    impact_pct: float = 0.0      # 对金价的估计%影响
    dgpr: float = 0.0            # GPR边际变化
    gpr_level: float = 0.0       # 当前GPR水平
    asset_confirm: float = 0.0   # 资产确认因子C
    decay: float = 0.0           # 时间衰减
    geo_weight: float = 0.0      # 动态权重
    regime_corr: float = 0.0     # GPR-金价滚动相关性
    channel: dict = field(default_factory=dict)  # 四通道明细
    warning: str = ""            # 风险提示文本
    action: str = "neutral"      # 决策建议
    
    # 保留旧版字段（向后兼容）
    risk_score: float = 0.0      # 旧版风险评分 0-10
    level: str = "无数据"         # 旧版风险等级
    articles: list = field(default_factory=list)
    hotspots: list = field(default_factory=list)
    summary: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# 全局参数
# ============================================================
PARAMS = {
    "gpr_scale": 0.025,          # WGC校准：每100点GPR → 2.5%金价
    "decay_lambda": 0.15,        # 日频衰减常数（半衰期~5交易日）
    "score_scale": 40.0,         # tanh前放大系数
    "base_geo_weight": 0.15,     # 地缘因子基础权重（从0.30降到0.15）
    "proxy_per_news": 3.5,       # 无GPR时，每条高危新闻代理GPR点数
    "high_severity_boost": 1.5,  # 核威胁/战争开始/升级类倍率
    "corr_clip": 0.6,            # 相关性用于权重时的裁剪区间半宽
}


# ============================================================
# 地缘冲突关键词（用于新闻代理分）
# ============================================================
HIGH_WEIGHT_KEYWORDS = [
    '战争', '军事冲突', '核武', '核弹', '导弹袭击', '全面战争',
    '入侵', '宣战', '武装冲突', '军事行动', '空袭', '轰炸',
    '制裁', '封锁', '禁运', '断交',
]

MEDIUM_WEIGHT_KEYWORDS = [
    '冲突', '紧张局势', '危机', '对峙', '摩擦', '升级',
    '军事部署', '军演', '武器', '导弹', '无人机',
    '地缘政治', '地缘风险', '地缘冲突', '代理人战争',
    '俄乌', '乌克兰', '中东', '以色列', '伊朗', '朝鲜',
    '台海', '南海', '克什米尔',
]

LOW_WEIGHT_KEYWORDS = [
    '局势', '外交', '谈判', '和平', '停火', '停战',
    '缓和', '磋商', '会谈', '协议', '条约',
    '避险', '恐慌', '不确定性', '风险',
]

HOTSPOTS = [
    '俄乌', '乌克兰', '俄罗斯', '中东', '以色列', '巴勒斯坦', '加沙',
    '伊朗', '朝鲜', '台海', '台湾海峡', '南海', '克什米尔',
    '叙利亚', '黎巴嫩', '也门', '红海', '苏丹', '缅甸',
]

# 新闻分类映射（用于代理分计算）
NEWS_CATEGORY_MAP = {
    'nuclear_threat': ['核武', '核弹', '核威胁', '核试验'],
    'war_onset': ['战争爆发', '开战', '宣战', '全面战争'],
    'war_escalation': ['战争升级', '冲突升级', '军事行动', '空袭', '轰炸'],
    'terrorist_act': ['恐怖袭击', '爆炸', '枪击', '自杀式'],
    'military_buildup': ['军事部署', '军演', '武器部署', '导弹部署'],
    'war_threat': ['战争威胁', '军事威胁', '武力威胁'],
    'peace_threat': ['和平威胁', '安全威胁'],
    'terrorist_threat': ['恐怖威胁', '恐怖主义'],
}


class GeopoliticalMonitor:
    """地缘政治风险监控器 v2.0"""
    
    def __init__(self, cache_dir: str = 'data'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / 'geopolitical_cache.json'
        self.articles_cache: List[Dict] = []
        self.last_event_time: Optional[datetime] = None
        self.load_cache()
    
    def load_cache(self):
        """加载缓存"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.articles_cache = data.get('articles', [])
                if data.get('last_event_time'):
                    self.last_event_time = datetime.fromisoformat(data['last_event_time'])
        except Exception as e:
            logger.warning(f"加载地缘缓存失败: {e}")
    
    def save_cache(self):
        """保存缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'articles': self.articles_cache[-100:],
                    'update_time': datetime.now().isoformat(),
                    'last_event_time': self.last_event_time.isoformat() if self.last_event_time else None,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存地缘缓存失败: {e}")
    
    # ============================================================
    # 新闻抓取（保留原有功能）
    # ============================================================
    def fetch_guancha(self) -> List[Dict]:
        """从观察者网获取国际新闻"""
        articles = []
        url = "https://www.guancha.cn/guojisaishi/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.encoding = 'utf-8'
            html = resp.text
            
            titles = re.findall(r'alt="([^"]{10,})"', html)
            for title in titles:
                if any(kw in title for kw in HOTSPOTS + MEDIUM_WEIGHT_KEYWORDS + HIGH_WEIGHT_KEYWORDS):
                    articles.append({
                        'title': title,
                        'source': '观察者网',
                        'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    })
        except Exception as e:
            logger.warning(f"观察者网获取失败: {e}")
        
        return articles
    
    def fetch_sina_world(self) -> List[Dict]:
        """从新浪获取国际新闻"""
        articles = []
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2510&num=30&page=1"
        headers = {
            'User-Agent': 'Mozilla/5.0 GoldAnalyzer/2.0'
        }
        
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            
            for item in data.get('result', {}).get('data', []):
                title = item.get('title', '')
                if not title:
                    continue
                all_keywords = HIGH_WEIGHT_KEYWORDS + MEDIUM_WEIGHT_KEYWORDS + LOW_WEIGHT_KEYWORDS + HOTSPOTS
                if any(kw in title for kw in all_keywords):
                    ctime = item.get('ctime', '')
                    try:
                        dt = datetime.fromtimestamp(int(ctime))
                        time_str = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        time_str = ctime
                    articles.append({
                        'title': title,
                        'source': '新浪',
                        'time': time_str,
                    })
        except Exception as e:
            logger.warning(f"新浪国际获取失败: {e}")
        
        return articles
    
    def fetch_all_news(self) -> List[Dict]:
        """获取所有新闻源"""
        all_articles = []
        
        articles = self.fetch_guancha()
        all_articles.extend(articles)
        logger.info(f"观察者网获取 {len(articles)} 条地缘相关新闻")
        
        articles = self.fetch_sina_world()
        all_articles.extend(articles)
        logger.info(f"新浪获取 {len(articles)} 条地缘相关新闻")
        
        # 去重
        seen = set()
        unique = []
        for a in all_articles:
            key = a['title'][:20]
            if key not in seen:
                seen.add(key)
                unique.append(a)
        
        self.articles_cache = unique
        self.save_cache()
        
        return unique
    
    # ============================================================
    # 第0/1层：GPR边际变化 / 新闻代理分
    # ============================================================
    def fetch_gpr_margin(self, gpr_series: Optional[Sequence[float]] = None) -> Tuple[float, float]:
        """
        计算GPR边际变化ΔGPR与当前水平
        优先使用外部GPR数据，缺失时返回(0, 0)
        """
        if not gpr_series or len(gpr_series) < 2:
            return 0.0, 0.0
        gpr_level = float(gpr_series[-1])
        dgpr = float(gpr_series[-1] - gpr_series[-2])
        return dgpr, gpr_level
    
    def news_proxy_score(self, articles: List[Dict] = None) -> Tuple[float, float]:
        """
        无GPR数据时的降级代理：按8类关键词加权合成代理ΔGPR
        返回 (proxy_dgpr, proxy_level)
        """
        if articles is None:
            articles = self.articles_cache
        
        if not articles:
            return 0.0, 0.0
        
        # 统计各类别新闻数量
        category_counts = {cat: 0 for cat in NEWS_CATEGORY_MAP.keys()}
        
        for article in articles:
            title = article.get('title', '')
            for cat, keywords in NEWS_CATEGORY_MAP.items():
                if any(kw in title for kw in keywords):
                    category_counts[cat] += 1
                    break  # 每篇文章只计一次
        
        # 计算代理分
        severity = {
            "war_threat": 1.0, "peace_threat": 1.0, "military_buildup": 0.8,
            "nuclear_threat": 1.5, "terrorist_threat": 1.0,
            "war_onset": 1.5, "war_escalation": 1.5, "terrorist_act": 1.2,
        }
        boost = PARAMS["high_severity_boost"]
        per = PARAMS["proxy_per_news"]
        
        level = 0.0
        for cat, count in category_counts.items():
            if count == 0:
                continue
            sev = severity.get(cat, 1.0)
            # 高危类额外加权
            if cat in ("nuclear_threat", "war_onset", "war_escalation"):
                sev *= boost
            level += count * sev * per
        
        return float(level), float(level)
    
    # ============================================================
    # 第2层：资产确认因子C
    # ============================================================
    def asset_confirmation(
        self,
        gold_ret: float = 0.0,
        dxy_ret: float = 0.0,
        ust10y_ret: float = 0.0,
        oil_ret: float = 0.0,
    ) -> float:
        """
        根据黄金/美元/美债/原油的协同方向判定资产确认因子C
        返回值约束到[-1, 1]
        
        判定规则：
          纯避险：金+ 美债+ 美元+ → +1.0
          通胀驱动：金+ 美元- 美债- → +0.6
          流动性抛售：金- → -0.5
          震荡未确认：金~0 → +0.2
        """
        def sgn(x: float) -> int:
            return 1 if x > 0.0005 else (-1 if x < -0.0005 else 0)
        
        sg, sd, su, so = sgn(gold_ret), sgn(dxy_ret), sgn(ust10y_ret), sgn(oil_ret)
        
        if sg == 0:
            return 0.2  # 黄金震荡，未确认
        if sg == -1:
            return -0.5  # 流动性抛售/利率压制主导
        
        # 黄金上涨情形
        if sd == 1 and su == 1:
            return 1.0  # 纯避险
        if sd == -1 and su == -1:
            return 0.6  # 通胀驱动
        if so == 1:
            return 0.7  # 原油单独推升（中东冲突典型）
        return 0.4  # 金涨但协同不强
    
    # ============================================================
    # 第3层：时间衰减
    # ============================================================
    def time_decay(self, days_since_event: int, lam: Optional[float] = None) -> float:
        """exp(-λt)，days_since_event为事件爆发后经过的交易日数"""
        if days_since_event < 0:
            days_since_event = 0
        lam = PARAMS["decay_lambda"] if lam is None else lam
        return math.exp(-lam * days_since_event)
    
    # ============================================================
    # 第4层：宏观四通道传导
    # ============================================================
    def macro_channels(
        self,
        inflation_signal: float = 0.0,
        rate_signal: float = 0.0,
        dollar_signal: float = 0.0,
    ) -> dict:
        """
        四通道合成：避险(直接)0.4 + 通胀0.25 + 利率0.2 + 美元0.15
        各通道信号输入建议已标准化到[-1, 1]
        """
        direct = 1.0  # 避险直接效应恒为正
        composite = (
            0.40 * direct
            + 0.25 * inflation_signal
            + 0.20 * rate_signal
            + 0.15 * dollar_signal
        )
        return {
            "safe_haven": 0.40 * direct,
            "inflation": 0.25 * inflation_signal,
            "rate": 0.20 * rate_signal,
            "dollar": 0.15 * dollar_signal,
            "composite": composite,
        }
    
    # ============================================================
    # 动态权重
    # ============================================================
    def dynamic_geo_weight(self, regime_corr: float, base: Optional[float] = None) -> float:
        """
        根据GPR-金价滚动相关性动态调整地缘权重
        regime_corr高(地缘主导期) → 上调；低(利率主导期) → 下调
        """
        base = PARAMS["base_geo_weight"] if base is None else base
        half = PARAMS["corr_clip"]
        factor = (max(-half, min(half, regime_corr)) + half) / (2 * half)
        return float(base * (0.5 + 0.5 * factor))
    
    # ============================================================
    # 主入口：计算地缘政治因子
    # ============================================================
    def compute_geo_risk(
        self,
        gpr_series: Optional[Sequence[float]] = None,
        gold_ret: float = 0.0,
        dxy_ret: float = 0.0,
        ust10y_ret: float = 0.0,
        oil_ret: float = 0.0,
        days_since_event: Optional[int] = None,
        regime_corr: float = 0.0,
        inflation_signal: float = 0.0,
        rate_signal: float = 0.0,
        dollar_signal: float = 0.0,
    ) -> GeoRiskResult:
        """
        地缘政治因子主计算函数
        
        参数：
          gpr_series: GPR指数序列（长度>=2），优先使用
          gold_ret/dxy_ret/ust10y_ret/oil_ret: 当日资产收益（小数）
          days_since_event: 当前地缘事件爆发后经过的交易日数
          regime_corr: GPR与金价的滚动相关性（60日）
          inflation/rate/dollar_signal: 宏观三通道标准化信号[-1,1]
        """
        # 自动计算days_since_event
        if days_since_event is None:
            if self.last_event_time:
                delta = datetime.now() - self.last_event_time
                days_since_event = max(0, delta.days)
            else:
                days_since_event = 0
        
        # 第0/1层：GPR边际 / 新闻代理
        dgpr, gpr_level = self.fetch_gpr_margin(gpr_series)
        used_proxy = False
        if dgpr == 0.0:
            dgpr, gpr_level = self.news_proxy_score()
            used_proxy = True
            if dgpr > 0:
                self.last_event_time = datetime.now()
        
        # 第2层：资产确认
        confirm = self.asset_confirmation(gold_ret, dxy_ret, ust10y_ret, oil_ret)
        
        # 第3层：时间衰减
        decay = self.time_decay(days_since_event)
        
        # 第4层：宏观通道
        ch = self.macro_channels(inflation_signal, rate_signal, dollar_signal)
        macro_dir = ch["composite"]
        
        # 影响力（对金价%影响）
        scale = PARAMS["gpr_scale"]
        impact = (dgpr / 100.0) * scale * confirm * decay * macro_dir
        
        # 标准化得分
        score = math.tanh(impact * PARAMS["score_scale"])
        
        # 动态权重
        weight = self.dynamic_geo_weight(regime_corr)
        
        # 决策建议
        action = "neutral"
        if confirm < 0:
            action = "caution"
        elif score > 0.4:
            action = "bullish"
        elif score < -0.4:
            action = "bearish"
        elif abs(score) <= 0.15:
            action = "neutral"
        else:
            action = "caution"
        
        # 风险提示
        warning = ""
        if used_proxy:
            warning = "GPR数据缺失，使用新闻关键词代理分，结果仅供参考"
        if abs(regime_corr) < 0.1:
            warning = (warning + "; " if warning else "") + "GPR-金价相关性偏低，地缘权重已下调"
        if confirm < 0:
            warning = (warning + "; " if warning else "") + "资产协同为负，地缘溢价可能回落"
        
        # 旧版字段（向后兼容）
        risk_score = min(10, max(0, abs(score) * 10))
        if risk_score >= 8:
            level = '极高风险 🔴'
        elif risk_score >= 6:
            level = '高风险 🟠'
        elif risk_score >= 4:
            level = '中等风险 🟡'
        elif risk_score >= 2:
            level = '低风险 🟢'
        else:
            level = '平静 🟢'
        
        # 检测热点地区
        detected_hotspots = set()
        for article in self.articles_cache:
            title = article.get('title', '')
            for hotspot in HOTSPOTS:
                if hotspot in title:
                    detected_hotspots.add(hotspot)
        
        summary = f"地缘风险得分{score:+.2f}，对金价影响{impact:+.2%}"
        if detected_hotspots:
            summary += f"，热点: {', '.join(list(detected_hotspots)[:3])}"
        
        result = GeoRiskResult(
            score=score,
            impact_pct=impact,
            dgpr=dgpr,
            gpr_level=gpr_level,
            asset_confirm=confirm,
            decay=decay,
            geo_weight=weight,
            regime_corr=regime_corr,
            channel=ch,
            warning=warning,
            action=action,
            # 旧版字段
            risk_score=risk_score,
            level=level,
            articles=self.articles_cache[:10],
            hotspots=list(detected_hotspots),
            summary=summary,
        )
        
        self.save_cache()
        return result
    
    # ============================================================
    # 向后兼容的接口
    # ============================================================
    def score_geopolitical_risk(self, articles: List[Dict] = None) -> Dict:
        """旧版接口，返回兼容格式"""
        if articles is None:
            articles = self.articles_cache
        
        if not articles:
            return {
                'score': 0,
                'level': '无数据',
                'articles': [],
                'hotspots': [],
                'summary': '暂无地缘冲突新闻',
            }
        
        # 使用新版计算
        result = self.compute_geo_risk()
        
        return {
            'score': round(result.risk_score, 1),
            'level': result.level,
            'articles': result.articles,
            'hotspots': result.hotspots,
            'summary': result.summary,
            'update_time': datetime.now().isoformat(),
            # 新增字段
            'geo_result': result.to_dict(),
        }
    
    def get_gold_impact_score(self) -> float:
        """
        旧版接口：获取地缘冲突对金价的利多分数
        返回：-1.0 ~ 1.0（新版标准化到[-1, 1]）
        """
        result = self.compute_geo_risk()
        return result.score
    
    def get_geo_result(self) -> GeoRiskResult:
        """新版接口：获取完整地缘政治因子结果"""
        return self.compute_geo_risk()


def format_geopolitical_report(risk_data: Dict) -> str:
    """生成地缘政治风险报告"""
    lines = []
    lines.append("\n【地缘政治风险 v2.0】")
    lines.append(f"  风险等级: {risk_data.get('level', '无数据')}")
    lines.append(f"  风险评分: {risk_data.get('score', 0):.1f}/10")
    lines.append(f"  摘要: {risk_data.get('summary', '')}")
    
    # 新增：详细因子分解
    geo_result = risk_data.get('geo_result')
    if geo_result:
        lines.append(f"\n  因子分解:")
        lines.append(f"    标准化得分: {geo_result.get('score', 0):+.2f}")
        lines.append(f"    对金价影响: {geo_result.get('impact_pct', 0):+.2%}")
        lines.append(f"    资产确认因子: {geo_result.get('asset_confirm', 0):+.2f}")
        lines.append(f"    时间衰减: {geo_result.get('decay', 0):.2f}")
        lines.append(f"    动态权重: {geo_result.get('geo_weight', 0):.2f}")
        lines.append(f"    决策建议: {geo_result.get('action', 'neutral')}")
        
        warning = geo_result.get('warning', '')
        if warning:
            lines.append(f"    ⚠️ {warning}")
    
    if risk_data.get('hotspots'):
        lines.append(f"  热点地区: {', '.join(risk_data['hotspots'][:5])}")
    
    articles = risk_data.get('articles', [])
    if articles:
        lines.append(f"\n  重要新闻:")
        for i, article in enumerate(articles[:5], 1):
            score = article.get('risk_score', 0)
            emoji = '🔴' if score >= 5 else ('🟠' if score >= 3 else '🟡')
            lines.append(f"    {emoji} [{article.get('source', '')}] {article['title'][:50]}")
    
    return '\n'.join(lines)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    monitor = GeopoliticalMonitor()
    
    print("获取地缘政治新闻...")
    articles = monitor.fetch_all_news()
    print(f"共获取 {len(articles)} 条相关新闻\n")
    
    print("计算地缘政治因子 v2.0...")
    result = monitor.compute_geo_risk(
        gold_ret=0.012,
        dxy_ret=0.003,
        ust10y_ret=0.005,
        oil_ret=0.008,
        regime_corr=0.25,
    )
    
    print(f"标准化得分: {result.score:+.2f}")
    print(f"对金价影响: {result.impact_pct:+.2%}")
    print(f"资产确认因子: {result.asset_confirm:+.2f}")
    print(f"时间衰减: {result.decay:.2f}")
    print(f"动态权重: {result.geo_weight:.2f}")
    print(f"决策建议: {result.action}")
    print(f"风险提示: {result.warning}")
    
    print("\n" + format_geopolitical_report(monitor.score_geopolitical_risk()))
