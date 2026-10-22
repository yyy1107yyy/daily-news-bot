import os
import requests
import feedparser
import akshare as ak
from datetime import datetime, timezone, timedelta

# 只需要企业微信 Webhook 地址，完全不需要大模型 API Key
WECOM_WEBHOOK_URL = os.environ["WECOM_WEBHOOK_URL"]

def get_world_news_rss() -> list:
    """从 Google News 中文国际频道 RSS 获取最新国际头条"""
    rss_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    news_list = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:8]:
            title = entry.title.rsplit(" - ", 1)[0]  # 清理末尾媒体后缀
            link = entry.link
            news_list.append(f"- [{title}]({link})")
    except Exception as e:
        news_list.append(f"- 国际RSS获取异常: {e}")
    return news_list

def get_cls_global_telegraph() -> list:
    """用 AkShare 获取财联社最新全球财经电报"""
    cls_list = []
    try:
        df = ak.stock_info_global_cls(symbol="全部")
        # 筛选带有国际、美、欧、俄、中东、黄金、原油等关键词的重磅快讯
        keywords = ["美", "欧", "俄", "乌", "伊朗", "中东", "原油", "黄金", "美联储", "央行", "GDP", "关税"]
        count = 0
        for _, row in df.iterrows():
            content = str(row.get("内容", ""))
            title = str(row.get("标题", ""))
            pub_time = str(row.get("发布时间", ""))[:5]
            text = title if title and title != "nan" else content
            if any(k in text for k in keywords) and len(text) > 10:
                short_text = text[:95] + "..." if len(text) > 95 else text
                cls_list.append(f"- `{pub_time}` {short_text}")
                count += 1
                if count >= 6:
                    break
    except Exception as e:
        cls_list.append(f"- 财联社快讯获取提示: {e}")
    return cls_list

def get_market_quotes() -> list:
    """用 AkShare 获取核心 ETF 最新收盘/盘面行情"""
    quotes = []
    target_etfs = {
        "513050": "中概互联网ETF",
        "517520": "永赢黄金股ETF",
        "518880": "华安黄金ETF",
        "512400": "有色金属ETF",
        "159930": "汇添富能源ETF"
    }
    try:
        df = ak.fund_etf_spot_em()
        sub = df[df["代码"].isin(target_etfs.keys())]
        for _, row in sub.iterrows():
            code = row["代码"]
            name = target_etfs.get(code, row["名称"])
            price = row["最新价"]
            pct = row["涨跌幅"]
            sign = "🔴" if float(pct) >= 0 else "🟢"
            quotes.append(f"- {sign} **{name} ({code})**：现价 `{price}` （**{pct}%**）")
    except Exception as e:
        quotes.append(f"- 行情接口非交易时段或暂不可用")
    return quotes

def build_daily_report() -> str:
    bj_time = datetime.now(timezone(timedelta(hours=8)))
    today_str = bj_time.strftime("%Y-%m-%d %H:%M")

    world_news = "\n".join(get_world_news_rss())
    cls_news = "\n".join(get_cls_global_telegraph())
    etf_quotes = "\n".join(get_market_quotes())

    report = f"""## 🌍 全球国际要闻与市场早报
> 更新时间：{today_str}（北京时间）

### 一、 国际新闻头条（点击标题可读原文）
{world_news}

### 二、 7×24小时全球政经与大宗快讯
{cls_news}

### 三、 核心关注 ETF 最新盘面追踪
{etf_quotes}"""
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
