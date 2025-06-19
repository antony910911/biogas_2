# streamlit_curve_manager.py
import streamlit as st
st.set_page_config(page_title="產氣曲線管理")

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import json
import os
from datetime import date
from biogas_2 import BiogasAnalyzer
from flask import Flask, request, jsonify
import threading


# === GitHub 儲存工具 ===
from github_utils import load_json_from_github, save_json_to_github, save_binary_to_github

def ensure_curve_local(curve_name):
    local_path = f"curves/{curve_name}"
    if not os.path.exists(local_path):
        # 下載 github 上的 curves/{curve_name} 存本地
        curve_data = load_json_from_github(f"curves/{curve_name}")
        os.makedirs("curves", exist_ok=True)
        with open(local_path, "w") as f:
            json.dump(curve_data, f, indent=2)
    return local_path

def list_curves_on_github(subdir="curves"):
    import requests, os
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    REPO = "antony910911/biogas_2"
    BRANCH = "main"
    url = f"https://api.github.com/repos/{REPO}/contents/{subdir}?ref={BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        files = [item["name"] for item in resp.json() if item["name"].endswith(".json")]
        return files
    return []


def push_png_to_github(local_path, remote_filename, commit_msg="自動上傳圖檔"):
    with open(local_path, "rb") as f:
        img_bytes = f.read()
    save_binary_to_github(
        filepath=remote_filename,   # 例如 "figures/2024-06-19_daily_distribution.png"
        bin_data=img_bytes,
        commit_msg=commit_msg
    )



# ==== 強制字型設定 ====
font_path = "fonts/NotoSansTC-Regular.ttf"
try:
    fm.fontManager.addfont(font_path)
    font_prop = fm.FontProperties(fname=font_path)
    font_name = font_prop.get_name()
    plt.rcParams['font.sans-serif'] = [font_name]
    plt.rcParams['axes.unicode_minus'] = False
except Exception as e:
    plt.rcParams['font.sans-serif'] = ['sans-serif']

st.title("🧪 沼氣產氣曲線管理中心")

# === 路徑設定（僅曲線存在本地）===
CURVE_DIR = "curves"
LOG_PATH = "cumulative_gas_log.json"
DAILY_RESULT_LOG = "daily_result_log.json"
ASSIGN_FILE = "curve_assignment.json"
os.makedirs(CURVE_DIR, exist_ok=True)

# === Webhook Flask app（可留可不留） ===
app = Flask(__name__)

@app.route("/reset_log", methods=["POST"])
def reset_log():
    BiogasAnalyzer({}).reset_cumulative_log(LOG_PATH)
    return jsonify({"status": "reset done"})

def run_webhook():
    app.run(port=5678, debug=False, use_reloader=False)

threading.Thread(target=run_webhook, daemon=True).start()

