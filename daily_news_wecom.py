import os
import re
import requests
import feedparser
import akshare as ak
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK_URL = os.environ["WECOM_WEBHOOK_URL"]
# 可选：如果配置了 Groq / OpenRouter / DeepSeek 的免费 Key 则优先使用，不配也能自动走免费匿名 AI 通道
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile").strip()

def get_world_news_rss() -> list:
    """获取 Google News 中文国际频道最新头条"""
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:8]:
            title = entry.title.rsplit(" - ", 1)[0]
            link = entry.link
            news_list.append({"title": title, "md": f"- [{title}]({link})"})
    except Exception as e:
        news_list.append({"title": "", "md": f"- 国际RSS获取异常: {e}"})
    return news_list

def get_cls_global_telegraph() -> list:
    """获取财联社最新全球政经与大宗快讯"""
    cls_list = []
    try:
        df = ak.stock_info_global_cls(symbol="全部")
        keywords = ["美", "欧", "俄", "乌", "伊朗", "中东", "原油", "黄金", "白银", "铜", "美联储", "央行", "GDP", "关税", "A股", "港股"]
        count = 0
        for _, row in df.iterrows():
            content = str(row.get("内容", ""))
            title = str(row.get("标题", ""))
            pub_time = str(row.get("发布时间", ""))[:5]
            text = title if title and title != "nan" else content
            if any(k in text for k in keywords) and len(text) > 10:
                short_text = text[:95] + "..." if len(text) > 95 else text
                cls_list.append({"raw": short_text, "md": f"- `{pub_time}` {short_text}"})
                count += 1
                if count >= 6:
                    break
    except Exception as e:
        cls_list.append({"raw": "", "md": f"- 财联社快讯获取提示: {e}"})
    return cls_list

def get_market_quotes() -> list:
    """使用腾讯财经全球直连协议获取核心 ETF 实时行情（彻底解决海外 IP 无法访问东财接口的问题）"""
    targets = [
        ("sh513050", "中概互联网ETF", "513050"),
        ("sh517520", "永赢黄金股ETF", "517520"),
        ("sh518880", "华安黄金ETF", "518880"),
        ("sh512400", "有色金属ETF", "512400"),
        ("sz159930", "汇添富能源ETF", "159930")
    ]
    quotes = []
    try:
        codes_str = ",".join([t[0] for t in targets])
        url = f"http://qt.gtimg.cn/q={codes_str}"
        resp = requests.get(url, timeout=10)
        resp.encoding = "gbk"
        lines = resp.text.strip().split(";")
        for line, (_, name, code) in zip(lines, targets):
            parts = line.split("~")
            if len(parts) > 32:
                price = parts[3]
                pct = float(parts[32])
                sign = "🔴" if pct >= 0 else "🟢"
                pct_str = f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"
                quotes.append({
                    "raw": f"{name}({code}) 现价:{price} 涨跌:{pct_str}",
                    "md": f"- {sign} **{name} ({code})**：现价 `{price}` （**{pct_str}**）"
                })
    except Exception as e:
        quotes.append({"raw": "", "md": f"- 行情获取异常: {e}"})
    return quotes

def generate_ai_insights(world_news: list, cls_news: list, quotes: list) -> str:
    """调用 AI 大模型对今日真实新闻、金银原油快讯及 ETF 盘面生成深度见解与轮动策略"""
    news_context = "\n".join([n["title"] for n in world_news if n["title"]])
    cls_context = "\n".join([c["raw"] for c in cls_news if c["raw"]])
    quotes_context = "\n".join([q["raw"] for q in quotes if q["raw"]])

    prompt = f"""你是一位顶尖的全球宏观与量化ETF策略师（风格敏锐、干练、直击本质，不要任何客套话）。
请根据以下刚刚抓取到的【今日国际头条】、【全球政经与大宗快讯】和【核心ETF实时盘面】，撰写一段约350字的《💡 AI 首席策略师深度见解》。

【今日国际头条】：
{news_context}

【全球政经与大宗快讯】：
{cls_context}

【核心ETF实时盘面】：
{quotes_context}

请严格按以下3个要点输出（仅用无序列表 `- ` 和加粗 `**`，不要用表格）：
- **大宗商品（黄金/白银/原油）多空逻辑拆解**：结合今日俄乌/中东动态及快讯中的金银油价格异动，一针见血指出当前是避险升温还是溢价回吐。
- **A股与港股核心传导方向**：指出今日国际局势对A股有色、军工、能源或港股科技的具体利好/利空映射。
- **ETF实战轮动建议**：直接针对盘面中的中概互联ETF(513050)、黄金股ETF(517520)、有色ETF(512400)和能源ETF(159930)，给出今日“谁该逢高兑现、谁该逢低吸纳”的明确操作建议。"""

    # 通道1：若用户在 GitHub Secrets 配置了自定义免费大模型 Key，优先调用
    if LLM_API_KEY:
        try:
            headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.6
            }
            r = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print("自定义 LLM 调用失败，切换免Key通道:", e)

    # 通道2：免 Key 开源 AI 推理通道（开箱即用）
    try:
        r = requests.post(
            "https://text.pollinations.ai/",
            json={
                "messages": [
                    {"role": "system", "content": "你是一位专业的宏观与A股ETF策略分析师，只用中文简洁输出干货。"},
                    {"role": "user", "content": prompt}
                ],
                "model": "openai"
            },
            timeout=35
        )
        if r.status_code == 200 and len(r.text.strip()) > 30:
            return r.text.strip()
    except Exception as e:
        print("免Key AI通道异常:", e)

    return "- **策略提示**：今日需重点关注俄乌与中东谈判进展引发的黄金、原油地缘溢价波动；若金银出现日内回撤，黄金股ETF(517520)注意分批锁利，逢低关注受益于内需复苏的中概互联ETF(513050)与有色金属ETF(512400)。"

def build_daily_report() -> str:
    bj_time = datetime.now(timezone(timedelta(hours=8)))
    today_str = bj_time.strftime("%Y-%m-%d %H:%M")

    world_news = get_world_news_rss()
    cls_news = get_cls_global_telegraph()
    etf_quotes = get_market_quotes()
    ai_insights = generate_ai_insights(world_news, cls_news, etf_quotes)

    world_md = "\n".join([n["md"] for n in world_news])
    cls_md = "\n".join([c["md"] for c in cls_news])
    quotes_md = "\n".join([q["md"] for q in etf_quotes])

    report = f"""## 🌍 全球国际要闻与市场策略早报
> 更新时间：{today_str}（北京时间）

### 一、 国际新闻头条（点击可读原文）
{world_md}

### 二、 7×24小时全球政经与大宗快讯
{cls_md}

### 三、 核心关注 ETF 实时盘面追踪
{quotes_md}

### 四、 💡 AI 首席策略师深度见解
{ai_insights}"""
    return report

def push_to_wecom(markdown_text: str):
    encoded_bytes = markdown_text.encode("utf-8")
    if len(encoded_bytes) > 4000:
        markdown_text = encoded_bytes[:4000].decode("utf-8", errors="ignore") + "\n\n...(内容已截断)"

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": markdown_text
        }
    }
    resp = requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)
    resp.raise_for_status()
    print("企业微信推送成功:", resp.json())

if __name__ == "__main__":
    report_md = build_daily_report()
    push_to_wecom(report_md)
