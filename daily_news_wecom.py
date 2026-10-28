import os
import re
import time
import urllib.parse
import requests
import feedparser
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK_URL = os.environ["WECOM_WEBHOOK_URL"]

def build_news_link(raw_title: str) -> str:
    """生成极简百度直达链接（严控字节数，防止超企业微信4096字节上限）"""
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
    """源 2：专属财经/金银/半导体通信/能源/A股动态 RSS"""
    query = urllib.parse.quote("财经 OR 黄金 OR 白银 OR 原油 OR 半导体 OR 通信 OR 算力 OR A股")
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
    """获取核心持仓与关注标的实时快照"""
    quotes_md = []
    targets = [
        ("sh515880", "通信ETF", "515880"),
        ("sz159327", "半导材料ETF", "159327"),
        ("sh517520", "永赢黄金股ETF", "517520"),
        ("sz002716", "湖南白银", "002716"),
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
            if len(parts) > 34:
                price = parts[3]
                pct = float(parts[32])
                sign = "🔴" if pct >= 0 else "🟢"
                pct_str = f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"
                quotes_md.append(f"- {sign} **{name} ({code})**：`{price}` (**{pct_str}**)")
    except Exception as e:
        quotes_md.append(f"- 行情获取异常: {e}")
    return quotes_md

def generate_ai_insights(world_news: list, custom_news: list) -> str:
    """调用 AI 专注提炼新闻核心增量与持仓利好利空风向（彻底剔除假点位）"""
    all_titles = [n["title"] for n in world_news + custom_news if n.get("title")]
    news_str = "\n".join([f"- {t}" for t in all_titles[:14]])
    
    prompt = f"""最新抓取的全球政治与财经要闻：
{news_str}

请作为首席宏观情报官，直接用中文输出一份 220 字以内的纯享版情报综述，严格遵守以下规则：
1. 严禁使用 Markdown 表格 `|`，全部使用 `- ` 无序列表。
2. 严禁预测或编造任何具体股价点位、支撑位、压力位或均线！只做新闻脱水与多空情绪映射。

请严格按以下格式输出：
**1. 本小时核心增量情报**
- （用1~2句话提炼上述新闻中最重要、最可能影响市场的硬核事件）
**2. 持仓板块多空风向标**
- **算力通信与半导体 (515880 / 159327)**：【🔴利好催化 / 🟢利空预警 / ⚪中性观察】（结合新闻用一句话说明逻辑）
- **黄金与白银贵金属 (517520 / 002716 / 518880)**：【🔴利好催化 / 🟢利空预警 / ⚪中性观察】（结合地缘与美联储消息一句话说明逻辑）
- **原油能源与有色中概 (159930 / 512400 / 513050)**：【🔴利好催化 / 🟢利空预警 / ⚪中性观察】（结合新闻一句话说明逻辑）"""

    for attempt in range(3):
        try:
            r = requests.post(
                "https://text.pollinations.ai/openai",
                json={
                    "model": "openai",
                    "messages": [
                        {"role": "system", "content": "你是一位敏锐的全球宏观与行业情报分析师，只做新闻脱水提炼与板块利好利空定性判断，绝不输出任何具体股价点位，绝不使用表格。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3
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
                
                if len(content) > 40 and "reasoning" not in content:
                    return content
        except Exception as e:
            print(f"主通道第 {attempt+1} 次尝试异常: {e}")
            time.sleep(2)

    return "**1. 本小时核心增量情报**\n- 全球地缘局势与海外流动性预期持续博弈，建议重点关注上方直达链接中的突发事件。\n**2. 持仓板块多空风向标**\n- **算力通信与半导体**：【⚪中性观察】关注海外AI算力资本开支与国产替代催化。\n- **黄金与白银贵金属**：【⚪中性观察】受地缘避险与加息预期双向拉锯。"

def send_wecom_md(content: str):
    """带字节级安全切割的推送函数"""
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
                time.sleep(1)
                part += 1
                chunk = f"📌 **【宏观战情速报（续 {part}）】**\n" + line + "\n"
            else:
                chunk += line + "\n"
        if chunk.strip():
            payload = {"msgtype": "markdown", "markdown": {"content": chunk.strip()}}
            requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)

if __name__ == "__main__":
    bj_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    world_news = get_world_news_rss()
    custom_news = get_custom_user_rss()
    quotes_md = get_market_quotes()
    ai_text = generate_ai_insights(world_news, custom_news)
    
    world_str = "\n".join([n["md"] for n in world_news]) if world_news else "- 暂无"
    custom_str = "\n".join([n["md"] for n in custom_news]) if custom_news else "- 暂无"
    quotes_str = "\n".join(quotes_md) if quotes_md else "- 暂无"
    
    full_msg = f"""🌍 **【宏观战情定期速报】**
> 更新时间：{bj_time}

### 一、 国际政治宏观头条
{world_str}

### 二、 🎯 专属财经订阅动态
{custom_str}

### 三、 核心持仓实时快照
{quotes_str}

### 四、 🧭 情报脱水与板块风向标
{ai_text}"""

    send_wecom_md(full_msg)
