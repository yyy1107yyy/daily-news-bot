import os
import re
import json
import time
import urllib.parse
import requests
import feedparser
import akshare as ak
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK_URL = os.environ["WECOM_WEBHOOK_URL"]

def get_world_news_rss() -> list:
    """源 1：国际政治宏观头条（不设硬性限制，多多益善）"""
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(rss_url)
        # 放宽至前 12 条
        for entry in feed.entries[:12]:
            title = entry.title.rsplit(" - ", 1)[0]
            short_q = urllib.parse.quote(title[:22])
            short_link = f"https://www.bing.com/news/search?q={short_q}"
            news_list.append({"title": title, "md": f"- [{title}]({short_link})"})
    except Exception as e:
        pass
    return news_list

def get_custom_user_rss() -> list:
    """源 2：专属财经资讯源（不设硬性限制）"""
    custom_rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRG9nTDJoMWVtdHNBWGhvWVd4bUv0gAE?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(custom_rss_url)
        # 放宽至前 12 条
        for entry in feed.entries[:12]:
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
    """调用 AI 大模型生成策略，并强力清洗底层 JSON 杂质"""
    quotes_str = " | ".join(quotes)
    all_titles = [n["title"] for n in world_news + custom_news if n.get("title")]
    news_str = "\n".join(all_titles[:15])  # 传给 AI 前 15 条核心标题作为宏观参考
    
    prompt = f"""最新抓取的全网宏观与财经动态：
{news_str}

核心ETF实时盘面：{quotes_str}

请作为顶尖宏观策略师，直接用中文输出一份 400 字左右的精炼策略点评。
注意：绝对不允许输出任何 JSON 格式、大括号、reasoning 或英文调试信息，必须纯粹输出 Markdown 正文，从 `### 1.` 开始：
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
                            {"role": "system", "content": "你是一位专业的宏观与A股ETF策略分析师。严禁输出任何 JSON、reasoning 或英文调试字段，只允许输出纯中文 Markdown。"},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.5
                    },
                    timeout=45
                )
                if r.status_code == 200:
                    raw_text = r.text.strip()
                    
                    if '"reasoning":' in raw_text or '{"tool_calls":' in raw_text or '{"choices":' in raw_text:
                        try:
                            data = json.loads(raw_text)
                            if isinstance(data, dict):
                                if "choices" in data:
                                    raw_text = data["choices"][0]["message"]["content"]
                                elif "message" in data:
                                    raw_text = data["message"].get("content", raw_text)
                        except Exception:
                            pass
                    
                    clean_text = raw_text.replace("\\n", "\n").replace('\\"', '"')
                    
                    if "### 1." in clean_text:
                        match = re.search(r"(###\s*1\..*)", clean_text, re.DOTALL)
                        if match:
                            result = match.group(1).strip()
                            result = re.sub(r"[\"}\]]+\s*$", "", result).strip()
                            return result
                            
                    if len(clean_text) > 50 and "reasoning" not in clean_text:
                        return clean_text
            except Exception:
                continue

    return "### 1. 宏观与地缘局势洞察\n- 多空博弈加剧，全球资产价格随消息面高频震荡。\n### 2. 核心 ETF 实战轮动建议\n- 严守仓位纪律，关注核心标的分时支撑与低吸机会。"

def push_msg(text: str):
    """智能分批推送：若内容超过企业微信字数限制，自动切分多条依次发送"""
    max_len = 3500  # 企业微信安全字符长度
    if len(text) <= max_len:
        payload = {"msgtype": "markdown", "markdown": {"content": text}}
        requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)
    else:
        # 按行智能切块，保证 Markdown 排版不被拦腰截断
        lines = text.split("\n")
        current_chunk = ""
        part_idx = 1
        for line in lines:
            if len(current_chunk) + len(line) + 1 > max_len:
                header_tip = f"📌 **【战情速报（续 {part_idx}）】**\n\n"
                payload = {"msgtype": "markdown", "markdown": {"content": header_tip + current_chunk}}
                requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)
                time.sleep(0.8)  # 间隔防频控
                part_idx += 1
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"
        if current_chunk:
            header_tip = f"📌 **【战情速报（续 {part_idx}）】**\n\n" if part_idx > 1 else ""
            payload = {"msgtype": "markdown", "markdown": {"content": header_tip + current_chunk}}
            requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)

if __name__ == "__main__":
    bj_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    world_news = get_world_news_rss()
    custom_news = get_custom_user_rss()
    quotes = get_market_quotes()
    
    ai_text = generate_ai_insights(quotes, world_news, custom_news)
    
    world_md = "\n".join([n["md"] for n in world_news]) if world_news else "- 暂无"
    custom_md = "\n".join([n["md"] for n in custom_news]) if custom_news else "- 暂无"
    quotes_md = "\n".join(quotes) if quotes else "- 暂无"
    
    msg = f"""🌍 **【宏观战情定期速报（全景满配版）】**
> 更新时间：{bj_time}（北京时间）

### 一、 国际政治宏观头条（精选全量）
{world_md}

### 二、 🎯 专属财经订阅源动态（精选全量）
{custom_md}

### 三、 核心关注 ETF 实时盘面
{quotes_md}

### 四、 💡 首席策略师深度点评
{ai_text}"""
    
    push_msg(msg)
    print("全景战报分批推送完成！")
