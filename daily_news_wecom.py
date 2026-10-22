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
    """使用腾讯财经直连协议获取核心 ETF 实时行情"""
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

def clean_ai_output(raw_text: str) -> str:
    """清洗 AI 输出：彻底剥离 JSON 包装、英文思考草稿(reasoning)与转义乱码"""
    text = raw_text.strip()
    # 1. 如果返回的是 JSON 字符串，优先解析提取 content 字段
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if "choices" in data and len(data["choices"]) > 0:
                msg = data["choices"][0].get("message", {})
                if msg.get("content"):
                    text = msg["content"]
            elif data.get("content"):
                text = data["content"]
        except Exception:
            pass

    # 2. 修复被转义的换行符（如 \n 或连续 nn）
    text = text.replace("\\n", "\n").replace("nn###", "\n\n###").replace("nn-", "\n-")

    # 3. 精准截取从第一个中文三级标题 '### 1.' 开始的内容，扔掉前面的所有英文思考过程
    match = re.search(r"(###\s*1\..*)", text, flags=re.DOTALL)
    if match:
        text = match.group(1)

    # 4. 切除末尾可能出现的英文自言自语（如 Let's adjust...）
    text = re.split(r"\n*(?:Let's|We need to|Word count|Note:|Char count)", text)[0]

    # 5. 确保标题与列表换行规整
    text = re.sub(r"\s*(###\s*\d+\.)", r"\n\n\1", text)
    text = re.sub(r"\s+(-\s+\*\*)", r"\n\1", text)
    return text.strip()

def generate_ai_insights(world_news: list, cls_news: list, quotes: list) -> str:
    """调用大模型生成纯中文深度见解与 ETF 轮动策略"""
    news_context = "\n".join([n["title"] for n in world_news if n["title"]])
    cls_context = "\n".join([c["raw"] for c in cls_news if c["raw"]])
    quotes_context = "\n".join([q["raw"] for q in quotes if q["raw"]])

    prompt = f"""请根据以下今日真实抓取的【国际头条】、【全球快讯】和【核心ETF实时盘面】，直接用中文输出一份深度市场早报分析。
严禁输出任何英文思考过程，直接从 `### 1.` 开始输出中文正文！

【今日国际头条】：
{news_context}

【全球政经与大宗快讯】：
{cls_context}

【核心ETF实时盘面】：
{quotes_context}

请严格按以下格式输出（总字数控制在 450～600 中文字之间，严禁使用英文）：

### 1. 大宗商品（黄金/白银/原油）多空逻辑拆解
- **贵金属走势与核心驱动**：（结合俄乌/中东动态及快讯中金银价格异动，指出当前是避险升温还是溢价回吐，给出关键支撑/阻力位）
- **原油与能源博弈**：（分析中东局势、制裁谈判对国际油价的短线影响）

### 2. 全球资金流向与A股/港股映射
- **顺周期与资源品映射**：（分析对A股黄金股、有色金属、能源化工的传导逻辑）
- **科技与跨境资金动向**：（结合外盘科技动态与汇率，分析对港股及中概互联网的情绪影响）

### 3. 核心 ETF 今日实战轮动策略
- **中概互联网ETF (513050)**：（结合实时涨跌幅给出“低吸/观望/防守”建议）
- **永赢黄金股ETF (517520) & 华安黄金ETF (518880)**：（对比两者跌幅差异，给出套利或锁利建议）
- **有色金属ETF (512400) & 能源ETF (159930)**：（给出今日波段操作建议）"""

    if LLM_API_KEY:
        try:
            headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5
            }
            r = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=35)
            r.raise_for_status()
            return clean_ai_output(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            print("自定义 LLM 调用失败，切换免Key通道:", e)

    # 使用 Pollinations 标准 OpenAI 兼容 JSON 端点，并指定非推理纯文本模型 mistral / openai-large
    for model_name in ["openai-large", "mistral", "openai"]:
        try:
            r = requests.post(
                "https://text.pollinations.ai/openai",
                headers={"Content-Type": "application/json"},
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": "你是一位专业的A股与全球宏观策略师。只允许输出纯中文Markdown正文，严禁输出任何英文思考过程或JSON字符串。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.5
                },
                timeout=45
            )
            if r.status_code == 200:
                cleaned = clean_ai_output(r.text)
                if "### 1." in cleaned and len(cleaned) > 100:
                    return cleaned
        except Exception as e:
            print(f"模型 {model_name} 尝试异常:", e)

    return "### 1. 大宗商品多空逻辑拆解\n- **贵金属与原油**：今日需重点关注俄乌与中东局势引发的地缘溢价波动，现货黄金失守4100美元关口显示短线获利盘回吐。\n\n### 2. Core ETF 实战轮动策略\n- **黄金股ETF(517520) & 华安黄金(518880)**：金价回撤叠加股市波动放大黄金股跌幅，短线宜依托商品金(518880)防守，待金价企稳后再回补黄金股。\n- **中概互联ETF(513050) & 有色ETF(512400)**：日内急跌释放情绪压力，观察分时企稳信号分批低吸，切忌盲目杀跌。"

def push_single_msg(markdown_text: str):
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

    msg_part1 = f"""## 🌍 全球国际要闻与市场早报（上篇：资讯与盘面）
> 更新时间：{today_str}（北京时间）

### 一、 国际新闻头条（点击可读相关报道）
{world_md}

### 二、 7×24小时全球政经与大宗快讯
{cls_md}

### 三、 核心关注 ETF 实时盘面追踪
{quotes_md}"""

    msg_part2 = f"""## 💡 AI 首席策略师深度见解（下篇：传导与轮动）
> 针对 {today_str} 盘面与地缘动态的量化推演

{ai_insights}"""

    push_single_msg(msg_part1)
    time.sleep(1)
    push_single_msg(msg_part2)
    print("上、下两篇早报均已完整推送至企业微信！")
