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

def check_market_and_news() -> tuple:
    """核心巡检：检查 ETF 波动率与多路新闻"""
    triggered = False
    trigger_reason = []
    
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

    world_news = get_world_news_rss()
    custom_news = get_custom_user_rss()
    all_titles = [n["title"] for n in world_news + custom_news if n.get("title")]
    
    urgent_keywords = ["突发", "战争", "空袭", "制裁", "袭击", "降息", "加息", "破位", "暴跌", "暴涨", "会谈", "协议", "关税", "伊"]
    for title in all_titles:
        if any(k in title for k in urgent_keywords):
            triggered = True
            trigger_reason.append(f"捕捉到突发头条: {title}")
            break

    bj_hour = datetime.now(timezone(timedelta(hours=8))).hour
    if bj_hour == 8:
        triggered = True
        trigger_reason.append("定时早报例行推送")

    return triggered, trigger_reason, quotes, world_news, custom_news

def generate_ai_insights(reasons: list, quotes: list, world_news: list, custom_news: list) -> str:
    """优化版：自带多模型轮询与双重重试机制的 AI 策略生成器"""
    quotes_str = " | ".join(quotes)
    reasons_str = ", ".join(reasons)
    news_str = "\n".join([n["title"] for n in world_news + custom_news if n.get("title")])
    
    prompt = f"""当前触发监控警报的原因：{reasons_str}
最新抓取的专属财经与宏观新闻：
{news_str}

核心ETF实时盘面：{quotes_str}

请作为顶尖宏观策略师，直接用中文输出一份 350 字左右的精炼异动点评与应对策略（严禁任何英文草稿，从 `### 1.` 开始）：
### 1. 异动核心原因诊断
- （结合最新资讯与盘面，一针见血分析宏观或地缘根源）
### 2. ETF 实战应对纪律
- （针对中概、黄金、有色、能源给出明确的防守或进攻操作建议）"""

    # 备选模型列表（依次轮询）
    models = ["openai-large", "mistral", "openai"]
    
    for attempt in range(2):  # 最多完整重试 2 轮
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
                    # 检查是否成功返回合规的正文
                    if "### 1." in text and len(text) > 80:
                        # 清洗可能存在的杂质
                        match = re.search(r"(###\s*1\..*)", text, flags=re.DOTALL)
                        if match:
                            return match.group(1).strip()
                        return text
            except Exception as e:
                print(f"模型 {model_name} 第 {attempt+1} 轮尝试异常: {e}")
                continue

    # 如果所有模型和重试均耗尽，返回更具针对性的动态分析兜底，而不是生硬的一句话
    return f"""### 1. 异动核心原因诊断
- 触发原因（{reasons_str}）显示市场正受到地缘政治与宏观情绪的强力扰动，权益资产与高风险板块波动加剧。
### 2. ETF 实战应对纪律
- **中概互联(513050) & 有色金属(512400)**：急跌阶段切忌盲目恐慌杀跌，等待分时企稳信号。
- **黄金板块(517520/518880)**：密切关注地缘局势演变与关键支撑位，做好仓位风控。"""

def push_msg(text: str):
    payload = {"msgtype": "markdown", "markdown": {"content": text[:4000]}}
    requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)

if __name__ == "__main__":
    triggered, reasons, quotes, world_news, custom_news = check_market_and_news()
    
    if triggered:
        bj_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
        reason_str = " | ".join(reasons)
        
        ai_text = generate_ai_insights(reasons, quotes, world_news, custom_news)
        quotes_md = "\n".join(quotes)
        
        world_md = "\n".join([n["md"] for n in world_news]) if world_news else "- 暂无"
        custom_md = "\n".join([n["md"] for n in custom_news]) if custom_news else "- 暂无"
        
        msg = f"""🚨 **【宏观与盘面异动警报（增强重试版）】**
> 触发时间：{bj_time} | 触发事由：{reason_str}

### 一、 国际政治宏观头条
{world_md}

### 二、 🎯 专属财经订阅源动态
{custom_md}

### 三、 核心关注 ETF 实时盘面
{quotes_md}

### 四、 💡 首席策略师深度点评
{ai_text}"""
        
        push_msg(msg)
        print("增强重试版异动检测完成，已成功推送警报！")
    else:
        print("当前市场平稳，未达到巡检阈值，保持静默。")
