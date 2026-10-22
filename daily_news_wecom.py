import os
import requests
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

# 直接从 GitHub Secrets 环境变量读取密钥
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
WECOM_WEBHOOK_URL = os.environ["WECOM_WEBHOOK_URL"]

def generate_daily_news() -> str:
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 开启 Google Search 实时联网搜索
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[grounding_tool],
        temperature=0.6
    )
    
    # 获取北京时间日期
    bj_time = datetime.now(timezone(timedelta(hours=8)))
    today_str = bj_time.strftime("%Y-%m-%d")
    
    prompt = f"""今天是北京时间 {today_str}。请联网搜集并整理过去24小时的最新国际新闻要闻与市场动态，生成一份企业微信早报。

请严格包含以下三个模块：
### 一、 全球核心地缘与政经要闻
（提炼4-6条欧美俄乌局势、中东动态、亚太及宏观经济核心要闻，每条简明扼要）

### 二、 国际大宗商品最新盘面与传导分析
（联网查询最新国际原油 WTI/布伦特、现货黄金/白银、铜等最新价格区间，并结合上述新闻简述多空驱动）

### 三、 A股板块与核心ETF早盘策略参考
（结合隔夜外盘与大宗商品走势，简评对A股黄金股如517520、中概互联如513050、有色及能源板块的今日操作启示）

排版要求：
1. 仅使用二级/三级标题、加粗和无序列表，不要使用Markdown表格（确保企业微信手机端阅读清晰）。
2. 全文字数控制在 1200 字以内，直接输出早报正文，不要任何寒暄开场白。"""
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config
    )
    return response.text

def push_to_wecom(markdown_text: str):
    # 企业微信 markdown 消息上限为 4096 字节，做安全截断保护
    encoded_bytes = markdown_text.encode("utf-8")
    if len(encoded_bytes) > 4000:
        markdown_text = encoded_bytes[:4000].decode("utf-8", errors="ignore") + "\n\n...(内容超长已截断)"
        
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": markdown_text
        }
    }
    resp = requests.post(WECOM_WEBHOOK_URL, json=payload, timeout=15)
    resp.raise_for_status()
    print("企业微信推送状态:", resp.json())

if __name__ == "__main__":
    news_brief = generate_daily_news()
    push_to_wecom(news_brief)
