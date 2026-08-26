#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件通知模块
支持 SMTP 发送分析报告和价格提醒
"""

import smtplib
import configparser
import logging
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from pathlib import Path
from app_paths import EMAIL_CONFIG, runtime_path

logger = logging.getLogger(__name__)


def load_email_config(config_path=EMAIL_CONFIG) -> configparser.ConfigParser:
    """加载邮件配置"""
    config = configparser.ConfigParser()
    config.read(runtime_path(config_path), encoding='utf-8')
    return config


def is_email_configured(config: configparser.ConfigParser) -> bool:
    """判断配置是否具备发送邮件所需的全部字段。"""
    if not config or not config.has_section('smtp'):
        return False
    required = ('server', 'port', 'user', 'password', 'recipients')
    if any(not config.get('smtp', key, fallback='').strip() for key in required):
        return False
    try:
        port = config.getint('smtp', 'port')
    except (ValueError, configparser.Error):
        return False
    return 1 <= port <= 65535


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


def send_analysis_report(config: configparser.ConfigParser, report: str, html_report: str = None) -> bool:
    """发送分析报告（支持纯文本和HTML格式）"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    subject = f"📊 黄金分析报告 - {now}"
    
    # 如果提供了HTML报告，使用multipart/alternative格式
    if html_report:
        try:
            html_content = html_report
            attachment_path = None
            try:
                candidate = Path(str(html_report)).expanduser()
                if candidate.is_file():
                    attachment_path = candidate.resolve()
                    html_content = attachment_path.read_text(encoding='utf-8')
            except (OSError, ValueError):
                # 原始 HTML 可能很长，或包含 Windows 路径不允许的字符；
                # 此时它本来就不是文件路径，直接作为邮件正文使用。
                attachment_path = None

            smtp_server = config.get('smtp', 'server')
            smtp_port = config.getint('smtp', 'port')
            smtp_user = config.get('smtp', 'user')
            smtp_pass = config.get('smtp', 'password')
            use_ssl = config.getboolean('smtp', 'ssl', fallback=True)
            recipients = [r.strip() for r in config.get('smtp', 'recipients').split(',')]
            
            msg = MIMEMultipart('mixed') if attachment_path else MIMEMultipart('alternative')
            msg['From'] = smtp_user
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject

            alternative = MIMEMultipart('alternative') if attachment_path else msg
            alternative.attach(MIMEText(report, 'plain', 'utf-8'))
            alternative.attach(MIMEText(html_content, 'html', 'utf-8'))
            if attachment_path:
                msg.attach(alternative)
                with attachment_path.open('rb') as f:
                    attachment = MIMEApplication(f.read(), _subtype='html')
                attachment.add_header(
                    'Content-Disposition', 'attachment', filename=attachment_path.name
                )
                msg.attach(attachment)
            
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                server.starttls()
            
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            server.quit()
            
            logger.info(
                "HTML邮件已发送: %s%s",
                subject,
                f"，附件={attachment_path.name}" if attachment_path else "",
            )
            return True
            
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False
    else:
        # 没有HTML报告，发送纯文本
        return send_email(config, subject, report)


def send_price_alert(config: configparser.ConfigParser, alert_msg: str, price: float, condition: str) -> bool:
    """发送价格提醒"""
    subject = f"⚠️ 金价提醒: {condition} @ {price:.2f}"
    return send_email(config, subject, alert_msg)


def create_default_config(config_path=EMAIL_CONFIG):
    """创建默认邮件配置"""
    config_path = runtime_path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    config = configparser.ConfigParser()
    config['smtp'] = {
        'server': 'smtp.qq.com',
        'port': '465',
        'user': '',
        'password': '',
        'ssl': 'true',
        'recipients': '',
    }
    config['options'] = {
        'send_report': 'false',
        'send_alert': 'false',
    }
    config['timer'] = {
        'align_to_midnight': 'true',
    }
    
    with config_path.open('w', encoding='utf-8') as f:
        config.write(f)
    
    logger.info(f"已创建默认邮件配置: {config_path}")
    return config


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    create_default_config()
    print("默认配置已创建，请编辑 config/email.ini 填入你的邮箱信息")
