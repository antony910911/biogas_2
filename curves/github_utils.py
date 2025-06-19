import requests
import os
import base64
import json

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
        content = resp.json()["content"]
        content = base64.b64decode(content).decode()
        return json.loads(content)
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



