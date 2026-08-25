#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件通知模块
支持 SMTP 发送分析报告和价格提醒
"""

import smtplib
import configparser
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)


def load_email_config(config_path: str = 'config/email.ini') -> configparser.ConfigParser:
    """加载邮件配置"""
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    return config


def send_email(config: configparser.ConfigParser, subject: str, body: str, html: bool = False) -> bool:
    """发送邮件"""
    try:
        smtp_server = config.get('smtp', 'server')
        smtp_port = config.getint('smtp', 'port')
        smtp_user = config.get('smtp', 'user')
        smtp_pass = config.get('smtp', 'password')
        use_ssl = config.getboolean('smtp', 'ssl', fallback=True)
        recipients = [r.strip() for r in config.get('smtp', 'recipients').split(',')]
        
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        
        content_type = 'html' if html else 'plain'
        msg.attach(MIMEText(body, content_type, 'utf-8'))
        
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
            server.starttls()
        
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"邮件已发送: {subject}")
        return True
        
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False


def send_analysis_report(config: configparser.ConfigParser, report: str) -> bool:
    """发送分析报告"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    subject = f"📊 黄金分析报告 - {now}"
    return send_email(config, subject, report)


def send_price_alert(config: configparser.ConfigParser, alert_msg: str, price: float, condition: str) -> bool:
    """发送价格提醒"""
    subject = f"⚠️ 金价提醒: {condition} @ {price:.2f}"
    return send_email(config, subject, alert_msg)


def create_default_config(config_path: str = 'config/email.ini'):
    """创建默认邮件配置"""
    import os
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    config = configparser.ConfigParser()
    config['smtp'] = {
        'server': 'smtp.qq.com',
        'port': '465',
        'user': 'your_email@qq.com',
        'password': 'your_auth_code',
        'ssl': 'true',
        'recipients': 'recipient@example.com',
    }
    
    with open(config_path, 'w', encoding='utf-8') as f:
        config.write(f)
    
    logger.info(f"已创建默认邮件配置: {config_path}")
    return config


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    create_default_config()
    print("默认配置已创建，请编辑 config/email.ini 填入你的邮箱信息")
