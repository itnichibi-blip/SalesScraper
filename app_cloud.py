import os
import sqlite3
import requests
import streamlit as st
import pandas as pd
from pathlib import Path

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────
API_KEY = st.secrets.get("GOOGLE_PLACES_API_KEY", os.getenv("GOOGLE_PLACES_API_KEY", ""))
PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DB_FILE   = "houjin.db"
PAGE_SIZE = 10

# ─────────────────────────────────────────────
# プルダウン選択肢
# ─────────────────────────────────────────────
REGIONS = [
    "広島市中区", "広島市東区", "広島市南区", "広島市西区",
    "広島市安佐南区", "広島市安佐北区", "広島市安芸区", "広島市佐伯区",
    "呉市", "竹原市", "三原市", "尾道市", "福山市", "府中市",
    "三次市", "庄原市", "大竹市", "東広島市", "廿日市市",
    "安芸高田市", "江田島市",
    "大阪市", "大阪市北区", "大阪市中央区", "大阪市西区",
    "東京都千代田区", "東京都中央区", "東京都港区", "東京都新宿区",
    "その他（直接入力）",
]

INDUSTRIES = [
    "卸売業", "小売業", "製造業", "建設業", "不動産業",
    "飲食業", "宿泊業", "医療・福祉", "教育・学習支援",
    "情報通信業", "運輸・郵便業", "金融・保険業",
    "サービス業", "農業・林業", "漁業",
    "印刷業", "広告業", "設計・デザイン業",
    "その他（直接入力）",
]

# ─────────────────────────────────────────────
# 国税庁DB検索
# ─────────────────────────────────────────────

def search_houjin_db(company_name: str) -> dict:
    result = {"法人番号": "不明", "郵便番号": "不明", "法人種別": "不明"}

    if not Path(DB_FILE).exists():
        return result

    def normalize(name: str) -> str:
        for prefix in ["株式会社", "有限会社", "合同会社", "合名会社", "合資会社",
                       "一般社団法人", "公益社団法人", "特定非営利活動法人", "医療法人"]:
            name = name.replace(prefix, "").strip()
        return name

    try:
        conn = sqlite3.connect(DB_FILE)
        cur  = conn.cursor()

        cur.execute(
            "SELECT houjin_no, zip_code, houjin_type FROM houjin WHERE houjin_name = ? LIMIT 1",
            (company_name,)
        )
        row = cur.fetchone()

        if not row:
            cur.execute(
                "SELECT houjin_no, zip_code, houjin_type FROM houjin WHERE houjin_name LIKE ? LIMIT 1",
                (f"{company_name}%",)
            )
            row = cur.fetchone()

        if not row:
            normalized = normalize(company_name)
            if normalized and normalized != company_name:
                cur.execute(
                    "SELECT houjin_no, zip_code, houjin_type FROM houjin WHERE houjin_name LIKE ? LIMIT 1",
                    (f"%{normalized}%",)
                )
                row = cur.fetchone()

        conn.close()

        if row:
            houjin_no, zip_code, houjin_type = row
            if zip_code and len(zip_code) == 7:
                zip_code = f"{zip_code[:3]}-{zip_code[3:]}"

            type_map = {
                "101": "国の機関", "201": "地方公共団体",
                "301": "株式会社", "302": "有限会社", "303": "合名会社",
                "304": "合資会社", "305": "合同会社",
                "399": "その他の設立登記法人",
                "401": "外国会社等", "499": "その他",
                "501": "公益社団法人", "502": "公益財団法人",
                "503": "一般社団法人", "504": "一般財団法人",
                "601": "各種農業組合等", "701": "医療法人",
                "801": "学校法人", "899": "その他の特別法人",
                "900": "特定非営利活動法人",
            }
            result["法人番号"] = houjin_no
            result["郵便番号"] = zip_code or "不明"
            result["法人種別"] = type_map.get(houjin_type, houjin_type)

    except Exception:
        pass

    return result


# ─────────────────────────────────────────────
# Google Places API (New)
# ─────────────────────────────────────────────

def search_places(query: str) -> list[dict]:
    results = []
    next_page_token = None
    while True:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": (
                "places.displayName,places.formattedAddress,"
                "places.nationalPhoneNumber,places.websiteUri,"
                "places.id,nextPageToken"
            ),
        }
        body = {"textQuery": query, "languageCode": "ja", "pageSize": 20}
        if next_page_token:
            body["pageToken"] = next_page_token

        response = requests.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            st.error(f"Places API エラー: {data['error'].get('message', '不明なエラー')}")
            break

        results.extend(data.get("places", []))
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
    return results


