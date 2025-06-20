import json
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import pandas as pd
import numpy as np
from github_utils import push_png_to_github
# 加入 github_utils：for log 檔案的 load/save
try:
    from github_utils import load_json_from_github, save_json_to_github
except ImportError:
    # 若未使用 github 直接運行，fallback 用本地
    load_json_from_github = None
    save_json_to_github = None

class BiogasAnalyzer:
    def __init__(self, curve_json_dict):
        # 標準曲線（本地存取）
        self.curves = {}
        for tank, curve_json_path in curve_json_dict.items():
            with open(curve_json_path, 'r') as f:
                self.curves[tank] = json.load(f)

    def analyze(self, start_dates, today_str, total_gas, cumulative_log_path=None, is_cumulative=True):
        today = datetime.strptime(today_str, "%Y-%m-%d").date()

        last_cumulative = 0.0
        # 累積資料從 github 取
        if is_cumulative and cumulative_log_path and load_json_from_github is not None:
            try:
                log = load_json_from_github(cumulative_log_path)
                prior_dates = [d for d in log.keys() if d < today_str]
                if prior_dates:
                    last_day = max(prior_dates)
                    last_cumulative = log.get(last_day, 0.0)
            except Exception:
                last_cumulative = 0.0
        else:
            # fallback 本地
            if is_cumulative and cumulative_log_path and os.path.exists(cumulative_log_path):
                with open(cumulative_log_path, 'r') as f:
                    log = json.load(f)
                prior_dates = [d for d in log.keys() if d < today_str]
                if prior_dates:
                    last_day = max(prior_dates)
                    last_cumulative = log.get(last_day, 0.0)

        total_gas_today = max(total_gas - last_cumulative, 0)

        result = {}
        norm_sum = 0
        for tank, start_date_str in start_dates.items():
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            days = (today - start_date).days + 1
            curve = self.curves[tank]
            yield_list = curve.get("normalized_yield", [])

            if days < 1:
                norm = 0
                stage = f"尚未啟動（提前 {abs(days)} 天）"
            elif days > len(yield_list):
                norm = 0
                stage = f"結束期（已超出試程 {days - len(yield_list)} 天）"
            else:
                norm = yield_list[days - 1]
                stage = self._get_stage(days)

            result[tank] = {
                "day": days,
                "normalized": norm,
                "start_date": str(start_date),
                "stage": stage
            }
            norm_sum += norm

        for tank in result:
            norm = result[tank]["normalized"]
            volume = round(norm / norm_sum * total_gas_today, 2) if norm_sum > 0 else 0
            result[tank]["volume"] = volume

        return result

    def _get_stage(self, day):
        if day <= 3:
            return "起始期"
        elif day <= 6:
            return "上升期"
        elif day <= 9:
            return "高原期"
        elif day <= 14:
            return "衰退期"
        else:
            return f"結束期（已超出試程 {day - 14} 天）"

    def plot_cumulative(self, cumulative_data: dict, active_tanks: dict, save_path: str = "cumulative_plot.png"):
        import matplotlib.pyplot as plt

        dates = sorted(cumulative_data.keys())
        values = [cumulative_data[d] for d in dates]

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(dates, values, marker='o', color='blue')
        for x, y in zip(dates, values):
            ax.annotate(f"{int(y)}", xy=(x, y), xytext=(0, 8), textcoords='offset points',
                        ha='center', fontsize=10, clip_on=False)
        tank_label = ", ".join([f"{k}({v})" for k, v in active_tanks.items()])
        ax.set_ylim(0, max(values) * 1.15 if values else 1)
        ax.set_title(f"累積沼氣量趨勢\n運轉槽: {tank_label}", fontsize=16)
        ax.set_xlabel("日期", fontsize=14)
        ax.set_ylabel("累積產氣量 m³", fontsize=14)
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True)
        plt.tight_layout()
        plt.savefig(save_path)
        plt.close(fig)
        # === 自動推圖到 GitHub ===
        try:
            remote_name = f"figures/{os.path.basename(save_path)}"
            push_png_to_github(save_path, remote_name, commit_msg="每日累積沼氣量趨勢圖")
        except Exception as e:
            print(f"[WARNING] push_png_to_github 失敗: {e}")
        return save_path

    def plot_daily_distribution(self, result: dict, date_str: str, save_path: str = "daily_distribution.png"):
        df = pd.DataFrame(result).T.reset_index(names="Tank")
        fig, ax = plt.subplots(figsize=(8, 6))
        colors = plt.cm.Set2(np.arange(len(df)))
        bars = ax.bar(df['Tank'], df['volume'], color=colors)
        max_height = df['volume'].max()
        ax.set_ylim(0, max_height * 1.15)
        for bar, (_, row) in zip(bars, df.iterrows()):
            height = bar.get_height()
            if height > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + max_height * 0.03,
                    f"{row['volume']:.2f}",
                    ha='center', va='bottom', fontsize=12, fontweight='bold',
                    clip_on=False
                )
        ax.set_ylabel("預估產氣量 m³", fontsize=14)
        ax.set_title(f"{date_str} 各槽預估產氣量", fontsize=16)
        ax.tick_params(labelsize=12)
        plt.tight_layout()
        plt.savefig(save_path)
        plt.close(fig)
            # === 新增：自動推圖到 GitHub
        try:
            remote_name = f"figures/{date_str}_daily_distribution.png"
            push_png_to_github(save_path, remote_name, commit_msg=f"{date_str} 每日產氣分布圖")
        except Exception as e:
            print(f"[WARNING] push_png_to_github 失敗: {e}")
        return save_path

    def plot_stacked_estimation_and_cumulative(self, daily_data: dict, cumulative_data: dict, active_tanks: dict, save_path: str = "stacked_daily_cumulative.png"):
        import matplotlib.pyplot as plt
        import pandas as pd
        import numpy as np

        dates = sorted(cumulative_data.keys())
        df_est = pd.DataFrame(index=dates)
        for date in dates:
            tanks = daily_data.get(date, [])
            for entry in tanks:
                tank = entry['Tank']
                df_est.at[date, tank] = entry['volume']
        df_est = df_est.fillna(0)

        fig, ax1 = plt.subplots(figsize=(14, 6))
        tank_colors = plt.cm.Set3.colors
        bars = df_est.plot(kind='bar', stacked=True, ax=ax1, color=tank_colors[:len(df_est.columns)], edgecolor='black')
        for i, date in enumerate(df_est.index):
            y_offset = 0
            for j, tank in enumerate(df_est.columns):
                value = df_est.loc[date, tank]
                if value > 0:
                    y = y_offset + value / 2
                    ax1.text(i, y, f"{value:.1f}", ha='center', va='center', fontsize=12, weight='bold')
                    y_offset += value
        ax2 = ax1.twinx()
        cumulative_values = [cumulative_data.get(d, 0) for d in dates]
        ax2.plot(dates, cumulative_values, color='blue', marker='o', label='累積產氣量')
        tank_label = ", ".join([f"{tank}({active_tanks.get(tank, '-')})" for tank in df_est.columns])
        ax1.set_xlabel("日期", fontsize=14)
        ax1.set_ylabel("預估產氣量 m³", color='black', fontsize=16)
        ax2.set_ylabel("累積產氣量 m³", color='blue', fontsize=16)
        ax1.set_title(f"每日預估產氣 + 累積產氣量疊加圖\n運轉槽: {tank_label}", fontsize=20, weight='bold')
        ax1.tick_params(axis='x', labelrotation=45, labelsize=12)
        ax1.tick_params(axis='y', labelsize=12)
        ax2.tick_params(axis='y', labelsize=12)
        ax1.legend(title="槽別", fontsize=12, loc="center left", bbox_to_anchor=(0.03, 0.88))
        plt.tight_layout()
        plt.savefig(save_path)
        plt.close(fig)
        # === 自動推圖到 GitHub ===
        try:
            remote_name = f"figures/{os.path.basename(save_path)}"
            push_png_to_github(save_path, remote_name, commit_msg="每日疊加圖")
        except Exception as e:
            print(f"[WARNING] push_png_to_github 失敗: {e}")
        return save_path

    # --------- 這裡開始是 github 版 json 寫入 ---------
    def update_cumulative_log(self, log_path: str, today: str, gas_value: float):
        if load_json_from_github is not None:
            try:
                cumulative_data = load_json_from_github(log_path)
            except Exception:
                cumulative_data = {}
            cumulative_data[today] = gas_value
            save_json_to_github(log_path, cumulative_data)
        else:
            # fallback
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    cumulative_data = json.load(f)
            else:
                cumulative_data = {}
            cumulative_data[today] = gas_value
            with open(log_path, "w") as f:
                json.dump(cumulative_data, f, indent=2)
        return cumulative_data

    def reset_cumulative_log(self, log_path: str):
        if save_json_to_github is not None:
            save_json_to_github(log_path, {})
            return {}
        else:
            with open(log_path, "w") as f:
                json.dump({}, f, indent=2)
            return {}

    def run_cumulative_pipeline(self, log_path: str, today: str, gas_value: float, active_tanks: dict, save_path: str = "cumulative_plot.png"):
        if load_json_from_github is not None:
            cumulative_data = self.update_cumulative_log(log_path, today, gas_value)
            return self.plot_cumulative(cumulative_data, active_tanks, save_path)
        else:
            # fallback 本地
            cumulative_data = self.update_cumulative_log(log_path, today, gas_value)
            return self.plot_cumulative(cumulative_data, active_tanks, save_path)

    def run_stacked_pipeline(self, daily_log_path: str, cumulative_log_path: str, active_tanks: dict, save_path: str = "stacked_daily_cumulative.png"):
        if load_json_from_github is not None:
            try:
                daily_data = load_json_from_github(daily_log_path)
            except Exception:
                daily_data = {}
            try:
                cumulative_data = load_json_from_github(cumulative_log_path)
            except Exception:
                cumulative_data = {}
        else:
            # fallback
            if os.path.exists(daily_log_path):
                with open(daily_log_path, "r") as f:
                    daily_data = json.load(f)
            else:
                daily_data = {}
            if os.path.exists(cumulative_log_path):
                with open(cumulative_log_path, "r") as f:
                    cumulative_data = json.load(f)
            else:
                cumulative_data = {}
        return self.plot_stacked_estimation_and_cumulative(daily_data, cumulative_data, active_tanks, save_path)
