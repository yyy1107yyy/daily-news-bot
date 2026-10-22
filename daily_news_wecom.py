import os
import re
import json
import urllib.parse
import requests
import feedparser
import akshare as ak
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK_URL = os.environ["WECOM_WEBHOOK_URL"]

def get_world_news_rss() -> list:
    """源 1：获取 Google News 中文国际频道最新头条"""
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:5]:
            title = entry.title.rsplit(" - ", 1)[0]
            short_q = urllib.parse.quote(title[:22])
            short_link = f"https://www.bing.com/news/search?q={short_q}"
            news_list.append({"title": title, "md": f"- [{title}]({short_link})"})
    except Exception as e:
        pass
    return news_list

def get_finance_news_rss() -> list:
    """源 2（新增）：获取华尔街见闻 / 财经宏观专项 RSS 动态"""
    # 采用稳定公开的财经宏观资讯 RSS
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRG9nTDJoMWVtdHNBWGhvWVd4bUv0gAE?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:4]:
            title = entry.title.rsplit(" - ", 1)[0]
            short_q = urllib.parse.quote(title[:22])
            short_link = f"https://www.bing.com/news/search?q={short_q}"
            news_list.append({"title": title, "md": f"- 📊 [{title}]({short_link})"})
    except Exception as e:
        pass
    return news_list

def check_market_and_news() -> tuple:
    """核心巡检：检查 ETF 波动率、双路新闻与突发关键词"""
    triggered = False
    trigger_reason = []
    
    # 1. 检查行情异动（阈值 1.2%）
    quotes = []
    targets = [
        ("sh513050", "中概互联网ETF", "513050"),
        ("sh517520", "永赢黄金股ETF", "517520"),
        ("sh518880", "华安黄金ETF", "518880"),
        ("sh512400", "有色金属ETF", "512400"),
        ("sz159930", "汇添富能源ETF", "159930")
    ]
    try:
        codes_str = ",".join([t[0] for t in targets])
        url = f"http://qt.gtimg.cn/q={codes_str}"
        resp = requests.get(url, timeout=10)
        resp.encoding = "gbk"
        for line, (_, name, code) in zip(resp.text.strip().split(";"), targets):
            parts = line.split("~")
            if len(parts) > 32:
                price = parts[3]
                pct = float(parts[32])
                sign = "🔴" if pct >= 0 else "🟢"
                pct_str = f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"
                quotes.append(f"- {sign} **{name} ({code})**：现价 `{price}` （**{pct_str}**）")
                
                if abs(pct) >= 1.2:
                    triggered = True
                    trigger_reason.append(f"核心资产 {name} 盘中异动达 {pct_str}")
    except Exception as e:
        quotes.append(f"- 行情获取异常: {e}")

    # 2. 检查双路新闻与突发关键词
    world_news = get_world_news_rss()
    finance_news = get_finance_news_rss()
    all_titles = [n["title"] for n in world_news + finance_news if n.get("title")]
    
    urgent_keywords = ["突发", "战争", "空袭", "制裁", "袭击", "降息", "加息", "破位", "暴跌", "暴涨", "会谈", "协议", "关税"]
    for title in all_titles:
        if any(k in title for k in urgent_keywords):
            triggered = True
            trigger_reason.append(f"捕捉到突发头条: {title}")
            break

    # 早上 8 点例行推送早报兜底
    bj_hour = datetime.now(timezone(timedelta(hours=8))).hour
    if bj_hour == 8:
        triggered = True
        trigger_reason.append("定时早报例行推送")

    return triggered, trigger_reason, quotes, world_news, finance_news

def generate_ai_insights(reasons: list, quotes: list, world_news: list, finance_news: list) -> str:
    quotes_str = " | ".join(quotes)
    reasons_str = ", ".join(reasons)
    news_str = "\n".join([n["title"] for n in world_news + finance_news if n.get("title")])
    
    prompt = f"""当前触发监控警报的原因：{reasons_str}
最新抓取的双路新闻动态：
{news_str}

核心ETF实时盘面：{quotes_str}

请作为顶尖宏观策略师，直接用中文输出一份 350 字左右的精炼异动点评与应对策略（严禁任何英文草稿，从 `### 1.` 开始）：
### 1. 异动核心原因诊断
- （结合最新双路新闻与盘面，一针见血分析宏观或地缘根源）
### 2. ETF 实战应对纪律
- （针对中概、黄金、有色、能源给出明确的防守或进攻操作建议）"""

    for model_name in ["openai-large", "mistral", "openai"]:
        try:
            r = requests.post(
                "https://text.pollinations.ai/openai",
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5
                },
                timeout=35
            )
            if r.status_code == 200 and "### 1." in r.text:
                return r.text.strip()
        except Exception:
            pass
    return "### 1. 异动诊断\n- 多空博弈加剧，市场盘面承压。\n### 2. 应对策略\n- 严守仓位纪律，关注核心均线支撑。"

def push_msg(text: str):
    payload = {"msgtype": "markdown", "markdown": {"content": text[:4000]}}
    requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)

if __name__ == "__main__":
    triggered, reasons, quotes, world_news, finance_news = check_market_and_news()
    
    if triggered:
        bj_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
        reason_str = " | ".join(reasons)
        
        ai_text = generate_ai_insights(reasons, quotes, world_news, finance_news)
        quotes_md = "\n".join(quotes)
        
        # 组装双路新闻摘要
        world_md = "\n".join([n["md"] for n in world_news]) if world_news else "- 暂无"
        finance_md = "\n".join([n["md"] for n in finance_news]) if finance_news else "- 暂无"
        
        msg = f"""🚨 **【宏观与盘面异动警报（双源增强版）】**
> 触发时间：{bj_time} | 触发事由：{reason_str}

### 一、 国际政治与宏观头条
{world_md}

### 二、 📊 财经专项快讯动态
{finance_md}

### 三、 核心关注 ETF 实时盘面
{quotes_md}

### 四、 💡 首席策略师深度点评
{ai_text}"""
        
        push_msg(msg)
        print("双源异动检测完成，已成功推送警报！")
    else:
        print("当前市场平稳，双源巡检未达阈值，保持静默。")
