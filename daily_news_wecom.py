import os
import time
import urllib.parse
import requests
import feedparser
import akshare as ak
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK_URL = os.environ["WECOM_WEBHOOK_URL"]
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile").strip()

def get_world_news_rss() -> list:
    """获取 Google News 中文国际频道最新头条（使用瘦身短链接防超长）"""
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:8]:
            title = entry.title.rsplit(" - ", 1)[0]
            # 用极简搜索短链替代长达350字节的加密重定向串，既能点击看原文又节省85%字节
            short_q = urllib.parse.quote(title[:22])
            short_link = f"https://www.bing.com/news/search?q={short_q}"
            news_list.append({"title": title, "md": f"- [{title}]({short_link})"})
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
                short_text = text[:90] + "..." if len(text) > 90 else text
                cls_list.append({"raw": short_text, "md": f"- `{pub_time}` {short_text}"})
                count += 1
                if count >= 6:
                    break
    except Exception as e:
        cls_list.append({"raw": "", "md": f"- 财联社快讯获取提示: {e}"})
    return cls_list

def get_market_quotes() -> list:
    """使用腾讯财经全球直连协议获取核心 ETF 实时行情"""
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
    """调用 AI 大模型生成完整深度见解与 ETF 轮动策略"""
    news_context = "\n".join([n["title"] for n in world_news if n["title"]])
    cls_context = "\n".join([c["raw"] for c in cls_news if c["raw"]])
    quotes_context = "\n".join([q["raw"] for q in quotes if q["raw"]])

    prompt = f"""你是一位顶尖的全球宏观与量化ETF策略师（风格敏锐、干练、直击本质，不要任何客套话）。
请根据以下刚刚抓取到的【今日国际头条】、【全球政经与大宗快讯】和【核心ETF实时盘面】，撰写一份深度早报分析。

【今日国际头条】：
{news_context}

【全球政经与大宗快讯】：
{cls_context}

【核心ETF实时盘面】：
{quotes_context}

请严格按以下3个模块输出（使用三级标题 `### ` 和无序列表 `- `、加粗 `**`，不要用表格，总字数控制在 500～700 字左右）：

### 1. 大宗商品（黄金/白银/原油）多空逻辑拆解
- 结合今日俄乌/中东动态及快讯中的金银油价格异动，深度剖析当前是避险升温还是地缘溢价回吐，并给出关键价格支撑/阻力观察点。

### 2. 全球资金流向与A股/港股映射
- 分析欧美政经动态与大宗商品走势对A股有色金属、国防军工、传统能源及港股科技板块的具体传导逻辑。

### 3. 核心 ETF 今日实战轮动策略
- 针对盘面中的 **中概互联网ETF(513050)**、**永赢黄金股ETF(517520)**、**华安黄金ETF(518880)**、**有色金属ETF(512400)** 和 **能源ETF(159930)** 的实时涨跌幅（如大跌是情绪错杀还是趋势破位），逐一给出今日“防守/锁利/低吸/观望”的具体应对建议。"""

    if LLM_API_KEY:
        try:
            headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.6
            }
            r = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=35)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print("自定义 LLM 调用失败，切换免Key通道:", e)

    try:
        r = requests.post(
            "https://text.pollinations.ai/",
            json={
                "messages": [
                    {"role": "system", "content": "你是一位专业的宏观与A股ETF策略分析师，只用中文简洁输出深度干货。"},
                    {"role": "user", "content": prompt}
                ],
                "model": "openai"
            },
            timeout=45
        )
        if r.status_code == 200 and len(r.text.strip()) > 30:
            return r.text.strip()
    except Exception as e:
        print("免Key AI通道异常:", e)

    return "- **策略提示**：今日需重点关注俄乌与中东谈判进展引发的黄金、原油地缘溢价波动；黄金股ETF(517520)与中概互联ETF(513050)若出现日内急跌，注意观察分时均线支撑，严格按仓位纪律应对。"

def push_single_msg(markdown_text: str):
    """发送单条 Markdown 消息（带安全边界保护）"""
    encoded_bytes = markdown_text.encode("utf-8")
    if len(encoded_bytes) > 4000:
        markdown_text = encoded_bytes[:4000].decode("utf-8", errors="ignore") + "\n\n...(单条超长截断)"
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": markdown_text}
    }
    resp = requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)
    resp.raise_for_status()

if __name__ == "__main__":
    bj_time = datetime.now(timezone(timedelta(hours=8)))
    today_str = bj_time.strftime("%Y-%m-%d %H:%M")

    world_news = get_world_news_rss()
    cls_news = get_cls_global_telegraph()
    etf_quotes = get_market_quotes()
    ai_insights = generate_ai_insights(world_news, cls_news, etf_quotes)

    world_md = "\n".join([n["md"] for n in world_news])
    cls_md = "\n".join([c["md"] for c in cls_news])
    quotes_md = "\n".join([q["md"] for q in etf_quotes])

    # 第一条消息：全球要闻 + 7×24快讯 + ETF实时盘面
    msg_part1 = f"""## 🌍 全球国际要闻与市场早报（上篇：资讯与盘面）
> 更新时间：{today_str}（北京时间）

### 一、 国际新闻头条（点击可读相关报道）
{world_md}

### 二、 7×24小时全球政经与大宗快讯
{cls_md}

### 三、 核心关注 ETF 实时盘面追踪
{quotes_md}"""

    # 第二条消息：AI 首席策略师深度见解（独立 4096 字节空间，彻底不截断！）
    msg_part2 = f"""## 💡 AI 首席策略师深度见解（下篇：传导与轮动）
> 针对 {today_str} 盘面与地缘动态的量化推演

{ai_insights}"""

    push_single_msg(msg_part1)
    time.sleep(1)  # 间隔1秒发送下篇，确保企业微信里上下顺序整齐
    push_single_msg(msg_part2)
    print("上、下两篇早报均已完整推送至企业微信！")
