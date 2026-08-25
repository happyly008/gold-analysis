#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观事件日历模块
基于FRED数据发布规律 + 网页抓取获取经济日历
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import calendar as cal_module

logger = logging.getLogger(__name__)

# 重要经济事件定义
IMPORTANT_EVENTS = {
    'nonfarm': {'name': '非农就业', 'impact': 'high', 'description': '每月第一个周五'},
    'unemployment': {'name': '失业率', 'impact': 'high', 'description': '与非农同时发布'},
    'cpi': {'name': 'CPI', 'impact': 'high', 'description': '每月中旬'},
    'ppi': {'name': 'PPI', 'impact': 'medium', 'description': '每月中旬'},
    'pce': {'name': 'PCE物价指数', 'impact': 'high', 'description': '每月月底'},
    'gdp': {'name': 'GDP', 'impact': 'high', 'description': '季度发布'},
    'fomc': {'name': 'FOMC会议', 'impact': 'high', 'description': '一年8次'},
    'retail_sales': {'name': '零售销售', 'impact': 'medium', 'description': '每月中旬'},
    'ism': {'name': 'ISM制造业', 'impact': 'medium', 'description': '每月第一个工作日'},
    'jolts': {'name': 'JOLTS职位空缺', 'impact': 'medium', 'description': '每月月初'},
}


