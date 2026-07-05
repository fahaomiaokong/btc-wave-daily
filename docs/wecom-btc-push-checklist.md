# 企业微信群机器人 BTC 推送准备清单

## 你后续需要补的账号和密钥

1. 微信账号
   - 用来登录企业微信并接收群消息。

2. 企业微信账号
   - 可以创建自己的企业/团队。
   - 第一版个人测试通常不需要企业认证。

3. 企业微信群
   - 建议群名：`BTC每日波浪分析`。
   - 群里可以先只有你自己。

4. 企业微信群机器人 Webhook
   - 在群里添加机器人后复制 Webhook。
   - 格式类似：

```text
https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
```

5. GitHub 仓库 Secret
   - 名称：`WECHAT_WEBHOOK`
   - 值：上面的企业微信群机器人 Webhook。
   - 注意不要提交到代码里。

6. 可选 GitHub Actions 变量
   - 名称：`PUBLIC_BASE_URL`
   - 值：GitHub Pages 或其他公开报告地址。
   - 没有这个也能推送文字和图片。

## 本地无密钥测试

使用已有报告，不抓新数据：

```bash
python3 scripts/daily_btc_push.py --skip-generate --dry-run --no-send-image
```

生成最新报告并预览推送内容：

```bash
python3 scripts/daily_btc_push.py --dry-run --no-send-image
```

## 真正推送前的最后一步

在 GitHub 仓库里添加 Secret：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
Name: WECHAT_WEBHOOK
Value: 企业微信群机器人 Webhook
```

然后到 Actions 页面手动运行 `Daily BTC WeCom Push`。

## 默认策略

- 标的：`BTC-USD`
- 周期：短期
- K线：日线
- 灵敏度：`0.04`
- 推送时间：北京时间每天 08:30
- 输出目录：`reports/`

## 注意

- Webhook 是密钥，不要发给别人。
- 没有 Webhook 时脚本会自动 dry-run，方便先跑通。
- 企业微信群机器人支持 Markdown 和图片消息；第一版会先发 Markdown，再发 PNG 图片。
