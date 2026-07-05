# 企业微信群机器人美股科技新闻推送清单

## 需要配置

1. 企业微信群机器人 Webhook
   - 在企业微信群里添加机器人，然后复制 Webhook。
   - 格式类似：

```text
https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
```

2. GitHub Actions Secret
   - 名称：`WECHAT_WEBHOOK`
   - 值：企业微信群机器人 Webhook
   - 路径：`Settings -> Secrets and variables -> Actions -> New repository secret`

3. 可选 LLM 摘要 Secret
   - 名称：`NEWS_LLM_API_KEY`
   - 值：OpenAI、DeepSeek 或其他 OpenAI-compatible 服务的 API Key
   - 不配置也能运行，但标题和摘要会更多保留 RSS 原文英文。

4. 可选 GitHub Actions Variables
   - `NEWS_LLM_BASE_URL`：默认 `https://api.openai.com/v1`
   - `NEWS_LLM_MODEL`：默认 `gpt-4o-mini`

## 本地测试

不访问网络，使用内置样例：

```bash
python3 scripts/daily_us_tech_news_push.py --sample --dry-run
```

访问 RSS 新闻源，但不推送：

```bash
python3 scripts/daily_us_tech_news_push.py --dry-run
```

关闭 LLM 改写，只看 RSS 原文摘要：

```bash
python3 scripts/daily_us_tech_news_push.py --dry-run --no-ai
```

添加额外 RSS 源：

```bash
python3 scripts/daily_us_tech_news_push.py --dry-run --rss-url "https://example.com/feed.xml"
```

## 默认策略

- 推送时间：北京时间每天 08:45
- 回看窗口：最近 30 小时
- 推送数量：最多 8 条
- 关注方向：美股科技、AI、半导体、云计算、大型互联网平台、科技股财报和评级
- 默认股票池：`NVDA, MSFT, AAPL, GOOGL, AMZN, META, TSLA, AMD, AVGO, ORCL, PLTR, CRWD, NET, ARM, SMCI, TSM`

## 说明

- 没有 `WECHAT_WEBHOOK` 时脚本会自动 dry-run，方便先跑通。
- 脚本会保存 Markdown 和 JSON 到 `reports/news/`。
- 第一版使用 RSS 标题和描述生成中文结构化摘要；后续可以接 OpenAI/DeepSeek 做更自然的中文总结和影响判断。
