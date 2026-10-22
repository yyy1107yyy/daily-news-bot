def generate_ai_insights(quotes: list, world_news: list, custom_news: list) -> str:
    """调用 AI 大模型生成策略，并自动清洗任何底层 JSON 或思维链杂质"""
    quotes_str = " | ".join(quotes)
    news_str = "\n".join([n["title"] for n in world_news + custom_news if n.get("title")])
    
    prompt = f"""最新抓取的双路新闻动态：
{news_str}

核心ETF实时盘面：{quotes_str}

请作为顶尖宏观策略师，直接用中文输出一份 350 字左右的精炼策略点评。
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
                    timeout=40
                )
                if r.status_code == 200:
                    raw_text = r.text.strip()
                    
                    # 🧽 强力清洗逻辑：如果里面不幸包含了大模型底层的 JSON 或 reasoning，尝试用正则把正文救回来
                    if '"reasoning":' in raw_text or '{"tool_calls":' in raw_text or '{"choices":' in raw_text:
                        try:
                            # 尝试按标准 JSON 解析，看能不能把 content 提出来
                            data = json.loads(raw_text)
                            if isinstance(data, dict):
                                # 逐层寻找可能的文本字段
                                if "choices" in data:
                                    raw_text = data["choices"][0]["message"]["content"]
                                elif "message" in data:
                                    raw_text = data["message"].get("content", raw_text)
                        except Exception:
                            pass
                    
                    # 清洗掉所有多余的转义换行符
                    clean_text = raw_text.replace("\\n", "\n").replace('\\"', '"')
                    
                    # 只要包含 "### 1." 就截取正文部分
                    if "### 1." in clean_text:
                        match = re.search(r"(###\s*1\..*)", clean_text, flags=dotall := re.DOTALL)
                        if match:
                            result = match.group(1).strip()
                            # 再次把结尾可能带有的大括号或杂质切掉
                            result = re.sub(r"[\"}\]]+\s*$", "", result).strip()
                            return result
                            
                    if len(clean_text) > 50 and "reasoning" not in clean_text:
                        return clean_text
            except Exception:
                continue

    return "### 1. 宏观与地缘局势洞察\n- 多空博弈加剧，全球资产价格随消息面震荡。\n### 2. 核心 ETF 实战轮动建议\n- 严守仓位纪律，关注核心标的分时支撑与低吸机会。"
