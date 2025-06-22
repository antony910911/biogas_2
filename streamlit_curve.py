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
import matplotlib.dates as mdates
import threading
from github_utils import GITHUB_TOKEN

font_path = "fonts/NotoSansTC-Regular.ttf"  # 字型檔路徑
fm.fontManager.addfont(font_path)
plt.rcParams['font.sans-serif'] = ['Noto Sans TC', 'Microsoft JhengHei', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False  # 避免負號亂碼

if not GITHUB_TOKEN:
    st.error("🚨 GITHUB_TOKEN 尚未設定，請到 secrets 或環境變數設定！")
else:
    print(f"[DEBUG] GITHUB_TOKEN loaded, first 4: {GITHUB_TOKEN[:4]}")

# 載入雲端 user_config
CONFIG_FILE = "user_config.json"
tanks = ["A", "B", "C"]

try:
    user_config = load_json_from_github(CONFIG_FILE)
except:
    user_config = {}

for tank in tanks:
    if tank not in user_config:
        user_config[tank] = {}
    user_config[tank].setdefault("start_date", str(date.today()))
    user_config[tank].setdefault("lock", False)
    user_config[tank].setdefault("run", False)
    # 初始化 session_state
    st.session_state.setdefault(f"start_{tank.lower()}", user_config[tank]["start_date"])
    st.session_state.setdefault(f"lock_{tank.lower()}", user_config[tank]["lock"])
    st.session_state.setdefault(f"run_{tank.lower()}", user_config[tank]["run"])

tab1, tab2, tab3 = st.tabs(["app說明頁","沼氣紀錄", "⚡️發電潛能紀錄"])


def ensure_curve_local(curve_name):
    """
    若本地無此曲線，則自動從 github 下載一份到 curves/ 資料夾
    """
    import os, json
    local_path = f"curves/{curve_name}"
    if not os.path.exists(local_path):
        curve_data = load_json_from_github(f"curves/{curve_name}")
        os.makedirs("curves", exist_ok=True)
        with open(local_path, "w") as f:
            json.dump(curve_data, f, indent=2)
    return local_path



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
    print("list 失敗:", resp.status_code, resp.text)
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

with tab1:

    st.title("🧪 沼氣管理平台 ℹ️ 使用說明")
    st.markdown("""
    ### 沼氣管理平台操作說明

    **功能介紹：**
    - `📈 產氣紀錄/分析`：管理與查詢每日各槽產氣數據，分析趨勢。
    - `⚡️ 發電潛能紀錄`：登錄甲烷濃度、產氣量，計算當日發電潛能與趨勢。
    - `ℹ️ 使用說明`：本頁即為功能操作說明、FAQ與技術支援窗口。

    **常見操作：**
    1. 點選「產氣紀錄/分析」進行數據登錄與查詢。
    2. 若要計算發電潛能，請切換至「發電潛能紀錄」頁。
    3. 系統所有數據皆自動存入 GitHub 雲端，不怕遺失。
    
    **遇到問題？**
    - 請確認 GitHub Token 設定正確，必要時重新整理頁面。

    ---
    """
    )

# === 路徑設定（僅曲線存在本地）===
CURVE_DIR = "curves"
LOG_PATH = "cumulative_gas_log.json"
DAILY_RESULT_LOG = "daily_result_log.json"
ASSIGN_FILE = "curve_assignment.json"
os.makedirs(CURVE_DIR, exist_ok=True)


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
with tab2:
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
        # ↓↓↓ 自動抓取本地檔案，沒有就下載
        local_path = ensure_curve_local(selected)
        with open(local_path, "r") as f:
            data = json.load(f)
        st.markdown(f"**名稱**：{data['name']}")
        st.markdown(f"**描述**：{data['description']}")
        df = pd.DataFrame({"Day": data['days'], "Normalized_Yield": data['normalized_yield']})
        fig, ax = plt.subplots()
        ax.plot(df['Day'], df['Normalized_Yield'], marker='o', color='green')
        ax.set_title(f"{data['name']} 曲線圖")
        st.pyplot(fig)

    # === 區塊 3：指派曲線 ===
    curve_files = list_curves_on_github()
    a_curve = b_curve = c_curve = None

    if not curve_files:
        st.warning("⚠️ 目前雲端 curves/ 沒有曲線 json 檔！請先新增。")
    else:
        # 嘗試讀取 assignment，取得預設值
        try:
            assign = load_json_from_github(ASSIGN_FILE)
            default_a = os.path.basename(assign.get("A", "")) if assign.get("A", "") else curve_files[0]
            default_b = os.path.basename(assign.get("B", "")) if assign.get("B", "") else curve_files[0]
            default_c = os.path.basename(assign.get("C", "")) if assign.get("C", "") else curve_files[0]
        except Exception:
            default_a = default_b = default_c = curve_files[0]

        col1, col2, col3 = st.columns(3)
        with col1:
            a_curve = st.selectbox(
                "槽 A 使用的曲線", curve_files,
                index=curve_files.index(default_a) if default_a in curve_files else 0,
                key="curve_a"
            )
        with col2:
            b_curve = st.selectbox(
                "槽 B 使用的曲線", curve_files,
                index=curve_files.index(default_b) if default_b in curve_files else 0,
                key="curve_b"
            )
        with col3:
            c_curve = st.selectbox(
                "槽 C 使用的曲線", curve_files,
                index=curve_files.index(default_c) if default_c in curve_files else 0,
                key="curve_c"
            )

        if a_curve and b_curve and c_curve:
            mapping = {
                "A": f"curves/{a_curve}",
                "B": f"curves/{b_curve}",
                "C": f"curves/{c_curve}"
            }
            if st.button("💾 儲存槽別指派設定"):
                save_json_to_github(ASSIGN_FILE, mapping)
                st.success("已儲存槽別指派設定！")
        else:
            st.info("請確認三個槽都已選擇曲線檔案。")


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

        # === 將 A/B/C 的設定寫入 user_config 並存到 GitHub ===
        for tank in tanks:
            user_config[tank]["start_date"] = str(st.session_state[f"start_{tank.lower()}"])
            user_config[tank]["lock"] = st.session_state[f"lock_{tank.lower()}"]
            user_config[tank]["run"] = st.session_state[f"run_{tank.lower()}"]
        save_json_to_github(CONFIG_FILE, user_config)



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
                    st.rerun()

                else:
                    st.warning("該日期已不在歷史紀錄中。")
            df_hist = pd.DataFrame(history[selected_day])
            st.dataframe(df_hist, use_container_width=True)
            fig, ax = plt.subplots(figsize=(8, 6))
            bars = ax.bar(df_hist['Tank'], df_hist['volume'], color='gray', width=0.2)
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






with tab3:
    ch4_label = "甲烷"  # 'CH₄'

    st.header(f"⚡️ 沼氣 {ch4_label} 濃度/產氣量/發電潛能管理")


    import matplotlib.dates as mdates
    # 字型設定
    font_path = "fonts/NotoSansTC-Regular.ttf"
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.sans-serif'] = ['Noto Sans TC', 'Microsoft JhengHei', 'Arial Unicode MS', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False

    st.markdown(f"""
    #### 🔢 發電潛能計算公式

    $$
    P_{{gen}}\\ (\\mathrm{{kW}}) = Q_{{gas}} \\times \\left( \\frac{{CH_4}}{{100}} \\right) \\times LHV_{{CH_4}} \\times \\eta
    $$

    - $Q_{{gas}}$：沼氣產氣量（m³/天，若已知每小時流量則用 m³/h）
    - $CH_4$：甲烷濃度（%）
    - $LHV_{{CH_4}}$：甲烷低位發熱值（9.97 kWh/m³）
    - $\\eta$：發電機組綜合發電效率（建議 35%，即 0.35）

    > ⚡️ **說明：**  
    > 本系統目前計算的是「理論最大發電功率（kW）」，如要轉換為「發電量（kWh）」，請乘以實際發電時數。
    > $$
    > E_{{gen}}\\ (\\mathrm{{kWh}}) = P_{{gen}}\\ (\\mathrm{{kW}}) \\times \\text{{運轉時數}}\\ (h)
    > $$
    """)

    def calc_power_potential(gas_volume, ch4_percent, eff=0.35):
        CH4_LHV = 9.97
        ch4_vol = gas_volume * (ch4_percent / 100)
        return round(ch4_vol * CH4_LHV * eff, 2)

    # 讀取雲端json
    daily_log = load_json_from_github("daily_result_log.json") or {}
    ch4_log = load_json_from_github("ch4_result_log.json") or {}

    # ===== 手動輸入/修正 CH₄ 濃度 =====
    st.subheader(f"手動新增/修正 {ch4_label} 濃度")
    all_dates = sorted(set(list(daily_log.keys()) + list(ch4_log.keys())), reverse=True)
    input_date = st.selectbox("選擇日期", all_dates, index=0 if all_dates else None)
    tank_choices = [tank.get("Tank") for tank in daily_log.get(input_date, [])] if input_date in daily_log else ["A", "B", "C"]
    input_tank = st.selectbox("選擇槽別", tank_choices)
    input_ch4 = st.number_input(f"輸入{ch4_label}濃度（%）", min_value=0.0, max_value=100.0, step=0.1,
                                value=ch4_log.get(input_date, {}).get(input_tank, 0.0))
    if st.button(f"儲存/覆寫該日該槽{ch4_label}濃度"):
        ch4_log.setdefault(input_date, {})
        ch4_log[input_date][input_tank] = input_ch4
        save_json_to_github("ch4_result_log.json", ch4_log)
        st.success(f"已儲存 {input_date} {input_tank} = {input_ch4:.1f}%")
        st.rerun()

    # ===== 刪除 CH₄ 紀錄 =====
    st.subheader(f"刪除 {ch4_label} 濃度紀錄")
    del_date = st.selectbox("選擇欲刪除日期", all_dates, key="del_date")
    if del_date and st.button(f"刪除 {del_date} 的 {ch4_label} 紀錄"):
        if del_date in ch4_log:
            del ch4_log[del_date]
            save_json_to_github("ch4_result_log.json", ch4_log)
            st.success(f"已刪除 {del_date} 的 {ch4_label} 濃度紀錄")
            st.rerun()

    # ===== 主表與自動計算發電潛能、加權平均、CH4產量 =====
    records = []
    for d in sorted(daily_log.keys()):
        tanks = daily_log[d]
        total_gas = 0
        total_ch4_weighted = 0
        power_total = 0
        tank_ch4s = []
        for tank in tanks:
            tank_name = tank.get("Tank")
            v = tank.get("volume", 0)
            ch4 = ch4_log.get(d, {}).get(tank_name, None)
            total_gas += v
            if ch4 is not None:
                total_ch4_weighted += v * ch4
                power = calc_power_potential(v, ch4)
                power_total += power
                tank_ch4s.append(f"{tank_name}:{ch4:.1f}%")
            else:
                tank_ch4s.append(f"{tank_name}:--")
        ch4_avg = total_ch4_weighted / total_gas if total_gas > 0 else None
        ch4_volume = ch4_avg * total_gas / 100 if ch4_avg is not None else None  # 這就是實際甲烷產量（m³）
        records.append({
            "日期": d,
            "產氣量": total_gas,
            f"加權{ch4_label}(%)": ch4_avg,
            f"{ch4_label}產量(m³)": ch4_volume,
            "發電潛能(kW)": power_total,
            f"各槽{ch4_label}": "; ".join(tank_ch4s)
        })

    df = pd.DataFrame(records)

    if not df.empty:
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期")
        st.dataframe(df, use_container_width=True)
        st.download_button("下載 Excel", df.to_csv(index=False), file_name="auto_power_potential_history.csv")

        # 畫圖

        fig, ax1 = plt.subplots(figsize=(10, 5))
        ax2 = ax1.twinx()
        width = 0.3

        # === bar: 加權CH₄(%) ===
        bars = ax1.bar(df["日期"], df[f"加權{ch4_label}(%)"], width=width, color='#68a5d7', alpha=0.8, label=f"加權{ch4_label}(%)")

        # --- 留頭頂空間 ---
        ymax = max(df[f"加權{ch4_label}(%)"].max(), 10)
        ax1.set_ylim(0, ymax * 1.15)  # 自動多預留15%

        # --- 數值標註，距離上方有間隔 ---
        bar_offset = ymax * 0.03
        for i, v in enumerate(df[f"加權{ch4_label}(%)"]):
            ax1.text(df["日期"].iloc[i], v + bar_offset, f"{v:.1f}", ha='center', va='bottom', fontsize=13, color='#1c3d5a', fontweight='bold')

        # === line: 發電潛能 ===
        ax2.plot(df["日期"], df["發電潛能(kW)"], color='r', marker='o', label="發電潛能(kW)")

        # --- x軸/y軸標題與顏色 ---
        ax1.set_ylabel(f"加權{ch4_label} (%)", fontsize=18, color='#0223db', fontweight='bold')
        ax2.set_ylabel("發電潛能 (kW)", fontsize=18, color='r', fontweight='bold')
        ax1.tick_params(axis='y', labelcolor='#0223db')
        ax2.tick_params(axis='y', labelcolor='r')
        ax1.set_xlabel("日期", fontsize=18, fontweight='bold')

        plt.title(f"加權{ch4_label}與發電潛能趨勢", fontsize=18, fontweight='bold')

        # --- x軸美化 ---
        locator = mdates.AutoDateLocator(minticks=5, maxticks=15)
        formatter = mdates.DateFormatter('%Y-%m-%d')
        ax1.xaxis.set_major_locator(locator)
        ax1.xaxis.set_major_formatter(formatter)
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=14, fontweight='bold')

        fig.tight_layout()
        st.pyplot(fig)


        st.markdown(f"#### 各槽每日{ch4_label}濃度")
        st.dataframe(df[["日期", f"各槽{ch4_label}"]])
    else:
        st.info("暫無每日產氣資料，請先分析或上傳 daily_result_log。")