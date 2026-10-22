import os
import re
import json
import urllib.parse
import requests
import feedparser
import akshare as ak
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK_URL = os.environ["WECOM_WEBHOOK_URL"]
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile").strip()

def check_market_and_news() -> tuple:
    """核心巡检：检查 ETF 波动率和突发地缘新闻关键词"""
    triggered = False
    trigger_reason = []
    
    # 1. 检查行情异动（任一 ETF 涨跌幅绝对值 >= 1.5% 即触发）
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
                
                # 异动阈值判断：绝对值 >= 1.5%
                if abs(pct) >= 1.5:
                    triggered = True
                    trigger_reason.append(f"核心资产 {name} 盘中异动达 {pct_str}")
    except Exception as e:
        quotes.append(f"- 行情获取异常: {e}")

    # 2. 检查突发新闻关键词
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    urgent_keywords = ["突发", "战争", "空袭", "制裁", "袭击", "降息", "加息", "破位", "暴跌", "暴涨", "会谈", "协议"]
    
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:6]:
            title = entry.title.rsplit(" - ", 1)[0]
            short_q = urllib.parse.quote(title[:22])
            short_link = f"https://www.bing.com/news/search?q={short_q}"
            news_list.append(f"- [{title}]({short_link})")
            
            # 如果新闻标题命中突发关键词，直接触发提醒
            if any(k in title for k in urgent_keywords):
                triggered = True
                trigger_reason.append(f"捕捉到突发头条: {title}")
    except Exception as e:
        news_list.append(f"- 国际RSS获取异常: {e}")

    # 【注】如果你希望平时早上 8 点那次雷打不动强制发送，可以把下面这行强制设为 True 或增加时间判断
    # 目前默认：只要有异动或突发新闻就发，平时风平浪静则静默跳过。
    # 为了防止你错过每日早报，我们也可以设定：北京时间早上 8:00 (UTC 0点) 强制触发一次，其余时间按异动触发！
    bj_hour = datetime.now(timezone(timedelta(hours=8))).hour
    if bj_hour == 8:
        triggered = True
        trigger_reason.append("定时早报例行推送")

    return triggered, trigger_reason, news_list, quotes

def generate_ai_insights(reasons: list, quotes: list) -> str:
    prompt = f"""当前触发监控警报的原因：{", ".join(reasons)}
核心ETF实时盘面：{" | ".join(quotes)}

请作为顶尖宏观策略师，直接用中文输出一份 300 字左右的精炼异动点评与应对策略（严禁任何英文草稿，从 `### 1.` 开始）：
### 1. 异动核心原因诊断
- （一针见血分析触发本次警报的宏观或地缘根源）
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
    return "### 1. 异动诊断\n- 盘面波动加剧，地缘与宏观预期交织。\n### 2. 应对策略\n- 严格执行仓位纪律，避免盲目追涨杀跌。"

def push_msg(text: str):
    payload = {"msgtype": "markdown", "markdown": {"content": text[:4000]}}
    requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)

if __name__ == "__main__":
    triggered, reasons, news, quotes = check_market_and_news()
    
    if triggered:
        bj_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
        reason_str = " | ".join(reasons)
        
        msg = f"""🚨 **【宏观与盘面异动警报】**
> 触发时间：{bj_time} | 触发事由：{reason_str}

### 一、 核心关注 ETF 实时盘面
{"\n".join(quotes)}

### 二、 💡 首席策略师异动点评
{generate_ai_insights(reasons, quotes)}"""
        
        push_msg(msg)
        print("检测到异动，已成功推送警报！")
    else:
        print("当前市场平稳，未达到异动阈值，保持静默。")
