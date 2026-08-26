#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
价格提醒模块
监控金价，触发条件时发送通知
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Callable, Optional
from app_paths import ALERTS_CONFIG, runtime_path

logger = logging.getLogger(__name__)


class PriceAlert:
    """价格提醒规则"""
    
    def __init__(self, name: str, condition: str, threshold: float, 
                 enabled: bool = True, cooldown_minutes: int = 30):
        self.name = name
        self.condition = condition  # 'above', 'below', 'change_pct'
        self.threshold = threshold
        self.enabled = enabled
        self.cooldown_minutes = cooldown_minutes
        self.last_triggered = None
    
    def check(self, current_price: float, prev_price: Optional[float] = None) -> bool:
        """检查是否触发"""
        if not self.enabled:
            return False
        
        triggered = False
        
        if self.condition == 'above':
            triggered = current_price >= self.threshold
        elif self.condition == 'below':
            triggered = current_price <= self.threshold
        elif self.condition == 'change_pct' and prev_price:
            change_pct = (current_price - prev_price) / prev_price * 100
            triggered = abs(change_pct) >= self.threshold
        
        # 冷却检查
        if triggered and self.last_triggered:
            elapsed = (datetime.now() - self.last_triggered).total_seconds() / 60
            if elapsed < self.cooldown_minutes:
                return False
        
        if triggered:
            self.last_triggered = datetime.now()
        
        return triggered
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'condition': self.condition,
            'threshold': self.threshold,
            'enabled': self.enabled,
            'cooldown_minutes': self.cooldown_minutes,
            'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PriceAlert':
        alert = cls(
            name=data['name'],
            condition=data['condition'],
            threshold=data['threshold'],
            enabled=data.get('enabled', True),
            cooldown_minutes=data.get('cooldown_minutes', 30),
        )
        if data.get('last_triggered'):
            alert.last_triggered = datetime.fromisoformat(data['last_triggered'])
        return alert


class GeopoliticalAlert:
    """地缘风险提醒规则"""
    
    def __init__(self, name: str, threshold: float = 2.0, 
                 cooldown_minutes: int = 120, enabled: bool = True):
        self.name = name
        self.threshold = threshold  # impact_score 阈值
        self.cooldown_minutes = cooldown_minutes
        self.enabled = enabled
        self.last_triggered = None
    
    def check(self, geo_impact_score: float) -> bool:
        """检查是否触发"""
        if not self.enabled:
            return False
        
        # 地缘分绝对值超过阈值才触发
        if abs(geo_impact_score) < self.threshold:
            return False
        
        # 冷却检查
        if self.last_triggered:
            elapsed = (datetime.now() - self.last_triggered).total_seconds() / 60
            if elapsed < self.cooldown_minutes:
                return False
        
        self.last_triggered = datetime.now()
        return True
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'threshold': self.threshold,
            'cooldown_minutes': self.cooldown_minutes,
            'enabled': self.enabled,
            'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'GeopoliticalAlert':
        alert = cls(
            name=data['name'],
            threshold=data['threshold'],
            cooldown_minutes=data.get('cooldown_minutes', 120),
            enabled=data.get('enabled', True),
        )
        if data.get('last_triggered'):
            alert.last_triggered = datetime.fromisoformat(data['last_triggered'])
        return alert


