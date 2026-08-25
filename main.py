#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金综合分析系统 v3.0
三套体系综合分析：
1. 基本面/宏观面（管方向）
2. 技术面（管节奏）
3. 资金/情绪面（管仓位）
"""

import sys
import os
import time
import logging
import logging.handlers
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import (
    get_all_realtime, get_treasury_yields, get_gold_klines,
    get_macro_data, get_all_sentiment_data
)
from analyzer import comprehensive_analysis, format_comprehensive_report
from alerts import AlertManager, create_default_alerts
from notifier import send_analysis_report, send_price_alert, load_email_config, create_default_config
from geopolitical import GeopoliticalMonitor
from correlation_analysis import correlation_analysis as run_correlation_analysis, format_correlation_report

# ========== 日志配置 ==========
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging(level=logging.INFO):
    """配置日志：控制台 + 文件轮转"""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 根logger最低级别
    
    # 格式
    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)-7s] %(name)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台 handler (INFO+)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    root_logger.addHandler(ch)
    
    # 文件 handler - 按天轮转，保留30天
    log_file = os.path.join(LOG_DIR, 'gold_analysis.log')
    fh = logging.handlers.TimedRotatingFileHandler(
        log_file, when='midnight', interval=1, backupCount=30,
        encoding='utf-8'
    )
    fh.setLevel(logging.DEBUG)  # 文件记录全部级别
    fh.setFormatter(fmt)
    root_logger.addHandler(fh)
    
    # 错误单独一份
    err_file = os.path.join(LOG_DIR, 'error.log')
    eh = logging.handlers.RotatingFileHandler(
        err_file, maxBytes=5*1024*1024, backupCount=5,
        encoding='utf-8'
    )
    eh.setLevel(logging.ERROR)
    eh.setFormatter(fmt)
    root_logger.addHandler(eh)
    
    return root_logger

logger = logging.getLogger('main')


def run_analysis_once(alert_manager=None, email_config=None, send_notification=True):
    """执行一次完整分析"""
    logger.info("开始执行黄金三体系综合分析...")
    
    # 1. 获取实时行情
    logger.info("获取实时行情...")
    realtime = get_all_realtime()
    
    # 2. 获取黄金K线
    logger.info("获取黄金K线数据...")
    klines = get_gold_klines()
    
    # 3. 获取宏观数据
    logger.info("获取宏观数据...")
    macro_data = get_macro_data()
    
    # 4. 获取资金面数据
    logger.info("获取资金面数据...")
    sentiment_data = get_all_sentiment_data()
    
    # 5. 创建地缘政治监控器
    logger.info("获取地缘政治新闻...")
    geo_monitor = GeopoliticalMonitor()
    
    # 6. 执行相关性分析（在综合分析之前，用于调整权重）
    logger.info("执行历史相关性分析...")
    correlations = {}
    try:
        correlations = run_correlation_analysis(klines)
        logger.info("相关性分析完成")
    except Exception as e:
        logger.error(f"相关性分析失败: {e}")
    
    # 7. 三体系综合分析（传入相关性数据）
    logger.info("执行三体系综合分析...")
    analysis = comprehensive_analysis(realtime, klines, macro_data, sentiment_data, geo_monitor, correlations)
    
    # 8. 生成报告
    report = format_comprehensive_report(analysis, realtime, macro_data)
    
    # 9. 格式化相关性报告
    correlation_report = format_correlation_report(correlations) if correlations else None
    
    # 9. 检查价格提醒
    if alert_manager and analysis.get('current_price', 0) > 0:
        triggered = alert_manager.check_price(analysis['current_price'])
        if triggered and email_config:
            for alert_data in triggered:
                msg = alert_manager.format_alert_message(alert_data)
                send_price_alert(email_config, msg, analysis['current_price'], alert_data['name'])
                logger.warning(f"触发提醒: {alert_data['name']}")
    
    # 10. 检查地缘风险提醒
    if alert_manager and analysis.get('geopolitical'):
        geo_impact = analysis['geopolitical'].get('impact_score', 0)
        geo_triggered = alert_manager.check_geopolitical(geo_impact)
        if geo_triggered and email_config:
            for alert_data in geo_triggered:
                msg = alert_manager.format_geo_alert_message(alert_data)
                send_price_alert(email_config, msg, analysis['current_price'], alert_data['name'])
                logger.warning(f"触发地缘风险提醒: {alert_data['name']}")
    
    # 9. 发送邮件通知
    if send_notification and email_config:
        send_analysis_report(email_config, report)
    
    logger.info("分析完成")
    return report, analysis


def main():
    # 初始化日志（先默认INFO，后面根据--debug调整）
    setup_logging(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='黄金综合分析系统 v3.0')
    parser.add_argument('--once', action='store_true', help='只执行一次')
    parser.add_argument('--interval', type=int, default=3600, help='定时间隔(秒)')
    parser.add_argument('--output', type=str, help='输出文件路径')
    parser.add_argument('--gui', action='store_true', help='启动GUI界面')
    parser.add_argument('--init-config', action='store_true', help='初始化默认配置')
    parser.add_argument('--debug', action='store_true', help='启用DEBUG日志级别')
    
    args = parser.parse_args()
    
    # 如果启用debug，重新配置日志级别
    if args.debug:
        setup_logging(level=logging.DEBUG)
        logger.debug("DEBUG日志已启用")
    
    # 初始化配置
    if args.init_config:
        logger.info("初始化默认配置...")
        create_default_config('config/email.ini')
        create_default_alerts('config/alerts.json')
        logger.info("配置初始化完成，请编辑 config/email.ini 填入邮箱信息")
        return
    
    # GUI模式
    if args.gui:
        from gui import main as gui_main
        gui_main()
        return
    
    # 加载配置
    alert_manager = AlertManager('config/alerts.json')
    email_config = None
    try:
        email_config = load_email_config('config/email.ini')
    except Exception as e:
        logger.warning(f"加载邮件配置失败: {e}，将不发送邮件")
    
    if args.once:
        report, analysis = run_analysis_once(
            alert_manager, email_config, send_notification=True
        )
        print(report)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"报告已保存到: {args.output}")
        return
    
    # 定时任务
    logger.info(f"启动定时任务，间隔 {args.interval} 秒")
    
    while True:
        try:
            report, analysis = run_analysis_once(
                alert_manager, email_config, send_notification=True
            )
            print(report)
            
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(report)
            
            logger.info(f"等待 {args.interval} 秒后执行下一次...")
            time.sleep(args.interval)
            
        except KeyboardInterrupt:
            logger.info("程序已停止")
            break
        except Exception as e:
            logger.error(f"执行失败: {e}")
            time.sleep(60)


if __name__ == '__main__':
    main()
