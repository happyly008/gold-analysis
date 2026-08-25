#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI界面模块 v3.1
适配新版信号引擎（方向层+执行层分层显示）
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import logging
from datetime import datetime
import sys
import os
import webbrowser
import matplotlib.font_manager as fm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import get_all_realtime, get_gold_klines, get_macro_data, get_all_sentiment_data
from analyzer import comprehensive_analysis, format_comprehensive_report
from fundamental_analyzer import format_fundamental_report
from sentiment_analyzer import format_sentiment_report
from geopolitical import GeopoliticalMonitor, format_geopolitical_report
from economic_calendar import EconomicCalendar, format_calendar_report
from correlation_analysis import correlation_analysis, format_correlation_report
from alerts import AlertManager, PriceAlert
from notifier import send_analysis_report, send_price_alert, load_email_config
from html_report import generate_html_report

logger = logging.getLogger(__name__)


class GoldAnalysisGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("\u9ec4\u91d1\u7efc\u5408\u5206\u6790\u7cfb\u7edf v3.1")
        self.root.geometry("1200x850")

        self.running = False
        self.analyzing = False  # 防止重复点击
        self.send_report_var = tk.BooleanVar(value=True)   # 是否发送分析报告
        self.send_alert_var = tk.BooleanVar(value=True)    # 是否发送价格提醒
        self.alert_manager = AlertManager()
        self.email_config = None
        self.geo_monitor = GeopoliticalMonitor()
        self.economic_calendar = EconomicCalendar()
        self.latest_html_path = None
        self.latest_analysis = None

        # 检测中文字体
        self.chinese_font = self._detect_chinese_font()
        logger.info(f"检测到中文字体: {self.chinese_font}")

        self.setup_ui()
        self.load_config()

    def _detect_chinese_font(self) -> str:
        """检测系统中可用的中文字体"""
        chinese_fonts = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 
                         'Noto Sans CJK SC', 'Source Han Sans SC', 'AR PL UMing CN']
        available = {f.name for f in fm.fontManager.ttflist}
        for font in chinese_fonts:
            if font in available:
                return font
        return 'DejaVu Sans'  # fallback

    def setup_ui(self):
        # \u9876\u90e8\u63a7\u5236\u680f
        control_frame = ttk.Frame(self.root, padding="5")
        control_frame.pack(fill=tk.X)

        self.btn_analyze = ttk.Button(control_frame, text="\u7acb\u5373\u5206\u6790", command=self.run_analysis)
        self.btn_analyze.pack(side=tk.LEFT, padx=5)
        self.btn_start = ttk.Button(control_frame, text="\u542f\u52a8\u5b9a\u65f6", command=self.start_schedule)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = ttk.Button(control_frame, text="\u505c\u6b62\u5b9a\u65f6", command=self.stop_schedule, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)
        self.btn_html = ttk.Button(control_frame, text="HTML\u62a5\u544a", command=self.open_html_report)
        self.btn_html.pack(side=tk.LEFT, padx=5)

        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Label(control_frame, text="\u95f4\u9694(\u79d2):").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value="3600")
        ttk.Entry(control_frame, textvariable=self.interval_var, width=8).pack(side=tk.LEFT, padx=5)

        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        self.status_label = ttk.Label(control_frame, text="\u5c31\u7eea", foreground="green")
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # Notebook
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 1: \u5b9e\u65f6\u884c\u60c5
        tab1 = ttk.Frame(notebook)
        notebook.add(tab1, text="\u5b9e\u65f6\u884c\u60c5")
        self.realtime_text = scrolledtext.ScrolledText(tab1, wrap=tk.WORD, font=("Consolas", 11))
        self.realtime_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 2: \u7efc\u5408\u62a5\u544a
        tab2 = ttk.Frame(notebook)
        notebook.add(tab2, text="\u7efc\u5408\u62a5\u544a")
        self.analysis_text = scrolledtext.ScrolledText(tab2, wrap=tk.WORD, font=("Consolas", 10))
        self.analysis_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 3: \u4fe1\u53f7\u9762\u677f\uff08\u65b0\u589e\uff09
        tab3 = ttk.Frame(notebook)
        notebook.add(tab3, text="\u4fe1\u53f7\u9762\u677f")
        self.signal_text = scrolledtext.ScrolledText(tab3, wrap=tk.WORD, font=("Consolas", 11))
        self.signal_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 4: \u57fa\u672c\u9762
        tab4 = ttk.Frame(notebook)
        notebook.add(tab4, text="\u57fa\u672c\u9762")
        self.fundamental_text = scrolledtext.ScrolledText(tab4, wrap=tk.WORD, font=("Consolas", 10))
        self.fundamental_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 5: \u8d44\u91d1\u9762
        tab5 = ttk.Frame(notebook)
        notebook.add(tab5, text="\u8d44\u91d1\u9762")
        self.sentiment_text = scrolledtext.ScrolledText(tab5, wrap=tk.WORD, font=("Consolas", 10))
        self.sentiment_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 6: \u5730\u7f18\u653f\u6cbb
        tab6 = ttk.Frame(notebook)
        notebook.add(tab6, text="\u5730\u7f18\u653f\u6cbb")
        self.geopolitical_text = scrolledtext.ScrolledText(tab6, wrap=tk.WORD, font=("Consolas", 10))
        self.geopolitical_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 7: \u76f8\u5173\u6027\u9a8c\u8bc1
        tab7 = ttk.Frame(notebook)
        notebook.add(tab7, text="\u76f8\u5173\u6027\u9a8c\u8bc1")
        self.correlation_text = scrolledtext.ScrolledText(tab7, wrap=tk.WORD, font=("Consolas", 10))
        self.correlation_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 8: \u7ecf\u6d4e\u65e5\u5386
        tab8 = ttk.Frame(notebook)
        notebook.add(tab8, text="\u7ecf\u6d4e\u65e5\u5386")
        self.calendar_text = scrolledtext.ScrolledText(tab8, wrap=tk.WORD, font=("Consolas", 10))
        self.calendar_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 9: 设置（合并所有配置）
        tab9 = ttk.Frame(notebook)
        notebook.add(tab9, text="设置")
        
        # 创建滚动容器
        canvas = tk.Canvas(tab9)
        scrollbar = ttk.Scrollbar(tab9, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 1. 邮件发送选项
        option_frame = ttk.LabelFrame(scrollable_frame, text="邮件发送选项", padding="10")
        option_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Checkbutton(option_frame, text="分析完成后发送报告邮件", variable=self.send_report_var).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(option_frame, text="价格触发时发送提醒邮件", variable=self.send_alert_var).pack(anchor=tk.W, pady=2)
        
        # 2. SMTP设置
        email_frame = ttk.LabelFrame(scrollable_frame, text="SMTP邮件服务器设置", padding="10")
        email_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(email_frame, text="SMTP服务器:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.smtp_server_var = tk.StringVar(value="smtp.qq.com")
        ttk.Entry(email_frame, textvariable=self.smtp_server_var, width=30).grid(row=0, column=1, padx=5)
        
        ttk.Label(email_frame, text="端口:").grid(row=0, column=2, sticky=tk.W)
        self.smtp_port_var = tk.StringVar(value="465")
        ttk.Entry(email_frame, textvariable=self.smtp_port_var, width=8).grid(row=0, column=3, padx=5)
        
        ttk.Label(email_frame, text="发件人:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.smtp_user_var = tk.StringVar()
        ttk.Entry(email_frame, textvariable=self.smtp_user_var, width=30).grid(row=1, column=1, padx=5)
        
        ttk.Label(email_frame, text="授权码:").grid(row=1, column=2, sticky=tk.W)
        self.smtp_pass_var = tk.StringVar()
        ttk.Entry(email_frame, textvariable=self.smtp_pass_var, width=20, show="*").grid(row=1, column=3, padx=5)
        
        ttk.Label(email_frame, text="收件人:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.smtp_recipients_var = tk.StringVar()
        ttk.Entry(email_frame, textvariable=self.smtp_recipients_var, width=40).grid(row=2, column=1, columnspan=2, padx=5)
        
        ttk.Label(email_frame, text="SSL:").grid(row=2, column=3, sticky=tk.W)
        self.smtp_ssl_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(email_frame, variable=self.smtp_ssl_var).grid(row=2, column=4, padx=5)
        
        btn_frame = ttk.Frame(email_frame)
        btn_frame.grid(row=3, column=0, columnspan=5, pady=10)
        ttk.Button(btn_frame, text="保存邮件设置", command=self.save_email_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="发送测试邮件", command=self.send_test_email).pack(side=tk.LEFT, padx=5)
        
        # 3. 定时任务设置
        timer_frame = ttk.LabelFrame(scrollable_frame, text="定时任务设置", padding="10")
        timer_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.align_to_midnight_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(timer_frame, text="对齐到0点0分0秒（从午夜开始计时周期）", variable=self.align_to_midnight_var).pack(anchor=tk.W, pady=2)
        ttk.Label(timer_frame, text="(开启后定时任务周期从每天0:00开始对齐，关闭则立即开始计时)", foreground="gray").pack(anchor=tk.W)
        
        # 4. 价格提醒设置
        alert_frame = ttk.LabelFrame(scrollable_frame, text="价格提醒设置", padding="10")
        alert_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.alert_tree = ttk.Treeview(alert_frame,
            columns=("name", "condition", "threshold", "enabled"),
            show="headings", height=8)
        self.alert_tree.heading("name", text="名称")
        self.alert_tree.heading("condition", text="条件")
        self.alert_tree.heading("threshold", text="阈值")
        self.alert_tree.heading("enabled", text="启用")
        self.alert_tree.column("name", width=150)
        self.alert_tree.column("condition", width=100)
        self.alert_tree.column("threshold", width=100)
        self.alert_tree.column("enabled", width=80)
        self.alert_tree.pack(fill=tk.X, pady=5)
        
        add_frame = ttk.Frame(alert_frame)
        add_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(add_frame, text="名称:").grid(row=0, column=0, sticky=tk.W, padx=2)
        self.alert_name_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.alert_name_var, width=15).grid(row=0, column=1, padx=2)
        
        ttk.Label(add_frame, text="条件:").grid(row=0, column=2, sticky=tk.W, padx=2)
        self.alert_condition_var = tk.StringVar(value="above")
        ttk.Combobox(add_frame, textvariable=self.alert_condition_var,
                    values=["above", "below", "change_pct"], width=10).grid(row=0, column=3, padx=2)
        
        ttk.Label(add_frame, text="阈值:").grid(row=0, column=4, sticky=tk.W, padx=2)
        self.alert_threshold_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.alert_threshold_var, width=10).grid(row=0, column=5, padx=2)
        
        ttk.Button(add_frame, text="添加", command=self.add_alert).grid(row=0, column=6, padx=5)
        ttk.Button(add_frame, text="删除", command=self.remove_alert).grid(row=0, column=7, padx=5)
        
        self.refresh_alert_list()

        # \u5e95\u90e8\u65e5\u5fd7
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.log_text = scrolledtext.ScrolledText(status_frame, height=4, font=("Consolas", 9))
        self.log_text.pack(fill=tk.X, padx=5, pady=5)

    def load_config(self):
        try:
            self.email_config = load_email_config('config/email.ini')
            if self.email_config.has_section('smtp'):
                self.smtp_server_var.set(self.email_config.get('smtp', 'server', fallback=''))
                self.smtp_port_var.set(self.email_config.get('smtp', 'port', fallback=''))
                self.smtp_user_var.set(self.email_config.get('smtp', 'user', fallback=''))
                self.smtp_recipients_var.set(self.email_config.get('smtp', 'recipients', fallback=''))
            # 读取邮件选项状态
            if self.email_config.has_section('options'):
                self.send_report_var.set(self.email_config.getboolean('options', 'send_report', fallback=True))
                self.send_alert_var.set(self.email_config.getboolean('options', 'send_alert', fallback=True))
            # 读取对齐时间配置
            if self.email_config.has_section('timer'):
                self.align_hour_var.set(self.email_config.get('timer', 'hour', fallback='0'))
                self.align_minute_var.set(self.email_config.get('timer', 'minute', fallback='0'))
                self.align_second_var.set(self.email_config.get('timer', 'second', fallback='0'))
        except Exception as e:
            self.log(f"加载配置失败: {e}")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        logger.info(message)

    def open_html_report(self):
        if self.latest_html_path and os.path.exists(self.latest_html_path):
            webbrowser.open(f'file://{self.latest_html_path}')
        else:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u5148\u70b9\u51fb\u201c\u7acb\u5373\u5206\u6790\u201d\u751f\u6210\u62a5\u544a")

    def run_analysis(self):
        if self.analyzing:
            self.log("\u5206\u6790\u6b63\u5728\u8fdb\u884c\u4e2d\uff0c\u8bf7\u7a0d\u5019...")
            return
        self.analyzing = True
        self.btn_analyze.config(state=tk.DISABLED)
        self.status_label.config(text="\u5206\u6790\u4e2d...", foreground="orange")
        self.log("\u5f00\u59cb\u5206\u6790...")

        def analysis_thread():
            try:
                realtime = get_all_realtime()
                klines = get_gold_klines()
                macro_data = get_macro_data()
                sentiment_data = get_all_sentiment_data()

                analysis = comprehensive_analysis(realtime, klines, macro_data, sentiment_data, self.geo_monitor)
                self.latest_analysis = analysis

                report = format_comprehensive_report(analysis, realtime, macro_data)
                fund_report = format_fundamental_report(analysis['fundamental'], macro_data)
                sent_report = format_sentiment_report(analysis['sentiment'])
                geo_report = format_geopolitical_report(
                    analysis['geopolitical'].get('risk', {})) if analysis.get('geopolitical') else '\u6682\u65e0\u6570\u636e'

                self.economic_calendar.refresh()
                cal_report = format_calendar_report(self.economic_calendar, days=7)

                corr_result = correlation_analysis(klines)
                corr_report = format_correlation_report(corr_result)

                html_path = generate_html_report(analysis, realtime, klines, macro_data)
                self.latest_html_path = html_path

                self.root.after(0, self.update_realtime_display, realtime, macro_data)
                self.root.after(0, self.update_analysis_display, report)
                self.root.after(0, self.update_signal_display, analysis)
                self.root.after(0, self.update_fundamental_display, fund_report)
                self.root.after(0, self.update_sentiment_display, sent_report)
                self.root.after(0, self.update_geopolitical_display, geo_report)
                self.root.after(0, self.update_correlation_display, corr_report)
                self.root.after(0, self.update_calendar_display, cal_report)

                # 发送分析报告邮件（可选）
                self.root.after(0, self.log, f"邮件配置: {self.email_config is not None}, 发送报告: {self.send_report_var.get()}")
                if self.email_config and self.send_report_var.get():
                    try:
                        self.root.after(0, self.log, "正在发送分析报告邮件...")
                        result = send_analysis_report(self.email_config, report)
                        if result:
                            self.root.after(0, self.log, "分析报告已发送至邮箱")
                        else:
                            self.root.after(0, self.log, "邮件发送返回False")
                    except Exception as e:
                        self.root.after(0, self.log, f"邮件发送失败: {e}")
                        logger.error(f"GUI邮件发送异常: {e}", exc_info=True)

                current_price = realtime.get('gold', {}).get('price', 0)
                triggered = self.alert_manager.check_price(current_price)
                if triggered and self.email_config and self.send_alert_var.get():
                    for ad in triggered:
                        msg = self.alert_manager.format_alert_message(ad)
                        send_price_alert(self.email_config, msg, current_price, ad['name'])
                        self.root.after(0, self.log, f"\u89e6\u53d1\u63d0\u9192: {ad['name']}")

                self.root.after(0, self.status_label.config, {"text": "\u5206\u6790\u5b8c\u6210", "foreground": "green"})
                self.root.after(0, self.log, "\u5206\u6790\u5b8c\u6210")
                self.root.after(0, self._analysis_done)

            except Exception as e:
                self.root.after(0, self.status_label.config, {"text": "\u5206\u6790\u5931\u8d25", "foreground": "red"})
                self.root.after(0, self.log, f"\u5206\u6790\u5931\u8d25: {e}")
                logger.error(f"\u5206\u6790\u5931\u8d25: {e}", exc_info=True)
                self.root.after(0, self._analysis_done)

        threading.Thread(target=analysis_thread, daemon=True).start()

    def update_realtime_display(self, realtime, macro_data):
        self.realtime_text.delete(1.0, tk.END)
        lines = []
        lines.append("=" * 60)
        lines.append(f"\u66f4\u65b0\u65f6\u95f4: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)

        gold = realtime.get('gold', {})
        if gold:
            lines.append(f"\n\u3010\u4f26\u6566\u91d1\u3011")
            lines.append(f"  \u73b0\u4ef7: {gold.get('price', 0):.2f}")
            lines.append(f"  \u6700\u9ad8: {gold.get('high', 0):.2f}  \u6700\u4f4e: {gold.get('low', 0):.2f}")
            lines.append(f"  \u5f00\u76d8: {gold.get('open', 0):.2f}")

        usd = realtime.get('usd_index', {})
        if usd:
            lines.append(f"\n\u3010\u7f8e\u5143\u6307\u6570\u3011 {usd.get('price', 0):.2f}")

        oil = realtime.get('oil', {})
        if oil:
            lines.append(f"\n\u3010\u7ebd\u7ea6\u539f\u6cb9\u3011 {oil.get('price', 0):.2f}")

        silver = realtime.get('silver', {})
        if silver:
            lines.append(f"\n\u3010\u7ebd\u7ea6\u767d\u94f6\u3011 {silver.get('price', 0):.2f}")

        if 'gold_silver_ratio' in realtime:
            lines.append(f"  \u91d1\u94f6\u6bd4: {realtime['gold_silver_ratio']:.2f}")

        if macro_data:
            lines.append(f"\n\u3010\u5b8f\u89c2\u6570\u636e\u3011")
            if 'real_rate' in macro_data:
                lines.append(f"  \u5b9e\u9645\u5229\u7387: {macro_data['real_rate'].get('value', 0):.2f}%")
            if 'us10y' in macro_data:
                lines.append(f"  10Y\u56fd\u503a: {macro_data['us10y'].get('value', 0):.2f}%")
            if 'inflation_expect' in macro_data:
                lines.append(f"  \u901a\u80c0\u9884\u671f: {macro_data['inflation_expect'].get('value', 0):.2f}%")
            if 'fed_rate' in macro_data:
                lines.append(f"  \u8054\u90a6\u57fa\u91d1\u5229\u7387: {macro_data['fed_rate'].get('value', 0):.2f}%")
            if 'vix' in macro_data:
                lines.append(f"  VIX: {macro_data['vix'].get('value', 0):.2f}")
            if 'unemployment_rate' in macro_data:
                lines.append(f"  \u5931\u4e1a\u7387: {macro_data['unemployment_rate'].get('value', 0):.1f}%")
            if 'cpi_yoy' in macro_data:
                lines.append(f"  CPI\u540c\u6bd4: {macro_data['cpi_yoy'].get('value', 0):.1f}%")
            if 'core_pce_yoy' in macro_data:
                lines.append(f"  \u6838\u5fc3PCE: {macro_data['core_pce_yoy'].get('value', 0):.1f}%")
            if 'gdp_growth' in macro_data:
                lines.append(f"  GDP\u589e\u901f: {macro_data['gdp_growth'].get('value', 0):.1f}%")

        self.realtime_text.insert(tk.END, '\n'.join(lines))

    def update_analysis_display(self, report):
        self.analysis_text.delete(1.0, tk.END)
        self.analysis_text.insert(tk.END, report)

    def update_signal_display(self, analysis):
        """\u4fe1\u53f7\u9762\u677f - \u5206\u5c42\u663e\u793a\u65b9\u5411+\u6267\u884c+\u5efa\u8bae"""
        self.signal_text.delete(1.0, tk.END)
        signals = analysis.get('signals', {})
        technical = analysis.get('technical', {})

        lines = []
        lines.append("=" * 60)
        lines.append("\u4fe1\u53f7\u9762\u677f v3.1")
        lines.append("=" * 60)

        # \u65b9\u5411\u5c42
        direction = signals.get('direction', 'neutral')
        dir_map = {'bullish': '\U0001f7e2 \u770b\u591a', 'bearish': '\U0001f534 \u770b\u7a7a', 'neutral': '\u26aa \u4e2d\u6027'}
        lines.append(f"\n\u3010\u65b9\u5411\u5c42\u3011")
        lines.append(f"  \u4e3b\u65b9\u5411: {dir_map.get(direction, direction)}")

        layer_scores = technical.get('layer_scores', {})
        layer_dirs = technical.get('layer_directions', {})
        if layer_scores:
            lines.append(f"\n  \u5206\u5c42\u72b6\u6001:")
            for layer_name in ['\u8d8b\u52bf', '\u6ce2\u6bb5', '\u65e5\u5185']:
                score = layer_scores.get(layer_name, 0)
                d = layer_dirs.get(layer_name, 'neutral')
                emoji = {'bullish': '\U0001f7e2', 'bearish': '\U0001f534', 'neutral': '\u26aa'}.get(d, '\u26aa')
                lines.append(f"    {emoji} {layer_name}: {score:+.2f} ({d})")

        lines.append(f"\n  \u4e00\u81f4\u6027: {technical.get('agreement', 0):.0f}%")
        lines.append(f"  \u7f6e\u4fe1\u5ea6: {technical.get('confidence', 0):.0f}%")

        # \u6267\u884c\u5c42
        execution = signals.get('execution', [])
        lines.append(f"\n\u3010\u6267\u884c\u5c42\u3011({len(execution)}\u4e2a\u4fe1\u53f7)")
        if execution:
            for sig in execution[:15]:
                emoji = '\U0001f7e2' if sig['type'] == 'BUY' else '\U0001f534'
                lines.append(f"  {emoji} {sig['type']} [{sig['layer']}-{sig['timeframe']}] {sig['reason']}")
        else:
            lines.append("  \u6682\u65e0\u4ea4\u53c9\u4fe1\u53f7\uff08\u7b49\u5f85MACD/KDJ\u91d1\u53c9\u6216\u6b7b\u53c9\u89e6\u53d1\uff09")

        # \u51b2\u7a81
        conflicts = signals.get('conflicts', [])
        if conflicts:
            lines.append(f"\n\u3010\u51b2\u7a81\u8b66\u544a\u3011")
            for c in conflicts:
                lines.append(f"  \u26a0\ufe0f {c['description']}")

        # \u64cd\u4f5c\u5efa\u8bae
        rec = signals.get('recommendation', {})
        if rec:
            lines.append(f"\n{'=' * 60}")
            lines.append("\u3010\u64cd\u4f5c\u5efa\u8bae\u3011")
            lines.append(f"  \u64cd\u4f5c: {rec.get('action', 'N/A')}")
            lines.append(f"  \u7b56\u7565: {rec.get('strategy', 'N/A')}")
            lines.append(f"  \u5165\u573a: {rec.get('entry', 'N/A')}")
            lines.append(f"  \u4ed3\u4f4d: {rec.get('position', 'N/A')}")
            lines.append(f"  \u6b62\u635f: {rec.get('stop_loss', 'N/A')}")
            lines.append(f"  \u76ee\u6807: {rec.get('target', 'N/A')}")
            lines.append(f"  \u6761\u4ef6: {rec.get('condition', 'N/A')}")

        lines.append(f"\n{'=' * 60}")
        lines.append("\u26a0\ufe0f \u4ee5\u4e0a\u4ec5\u4f9b\u53c2\u8003\uff0c\u4e0d\u6784\u6210\u6295\u8d44\u5efa\u8bae\u3002")

        self.signal_text.insert(tk.END, '\n'.join(lines))

    def update_fundamental_display(self, report):
        self.fundamental_text.delete(1.0, tk.END)
        self.fundamental_text.insert(tk.END, report)

    def update_sentiment_display(self, report):
        self.sentiment_text.delete(1.0, tk.END)
        self.sentiment_text.insert(tk.END, report)

    def update_geopolitical_display(self, report):
        self.geopolitical_text.delete(1.0, tk.END)
        self.geopolitical_text.insert(tk.END, report)

    def update_correlation_display(self, report):
        self.correlation_text.delete(1.0, tk.END)
        self.correlation_text.insert(tk.END, report)

    def update_calendar_display(self, report):
        self.calendar_text.delete(1.0, tk.END)
        self.calendar_text.insert(tk.END, report)

    def _analysis_done(self):
        """分析完成后恢复按钮状态"""
        self.analyzing = False
        self.btn_analyze.config(state=tk.NORMAL)

    def start_schedule(self):
        if self.running:
            self.log("\u5b9a\u65f6\u4efb\u52a1\u5df2\u5728\u8fd0\u884c")
            return
        try:
            interval = int(self.interval_var.get())
        except ValueError:
            messagebox.showerror("\u9519\u8bef", "\u8bf7\u8f93\u5165\u6709\u6548\u95f4\u9694")
            return
        self.running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status_label.config(text=f"\u5b9a\u65f6\u8fd0\u884c\u4e2d ({interval}\u79d2)", foreground="green")
        
        # 根据开关决定是否对齐到0点
        from datetime import datetime, timedelta
        now = datetime.now()
        
        if self.align_to_midnight_var.get():
            # 对齐到0点0分0秒
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elapsed = (now - midnight).total_seconds()
            periods_passed = int(elapsed / interval)
            next_run = midnight + timedelta(seconds=(periods_passed + 1) * interval)
            wait_seconds = (next_run - now).total_seconds()
            
            self.log(f"启动定时，间隔{interval}秒，已对齐到0点")
            self.log(f"下次执行: {next_run.strftime('%H:%M:%S')} ({int(wait_seconds)}秒后)")

            def loop():
                # 先立即执行一次
                self.run_analysis()
                # 等待到对齐点
                time.sleep(wait_seconds)
                while self.running:
                    self.run_analysis()
                    time.sleep(interval)
        else:
            # 不对齐，立即开始
            self.log(f"启动定时，间隔{interval}秒，立即开始")

            def loop():
                self.run_analysis()
                while self.running:
                    time.sleep(interval)
                    if self.running:
                        self.run_analysis()
        
        threading.Thread(target=loop, daemon=True).start()

    def stop_schedule(self):
        self.running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_label.config(text="\u5df2\u505c\u6b62", foreground="gray")
        self.log("\u5b9a\u65f6\u5df2\u505c\u6b62")

    def add_alert(self):
        name = self.alert_name_var.get()
        condition = self.alert_condition_var.get()
        threshold_str = self.alert_threshold_var.get()
        if not name or not threshold_str:
            messagebox.showerror("\u9519\u8bef", "\u8bf7\u586b\u5199\u540d\u79f0\u548c\u9608\u503c")
            return
        try:
            threshold = float(threshold_str)
        except ValueError:
            messagebox.showerror("\u9519\u8bef", "\u9608\u503c\u5fc5\u987b\u662f\u6570\u5b57")
            return
        alert = PriceAlert(name, condition, threshold)
        self.alert_manager.add_alert(alert)
        self.refresh_alert_list()
        self.alert_name_var.set('')
        self.alert_threshold_var.set('')
        self.log(f"\u5df2\u6dfb\u52a0\u63d0\u9192: {name}")

    def remove_alert(self):
        selected = self.alert_tree.selection()
        if not selected:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u5148\u9009\u62e9")
            return
        item = self.alert_tree.item(selected[0])
        name = item['values'][0]
        self.alert_manager.remove_alert(name)
        self.refresh_alert_list()
        self.log(f"\u5df2\u5220\u9664\u63d0\u9192: {name}")

    def refresh_alert_list(self):
        for item in self.alert_tree.get_children():
            self.alert_tree.delete(item)
        for alert in self.alert_manager.alerts:
            cm = {'above': '\u7a81\u7834\u4e0a\u65b9', 'below': '\u8dcc\u7834\u4e0b\u65b9', 'change_pct': '\u6ce2\u52a8%'}
            self.alert_tree.insert('', 'end', values=(
                alert.name, cm.get(alert.condition, alert.condition),
                alert.threshold, '\u2713' if alert.enabled else '\u2717'))

    def save_email_config(self):
        import configparser
        config = configparser.ConfigParser()
        config['smtp'] = {
            'server': self.smtp_server_var.get(),
            'port': self.smtp_port_var.get(),
            'user': self.smtp_user_var.get(),
            'password': self.smtp_pass_var.get(),
            'ssl': str(self.smtp_ssl_var.get()).lower(),
            'recipients': self.smtp_recipients_var.get(),
        }
        # 保存邮件选项状态
        config['options'] = {
            'send_report': str(self.send_report_var.get()).lower(),
            'send_alert': str(self.send_alert_var.get()).lower(),
        }
        # 保存对齐时间配置
        config['timer'] = {
            'hour': self.align_hour_var.get(),
            'minute': self.align_minute_var.get(),
            'second': self.align_second_var.get(),
        }
        os.makedirs('config', exist_ok=True)
        with open('config/email.ini', 'w', encoding='utf-8') as f:
            config.write(f)
        self.email_config = config
        self.log("配置已保存")
        messagebox.showinfo("成功", "配置已保存")

    def send_test_email(self):
        if not self.email_config:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u5148\u4fdd\u5b58\u914d\u7f6e")
            return
        def test():
            ok = send_analysis_report(self.email_config, "\u6d4b\u8bd5\u90ae\u4ef6\n\n\u9ec4\u91d1\u5206\u6790\u7cfb\u7edf")
            if ok:
                self.root.after(0, messagebox.showinfo, "\u6210\u529f", "\u6d4b\u8bd5\u90ae\u4ef6\u5df2\u53d1\u9001")
            else:
                self.root.after(0, messagebox.showerror, "\u5931\u8d25", "\u53d1\u9001\u5931\u8d25\uff0c\u68c0\u67e5\u914d\u7f6e")
        threading.Thread(target=test, daemon=True).start()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    root = tk.Tk()
    app = GoldAnalysisGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
