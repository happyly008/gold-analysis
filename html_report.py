#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML图表化报告生成器
生成包含图表的HTML格式分析报告
"""

import os
import base64
from io import BytesIO
from datetime import datetime
from typing import Dict, List
import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import logging

logger = logging.getLogger(__name__)

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def fig_to_base64(fig) -> str:
    """将matplotlib图表转换为base64编码"""
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return img_base64


def parse_time(time_val):
    """解析时间字段，支持字符串和数字格式"""
    if isinstance(time_val, str):
        # 尝试解析日期字符串
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y%m%d']:
            try:
                return datetime.strptime(time_val, fmt)
            except ValueError:
                continue
        return datetime.now()
    elif isinstance(time_val, (int, float)):
        return datetime.fromtimestamp(time_val)
    else:
        return datetime.now()


def create_price_chart(candles: List[Dict], title: str = "黄金价格走势") -> str:
    """创建价格走势图"""
    if not candles or len(candles) < 2:
        return ""
    
    # 取最近60个数据点
    recent = candles[-60:] if len(candles) > 60 else candles
    
    dates = [parse_time(c['time']) for c in recent]
    closes = [c['close'] for c in recent]
    highs = [c['high'] for c in recent]
    lows = [c['low'] for c in recent]
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), height_ratios=[3, 1])
    
    # 价格图
    ax1.plot(dates, closes, 'b-', linewidth=1.5, label='收盘价')
    ax1.fill_between(dates, lows, highs, alpha=0.2, color='blue')
    ax1.set_title(title, fontsize=14, fontweight='bold')
    ax1.set_ylabel('价格 (USD)')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left')
    
    # 添加最新价格标注
    latest_price = closes[-1]
    ax1.annotate(f'${latest_price:.2f}', 
                xy=(dates[-1], latest_price),
                xytext=(10, 10), textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.7),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
    
    # 成交量图
    volumes = [c.get('volume', 0) for c in recent]
    colors = ['green' if closes[i] >= closes[i-1] else 'red' 
              for i in range(1, len(closes))]
    colors.insert(0, 'green')
    
    ax2.bar(dates, volumes, color=colors, alpha=0.6, width=0.8)
    ax2.set_ylabel('成交量')
    ax2.set_xlabel('时间')
    ax2.grid(True, alpha=0.3)
    
    # 格式化x轴日期
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    return fig_to_base64(fig)


def create_indicator_chart(candles: List[Dict], indicators: Dict) -> str:
    """创建技术指标图表"""
    if not candles or len(candles) < 30:
        return ""
    
    recent = candles[-60:] if len(candles) > 60 else candles
    dates = [parse_time(c['time']) for c in recent]
    closes = [c['close'] for c in recent]
    
    fig, axes = plt.subplots(3, 1, figsize=(10, 8))
    
    # 价格 + 均线
    ax1 = axes[0]
    ax1.plot(dates, closes, 'k-', linewidth=1.5, label='价格')
    
    # 计算并绘制均线
    for period, color in [(5, 'blue'), (10, 'orange'), (20, 'purple')]:
        if len(closes) >= period:
            ma = []
            for i in range(len(closes)):
                if i < period - 1:
                    ma.append(None)
                else:
                    ma.append(sum(closes[i-period+1:i+1]) / period)
            ax1.plot(dates, ma, color=color, linewidth=1, label=f'MA{period}')
    
    ax1.set_title('价格与均线', fontsize=12)
    ax1.set_ylabel('价格')
    ax1.legend(loc='upper left', fontsize=8)
    ax1.grid(True, alpha=0.3)
    
    # MACD
    ax2 = axes[1]
    if 'macd' in indicators:
        macd_data = indicators['macd']
        # 简化显示
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax2.text(0.5, 0.5, f"MACD: DIF={macd_data.get('dif', 0):.2f}, DEA={macd_data.get('dea', 0):.2f}",
                transform=ax2.transAxes, ha='center', fontsize=10)
    ax2.set_title('MACD指标')
    ax2.set_ylabel('MACD')
    ax2.grid(True, alpha=0.3)
    
    # RSI
    ax3 = axes[2]
    if 'rsi14' in indicators:
        rsi = indicators['rsi14']
        ax3.axhline(y=70, color='red', linestyle='--', linewidth=0.8, label='超买(70)')
        ax3.axhline(y=30, color='green', linestyle='--', linewidth=0.8, label='超卖(30)')
        ax3.axhline(y=50, color='gray', linestyle='-', linewidth=0.5)
        ax3.fill_between([0, 1], 70, 100, alpha=0.1, color='red')
        ax3.fill_between([0, 1], 0, 30, alpha=0.1, color='green')
        ax3.text(0.5, rsi, f'RSI={rsi:.1f}', transform=ax3.get_xaxis_transform(),
                ha='center', fontsize=10, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax3.set_ylim(0, 100)
    ax3.set_title('RSI指标(14)')
    ax3.set_ylabel('RSI')
    ax3.legend(loc='upper right', fontsize=8)
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig_to_base64(fig)


def create_score_gauge(scores: Dict) -> str:
    """创建得分仪表盘"""
    fig, ax = plt.subplots(figsize=(8, 3))
    
    categories = ['技术面', '基本面', '资金面', '地缘']
    values = [
        scores.get('technical', 0),
        scores.get('fundamental', 0),
        scores.get('sentiment', 0),
        scores.get('geopolitical', 0)
    ]
    
    colors = ['#2196F3', '#4CAF50', '#FF9800', '#F44336']
    
    bars = ax.barh(categories, values, color=colors, height=0.6)
    
    # 添加数值标签
    for bar, val in zip(bars, values):
        width = bar.get_width()
        ax.text(width + 0.1 if width >= 0 else width - 0.1,
                bar.get_y() + bar.get_height()/2,
                f'{val:.2f}',
                ha='left' if width >= 0 else 'right',
                va='center', fontsize=12, fontweight='bold')
    
    ax.set_xlim(-5, 5)
    ax.axvline(x=0, color='black', linewidth=1)
    ax.set_title('三体系得分对比', fontsize=14, fontweight='bold')
    ax.grid(True, axis='x', alpha=0.3)
    
    plt.tight_layout()
    return fig_to_base64(fig)


def generate_html_report(analysis: Dict, realtime: Dict, klines: Dict, 
                         macro_data: Dict, output_path: str = None) -> str:
    """生成HTML报告"""
    
    # 生成图表
    price_chart = ""
    indicator_chart = ""
    score_gauge = ""
    
    if klines and 'daily' in klines:
        price_chart = create_price_chart(klines['daily'], "黄金日线走势图")
    
    if klines and 'daily' in klines:
        from indicators import calc_all_indicators
        indicators = calc_all_indicators(klines['daily'])
        indicator_chart = create_indicator_chart(klines['daily'], indicators)
    
    scores = {
        'technical': analysis.get('technical', {}).get('combined_score', 0),
        'fundamental': analysis.get('fundamental', {}).get('combined_score', 0),
        'sentiment': analysis.get('sentiment', {}).get('combined_score', 0)
    }
    score_gauge = create_score_gauge(scores)
    
    # 构建HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>黄金三体系分析报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
    <style>
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
        }}
        .header .time {{
            margin-top: 10px;
            opacity: 0.9;
        }}
        .card {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .card h2 {{
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            margin-top: 0;
        }}
        .price-info {{
            display: flex;
            justify-content: space-around;
            flex-wrap: wrap;
        }}
        .price-item {{
            text-align: center;
            padding: 15px;
            min-width: 150px;
        }}
        .price-item .label {{
            color: #666;
            font-size: 14px;
        }}
        .price-item .value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
            margin-top: 5px;
        }}
        .price-item .change {{
            font-size: 14px;
            margin-top: 5px;
        }}
        .up {{ color: #f44336; }}
        .down {{ color: #4CAF50; }}
        .verdict {{
            text-align: center;
            padding: 20px;
            font-size: 32px;
            font-weight: bold;
        }}
        .verdict.bullish {{ color: #f44336; }}
        .verdict.bearish {{ color: #4CAF50; }}
        .verdict.neutral {{ color: #FF9800; }}
        .score-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .score-table th, .score-table td {{
            padding: 12px;
            text-align: center;
            border: 1px solid #ddd;
        }}
        .score-table th {{
            background: #f5f5f5;
        }}
        .chart-container {{
            text-align: center;
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 5px;
        }}
        .signals {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .signal {{
            padding: 10px 15px;
            border-radius: 5px;
            font-size: 14px;
        }}
        .signal.buy {{
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }}
        .signal.sell {{
            background: #e8f5e9;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }}
        .footer {{
            text-align: center;
            color: #666;
            font-size: 12px;
            padding: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏆 黄金三体系分析报告</h1>
        <div class="time">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>
    
    <div class="card">
        <h2>📊 实时行情</h2>
        <div class="price-info">
"""
    
    # 添加价格信息
    gold = realtime.get('gold', {})
    if gold:
        html += f"""
            <div class="price-item">
                <div class="label">伦敦金 (XAU/USD)</div>
                <div class="value">${gold.get('price', 0):.2f}</div>
                <div class="change">高: ${gold.get('high', 0):.2f} 低: ${gold.get('low', 0):.2f}</div>
            </div>
"""
    
    usd = realtime.get('usd_index', {})
    if usd:
        html += f"""
            <div class="price-item">
                <div class="label">美元指数</div>
                <div class="value">{usd.get('price', 0):.2f}</div>
            </div>
"""
    
    html += """
        </div>
    </div>
    
    <div class="card">
        <h2>🎯 综合判断</h2>
"""
    
    overall = analysis.get('overall', '中性')
    verdict_class = 'neutral'
    if '看多' in overall or '强烈看多' in overall:
        verdict_class = 'bullish'
    elif '看空' in overall or '强烈看空' in overall:
        verdict_class = 'bearish'
    
    html += f"""
        <div class="verdict {verdict_class}">{overall}</div>
        <table class="score-table">
            <tr>
                <th>体系</th>
                <th>得分</th>
                <th>权重</th>
                <th>判断</th>
            </tr>
"""
    
    tech = analysis.get('technical', {})
    fund = analysis.get('fundamental', {})
    sent = analysis.get('sentiment', {})
    geo = analysis.get('geopolitical', {})
    
    html += f"""
            <tr>
                <td>技术面</td>
                <td>{tech.get('combined_score', 0):.2f}</td>
                <td>40%</td>
                <td>{tech.get('overall', 'N/A')}</td>
            </tr>
            <tr>
                <td>基本面</td>
                <td>{fund.get('combined_score', 0):.2f}</td>
                <td>35%</td>
                <td>{fund.get('overall', 'N/A')}</td>
            </tr>
            <tr>
                <td>资金面</td>
                <td>{sent.get('combined_score', 0):.2f}</td>
                <td>25%</td>
                <td>{sent.get('overall', 'N/A')}</td>
            </tr>
            <tr>
                <td>地缘政治</td>
                <td>{geo.get('impact_score', 0):.2f}</td>
                <td>动态</td>
                <td>{geo.get('risk', {}).get('level', 'N/A')}</td>
            </tr>
        </table>
    </div>
"""
    
    # 添加图表
    if score_gauge:
        html += f"""
    <div class="card">
        <h2>📈 得分可视化</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{score_gauge}" alt="得分图表">
        </div>
    </div>
"""
    
    if price_chart:
        html += f"""
    <div class="card">
        <h2>📉 价格走势图</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{price_chart}" alt="价格走势图">
        </div>
    </div>
"""
    
    if indicator_chart:
        html += f"""
    <div class="card">
        <h2>🔧 技术指标</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{indicator_chart}" alt="技术指标图">
        </div>
    </div>
"""
    
    # 交易信号（新格式：字典，包含direction/execution/conflicts/recommendation）
    signals = analysis.get('signals', {})
    if isinstance(signals, dict) and (signals.get('execution') or signals.get('recommendation')):
        direction = signals.get('direction', 'neutral')
        direction_map = {'bullish': '🟢 看多', 'bearish': '🔴 看空', 'neutral': '⚪ 中性'}
        execution = signals.get('execution', [])
        conflicts = signals.get('conflicts', [])
        rec = signals.get('recommendation', {})
        
        html += f"""
    <div class="card">
        <h2>💡 交易信号</h2>
        <p><strong>主方向:</strong> {direction_map.get(direction, direction)}</p>
"""
        if execution:
            html += """<h3>执行层信号</h3><div class="signals">"""
            for sig in execution:
                sig_class = 'buy' if sig.get('type') == 'BUY' else 'sell'
                emoji = '🟢' if sig.get('type') == 'BUY' else '🔴'
                layer = sig.get('layer', '')
                timeframe = sig.get('timeframe', '')
                reason = sig.get('reason', '')
                html += f"""
            <div class="signal {sig_class}">
                {emoji} <strong>{sig.get('type', '')}</strong> [{layer}-{timeframe}]<br>
                <small>{reason}</small>
            </div>
"""
            html += "</div>"
        else:
            html += "<p>暂无交叉信号（等待MACD/KDJ金叉或死叉触发）</p>"
        
        if conflicts:
            html += "<h3>⚠️ 冲突警告</h3><ul>"
            for c in conflicts:
                html += f"<li>{c.get('description', '')}</li>"
            html += "</ul>"
        
        if rec:
            html += f"""
        <h3>📋 操作建议</h3>
        <table>
            <tr><td><strong>操作</strong></td><td>{rec.get('action', 'N/A')}</td></tr>
            <tr><td><strong>策略</strong></td><td>{rec.get('strategy', 'N/A')}</td></tr>
            <tr><td><strong>入场</strong></td><td>{rec.get('entry', 'N/A')}</td></tr>
            <tr><td><strong>仓位</strong></td><td>{rec.get('position', 'N/A')}</td></tr>
            <tr><td><strong>止损</strong></td><td>{rec.get('stop_loss', 'N/A')}</td></tr>
            <tr><td><strong>目标</strong></td><td>{rec.get('target', 'N/A')}</td></tr>
            <tr><td><strong>条件</strong></td><td>{rec.get('condition', 'N/A')}</td></tr>
        </table>
"""
        html += """
    </div>
"""
    
    # 页脚
    html += f"""
    <div class="footer">
        <p>本报告由黄金分析系统v3.0自动生成，仅供参考，不构成投资建议。</p>
        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
</body>
</html>
"""
    
    # 保存文件
    if output_path is None:
        output_dir = os.path.join(os.path.dirname(__file__), 'reports')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, 
                                   f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    logger.info(f"HTML报告已生成: {output_path}")
    return output_path


if __name__ == '__main__':
    # 测试
    from data_fetcher import get_all_realtime, get_gold_klines, get_macro_data
    from analyzer import comprehensive_analysis
    
    print("获取数据...")
    realtime = get_all_realtime()
    klines = get_gold_klines()
    macro_data = get_macro_data()
    
    print("执行分析...")
    analysis = comprehensive_analysis(realtime, klines, macro_data, {})
    
    print("生成HTML报告...")
    path = generate_html_report(analysis, realtime, klines, macro_data)
    print(f"报告已保存: {path}")