class EconomicCalendar:
    """经济事件日历"""
    
    def __init__(self, cache_dir: str = 'data'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / 'economic_calendar.json'
        self.events: List[Dict] = []
        self.load_cache()
    
    def load_cache(self):
        """加载缓存"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.events = data.get('events', [])
                logger.debug(f"加载经济日历缓存: {len(self.events)} 条事件")
        except Exception as e:
            logger.warning(f"加载经济日历缓存失败: {e}")
    
    def save_cache(self):
        """保存缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'events': self.events,
                    'update_time': datetime.now().isoformat(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存经济日历缓存失败: {e}")
    
    def generate_predictive_events(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        基于历史发布规律预测未来事件
        美国数据发布时间有固定规律
        """
        events = []
        current = start_date
        
        while current <= end_date:
            year, month = current.year, current.month
            
            # 非农就业 & 失业率：每月第一个周五
            first_day = datetime(year, month, 1)
            first_friday = first_day + timedelta(days=(4 - first_day.weekday() + 7) % 7)
            if start_date <= first_friday <= end_date:
                events.append({
                    'title': '非农就业报告',
                    'event_type': 'nonfarm',
                    'datetime': first_friday.replace(hour=8, minute=30).isoformat(),
                    'importance': 3,
                    'source': 'predicted'
                })
            
            # ISM制造业：每月第一个工作日
            first_weekday = first_day
            while first_weekday.weekday() >= 5:  # 跳过周末
                first_weekday += timedelta(days=1)
            if start_date <= first_weekday <= end_date:
                events.append({
                    'title': 'ISM制造业PMI',
                    'event_type': 'ism',
                    'datetime': first_weekday.replace(hour=10, minute=0).isoformat(),
                    'importance': 2,
                    'source': 'predicted'
                })
            
            # CPI：每月10-15日之间
            cpi_date = datetime(year, month, 13)
            while cpi_date.weekday() >= 5:
                cpi_date += timedelta(days=1)
            if start_date <= cpi_date <= end_date:
                events.append({
                    'title': '消费者物价指数(CPI)',
                    'event_type': 'cpi',
                    'datetime': cpi_date.replace(hour=8, minute=30).isoformat(),
                    'importance': 3,
                    'source': 'predicted'
                })
            
            # PPI：每月15日左右
            ppi_date = datetime(year, month, 15)
            while ppi_date.weekday() >= 5:
                ppi_date += timedelta(days=1)
            if start_date <= ppi_date <= end_date:
                events.append({
                    'title': '生产者物价指数(PPI)',
                    'event_type': 'ppi',
                    'datetime': ppi_date.replace(hour=8, minute=30).isoformat(),
                    'importance': 2,
                    'source': 'predicted'
                })
            
            # 零售销售：每月15-17日
            retail_date = datetime(year, month, 16)
            while retail_date.weekday() >= 5:
                retail_date += timedelta(days=1)
            if start_date <= retail_date <= end_date:
                events.append({
                    'title': '零售销售',
                    'event_type': 'retail_sales',
                    'datetime': retail_date.replace(hour=8, minute=30).isoformat(),
                    'importance': 2,
                    'source': 'predicted'
                })
            
            # PCE物价指数：每月月底（最后几天）
            last_day = datetime(year, month, cal_module.monthrange(year, month)[1])
            pce_date = last_day - timedelta(days=2)
            while pce_date.weekday() >= 5:
                pce_date -= timedelta(days=1)
            if start_date <= pce_date <= end_date:
                events.append({
                    'title': 'PCE物价指数',
                    'event_type': 'pce',
                    'datetime': pce_date.replace(hour=8, minute=30).isoformat(),
                    'importance': 3,
                    'source': 'predicted'
                })
            
            # 跳到下个月
            if month == 12:
                current = datetime(year + 1, 1, 1)
            else:
                current = datetime(year, month + 1, 1)
        
        return events
    
    def fetch_from_forex_factory(self) -> List[Dict]:
        """从ForexFactory获取经济日历"""
        events = []
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            
            for item in data:
                if item.get('country') != 'USD':
                    continue
                
                title = item.get('title', '')
                event_type = self._match_event_type(title)
                if not event_type:
                    continue
                
                events.append({
                    'title': title,
                    'event_type': event_type,
                    'datetime': item.get('date', ''),
                    'importance': 3 if item.get('impact') == 'High' else 2,
                    'actual': item.get('actual', ''),
                    'forecast': item.get('forecast', ''),
                    'previous': item.get('previous', ''),
                    'source': 'forex_factory'
                })
        except Exception as e:
            logger.warning(f"ForexFactory获取失败: {e}")
        
        return events
    
    def _match_event_type(self, title: str) -> Optional[str]:
        """匹配事件类型"""
        title_lower = title.lower()
        keywords_map = {
            'nonfarm': ['nonfarm', 'non-farm', 'payrolls', 'employment'],
            'unemployment': ['unemployment', 'jobless'],
            'cpi': ['cpi', 'consumer price'],
            'ppi': ['ppi', 'producer price'],
            'pce': ['pce', 'personal consumption'],
            'gdp': ['gdp', 'gross domestic'],
            'fomc': ['fomc', 'fed meeting', 'fed decision'],
            'retail_sales': ['retail sales'],
            'ism': ['ism', 'manufacturing pmi'],
            'jolts': ['jolts', 'job openings'],
        }
        
        for event_type, keywords in keywords_map.items():
            if any(kw in title_lower for kw in keywords):
                return event_type
        
        return None
    
    def refresh(self) -> int:
        """刷新日历数据"""
        logger.info("刷新经济日历...")
        
        now = datetime.now()
        end_date = now + timedelta(days=30)
        
        # 1. 尝试从ForexFactory获取实时数据
        live_events = self.fetch_from_forex_factory()
        logger.info(f"ForexFactory: {len(live_events)} 条")
        
        # 2. 生成预测事件
        predicted_events = self.generate_predictive_events(now, end_date)
        logger.info(f"预测事件: {len(predicted_events)} 条")
        
        # 3. 合并去重
        all_events = live_events.copy()
        seen_keys = {f"{e['title']}_{e['datetime'][:10]}" for e in live_events}
        
        for pred in predicted_events:
            key = f"{pred['title']}_{pred['datetime'][:10]}"
            if key not in seen_keys:
                all_events.append(pred)
                seen_keys.add(key)
        
        # 4. 按时间排序
        all_events.sort(key=lambda x: x.get('datetime', ''))
        
        self.events = all_events
        self.save_cache()
        
        logger.info(f"经济日历更新完成: {len(all_events)} 条事件")
        return len(all_events)
    
    def get_upcoming_events(self, days: int = 7) -> List[Dict]:
        """获取未来N天的重要事件"""
        now = datetime.now()
        cutoff = now + timedelta(days=days)
        
        upcoming = []
        for event in self.events:
            try:
                dt_str = event.get('datetime', '')
                if not dt_str:
                    continue
                
                # 解析ISO格式时间
                dt = None
                for fmt in [
                    '%Y-%m-%dT%H:%M:%S',
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d',
                ]:
                    try:
                        dt = datetime.strptime(dt_str[:19], fmt)
                        break
                    except ValueError:
                        continue
                
                if not dt:
                    continue
                
                if now <= dt <= cutoff:
                    event_info = event.copy()
                    event_info['parsed_datetime'] = dt
                    event_info['days_until'] = (dt - now).days
                    upcoming.append(event_info)
            except Exception as e:
                logger.debug(f"解析事件时间失败: {event}, {e}")
                continue
        
        upcoming.sort(key=lambda x: x.get('parsed_datetime', now))
        return upcoming
    
    def get_event_summary(self, days: int = 7) -> str:
        """生成事件摘要"""
        upcoming = self.get_upcoming_events(days)
        
        if not upcoming:
            return f"未来{days}天暂无重要经济数据发布"
        
        lines = [f"📅 未来{days}天重要经济事件 ({len(upcoming)}个):"]
        lines.append("")
        
        for event in upcoming[:10]:
            event_type = event.get('event_type', '')
            config = IMPORTANT_EVENTS.get(event_type, {})
            
            name = config.get('name', event.get('title', '未知'))
            impact = config.get('impact', 'medium')
            days_until = event.get('days_until', 0)
            dt = event.get('parsed_datetime')
            
            impact_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(impact, '⚪')
            
            if days_until == 0:
                time_str = f"今天 {dt.strftime('%H:%M')}" if dt else "今天"
            elif days_until == 1:
                time_str = f"明天 {dt.strftime('%H:%M')}" if dt else "明天"
            else:
                time_str = f"{days_until}天后 ({dt.strftime('%m/%d %H:%M')})" if dt else f"{days_until}天后"
            
            lines.append(f"  {impact_emoji} {name} - {time_str}")
            
            prev = event.get('previous', '')
            forecast = event.get('forecast', '')
            if prev or forecast:
                detail_parts = []
                if prev:
                    detail_parts.append(f"前值:{prev}")
                if forecast:
                    detail_parts.append(f"预期:{forecast}")
                lines.append(f"      {' | '.join(detail_parts)}")
        
        return '\n'.join(lines)


def format_calendar_report(calendar: EconomicCalendar, days: int = 7) -> str:
    """生成日历报告"""
    lines = []
    lines.append("\n【宏观事件日历】")
    lines.append(calendar.get_event_summary(days))
    return '\n'.join(lines)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    calendar = EconomicCalendar()
    count = calendar.refresh()
    
    print(f"\n获取到 {count} 条事件\n")
    print(calendar.get_event_summary(7))
