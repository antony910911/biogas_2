import os
import requests
import base64
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, TextSendMessage, ImageSendMessage
)

from biogas_2 import BiogasAnalyzer
from streamlit_curve import load_json_from_github, save_json_to_github

# === 初始設定 ===
load_dotenv()
app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "antony910911/biogas_2")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# === 公用參數 ===
PHOTO_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/photo"

# === 工具函數：取得目前運轉中的槽與啟動日（與 Streamlit 完全同步） ===
def get_active_tanks():
    user_config = load_json_from_github("user_config.json")
    # 只回傳 run=True 的槽與啟動日
    return {tank: conf["start_date"] for tank, conf in user_config.items() if conf.get("run", False)}

# === 工具函數：支援 LINE 下「6/21 A槽 啟動」、「6/25 B槽 結束」 ===
def handle_tank_event_command(msg):
    import re
    m = re.match(r"(\d{1,2}/\d{1,2})\s*([ABC])槽\s*(啟動|結束)", msg)
    if not m:
        return TextSendMessage(text="❌ 指令格式錯誤，請用 6/21 A槽 啟動")
    dt, tank, op = m.groups()
    y = date.today().year
    try:
        dt_obj = datetime.strptime(f"{y}/{dt}", "%Y/%m/%d").date()
    except Exception:
        return TextSendMessage(text="❌ 日期格式錯誤")
    user_config = load_json_from_github("user_config.json")
    tank = tank.upper()
    if tank not in user_config:
        return TextSendMessage(text=f"❌ 查無 {tank} 槽")
    if op == "啟動":
        user_config[tank]["run"] = True
        user_config[tank]["start_date"] = str(dt_obj)
    else:
        user_config[tank]["run"] = False
    save_json_to_github("user_config.json", user_config)
    return TextSendMessage(text=f"✅ 已設定 {tank} 槽 {'啟動' if op=='啟動' else '結束'}於 {dt_obj}")

# === Home Page (健康檢查用) ===
@app.route("/")
def home():
    return "Biogas Webhook is running."

# === LINE Webhook ===
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError as e:
        print(f"[ERROR] LINE Signature invalid: {e}")
        abort(400)
    return 'OK'

# === 主訊息處理 ===
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()

    # 幫助/說明
    if msg in ["指令", "help", "說明"]:
        reply = handle_help_command()
        line_bot_api.reply_message(event.reply_token, reply)
        return

    # 今日產氣：今日產氣 720
    if msg.startswith("今日產氣"):
        value_str = msg.replace("今日產氣", "").strip()
        replies = handle_today_gas_command(value_str)
        line_bot_api.reply_message(event.reply_token, replies)
        return

    # 啟動/結束
    if "啟動" in msg or "結束" in msg:
        reply = handle_tank_event_command(msg)
        line_bot_api.reply_message(event.reply_token, reply)
        return

    # 目前階段
    if msg == "目前階段":
        reply = handle_current_stage_command()
        line_bot_api.reply_message(event.reply_token, reply)
        return

    # 查詢 yyyy-mm-dd
    if msg.startswith("查詢"):
        date_str = msg.replace("查詢", "").strip()
        reply, images = handle_query_by_date_command(date_str)
        line_bot_api.reply_message(event.reply_token, [reply]+images)
        return

    # 週報
    if msg == "週報":
        reply = handle_weekly_report_command()
        line_bot_api.reply_message(event.reply_token, reply)
        return

    # AI分析
    if msg == "AI分析":
        reply = handle_ai_summary_command()
        line_bot_api.reply_message(event.reply_token, reply)
        return

    # 多日批次輸入（多行 YYYY-MM-DD 數值）
    if "\n" in msg and all(len(line.strip().split()) == 2 for line in msg.strip().split("\n")):
        replies = handle_batch_gas_input_command(msg)
        line_bot_api.reply_message(event.reply_token, replies)
        return

    # fallback
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❓ 尚未支援此指令（請輸入「指令」查看用法）"))