# 預設初始化 session state（防止第一次提交無效）
def init_state():
    defaults = {
        "today_date": date.today(),
        "is_cumulative": True,
        "gas_input": 0.0,
        "run_a": True,
        "run_b": True,
        "run_c": True,
        "start_a": date.today(),
        "start_b": date.today(),
        "start_c": date.today(),
        "lock_a": False,
        "lock_b": False,
        "lock_c": False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# === 區塊 1：上傳標準曲線 ===
st.header("📤 上傳標準曲線")
file = st.file_uploader("請上傳 CSV 或 JSON 曲線檔", type=["csv", "json"])
if file:
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
        st.success("成功讀取 CSV！")
    else:
        raw = json.load(file)
        df = pd.DataFrame({"Day": raw['days'], "Yield": raw['raw_yield']})

    df['Normalized_Yield'] = df['Yield'] / df['Yield'].max()
    st.dataframe(df)

    fig, ax = plt.subplots()
    ax.plot(df['Day'], df['Normalized_Yield'], marker='o')
    ax.set_xlabel("Day")
    ax.set_ylabel("Normalized Yield")
    ax.set_title("Biogas Production Curve")
    st.pyplot(fig)

    name_default = os.path.splitext(file.name)[0]
    name = st.text_input("請輸入曲線名稱", value=name_default)
    desc = st.text_area("描述", value="描述這條曲線的特性")
    if st.button("✅ 儲存曲線"):
        out = {
            "name": name,
            "description": desc,
            "days": df['Day'].tolist(),
            "normalized_yield": df['Normalized_Yield'].round(6).tolist(),
            "raw_yield": df['Yield'].tolist()
        }
        # 本地存一份（非必要，可拿掉）
        with open(f"{CURVE_DIR}/{name}.json", "w") as f:
            json.dump(out, f, indent=2)
        # 雲端 GitHub 也存一份
        from github_utils import save_json_to_github
        save_json_to_github(f"curves/{name}.json", out, commit_msg=f"新增/更新標準曲線 {name}")

        st.success(f"已儲存為 {name}.json，並同步上傳至 GitHub")


# === 區塊 2：曲線列表 ===
st.header("📚 已有曲線管理")

# 新的（自動抓 github 曲線 json 檔名）
curve_files = list_curves_on_github()

selected = st.selectbox("選擇查看某條曲線", curve_files)
if selected:
    with open(f"{CURVE_DIR}/{selected}") as f:
        data = json.load(f)
    st.markdown(f"**名稱**：{data['name']}")
    st.markdown(f"**描述**：{data['description']}")
    df = pd.DataFrame({"Day": data['days'], "Normalized_Yield": data['normalized_yield']})
    fig, ax = plt.subplots()
    ax.plot(df['Day'], df['Normalized_Yield'], marker='o', color='green')
    ax.set_title(f"{data['name']} 曲線圖")
    st.pyplot(fig)

# === 區塊 3：指派曲線 ===
st.header("🧩 指派曲線給各槽")
col1, col2, col3 = st.columns(3)
with col1:
    a_curve = st.selectbox("槽 A 使用的曲線", curve_files, key="curve_a")
with col2:
    b_curve = st.selectbox("槽 B 使用的曲線", curve_files, key="curve_b")
with col3:
    c_curve = st.selectbox("槽 C 使用的曲線", curve_files, key="curve_c")

mapping = {"A": os.path.join(CURVE_DIR, a_curve), "B": os.path.join(CURVE_DIR, b_curve), "C": os.path.join(CURVE_DIR, c_curve)}
if st.button("💾 儲存槽別指派設定"):
    # 曲線指派設定也存 github
    save_json_to_github(ASSIGN_FILE, mapping)
    st.success("已儲存槽別指派設定！")

# === 區塊 4 :即時產氣分析設定表單（含啟動日鎖定功能） ===
st.header("📊 即時產氣分析")
if st.button("🧹 一鍵歸零累積紀錄"):
    # 歸零只影響 json，直接覆蓋 github json
    save_json_to_github(LOG_PATH, {})
    save_json_to_github(DAILY_RESULT_LOG, {})
    st.success("累積紀錄與圖表已清空！")

with st.form("analysis_form"):
    col1, col2 = st.columns(2)
    with col1:
        date_today = st.date_input("選擇今天日期", value=st.session_state["today_date"])
    with col2:
        is_cumulative = st.checkbox("輸入為累積值", value=st.session_state["is_cumulative"], key="is_cumulative_chk")
        gas_input = st.number_input("輸入沼氣量 (m³)", min_value=0.0, step=0.1, value=st.session_state["gas_input"])

    st.markdown("**請輸入每個槽的啟動日期與是否運轉中：**")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        run_a = st.checkbox(" A 槽運轉中", value=st.session_state["run_a"], key="run_a_chk")
        lock_a = st.checkbox("🔒 鎖定啟動日 A", value=st.session_state["lock_a"], key="lock_a_chk")
        start_a = st.date_input(" A 槽啟動日", value=st.session_state["start_a"], key="start_a_input", disabled=lock_a)
    with col_b:
        run_b = st.checkbox(" B 槽運轉中", value=st.session_state["run_b"], key="run_b_chk")
        lock_b = st.checkbox("🔒 鎖定啟動日 B", value=st.session_state["lock_b"], key="lock_b_chk")
        start_b = st.date_input(" B 槽啟動日", value=st.session_state["start_b"], key="start_b_input", disabled=lock_b)
    with col_c:
        run_c = st.checkbox(" C 槽運轉中", value=st.session_state["run_c"], key="run_c_chk")
        lock_c = st.checkbox("🔒 鎖定啟動日 C", value=st.session_state["lock_c"], key="lock_c_chk")
        start_c = st.date_input(" C 槽啟動日", value=st.session_state["start_c"], key="start_c_input", disabled=lock_c)

    submitted = st.form_submit_button("🚀 執行分析")

if submitted:
    st.session_state["today_date"] = date_today
    st.session_state["is_cumulative"] = is_cumulative
    st.session_state["gas_input"] = gas_input
    st.session_state["run_a"] = run_a
    st.session_state["run_b"] = run_b
    st.session_state["run_c"] = run_c
    st.session_state["lock_a"] = lock_a
    st.session_state["lock_b"] = lock_b
    st.session_state["lock_c"] = lock_c
    st.session_state["analysis_ran"] = True 
    if not lock_a:
        st.session_state["start_a"] = start_a
    if not lock_b:
        st.session_state["start_b"] = start_b
    if not lock_c:
        st.session_state["start_c"] = start_c

    st.success("設定已送出並完成分析準備！")

    active_tanks = {}
    if run_a: active_tanks["A"] = str(start_a)
    if run_b: active_tanks["B"] = str(start_b)
    if run_c: active_tanks["C"] = str(start_c)

    # 從 github 讀取曲線指派設定
    try:
        full_mapping = load_json_from_github(ASSIGN_FILE)
        active_mapping = {k: full_mapping[k] for k in active_tanks if k in full_mapping}
    except Exception as e:
        st.error(f"❗ 無法讀取指派設定：{e}")
        st.stop()

    analyzer = BiogasAnalyzer(active_mapping)
    result = analyzer.analyze(
        start_dates=active_tanks,
        today_str=str(date_today),
        total_gas=gas_input,
        cumulative_log_path=LOG_PATH,
        is_cumulative=True
    )

    df_result = pd.DataFrame(result).T.reset_index(names="Tank")
    st.subheader("📋 分析結果")
    st.dataframe(df_result, use_container_width=True)

    # 從 github 讀歷史，更新，寫回 github
    try:
        history = load_json_from_github(DAILY_RESULT_LOG)
    except:
        history = {}
    history[str(date_today)] = df_result.to_dict(orient="records")
    save_json_to_github(DAILY_RESULT_LOG, history)

    # 畫分布圖（本地產生圖片，不存 github）
    plot_path = analyzer.plot_daily_distribution(result, date_str=str(date_today))
    st.image(plot_path, caption=f"{date_today} 各槽預估產氣量", use_container_width=True)
    # push到GitHub
    push_png_to_github(
        plot_path,
        f"figures/{date_today}_daily_distribution.png",
        commit_msg=f"每日產氣分布圖：{date_today}"
    )

    # 累積圖也同步 github
    plot_path = analyzer.run_cumulative_pipeline(
        log_path=LOG_PATH,
        today=str(date_today),
        gas_value=gas_input,
        active_tanks=active_tanks
    )
    st.image(plot_path, caption="📈 累積沼氣量趨勢", use_container_width=True)
    # push到GitHub
    push_png_to_github(
        plot_path,
        f"figures/{date_today}_cumulative.png",
        commit_msg=f"每日累積圖：{date_today}"
    )


    csv = df_result.to_csv(index=False).encode('utf-8')
    st.download_button("📥 下載分析結果 CSV", csv, file_name="biogas_analysis_result.csv")

    # 疊加圖
    stacked_path = analyzer.run_stacked_pipeline(DAILY_RESULT_LOG, LOG_PATH, active_tanks)
    st.image(stacked_path, caption="📊 每日預估產氣 + 累積產氣量疊加圖（含各槽）", use_container_width=True)
    # push到GitHub
    push_png_to_github(
        stacked_path,
        f"figures/{date_today}_stacked.png",
        commit_msg=f"每日疊加圖：{date_today}"
    )

# 首頁預設展示現有圖（如有）
if not st.session_state.get("analysis_ran", False):
    if os.path.exists("cumulative_plot.png"):
        st.image("cumulative_plot.png", caption="📈 累積沼氣量趨勢", use_container_width=True)
    if os.path.exists("stacked_daily_cumulative.png"):
        st.image("stacked_daily_cumulative.png", caption="📊 每日預估產氣 + 累積產氣量疊加圖（含各槽）", use_container_width=True)

# === 區塊 5：歷史預估產氣量查詢（全部讀 github） ===
st.header("🕓 歷史預估產氣量查詢")
try:
    history = load_json_from_github(DAILY_RESULT_LOG)
    dates = list(history.keys())
    selected_day = st.selectbox("選擇日期查看分析結果", options=sorted(dates, reverse=True))
    if selected_day:
        # 刪除按鈕
        if st.button(f"🗑️ 刪除 {selected_day} 這一天的紀錄"):
            if selected_day in history:
                del history[selected_day]
                save_json_to_github(DAILY_RESULT_LOG, history)
                st.success(f"已刪除 {selected_day} 的紀錄")
                st.experimental_rerun()
            else:
                st.warning("該日期已不在歷史紀錄中。")
        df_hist = pd.DataFrame(history[selected_day])
        st.dataframe(df_hist, use_container_width=True)
        fig, ax = plt.subplots(figsize=(8, 6))
        bars = ax.bar(df_hist['Tank'], df_hist['volume'], color='gray', width=0.5)
        max_vol = df_hist['volume'].max()
        ax.set_ylim(0, max_vol * 1.20)
        for idx, row in df_hist.iterrows():
            ax.text(
                idx,
                row['volume'] + max_vol * 0.02,
                f"{row['volume']:.1f}",
                ha='center', va='bottom', fontsize=14, fontweight='bold',
                clip_on=False
            )
        ax.set_title(f"{selected_day} 各槽預估產氣量", fontsize=18)
        ax.set_xlabel("槽別", fontsize=14)
        ax.set_ylabel("產氣量 Nm³", fontsize=14)
        ax.tick_params(axis='both', labelsize=13)
        plt.tight_layout()
        st.pyplot(fig)
    else:
        st.info("尚無歷史紀錄。")
except Exception as e:
    st.info(f"歷史紀錄讀取失敗：{e}")
