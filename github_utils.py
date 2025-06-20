import requests
import os
import base64
import json

def get_github_token():
    # 1. 先抓 streamlit secrets
    try:
        import streamlit as st
        token = st.secrets["GITHUB_TOKEN"]
    except Exception:
        # 2. 再抓環境變數
        token = os.environ.get("GITHUB_TOKEN")
    return token


# === 設定區 ===
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # 建議設成 Streamlit Cloud secret
REPO = "antony910911/biogas_2"         # <<== 換成你的 GitHub 使用者名稱
BRANCH = "main"
API_URL = f"https://api.github.com/repos/{REPO}/contents"

# === 從 GitHub 讀 JSON 檔 ===
def load_json_from_github(filename):
    url = f"{API_URL}/{filename}?ref={BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        try:
            content = resp.json()["content"]
            content = base64.b64decode(content).decode()
            data = json.loads(content)
            # ⭐ 防呆：如果不是 dict，直接報警告
            if not isinstance(data, dict):
                print(f"[WARNING] {filename} 讀取後型別為 {type(data)}，預期應為 dict，自動回傳空字典")
                return {}
            return data
        except Exception as e:
            print(f"[WARNING] 讀取 {filename} 時 JSON 格式異常：{e}")
            return {}
    print(f"[WARNING] 下載 {filename} 失敗，status: {resp.status_code}")
    return {}

# === 寫 JSON 檔到 GitHub ===
def save_json_to_github(filename, data, commit_msg="Update JSON via Streamlit"):
    url = f"{API_URL}/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    # 先讀 SHA
    get_resp = requests.get(url, headers=headers)
    sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None
    # encode data
    b64_data = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode()).decode()
    body = {
        "message": commit_msg,
        "content": b64_data,
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    put_resp = requests.put(url, headers=headers, json=body)
    return put_resp.status_code in [200, 201]



def save_json_to_github_subdir(subdir, filename, data, commit_msg="Upload curve via Streamlit"):
    import os
    # e.g. subdir = "curves", filename = "mycurve.json"
    fullpath = f"{subdir}/{filename}"
    return save_json_to_github(fullpath, data, commit_msg)



def save_binary_to_github(filepath, bin_data, commit_msg="Upload image via Streamlit"):
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    REPO = "antony910911/biogas_2"         # <<<<<< 記得替換
    BRANCH = "main"
    API_URL = f"https://api.github.com/repos/{REPO}/contents/{filepath}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    # 查詢 SHA（如有同名檔案）
    get_resp = requests.get(API_URL, headers=headers)
    sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

    b64_data = base64.b64encode(bin_data).decode()
    body = {
        "message": commit_msg,
        "content": b64_data,
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    put_resp = requests.put(API_URL, headers=headers, json=body)
    return put_resp.status_code in [200, 201]


def list_curves_on_github(subdir="curves"):
    url = f"{API_URL}/{subdir}?ref={BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return [item["name"] for item in resp.json() if item["name"].endswith(".json")]
    print("list 失敗:", resp.status_code, resp.text)
    return []