# === 圖片訊息處理 (可選，放大你的專案) ===
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 圖片辨識尚未開放，請用文字指令查詢。"))

# === 幫助說明 ===
def handle_help_command():
    return TextSendMessage(text=(
        "✅ 支援指令一覽：\n"
        "1️⃣ 啟動/結束紀錄：\n"
        "    例：6/10 A槽 啟動、6/20 A槽 結束\n"
        "2️⃣ 查詢目前狀態：\n"
        "    ➤ 指令：目前階段\n"
        "3️⃣ 登記今日產氣量：\n"
        "    ➤ 指令：今日產氣 720\n"
        "4️⃣ 查詢指定日期：\n"
        "    ➤ 指令：查詢 2025-06-15\n"
        "5️⃣ 產氣週報：\n"
        "    ➤ 指令：週報\n"
        "6️⃣ 多日批次輸入：\n"
        "    ➤ 格式：多行 YYYY-MM-DD 數值（貼上多行）\n"
        "7️⃣ AI 分析摘要：\n"
        "    ➤ 指令：AI分析"
    ))

# === 今日產氣指令（直接用 get_active_tanks） ===
def handle_today_gas_command(value_str):
    try:
        value = float(value_str)
        today_str = str(date.today())
        active_tanks = get_active_tanks()
        analyzer = BiogasAnalyzer(active_tanks)
        result = analyzer.analyze(active_tanks, today_str, value)
        history = load_json_from_github("daily_result_log.json")
        history[today_str] = result
        save_json_to_github("daily_result_log.json", history, f"記錄 {today_str} 產氣量")
        analyzer.update_cumulative_log(today_str, value)
        # 產圖
        analyzer.plot_daily_distribution(result, today_str)
        analyzer.run_stacked_pipeline("daily_result_log.json", "cumulative_gas_log.json", active_tanks)
        # 回傳圖片
        imgs = [
            ImageSendMessage(original_content_url=f"{PHOTO_BASE_URL}/daily_plot_{today_str}.png", preview_image_url=f"{PHOTO_BASE_URL}/daily_plot_{today_str}.png"),
            ImageSendMessage(original_content_url=f"{PHOTO_BASE_URL}/stacked_{today_str}.png", preview_image_url=f"{PHOTO_BASE_URL}/stacked_{today_str}.png"),
            ImageSendMessage(original_content_url=f"{PHOTO_BASE_URL}/cumulative_plot_{today_str}.png", preview_image_url=f"{PHOTO_BASE_URL}/cumulative_plot_{today_str}.png"),
        ]
        return [TextSendMessage(text=f"✅ 已記錄今日產氣量：{value:.1f} m³")] + imgs
    except Exception as e:
        return [TextSendMessage(text=f"❌ 請輸入正確格式，例如：今日產氣 720\n({e})")]

# === 查詢指定日期 ===
def handle_query_by_date_command(date_str):
    history = load_json_from_github("daily_result_log.json")
    if date_str not in history:
        return TextSendMessage(text=f"❌ 查無 {date_str} 紀錄"), []
    items = history[date_str]
    total = sum(i['volume'] for i in items)
    reply = f"📅 {date_str} 各槽產氣狀態：\n"
    for item in items:
        reply += f"槽 {item.get('Tank', '')}：{item.get('stage', '')} 第{item.get('day', '')}天\n產氣 {item.get('volume', 0):.1f} m³\n"
    reply += f"\n🔢 總產氣：{total:.1f} m³"
    images = [
        ImageSendMessage(original_content_url=f"{PHOTO_BASE_URL}/daily_plot_{date_str}.png", preview_image_url=f"{PHOTO_BASE_URL}/daily_plot_{date_str}.png"),
        ImageSendMessage(original_content_url=f"{PHOTO_BASE_URL}/stacked_{date_str}.png", preview_image_url=f"{PHOTO_BASE_URL}/stacked_{date_str}.png"),
        ImageSendMessage(original_content_url=f"{PHOTO_BASE_URL}/cumulative_plot_{date_str}.png", preview_image_url=f"{PHOTO_BASE_URL}/cumulative_plot_{date_str}.png"),
    ]
    return TextSendMessage(text=reply), images

