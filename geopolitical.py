#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
地缘冲突监控模块
定时获取地缘政治风险新闻，评估对金价的影响

数据源：
- 观察者网国际新闻 (guancha.cn)
- 新浪国际新闻
- GPR指数 (备用)
"""

import requests
import re
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# 地缘冲突关键词（权重从高到低）
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

# 热点地区
HOTSPOTS = [
    '俄乌', '乌克兰', '俄罗斯', '中东', '以色列', '巴勒斯坦', '加沙',
    '伊朗', '朝鲜', '台海', '台湾海峡', '南海', '克什米尔',
    '叙利亚', '黎巴嫩', '也门', '红海', '苏丹', '缅甸',
]


class GeopoliticalMonitor:
    """地缘政治风险监控器"""
    
    def __init__(self, cache_dir: str = 'data'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / 'geopolitical_cache.json'
        self.articles_cache: List[Dict] = []
        self.load_cache()
    
    def load_cache(self):
        """加载缓存"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.articles_cache = data.get('articles', [])
        except Exception as e:
            logger.warning(f"加载地缘缓存失败: {e}")
    
    def save_cache(self):
        """保存缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'articles': self.articles_cache[-100:],  # 只保留最近100条
                    'update_time': datetime.now().isoformat(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存地缘缓存失败: {e}")
    
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
            
            # 提取标题
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
                # 检查是否包含地缘相关关键词
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
        
        # 观察者网
        articles = self.fetch_guancha()
        all_articles.extend(articles)
        logger.info(f"观察者网获取 {len(articles)} 条地缘相关新闻")
        
        # 新浪
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
    
    def score_geopolitical_risk(self, articles: List[Dict] = None) -> Dict:
        """
        评估地缘政治风险等级
        返回: score(0-10), level, articles, hotspots
        """
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
        
        total_score = 0.0
        relevant_articles = []
        detected_hotspots = set()
        
        for article in articles:
            title = article['title']
            article_score = 0.0
            
            # 高权重关键词
            for kw in HIGH_WEIGHT_KEYWORDS:
                if kw in title:
                    article_score += 3.0
            
            # 中权重关键词
            for kw in MEDIUM_WEIGHT_KEYWORDS:
                if kw in title:
                    article_score += 1.5
            
            # 低权重关键词
            for kw in LOW_WEIGHT_KEYWORDS:
                if kw in title:
                    article_score += 0.5
            
            # 热点地区
            for hotspot in HOTSPOTS:
                if hotspot in title:
                    article_score += 1.0
                    detected_hotspots.add(hotspot)
            
            if article_score > 0:
                article['risk_score'] = round(article_score, 1)
                relevant_articles.append(article)
                total_score += article_score
        
        # 归一化到 0-10
        if relevant_articles:
            # 考虑数量和严重程度
            count_factor = min(len(relevant_articles) / 5, 3.0)  # 数量因子(最多3倍)
            avg_severity = total_score / len(relevant_articles)  # 平均严重程度
            raw_score = count_factor * avg_severity
            normalized = min(10, raw_score)
        else:
            normalized = 0
        
        # 风险等级
        if normalized >= 8:
            level = '极高风险 🔴'
        elif normalized >= 6:
            level = '高风险 🟠'
        elif normalized >= 4:
            level = '中等风险 🟡'
        elif normalized >= 2:
            level = '低风险 🟢'
        else:
            level = '平静 🟢'
        
        # 按风险分数排序
        relevant_articles.sort(key=lambda x: x.get('risk_score', 0), reverse=True)
        
        # 生成摘要
        if relevant_articles:
            top_titles = [a['title'][:40] for a in relevant_articles[:3]]
            summary = f"检测到{len(relevant_articles)}条地缘风险新闻"
            if detected_hotspots:
                summary += f"，热点地区: {', '.join(list(detected_hotspots)[:3])}"
        else:
            summary = '当前无显著地缘政治风险'
        
        return {
            'score': round(normalized, 1),
            'level': level,
            'articles': relevant_articles[:10],
            'hotspots': list(detected_hotspots),
            'summary': summary,
            'update_time': datetime.now().isoformat(),
        }
    
    def get_gold_impact_score(self) -> float:
        """
        获取地缘冲突对金价的利多分数
        地缘风险越高，越利好黄金
        返回: -1.0 ~ 3.0
        """
        risk = self.score_geopolitical_risk()
        score = risk['score']
        
        if score >= 8:
            return 3.0   # 极高风险，强烈利好
        elif score >= 6:
            return 2.0   # 高风险，利好
        elif score >= 4:
            return 1.0   # 中等风险，偏利好
        elif score >= 2:
            return 0.5   # 低风险，轻微利好
        else:
            return 0.0   # 平静，无影响


def format_geopolitical_report(risk_data: Dict) -> str:
    """生成地缘政治风险报告"""
    lines = []
    lines.append("\n【地缘政治风险】")
    lines.append(f"  风险等级: {risk_data.get('level', '无数据')}")
    lines.append(f"  风险评分: {risk_data.get('score', 0):.1f}/10")
    lines.append(f"  摘要: {risk_data.get('summary', '')}")
    
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
    
    print("评估风险等级...")
    risk = monitor.score_geopolitical_risk()
    print(format_geopolitical_report(risk))
    
    print(f"\n对金价影响分数: {monitor.get_gold_impact_score():.1f}")
