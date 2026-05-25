import json
import re
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# ============================================================
# 1. 读取数据（处理 marriott.py 追加写入的多个 JSON 对象）
# ============================================================
DATA_PATH = "data/marriott_shanghai_hotels.json"

with open(DATA_PATH, "r", encoding="utf-8") as f:
    raw_text = f.read()

# 文件由多个 JSON 对象组成，之间用 ",\n" 分隔，用 json.JSONDecoder 逐个解析
decoder = json.JSONDecoder()
records = []
pos = 0
raw_text = raw_text.strip()
while pos < len(raw_text):
    # 跳过空白和逗号分隔符
    while pos < len(raw_text) and raw_text[pos] in " \t\n\r,":
        pos += 1
    if pos >= len(raw_text):
        break
    obj, end = decoder.raw_decode(raw_text, pos)
    records.append(obj)
    pos = end

# ============================================================
# 2. 整理数据：按酒店聚合每个日期的价格
# ============================================================
# hotel_trends: { hotel_id: { "name": ..., "brand": ..., "dates": [...], "prices": [...] } }
hotel_trends = {}

for record in records:
    record_time = datetime.fromisoformat(record["record_time"])
    for hotel in record["hotels"]:
        hid = hotel["hotel_id"]
        price = hotel["rooms"][0]["price"] if hotel["rooms"] else None
        if price is None:
            continue
        if hid not in hotel_trends:
            hotel_trends[hid] = {
                "name": hotel["hotel_name"],
                "brand": hotel["hotel_brand"],
                "dates": [],
                "prices": [],
            }
        hotel_trends[hid]["dates"].append(record_time)
        hotel_trends[hid]["prices"].append(price)

# ============================================================
# 3. 配置中文字体
# ============================================================
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

# ============================================================
# 4. 画图准备 —— 创建子图和坐标系
# ============================================================
n = len(hotel_trends)
if n == 0:
    print("没有找到酒店数据")
    exit()

# 自动计算行列数
cols = min(3, n)
rows = (n + cols - 1) // cols

fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 4 * rows))
# fig.suptitle("万豪上海酒店价格走势", fontsize=16, fontweight="bold")

# 统一 axes 为一维列表
if n == 1:
    axes = [axes]
else:
    axes = axes.flatten()

for idx, (hid, trend) in enumerate(hotel_trends.items()):
    ax = axes[idx]
    dates = trend["dates"]
    prices = trend["prices"]

    # 按时间排序
    sorted_pairs = sorted(zip(dates, prices), key=lambda x: x[0])
    dates = [p[0] for p in sorted_pairs]
    prices = [p[1] for p in sorted_pairs]

    # 画折线图
    ax.plot(dates, prices, marker="o", linewidth=2, markersize=6, color="#1f77b4")
    ax.set_title(trend["name"], fontsize=11)
    ax.set_ylabel("价格 (CNY)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.tick_params(axis="x", rotation=45, labelsize=8)

    # 标注最低价和最高价
    if len(prices) >= 2:
        min_idx = prices.index(min(prices))
        max_idx = prices.index(max(prices))

        ax.annotate(
            f"最低 ￥{prices[min_idx]:.0f}",
            xy=(dates[min_idx], prices[min_idx]),
            xytext=(0, -20), textcoords="offset points",
            fontsize=8, color="green", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="green", lw=1),
            ha="center",
        )
        ax.annotate(
            f"最高 ￥{prices[max_idx]:.0f}",
            xy=(dates[max_idx], prices[max_idx]),
            xytext=(0, 15), textcoords="offset points",
            fontsize=8, color="red", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="red", lw=1),
            ha="center",
        )
    elif len(prices) == 1:
        ax.annotate(
            f"￥{prices[0]:.0f}",
            xy=(dates[0], prices[0]),
            fontsize=8, ha="center",
        )

    ax.grid(True, alpha=0.3)

# 隐藏多余的空白子图
for j in range(n, len(axes)):
    axes[j].set_visible(False)

# ============================================================
# 5. 分析：最新价是否是最低价 & 最新价最低的五个酒店
# ============================================================
latest_prices = {}  # {hotel_id: (name, latest_date, latest_price, min_price)}

for hid, trend in hotel_trends.items():
    dates = trend["dates"]
    prices = trend["prices"]
    sorted_pairs = sorted(zip(dates, prices), key=lambda x: x[0])
    sorted_dates = [p[0] for p in sorted_pairs]
    sorted_prices = [p[1] for p in sorted_pairs]
    latest_price = sorted_prices[-1]
    min_price = min(sorted_prices)
    latest_prices[hid] = (trend["name"], sorted_dates[-1], latest_price, min_price)

# 5a. 最新价等于最低价的酒店
lowest_hits = [
    (hid, name, price)
    for hid, (name, _, price, min_p) in latest_prices.items()
    if price == min_p
]

print("\n========== 当前价格为历史最低价的酒店 ==========")
if lowest_hits:
    for hid, name, price in lowest_hits:
        print(f"  {name}  ￥{price:.0f}")
else:
    print("  无")

# 5b. 最新价最低的五个酒店
top5 = sorted(latest_prices.items(), key=lambda x: x[1][2])[:5]

print("\n========== 当前价格最低的五个酒店 ==========")
for hid, (name, date, price, min_p) in top5:
    if price == min_p:
        tag = " ← 历史最低!"
    else:
        tag = f" (历史最低 ￥{min_p:.0f})"
    print(f"  {name}  ￥{price:.0f}{tag}")

# 5c. 保存到 data/
data_dir = "data"
os.makedirs(data_dir, exist_ok=True)

# 保存最新价即最低价的酒店
lowest_hits_path = os.path.join(data_dir, "latest_is_lowest.txt")
with open(lowest_hits_path, "w", encoding="utf-8") as f:
    f.write(f"最新价即最低价的酒店（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n")
    f.write("=" * 50 + "\n")
    if lowest_hits:
        for hid, name, price in lowest_hits:
            f.write(f"{name}  ￥{price:.0f}\n")
    else:
        f.write("无\n")
print(f"\n已保存到 {lowest_hits_path}")

# 保存最新价最低的五个酒店
top5_path = os.path.join(data_dir, "lowest_5_latest.txt")
with open(top5_path, "w", encoding="utf-8") as f:
    f.write(f"最新价最低的五个酒店（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n")
    f.write("=" * 50 + "\n")
    for hid, (name, date, price, min_p) in top5:
        tag = " ← 历史最低!" if price == min_p else f" (历史最低 ￥{min_p:.0f})"
        f.write(f"{name}  ￥{price:.0f}{tag}\n")
print(f"已保存到 {top5_path}")

# ============================================================
# 6. 渲染并保存图表
# ============================================================
plt.tight_layout()
out_dir = os.path.join("data", "charts")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "price_trends.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"已保存到 {out_path}")