# === 查詢目前階段 ===
def handle_current_stage_command():
    history = load_json_from_github("daily_result_log.json")
    if not history:
        return TextSendMessage(text="❌ 尚無分析資料")
    latest_date = max(history.keys())
    items = history[latest_date]
    reply = f"分析日期：{latest_date}\n"
    for item in items:
        reply += f"槽 {item.get('Tank', '')}：{item.get('stage', '')} 第{item.get('day', '')}天 產氣 {item.get('volume', 0):.1f} m³\n"
    total = sum(i.get('volume', 0) for i in items)
    reply += f"\n總產氣量：{total:.1f} m³"
    return TextSendMessage(text=reply)

# === 產氣週報 ===
def handle_weekly_report_command():
    history = load_json_from_github("daily_result_log.json")
    today = date.today()
    last7 = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    reply = "📊 一週產氣概況：\n"
    for d in last7:
        if d in history:
            total = sum(i.get('volume', 0) for i in history[d])
            reply += f"{d}：{total:.1f} m³\n"
        else:
            reply += f"{d}：無資料\n"
    return TextSendMessage(text=reply)

# === AI 智能摘要（範例） ===
def handle_ai_summary_command():
    history = load_json_from_github("daily_result_log.json")
    if not history:
        return TextSendMessage(text="❌ 尚無歷史資料")
    today = max(history.keys())
    data = history[today]
    summary = "📈 智能分析：\n"
    for i in data:
        if i.get('volume', 0) < 50:
            summary += f"槽{i.get('Tank', '')}產氣偏低，建議檢查進料或菌活性\n"
        elif i.get('stage', '') == '高峰期':
            summary += f"槽{i.get('Tank', '')}處於高峰，維持良好\n"
    return TextSendMessage(text=summary)

# === 多日批次輸入（也用 get_active_tanks） ===
def handle_batch_gas_input_command(msg):
    lines = msg.strip().split("\n")
    history = load_json_from_github("daily_result_log.json")
    updated_dates = []
    last_date = None

    for line in lines:
        if line.strip():
            try:
                date_str, val = line.strip().split()
                val = float(val)
                active_tanks = get_active_tanks()
                analyzer = BiogasAnalyzer(active_tanks)
                result = analyzer.analyze(active_tanks, date_str, val)
                history[date_str] = result
                analyzer.update_cumulative_log(date_str, val)
                last_date = date_str
                updated_dates.append(f"{date_str} ✔ {val} m³")
            except Exception as e:
                updated_dates.append(f"{line.strip()} ❌ 格式錯誤 ({e})")

    save_json_to_github("daily_result_log.json", history, "批次輸入多日產氣量")

    if last_date:
        analyzer.plot_daily_distribution(history[last_date], last_date)
        analyzer.run_stacked_pipeline("daily_result_log.json", "cumulative_gas_log.json", active_tanks)
        imgs = [
            ImageSendMessage(original_content_url=f"{PHOTO_BASE_URL}/daily_plot_{last_date}.png", preview_image_url=f"{PHOTO_BASE_URL}/daily_plot_{last_date}.png"),
            ImageSendMessage(original_content_url=f"{PHOTO_BASE_URL}/stacked_{last_date}.png", preview_image_url=f"{PHOTO_BASE_URL}/stacked_{last_date}.png"),
            ImageSendMessage(original_content_url=f"{PHOTO_BASE_URL}/cumulative_plot_{last_date}.png", preview_image_url=f"{PHOTO_BASE_URL}/cumulative_plot_{last_date}.png"),
        ]
        return [TextSendMessage(text="\n".join(updated_dates))] + imgs
    else:
        return [TextSendMessage(text="\n".join(updated_dates))]

# === Flask 啟動入口 ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5678))
    app.run(host="0.0.0.0", port=port)
