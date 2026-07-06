# 企业微信群机器人美股板块涨跌推送清单

## 推送内容

- 11 个 SPDR 行业 ETF 的近一交易日涨跌：
  - `XLK` 科技
  - `XLC` 通信服务
  - `XLY` 可选消费
  - `XLP` 必选消费
  - `XLF` 金融
  - `XLV` 医疗保健
  - `XLI` 工业
  - `XLE` 能源
  - `XLB` 材料
  - `XLRE` 房地产
  - `XLU` 公用事业
- 按绝对涨跌幅筛选波动较大的板块。
- 结合市场新闻标题，生成中文原因。

## 需要配置

1. 必需 Secret
   - `WECHAT_WEBHOOK`：企业微信群机器人 Webhook

2. 可选 LLM 配置
   - `NEWS_LLM_API_KEY`：OpenAI、DeepSeek 或其他 OpenAI-compatible API Key
   - `NEWS_LLM_BASE_URL`：默认 `https://api.openai.com/v1`
   - `NEWS_LLM_MODEL`：默认 `gpt-4o-mini`

不配置 LLM 也能运行，但“原因”会使用基于新闻关键词的保守兜底描述。

## 本地测试

不访问网络，使用样例数据：

```bash
python3 scripts/daily_us_sector_push.py --sample --dry-run --no-ai
```

访问行情和新闻源，但不推送：

```bash
python3 scripts/daily_us_sector_push.py --dry-run --no-ai
```

## 默认策略

- 推送时间：北京时间每天 08:55
- 行情来源：Yahoo Finance chart API
- 新闻来源：Yahoo Finance、CNBC、MarketWatch RSS
- 原因数量：默认解释涨跌幅绝对值最大的 5 个板块
