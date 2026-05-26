import os
import subprocess

import plot_trends
import send_email


CONDA_ENV = "crawler"


def main():
    if os.environ.get("CONDA_DEFAULT_ENV") != CONDA_ENV:
        print(f"当前不在 {CONDA_ENV} 环境中，通过 conda run 切换...")
        subprocess.run(
            ["conda", "run", "-n", CONDA_ENV, "python", "main.py"],
            check=True,
        )
        return

    print("=" * 50)
    print("Step 1: 生成价格趋势图")
    print("=" * 50)
    plot_trends.main()

    print("\n" + "=" * 50)
    print("Step 2: 发送邮件")
    print("=" * 50)
    send_email.send_chart()

    print("\n完成: 图表已生成并发送")


if __name__ == "__main__":
    main()