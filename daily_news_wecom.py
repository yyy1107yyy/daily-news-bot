import os
import re
import json
import time
import urllib.parse
import requests
import feedparser
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK_URL = os.environ["WECOM_WEBHOOK_URL"]

def get_world_news_rss() -> list:
    """源 1：国际政治宏观头条"""
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:8]:
            raw_title = entry.title.rsplit(" - ", 1)[0]
            show_title = raw_title[:28] + "..." if len(raw_title) > 30 else raw_title
            short_q = urllib.parse.quote(raw_title[:10])
            short_link = f"https://cn.bing.com/news/search?q={short_q}"
            news_list.append({"title": raw_title, "md": f"- [{show_title}]({short_link})"})
    except Exception:
        pass
    return news_list

def get_custom_user_rss() -> list:
    """源 2：专属财经/黄金/能源/宏观动态 RSS（已修复为空的问题）"""
    custom_rss_url = "https://news.google.com/rss/search?q=%E8%B4%A2%E7%BB%8F+OR+%E9%BB%84%E9%87%91+OR+%E5%8E%9F%E6%B2%B9+OR+%E7%BE%8E%E8%81%94%E5%82%A8+OR+A%E8%82%A1&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(custom_rss_url)
        for entry in feed.entries[:6]:
            raw_title = entry.title.rsplit(" - ", 1)[0]
            show_title = raw_title[:28] + "..." if len(raw_title) > 30 else raw_title
            short_q = urllib.parse.quote(raw_title[:10])
            short_link = f"https://cn.bing.com/news/search?q={short_q}"
            news_list.append({"title": raw_title, "md": f"- 🎯 [{show_title}]({short_link})"})
    except Exception:
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
    """调用 AI 生成深度策略（标准 JSON 解析 + 多重快速重试，绝不误杀正常回复）"""
    quotes_str = " | ".join(quotes)
    all_titles = [n["title"] for n in world_news + custom_news if n.get("title")]
    news_str = "\n".join([f"- {t}" for t in all_titles[:14]])
    
    prompt = f"""最新国际与财经要闻：
{news_str}

核心ETF盘面：{quotes_str}

请作为首席宏观策略师，直接用中文输出一份 300 字左右的深度点评与实战操作建议，分为以下两部分：
**1. 核心地缘与宏观洞察**
（结合上述新闻分析当前地缘冲突、通胀或资金情绪演变）
**2. 核心 ETF 实战应对策略**
（分别针对中概513050、黄金517520/518880、有色512400、能源159930给出具体操作建议）"""

    # 通道 1：使用响应最快的标准接口轮询重试 3 次
    for attempt in range(3):
        try:
            r = requests.post(
                "https://text.pollinations.ai/openai",
                json={
                    "model": "openai",
                    "messages": [
                        {"role": "system", "content": "你是一位专业的宏观与ETF实战策略师，只输出纯中文Markdown正文，不要输出任何英文思考过程。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.6
                },
                timeout=30
            )
            if r.status_code == 200:
                content = ""
                try:
                    data = r.json()
                    if isinstance(data, dict) and "choices" in data:
                        content = data["choices"][0].get("message", {}).get("content", "")
                except Exception:
                    content = r.text
                
                content = content.strip()
                # 如果还是带了未解析的 JSON 外壳，做二次提取
                if '{"choices":' in content or '"reasoning":' in content:
                    m = re.search(r'"content"\s*:\s*"(.*?)"\s*,\s*"(?:reasoning|tool_calls|refusal)"', content, re.DOTALL)
                    if m:
                        content = m.group(1).replace("\\n", "\n").replace('\\"', '"').strip()
                
                if len(content) > 50 and "reasoning" not in content:
                    return content
        except Exception as e:
            print(f"主通道第 {attempt+1} 次尝试异常: {e}")
            time.sleep(2)

    # 通道 2：极速纯文本备用通道
    try:
        r2 = requests.post(
            "https://text.pollinations.ai/",
            json={
                "messages": [
                    {"role": "system", "content": "你是专业宏观策略师，只输出中文。"},
                    {"role": "user", "content": prompt}
                ],
                "model": "openai"
            },
            timeout=30
        )
        if r2.status_code == 200 and len(r2.text.strip()) > 50:
            return r2.text.strip()
    except Exception:
        pass

    return "**1. 核心地缘与宏观洞察**\n- 当前国际地缘风险持续发酵，市场避险情绪升温，资金在风险资产与避险板块间高频博弈。\n**2. 核心 ETF 实战应对策略**\n- **中概与有色**：短线承压，严控仓位耐心等待企稳信号。\n- **黄金与能源**：受益于地缘溢价支撑，逢回调可关注分批配置机会。"

def send_wecom_md(content: str):
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    resp = requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)
    print(f"推送状态: {resp.status_code}, 响应: {resp.text}")

if __name__ == "__main__":
    bj_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    world_news = get_world_news_rss()
    custom_news = get_custom_user_rss()
    quotes = get_market_quotes()
    ai_text = generate_ai_insights(quotes, world_news, custom_news)
    
    world_md = "\n".join([n["md"] for n in world_news]) if world_news else "- 暂无"
    custom_md = "\n".join([n["md"] for n in custom_news]) if custom_news else "- 暂无"
    quotes_md = "\n".join(quotes) if quotes else "- 暂无"
    
    full_msg = f"""🌍 **【宏观战情定期速报】**
> 更新时间：{bj_time}

### 一、 国际政治宏观头条
{world_md}

### 二、 🎯 专属财经订阅动态
{custom_md}

### 三、 核心关注 ETF 盘面
{quotes_md}

### 四、 💡 首席策略师点评
{ai_text}"""

    # 企业微信单条 Markdown 限制为 4096 字节（UTF-8）
    if len(full_msg.encode("utf-8")) <= 3950:
        send_wecom_md(full_msg)
    else:
        # 若内容极多超出单条字节上限，优雅分为“资讯盘面卡”与“AI策略卡”两张完整卡片推送
        part1_msg = f"""🌍 **【宏观战情定期速报（上：资讯与盘面）】**
> 更新时间：{bj_time}

### 一、 国际政治宏观头条
{world_md}

### 二、 🎯 专属财经订阅动态
{custom_md}

### 三、 核心关注 ETF 盘面
{quotes_md}"""

        part2_msg = f"""💡 **【宏观战情定期速报（下：首席策略师点评）】**
> 更新时间：{bj_time}

{ai_text}"""
        send_wecom_md(part1_msg)
        time.sleep(1)
        send_wecom_md(part2_msg)
