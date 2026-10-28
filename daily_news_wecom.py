import os
import re
import json
import time
import urllib.parse
import requests
import feedparser
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK_URL = os.environ["WECOM_WEBHOOK_URL"]

def build_news_link(raw_title: str) -> str:
    """生成极简百度直达链接（严格控制字节长度，防止撑爆企业微信4096字节上限）"""
    clean_kw = re.sub(r"[^\w\u4e00-\u9fa5]", "", raw_title)[:12]
    encoded_kw = urllib.parse.quote(clean_kw)
    return f"https://www.baidu.com/s?wd={encoded_kw}"

def get_world_news_rss() -> list:
    """源 1：国际政治宏观头条"""
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:8]:
            raw_title = entry.title.rsplit(" - ", 1)[0]
            safe_title = raw_title.replace("[", "【").replace("]", "】")
            show_title = safe_title[:26] + "..." if len(safe_title) > 28 else safe_title
            link = build_news_link(raw_title)
            news_list.append({"title": raw_title, "md": f"- [{show_title}]({link})"})
    except Exception:
        pass
    return news_list

def get_custom_user_rss() -> list:
    """源 2：专属财经/黄金白银/半导体通信/能源/A股动态 RSS"""
    # 新增白银、半导体、通信关键词，精准覆盖新持仓
    query = urllib.parse.quote("财经 OR 黄金 OR 白银 OR 原油 OR 半导体 OR 通信 OR 美联储 OR A股")
    custom_rss_url = f"https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(custom_rss_url)
        for entry in feed.entries[:6]:
            raw_title = entry.title.rsplit(" - ", 1)[0]
            safe_title = raw_title.replace("[", "【").replace("]", "】")
            show_title = safe_title[:26] + "..." if len(safe_title) > 28 else safe_title
            link = build_news_link(raw_title)
            news_list.append({"title": raw_title, "md": f"- 🎯 [{show_title}]({link})"})
    except Exception:
        pass
    return news_list

def get_market_quotes() -> list:
    """获取核心持仓与关注 ETF/个股实时盘面数据"""
    quotes = []
    targets = [
        ("sh515880", "通信ETF", "515880"),
        ("sz159327", "半导材料ETF", "159327"),
        ("sz002716", "湖南白银", "002716"),
        ("sh517520", "永赢黄金股ETF", "517520"),
        ("sh518880", "华安黄金ETF", "518880"),
        ("sh513050", "中概互联网ETF", "513050"),
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
    """调用 AI 生成深度策略与被套持仓解套建议（严禁画表格）"""
    quotes_str = " | ".join(quotes)
    all_titles = [n["title"] for n in world_news + custom_news if n.get("title")]
    news_str = "\n".join([f"- {t}" for t in all_titles[:14]])
    
    prompt = f"""最新国际与财经要闻：
{news_str}

核心持仓与关注盘面：{quotes_str}

请作为首席宏观策略师，直接用中文输出一份 320 字左右的精炼点评与实战解套建议，分为以下两部分（注意：严禁使用 Markdown 表格 `|`，全部使用 `- ` 无序列表）：
**1. 核心地缘与宏观洞察**
- （结合上述新闻一针见血分析地缘、通胀、科技算力或贵金属情绪）
**2. 重点持仓解套与实战应对策略**
- **科技硬核组（通信ETF 515880 / 半导材料 159327）**：（针对被套持仓，结合盘面给出具体支撑位、反弹减仓或日内做T降成本建议）
- **贵金属被套组（黄金股 517520 / 湖南白银 002716 / 黄金 518880）**：（结合金银走势，给出具体补仓/做T或止盈止损点位建议）
- **宏观风向组（中概 513050 / 有色 512400 / 能源 159930）**：（给出简明操作建议）"""

    for attempt in range(3):
        try:
            r = requests.post(
                "https://text.pollinations.ai/openai",
                json={
                    "model": "openai",
                    "messages": [
                        {"role": "system", "content": "你是一位专业的宏观与ETF/个股实战策略师，只输出纯中文列表格式正文，严禁使用Markdown表格，不要输出任何英文思考过程。"},
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
                if '{"choices":' in content or '"reasoning":' in content:
                    m = re.search(r'"content"\s*:\s*"(.*?)"\s*,\s*"(?:reasoning|tool_calls|refusal)"', content, re.DOTALL)
                    if m:
                        content = m.group(1).replace("\\n", "\n").replace('\\"', '"').strip()
                
                if len(content) > 50 and "reasoning" not in content:
                    return content
        except Exception as e:
            print(f"主通道第 {attempt+1} 次尝试异常: {e}")
            time.sleep(2)

    return "**1. 核心地缘与宏观洞察**\n- 当前国际地缘与宏观预期交织，资金在科技成长与贵金属避险板块间高频轮动。\n**2. 重点持仓解套与实战应对策略**\n- **通信ETF (515880) / 半导材料 (159327)**：短线关注下方支撑企稳信号，被套仓位切忌盲目割肉，可逢急跌企稳后利用日内底仓做T降低持仓成本。\n- **黄金股 (517520) / 湖南白银 (002716)**：受外盘金银震荡影响，耐心等待企稳反弹再择机分批调整仓位。\n- **中概 / 有色 / 能源**：控制仓位，结合板块轮动逢低分批应对。"

def send_wecom_md(content: str):
    """带字节级安全切割的推送函数，确保任何一部分都绝不因为超4096字节被吞"""
    max_bytes = 3800
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        resp = requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)
        print(f"单条推送状态: {resp.status_code}, 字节数: {len(encoded)}, 响应: {resp.text}")
    else:
        lines = content.split("\n")
        chunk = ""
        part = 1
        for line in lines:
            if len((chunk + line + "\n").encode("utf-8")) > max_bytes:
                payload = {"msgtype": "markdown", "markdown": {"content": chunk.strip()}}
                resp = requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)
                print(f"分段 {part} 推送状态: {resp.status_code}, 响应: {resp.text}")
                time.sleep(1)
                part += 1
                chunk = f"📌 **【宏观战情速报（续 {part}）】**\n" + line + "\n"
            else:
                chunk += line + "\n"
        if chunk.strip():
            payload = {"msgtype": "markdown", "markdown": {"content": chunk.strip()}}
            resp = requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)
            print(f"分段 {part} 推送状态: {resp.status_code}, 响应: {resp.text}")

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

### 三、 核心持仓与关注盘面
{quotes_md}

### 四、 💡 首席策略师解套与点评
{ai_text}"""

    send_wecom_md(full_msg)
