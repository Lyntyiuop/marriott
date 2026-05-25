import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

CHART_PATH = 'data/charts/price_trends.png'
LOWEST_HITS_PATH = 'data/latest_is_lowest.txt'
TOP5_PATH = 'data/lowest_5_latest.txt'


def send_chart(chart_path=CHART_PATH):
    sender = os.getenv('EMAIL_SENDER')
    password = os.getenv('EMAIL_PASSWORD')
    receiver = os.getenv('EMAIL_RECEIVER')
    smtp_server = os.getenv('EMAIL_SMTP_SERVER')
    smtp_port = int(os.getenv('EMAIL_SMTP_PORT'))

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    message = MIMEMultipart()
    message['From'] = Header(sender)
    message['To'] = Header(receiver)
    message['Subject'] = Header(f"marriott shanghai 价格趋势图 - {current_time}")

    # # 读取分析结果
    # body_lines = [f"万豪上海酒店价格监控 - {current_time}", "=" * 50]
    body_lines = []

    if os.path.exists(LOWEST_HITS_PATH):
        with open(LOWEST_HITS_PATH, "r", encoding="utf-8") as f:
            body_lines.append(f.read().strip())

    if os.path.exists(TOP5_PATH):
        with open(TOP5_PATH, "r", encoding="utf-8") as f:
            body_lines.append(f.read().strip())

    body = "\n\n".join(body_lines)
    message.attach(MIMEText(body, 'plain', 'utf-8'))

    with open(chart_path, 'rb') as f:
        img = MIMEImage(f.read())
        img.add_header('Content-Disposition', 'attachment', filename=os.path.basename(chart_path))
        message.attach(img)

    try:
        smtp_obj = smtplib.SMTP_SSL(smtp_server, smtp_port)
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, [receiver], message.as_string())
        smtp_obj.quit()
        print(f"图表已成功发送到 {receiver}")
        return True
    except Exception as e:
        print(f"发送失败：{str(e)}")
        return False


if __name__ == "__main__":
    send_chart()