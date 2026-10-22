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
    """源 1：国际政治宏观头条"""
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:4]:
            title = entry.title.rsplit(" - ", 1)[0]
            short_q = urllib.parse.quote(title[:22])
            short_link = f"https://www.bing.com/news/search?q={short_q}"
            news_list.append({"title": title, "md": f"- [{title}]({short_link})"})
    except Exception as e:
        pass
    return news_list

def get_custom_user_rss() -> list:
    """源 2：专属财经资讯源"""
    custom_rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRG9nTDJoMWVtdHNBWGhvWVd4bUv0gAE?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(custom_rss_url)
        for entry in feed.entries[:4]:
            title = entry.title.rsplit(" - ", 1)[0]
            short_q = urllib.parse.quote(title[:22])
            short_link = f"https://www.bing.com/news/search?q={short_q}"
            news_list.append({"title": title, "md": f"- 🎯 [{title}]({short_link})"})
    except Exception as e:
        pass
    return news_list

def get_market_quotes() -> list:
    """获取核心 ETF 实时盘面数据"""
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
    except Exception as e:
        quotes.append(f"- 行情获取异常: {e}")
    return quotes

def generate_ai_insights(quotes: list, world_news: list, custom_news: list) -> str:
    """调用 AI 大模型生成深度宏观与 ETF 轮动策略"""
    quotes_str = " | ".join(quotes)
    news_str = "\n".join([n["title"] for n in world_news + custom_news if n.get("title")])
    
    prompt = f"""最新抓取的双路新闻动态：
{news_str}

核心ETF实时盘面：{quotes_str}

请作为顶尖宏观策略师，直接用中文输出一份 350 字左右的精炼策略点评（严禁任何英文草稿，从 `### 1.` 开始）：
### 1. 宏观与地缘局势洞察
- （结合最新资讯一针见血分析当前宏观或地缘演变）
### 2. 核心 ETF 实战轮动建议
- （针对中概、黄金、有色、能源给出明确的波段或防守操作建议）"""

    models = ["openai-large", "mistral", "openai"]
    for attempt in range(2):
        for model_name in models:
            try:
                r = requests.post(
                    "https://text.pollinations.ai/openai",
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": "你是一位专业的宏观与A股ETF策略分析师，只允许输出纯中文Markdown正文。"},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.5
                    },
                    timeout=40
                )
                if r.status_code == 200:
                    text = r.text.strip()
                    if "### 1." in text and len(text) > 80:
                        match = re.search(r"(###\s*1\..*)", text, flags=re.DOTALL)
                        if match:
                            return match.group(1).strip()
                        return text
            except Exception:
                continue

    return "### 1. 宏观与地缘局势洞察\n- 多空博弈加剧，全球资产价格随消息面震荡。\n### 2. 核心 ETF 实战轮动建议\n- 严守仓位纪律，关注核心标的分时支撑与低吸机会。"

def push_msg(text: str):
    payload = {"msgtype": "markdown", "markdown": {"content": text[:4000]}}
    requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)

if __name__ == "__main__":
    bj_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    # 强制获取最新资讯与盘面
    world_news = get_world_news_rss()
    custom_news = get_custom_user_rss()
    quotes = get_market_quotes()
    
    ai_text = generate_ai_insights(quotes, world_news, custom_news)
    
    world_md = "\n".join([n["md"] for n in world_news]) if world_news else "- 暂无"
    custom_md = "\n".join([n["md"] for n in custom_news]) if custom_news else "- 暂无"
    quotes_md = "\n".join(quotes) if quotes else "- 暂无"
    
    msg = f"""🌍 **【宏观战情定期速报】**
> 更新时间：{bj_time}（北京时间）

### 一、 国际政治宏观头条
{world_md}

### 二、 🎯 专属财经订阅源动态
{custom_md}

### 三、 核心关注 ETF 实时盘面
{quotes_md}

### 四、 💡 首席策略师深度点评
{ai_text}"""
    
    # 无条件强制推送
    push_msg(msg)
    print("定期战报已成功推送至企业微信！")