def build_dataframe(places: list[dict], progress_bar) -> pd.DataFrame:
    rows = []
    total = len(places)
    for i, place in enumerate(places):
        name    = place.get("displayName", {}).get("text", "情報なし")
        address = place.get("formattedAddress", "情報なし")
        tel     = place.get("nationalPhoneNumber", "情報なし")
        website = place.get("websiteUri", "情報なし")

        # 国税庁DB検索
        houjin = search_houjin_db(name)

        rows.append({
            "社名":         name,
            "郵便番号":     houjin["郵便番号"],
            "住所":         address,
            "TEL":          tel,
            "WebサイトURL": website,
            "法人番号":     houjin["法人番号"],
            "法人種別":     houjin["法人種別"],
        })
        progress_bar.progress((i + 1) / total, text=f"処理中… {i + 1} / {total} 件")
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# Streamlit UI
# ─────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="SalesScraper – 営業リスト作成ツール",
        page_icon="🔍",
        layout="wide",
    )
    st.title("🔍 SalesScraper（仮） – 営業リスト自動作成ツール")
    st.caption("クラウド版：Google Places API + 国税庁DB による企業情報取得・CSV出力")

    if not API_KEY:
        st.error("⚠️ GOOGLE_PLACES_API_KEY が設定されていません。")
        st.stop()

    # ── 入力フォーム ─────────────────────────
    with st.form("search_form"):
        col1, col2 = st.columns(2)
        with col1:
            region_select = st.selectbox("🗾 地域", REGIONS)
            if region_select == "その他（直接入力）":
                region = st.text_input("地域を入力してください", placeholder="例：岡山市北区")
            else:
                region = region_select
        with col2:
            industry_select = st.selectbox("🏭 業種", INDUSTRIES)
            if industry_select == "その他（直接入力）":
                industry = st.text_input("業種を入力してください", placeholder="例：印刷業")
            else:
                industry = industry_select

        submitted = st.form_submit_button("🔎 検索する", use_container_width=True)

    # ── 検索実行 ─────────────────────────────
    if submitted:
        if not region or not industry:
            st.warning("地域と業種の両方を入力してください。")
            st.stop()

        query = f"{region} {industry}"
        st.info(f"検索クエリ：**{query}**")

        with st.spinner("Google Places API で企業を検索中…"):
            try:
                places = search_places(query)
            except requests.RequestException as e:
                st.error(f"API 通信エラー：{e}")
                st.stop()

        if not places:
            st.warning("検索結果が0件でした。条件を変えてお試しください。")
            st.stop()

        st.success(f"✅ {len(places)} 件の企業が見つかりました。")

        progress_bar = st.progress(0, text="データを整理・国税庁DB検索中…")
        df = build_dataframe(places, progress_bar)
        progress_bar.empty()

        # セッションに保存
        st.session_state["df"]           = df
        st.session_state["region"]       = region
        st.session_state["industry"]     = industry
        st.session_state["current_page"] = 0
        for idx in df.index:
            st.session_state[f"check_{idx}"] = False

    # ── 結果表示 ─────────────────────────────
    if "df" not in st.session_state:
        return

    df       = st.session_state["df"]
    region   = st.session_state["region"]
    industry = st.session_state["industry"]

    # ── ページネーション設定 ─────────────────
    total_pages = max(1, (len(df) + PAGE_SIZE - 1) // PAGE_SIZE)
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = 0

    # 全選択・全解除
    st.subheader(f"📋 検索結果一覧（{len(df)} 件）")
    col_all, col_none, _ = st.columns([1, 1, 6])
    with col_all:
        if st.button("☑ 全選択"):
            for idx in df.index:
                st.session_state[f"check_{idx}"] = True
    with col_none:
        if st.button("☐ 全解除"):
            for idx in df.index:
                st.session_state[f"check_{idx}"] = False

    # ページネーションUI
    page      = st.session_state["current_page"]
    start_idx = page * PAGE_SIZE
    end_idx   = min(start_idx + PAGE_SIZE, len(df))
    page_df   = df.iloc[start_idx:end_idx]

    col_prev, col_info, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("← 前へ", disabled=(page == 0)):
            st.session_state["current_page"] -= 1
            st.rerun()
    with col_info:
        st.markdown(
            f"<div style='text-align:center; padding-top:8px;'>"
            f"{page + 1} / {total_pages} ページ（{start_idx + 1}〜{end_idx}件目）"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("次へ →", disabled=(page >= total_pages - 1)):
            st.session_state["current_page"] += 1
            st.rerun()

    # 各会社カード
    for i, row in page_df.iterrows():
        if f"check_{i}" not in st.session_state:
            st.session_state[f"check_{i}"] = False

        with st.expander(f"🏢 {row['社名']}", expanded=False):
            st.session_state[f"check_{i}"] = st.checkbox(
                "✅ この会社を出力対象に含める",
                value=st.session_state[f"check_{i}"],
                key=f"cb_{i}",
            )
            st.markdown(f"**郵便番号：** {row['郵便番号']}")
            st.markdown(f"**住所：** {row['住所']}")
            st.markdown(f"**TEL：** {row['TEL']}")
            if row["WebサイトURL"] != "情報なし":
                st.markdown(f"**URL：** [{row['WebサイトURL']}]({row['WebサイトURL']})")
            else:
                st.markdown("**URL：** 情報なし")
            st.markdown(f"**法人番号：** {row['法人番号']}")
            st.markdown(f"**法人種別：** {row['法人種別']}")

    # ── 出力エリア ───────────────────────────
    st.divider()
    selected_indices = [i for i in df.index if st.session_state.get(f"check_{i}", False)]
    selected_count   = len(selected_indices)

    st.subheader(f"📤 CSV出力（{selected_count} 件選択中）")

    if selected_count == 0:
        st.info("会社のチェックボックスにチェックを入れるとCSV出力できます。")
        return

    export_df = df.loc[selected_indices, ["社名", "郵便番号", "住所", "TEL", "法人番号", "法人種別"]].reset_index(drop=True)

    st.markdown(f"**出力プレビュー（{len(export_df)} 件）**")
    st.dataframe(export_df, use_container_width=True)

    csv_bytes = export_df.to_csv(index=False).encode("shift_jis", errors="ignore")
    st.download_button(
        label="📥 CSVでダウンロード",
        data=csv_bytes,
        file_name=f"sales_list_{region}_{industry}.csv",
        mime="text/csv",
        use_container_width=True,
    )


if __name__ == "__main__":
    main()
