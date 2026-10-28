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

def get_market_quotes() -> tuple:
    """获取实时盘面数据（同时提取现价、涨跌幅、最高价、最低价喂给AI防串台）"""
    quotes_md = []
    ai_quotes_detail = []
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
                price = parts[3]      # 当前最新价
                prev_close = parts[4] # 昨收价
                high = parts[33]      # 今日最高价
                low = parts[34]       # 今日最低价
                pct = float(parts[32])
                sign = "🔴" if pct >= 0 else "🟢"
                pct_str = f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"
                quotes_md.append(f"- {sign} **{name} ({code})**：`{price}` (**{pct_str}**)  `[高:{high} 低:{low}]`")
                ai_quotes_detail.append(
                    f"【{name}(代码:{code})】精确现价={price}元, 今日涨跌幅={pct_str}, 昨收={prev_close}元, 今日最高={high}元, 今日最低={low}元"
                )
    except Exception as e:
        quotes_md.append(f"- 行情获取异常: {e}")
    return quotes_md, ai_quotes_detail

def generate_ai_insights(ai_quotes_detail: list, world_news: list, custom_news: list) -> str:
    """调用 AI 生成深度策略（严禁价格串台、严禁编造均线）"""
    quotes_block = "\n".join(ai_quotes_detail)
    all_titles = [n["title"] for n in world_news + custom_news if n.get("title")]
    news_str = "\n".join([f"- {t}" for t in all_titles[:14]])
    
    prompt = f"""最新国际与财经要闻：
{news_str}

真实盘面精确数据（请严格核对每只标的的精确现价，绝对禁止将不同标的的价格张冠李戴！）：
{quotes_block}

请作为首席宏观策略师，直接用中文输出一份 350 字左右的精炼点评与解套建议，严格遵守以下铁律：
1. 严禁使用 Markdown 表格 `|`，全部使用 `- ` 无序列表。
2. 严禁编造未提供的“5日/20日均线”数据！所有支撑位、压力位、做T区间必须严格基于上方提供的【精确现价、昨收、今日最高、今日最低】在合理几个百分点的范围内推算！

请按以下格式输出：
**1. 核心地缘与宏观洞察**
- （结合上述新闻一针见血分析地缘、通胀、AI算力通信或金银情绪）
**2. 四大被套持仓一对一解套策略**
- **通信ETF (515880)**：（先写出当前精确现价，再结合今日高低点给出日内做T或反弹减亏的具体价格区间）
- **半导材料ETF (159327)**：（先写出当前精确现价，再给出具体支撑压力与解套操作建议）
- **永赢黄金股 (517520)**：（先写出当前精确现价，结合金价走势给出具体解套/做T点位）
- **湖南白银 (002716)**：（先写出当前精确现价，结合白银弹性给出具体支撑压力与操作建议）
**3. 宏观风向观察（黄金518880 / 中概513050 / 有色512400 / 能源159930）**
- （结合各自精确现价，用一两句话给出简明应对方向）"""

    for attempt in range(3):
        try:
            r = requests.post(
                "https://text.pollinations.ai/openai",
                json={
                    "model": "openai",
                    "messages": [
                        {"role": "system", "content": "你是一位严谨的量化与ETF实战策略师。你必须100%忠实于用户提供的每只股票的精确现价，所有给出的支撑位和目标价必须与该标的现价处于同一数量级（误差不超过±10%），严禁串台，严禁编造均线，严禁使用表格。"},
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
                
                if len(content) > 50 and "reasoning" not in content:
                    return content
        except Exception as e:
            print(f"主通道第 {attempt+1} 次尝试异常: {e}")
            time.sleep(2)

    return "**1. 核心地缘与宏观洞察**\n- 当前国际地缘与宏观预期交织，资金在科技成长与贵金属避险板块间高频轮动。\n**2. 四大被套持仓一对一解套策略**\n- **通信ETF (515880) & 半导材料 (159327)**：请参考上方盘面高低点区间，被套仓位切忌在日内低点盲目割肉，可逢急跌企稳后利用底仓做T降低成本。\n- **黄金股 (517520) & 湖南白银 (002716)**：受外盘金银震荡影响，关注日内低点支撑，耐心等待企稳反弹再择机分批T出。"

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
    quotes_md, ai_quotes_detail = get_market_quotes()
    ai_text = generate_ai_insights(ai_quotes_detail, world_news, custom_news)
    
    world_md = "\n".join([n["md"] for n in world_news]) if world_news else "- 暂无"
    custom_md = "\n".join([n["md"] for n in custom_news]) if custom_news else "- 暂无"
    quotes_str = "\n".join(quotes_md) if quotes_md else "- 暂无"
    
    full_msg = f"""🌍 **【宏观战情定期速报】**
> 更新时间：{bj_time}

### 一、 国际政治宏观头条
{world_md}

### 二、 🎯 专属财经订阅动态
{custom_md}

### 三、 核心持仓与关注盘面
{quotes_str}

### 四、 💡 首席策略师解套与点评
{ai_text}"""

    send_wecom_md(full_msg)
