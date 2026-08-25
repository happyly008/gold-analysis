#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
央行购金数据模块
数据来源：世界黄金协会(WGC)季度报告
由于没有免费API，使用静态数据+手动更新方式
"""

from typing import Dict, List
import json
import os
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# 数据文件路径
DATA_DIR = Path(__file__).parent / 'data'
CENTRAL_BANK_DATA_FILE = DATA_DIR / 'central_bank_gold.json'

# 央行购金数据（吨）- 来自WGC季度报告
# 数据更新频率：季度
CENTRAL_BANK_GOLD_DATA = {
    "2024_Q3": {
        "total_purchases": 186,
        "top_buyers": [
            {"country": "Poland", "purchases": 19},
            {"country": "Turkey", "purchases": 16},
            {"country": "India", "purchases": 14},
            {"country": "Azerbaijan", "purchases": 12},
            {"country": "Hungary", "purchases": 10}
        ],
        "quarter": "2024-Q3",
        "date": "2024-11-07"
    },
    "2024_Q2": {
        "total_purchases": 184,
        "top_buyers": [
            {"country": "Turkey", "purchases": 23},
            {"country": "India", "purchases": 19},
            {"country": "Poland", "purchases": 15},
            {"country": "Azerbaijan", "purchases": 12},
            {"country": "China", "purchases": 10}
        ],
        "quarter": "2024-Q2",
        "date": "2024-08-01"
    },
    "2024_Q1": {
        "total_purchases": 290,
        "top_buyers": [
            {"country": "China", "purchases": 27},
            {"country": "India", "purchases": 27},
            {"country": "Turkey", "purchases": 23},
            {"country": "Poland", "purchases": 17},
            {"country": "Czech Republic", "purchases": 11}
        ],
        "quarter": "2024-Q1",
        "date": "2024-05-02"
    },
    "2023_Q4": {
        "total_purchases": 475,
        "top_buyers": [
            {"country": "China", "purchases": 44},
            {"country": "Poland", "purchases": 38},
            {"country": "Singapore", "purchases": 33},
            {"country": "Turkey", "purchases": 29},
            {"country": "India", "purchases": 23}
        ],
        "quarter": "2023-Q4",
        "date": "2024-02-01"
    },
    "2023_Q3": {
        "total_purchases": 337,
        "top_buyers": [
            {"country": "China", "purchases": 78},
            {"country": "Poland", "purchases": 33},
            {"country": "Turkey", "purchases": 31},
            {"country": "Singapore", "purchases": 26},
            {"country": "Iraq", "purchases": 11}
        ],
        "quarter": "2023-Q3",
        "date": "2023-11-02"
    },
    "2023_Q2": {
        "total_purchases": 456,
        "top_buyers": [
            {"country": "China", "purchases": 103},
            {"country": "Poland", "purchases": 90},
            {"country": "Singapore", "purchases": 77},
            {"country": "Iraq", "purchases": 34},
            {"country": "Turkey", "purchases": 33}
        ],
        "quarter": "2023-Q2",
        "date": "2023-08-03"
    },
    "2023_Q1": {
        "total_purchases": 387,
        "top_buyers": [
            {"country": "Singapore", "purchases": 70},
            {"country": "Turkey", "purchases": 65},
            {"country": "China", "purchases": 64},
            {"country": "Iraq", "purchases": 31},
            {"country": "India", "purchases": 27}
        ],
        "quarter": "2023-Q1",
        "date": "2023-05-04"
    }
}

# 全球央行黄金储备（吨）- 截至2024年Q3
CENTRAL_BANK_RESERVES = {
    "United States": 8133.5,
    "Germany": 3351.5,
    "Italy": 2451.8,
    "France": 2436.6,
    "Russia": 2332.7,
    "China": 2264.3,
    "Switzerland": 1040.0,
    "Japan": 846.0,
    "India": 854.7,
    "Netherlands": 612.5
}


def get_latest_central_bank_data() -> Dict:
    """获取最新的央行购金数据（优先从JSON文件读取）"""
    try:
        # 优先从JSON文件读取
        if CENTRAL_BANK_DATA_FILE.exists():
            with open(CENTRAL_BANK_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data:
                    latest_key = max(data.keys())
                    logger.info(f"从JSON文件加载央行购金数据: {latest_key}")
                    return data[latest_key]
        
        # Fallback到静态数据
        logger.info("使用静态央行购金数据")
        latest_key = max(CENTRAL_BANK_GOLD_DATA.keys())
        return CENTRAL_BANK_GOLD_DATA[latest_key]
    except Exception as e:
        logger.error(f"获取央行购金数据失败: {e}")
        return {}


def get_central_bank_trend(quarters: int = 4) -> List[Dict]:
    """获取央行购金趋势（最近N个季度）"""
    try:
        sorted_keys = sorted(CENTRAL_BANK_GOLD_DATA.keys(), reverse=True)
        trend = []
        for key in sorted_keys[:quarters]:
            data = CENTRAL_BANK_GOLD_DATA[key]
            trend.append({
                "quarter": data["quarter"],
                "total_purchases": data["total_purchases"],
                "date": data["date"]
            })
        return trend
    except Exception as e:
        logger.error(f"获取央行购金趋势失败: {e}")
        return []


def calculate_central_bank_score(data: Dict, trend: List[Dict]) -> Dict:
    """
    计算央行购金对金价的支撑评分
    
    逻辑：
    - 单季度购金量 > 300吨：强烈看多（+2.0）
    - 单季度购金量 200-300吨：看多（+1.5）
    - 单季度购金量 100-200吨：中性偏多（+0.5）
    - 单季度购金量 < 100吨：中性（0.0）
    
    趋势加分：
    - 连续3个季度 > 200吨：额外+0.5
    - 中国/印度等大买家持续增持：额外+0.3
    """
    score = 0.0
    reasons = []
    
    if not data:
        return {
            "score": 0.0,
            "reasons": ["央行购金数据不可用"],
            "outlook": "neutral"
        }
    
    total_purchases = data.get("total_purchases", 0)
    
    # 基础评分
    if total_purchases >= 300:
        score += 2.0
        reasons.append(f"央行单季度购金{total_purchases}吨，强烈支撑金价")
    elif total_purchases >= 200:
        score += 1.5
        reasons.append(f"央行单季度购金{total_purchases}吨，支撑金价")
    elif total_purchases >= 100:
        score += 0.5
        reasons.append(f"央行单季度购金{total_purchases}吨，中性支撑")
    else:
        reasons.append(f"央行单季度购金{total_purchases}吨，支撑较弱")
    
    # 趋势分析
    if trend and len(trend) >= 3:
        recent_3 = [t["total_purchases"] for t in trend[:3]]
        avg_3q = sum(recent_3) / len(recent_3)
        
        if avg_3q >= 200:
            score += 0.5
            reasons.append(f"近3季度平均购金{avg_3q:.0f}吨，持续强劲")
        
        # 检查中国/印度等大买家
        top_buyers = data.get("top_buyers", [])
        major_buyers = ["China", "India", "Turkey"]
        major_purchases = sum(b["purchases"] for b in top_buyers if b["country"] in major_buyers)
        
        if major_purchases >= 30:
            score += 0.3
            reasons.append(f"中印土等大买家合计购金{major_purchases}吨")
    
    # 总体判断
    if score >= 2.0:
        outlook = "strongly_bullish"
    elif score >= 1.0:
        outlook = "bullish"
    elif score >= 0.5:
        outlook = "slightly_bullish"
    else:
        outlook = "neutral"
    
    return {
        "score": round(score, 2),
        "reasons": reasons,
        "outlook": outlook,
        "total_purchases": total_purchases,
        "quarter": data.get("quarter", ""),
        "top_buyers": data.get("top_buyers", [])[:5]
    }


def format_central_bank_report(cb_data: Dict) -> str:
    """格式化央行购金报告"""
    lines = []
    lines.append("\n【央行购金分析】")
    
    if not cb_data:
        lines.append("  数据不可用")
        return "\n".join(lines)
    
    lines.append(f"  评分: {cb_data.get('score', 0):.2f} ({cb_data.get('outlook', 'neutral')})")
    lines.append(f"  最新季度: {cb_data.get('quarter', 'N/A')}")
    lines.append(f"  购金量: {cb_data.get('total_purchases', 0)}吨")
    
    reasons = cb_data.get("reasons", [])
    if reasons:
        lines.append("  分析:")
        for reason in reasons[:3]:
            lines.append(f"    - {reason}")
    
    top_buyers = cb_data.get("top_buyers", [])
    if top_buyers:
        lines.append("  主要买家:")
        for buyer in top_buyers[:5]:
            lines.append(f"    - {buyer['country']}: {buyer['purchases']}吨")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    
    latest = get_latest_central_bank_data()
    trend = get_central_bank_trend(4)
    
    print("最新央行购金数据:")
    print(json.dumps(latest, indent=2, ensure_ascii=False))
    
    print("\n近4季度趋势:")
    for t in trend:
        print(f"  {t['quarter']}: {t['total_purchases']}吨")
    
    score_data = calculate_central_bank_score(latest, trend)
    print("\n评分分析:")
    print(format_central_bank_report(score_data))
