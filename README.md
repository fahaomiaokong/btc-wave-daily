# btc-wave-daily

企业微信群机器人自动推送项目：

- 每日 BTC 波浪分析和走势图
- 每日美股科技新闻摘要

## 美股科技新闻摘要

```bash
python3 scripts/daily_us_tech_news_push.py --sample --dry-run
```

## 企业微信配置

在仓库 Secrets 中添加企业微信群机器人 Webhook：

```text
WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
```

可选：如果想让日报自动改写成更自然的中文，在 Secrets/Variables 中添加：

```text
NEWS_LLM_API_KEY=你的 API Key
NEWS_LLM_BASE_URL=https://api.openai.com/v1
NEWS_LLM_MODEL=gpt-4o-mini
```

然后手动运行 `Daily US Tech News WeCom Push`，或等待北京时间每天 08:45 自动运行。