class AlertManager:
    """提醒管理器"""
    
    def __init__(self, config_path=ALERTS_CONFIG):
        self.config_path = runtime_path(config_path)
        self.alerts: List[PriceAlert] = []
        self.geo_alerts: List[GeopoliticalAlert] = []
        self.prev_price = None
        self.load_alerts()
    
    def load_alerts(self):
        """加载提醒规则"""
        if not os.path.exists(self.config_path):
            self.alerts = []
            self.geo_alerts = [GeopoliticalAlert('地缘风险升级', threshold=2.0)]
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 加载价格提醒
            self.alerts = [PriceAlert.from_dict(a) for a in data.get('price_alerts', [])]
            
            # 加载地缘风险提醒
            self.geo_alerts = [GeopoliticalAlert.from_dict(a) for a in data.get('geo_alerts', [])]
            if not self.geo_alerts:
                self.geo_alerts = [GeopoliticalAlert('地缘风险升级', threshold=2.0)]
            
            logger.info(f"已加载 {len(self.alerts)} 条价格提醒, {len(self.geo_alerts)} 条地缘风险提醒")
        except Exception as e:
            logger.error(f"加载提醒规则失败: {e}")
            self.alerts = []
            self.geo_alerts = [GeopoliticalAlert('地缘风险升级', threshold=2.0)]
    
    def save_alerts(self):
        """保存提醒规则"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'price_alerts': [a.to_dict() for a in self.alerts],
                'geo_alerts': [a.to_dict() for a in self.geo_alerts]
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存提醒规则失败: {e}")
    
    def add_alert(self, alert: PriceAlert):
        """添加价格提醒"""
        self.alerts.append(alert)
        self.save_alerts()
        logger.info(f"已添加价格提醒: {alert.name}")
    
    def add_geo_alert(self, alert: GeopoliticalAlert):
        """添加地缘风险提醒"""
        self.geo_alerts.append(alert)
        self.save_alerts()
        logger.info(f"已添加地缘风险提醒: {alert.name}")
    
    def remove_alert(self, name: str):
        """删除提醒"""
        self.alerts = [a for a in self.alerts if a.name != name]
        self.geo_alerts = [a for a in self.geo_alerts if a.name != name]
        self.save_alerts()
        logger.info(f"已删除提醒: {name}")
    
    def check_price(self, current_price: float) -> List[Dict]:
        """
        检查价格，返回触发的提醒
        """
        triggered = []
        
        for alert in self.alerts:
            if alert.check(current_price, self.prev_price):
                triggered.append({
                    'name': alert.name,
                    'condition': alert.condition,
                    'threshold': alert.threshold,
                    'price': current_price,
                    'time': datetime.now().isoformat(),
                })
                logger.warning(f"⚠️ 触发提醒: {alert.name} - 当前价格 {current_price:.2f}")
        
        self.prev_price = current_price
        return triggered
    
    def check_geopolitical(self, geo_impact_score: float) -> List[Dict]:
        """
        检查地缘风险，返回触发的提醒
        """
        triggered = []
        
        for alert in self.geo_alerts:
            if alert.check(geo_impact_score):
                triggered.append({
                    'name': alert.name,
                    'threshold': alert.threshold,
                    'geo_impact_score': geo_impact_score,
                    'time': datetime.now().isoformat(),
                })
                direction = '看多' if geo_impact_score > 0 else '看空'
                logger.warning(f"⚠️ 触发地缘风险提醒: {alert.name} - 地缘影响分 {geo_impact_score:.2f} ({direction})")
        
        return triggered
    
    def format_alert_message(self, alert_data: Dict) -> str:
        """格式化价格提醒消息"""
        condition_map = {
            'above': '突破上方',
            'below': '跌破下方',
            'change_pct': '波动超过',
        }
        
        condition = condition_map.get(alert_data['condition'], alert_data['condition'])
        threshold = alert_data['threshold']
        price = alert_data['price']
        name = alert_data['name']
        
        if alert_data['condition'] == 'change_pct':
            msg = f"⚠️ 【{name}】\n金价波动超过 {threshold:.2f}%\n当前价格: {price:.2f}"
        else:
            msg = f"⚠️ 【{name}】\n金价{condition} {threshold:.2f}\n当前价格: {price:.2f}"
        
        return msg
    
    def format_geo_alert_message(self, alert_data: Dict) -> str:
        """格式化地缘风险提醒消息"""
        name = alert_data['name']
        threshold = alert_data['threshold']
        geo_impact_score = alert_data['geo_impact_score']
        
        if geo_impact_score > 0:
            direction = '看多（避险需求上升）'
        else:
            direction = '看空（流动性风险或风险偏好上升）'
        
        msg = f"⚠️ 【{name}】\n地缘风险影响分超过阈值 {threshold:.2f}\n当前影响分: {geo_impact_score:.2f}\n方向判断: {direction}"
        
        return msg


# 默认提醒规则
DEFAULT_ALERTS = [
    PriceAlert('金价突破3500', 'above', 3500),
    PriceAlert('金价跌破3300', 'below', 3300),
    PriceAlert('大幅波动5%', 'change_pct', 5.0),
]


def create_default_alerts(config_path=ALERTS_CONFIG):
    """创建默认提醒规则"""
    manager = AlertManager(config_path)
    manager.alerts = DEFAULT_ALERTS
    manager.save_alerts()
    logger.info("已创建默认提醒规则")
    return manager


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    create_default_alerts()
    print("默认提醒规则已创建")
