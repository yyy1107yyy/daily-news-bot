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
    """源 1：国际政治宏观头条（精选多条，自动裁剪过长标题）"""
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:10]:
            title = entry.title.rsplit(" - ", 1)[0]
            if len(title) > 28:
                title = title[:26] + "..."
            short_q = urllib.parse.quote(title[:20])
            short_link = f"https://www.bing.com/news/search?q={short_q}"
            news_list.append(f"- [{title}]({short_link})")
    except Exception as e:
        pass
    return news_list

def get_custom_user_rss() -> list:
    """源 2：专属财经资讯源（精选多条）"""
    custom_rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRG9nTDJoMWVtdHNBWGhvWVd4bUv0gAE?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(custom_rss_url)
        for entry in feed.entries[:10]:
            title = entry.title.rsplit(" - ", 1)[0]
            if len(title) > 28:
                title = title[:26] + "..."
            short_q = urllib.parse.quote(title[:20])
            short_link = f"https://www.bing.com/news/search?q={short_q}"
            news_list.append(f"- 🎯 [{title}]({short_link})")
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
                quotes.append(f"- {sign} **{name} ({code})**：`{price}` (**{pct_str}**)")
    except Exception as e:
        quotes.append(f"- 行情获取异常: {e}")
    return quotes

def generate_ai_insights(quotes: list, world_news: list, custom_news: list) -> str:
    """调用 AI 生成精炼策略，确保无杂质"""
    quotes_str = " | ".join(quotes)
    all_news = world_news + custom_news
    news_str = "\n".join(all_news[:15])
    
    prompt = f"""宏观资讯参考：
{news_str}

盘面：{quotes_str}

请作为顶尖宏观策略师，用纯中文输出 250 字左右的精炼点评（严禁任何JSON或英文，从 `### 1.` 开始）：
### 1. 核心地缘与宏观洞察
- （一针见血总结当前主要风险）
### 2. ETF 应对纪律
- （给出简明扼要的仓位操作建议）"""

    models = ["openai-large", "mistral", "openai"]
    for model_name in models:
        try:
            r = requests.post(
                "https://text.pollinations.ai/openai",
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": "你是专业宏观策略师，只输出纯中文Markdown正文。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.5
                },
                timeout=40
            )
            if r.status_code == 200:
                raw_text = r.text.strip()
                if '"reasoning":' in raw_text or '{"tool_calls":' in raw_text:
                    try:
                        data = json.loads(raw_text)
                        if "choices" in data:
                            raw_text = data["choices"][0]["message"]["content"]
                    except Exception:
                        pass
                clean_text = raw_text.replace("\\n", "\n").replace('\\"', '"')
                if "### 1." in clean_text:
                    match = re.search(r"(###\s*1\..*)", clean_text, re.DOTALL)
                    if match:
                        return re.sub(r"[\"}\]]+\s*$", "", match.group(1)).strip()
        except Exception:
            continue
    return "### 1. 核心地缘与宏观洞察\n- 局势震荡加剧，风险偏好低位徘徊。\n### 2. ETF 应对纪律\n- 严守仓位，逢低关注避险与能源配置。"

def push_msg(text: str):
    payload = {"msgtype": "markdown", "markdown": {"content": text}}
    resp = requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)
    print(f"推送响应码: {resp.status_code}, 返回内容: {resp.text}")

if __name__ == "__main__":
    bj_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    world_news = get_world_news_rss()
    custom_news = get_custom_user_rss()
    quotes = get_market_quotes()
    
    ai_text = generate_ai_insights(quotes, world_news, custom_news)
    
    world_md = "\n".join(world_news) if world_news else "- 暂无"
    custom_md = "\n".join(custom_news) if custom_news else "- 暂无"
    quotes_md = "\n".join(quotes) if quotes else "- 暂无"
    
    msg = f"""🌍 **【宏观战情定期速报】**
> 更新时间：{bj_time}

### 一、 国际政治宏观头条
{world_md}

### 二、 🎯 专属财经订阅动态
{custom_md}

### 三、 核心关注 ETF 盘面
{quotes_md}

### 四、 💡 首席策略师点评
{ai_text}"""
    
    push_msg(msg)
    print("完美单条战报推送完成！")
