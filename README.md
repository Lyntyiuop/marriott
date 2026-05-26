# Marriott 中国酒店价格监控

定时抓取万豪中国各省级行政区五星级以上酒店最低价（贵州和青海没有），生成价格趋势图并邮件推送。

## 项目结构

```
marriott.py          # 核心：Selenium 抓取万豪搜索结果，遍历全国各省
plot_trends.py       # 分析历史价格数据，生成趋势图 + 最低价报告
send_email.py        # 通过 SMTP 发送图表邮件
main.py              # 一键执行：绘图 → 发邮件
data/                 # 酒店 JSON 数据 + 图表输出
requirements.txt
```

## 定时运行
1. Windows 任务计划程序 → 创建任务 → 运行marriott.py
2. Windows 任务计划程序 → 创建任务 → 运行main.py

注：#1的频率可以略高于#2，比如每小时运行一次marriott.py，每天运行一次main.py


## 邮件配置

在 `.env` 中设置：

```
EMAIL_SENDER=xxx@qq.com
EMAIL_PASSWORD=xxx
EMAIL_RECEIVER=xxx@qq.com
EMAIL_SMTP_SERVER=smtp.qq.com
EMAIL_SMTP_PORT=465
```
