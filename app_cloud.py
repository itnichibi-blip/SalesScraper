import os
import requests
import streamlit as st
import pandas as pd

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────
# Streamlit Community CloudではSecretsから取得
API_KEY = st.secrets.get("GOOGLE_PLACES_API_KEY", os.getenv("GOOGLE_PLACES_API_KEY", ""))

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

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
# Google Places API (New)
# ─────────────────────────────────────────────

def search_places(query: str, max_results: int = 20) -> list[dict]:
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

        if len(results) >= max_results:
            results = results[:max_results]
            break

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
    return results


def build_dataframe(places: list[dict], progress_bar) -> pd.DataFrame:
    rows = []
    total = len(places)
    for i, place in enumerate(places):
        rows.append({
            "社名":         place.get("displayName", {}).get("text", "情報なし"),
            "住所":         place.get("formattedAddress", "情報なし"),
            "TEL":          place.get("nationalPhoneNumber", "情報なし"),
            "WebサイトURL": place.get("websiteUri", "情報なし"),
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
    st.caption("クラウド版：Google Places API による企業情報取得・CSV出力")

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

        max_results = st.slider(
            "🔢 取得件数の上限",
            min_value=5,
            max_value=60,
            value=20,
            step=5,
            help="件数が多いほど時間がかかります。"
        )
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
                places = search_places(query, max_results)
            except requests.RequestException as e:
                st.error(f"API 通信エラー：{e}")
                st.stop()

        if not places:
            st.warning("検索結果が0件でした。条件を変えてお試しください。")
            st.stop()

        st.success(f"✅ {len(places)} 件の企業が見つかりました。")

        progress_bar = st.progress(0, text="データを整理しています…")
        df = build_dataframe(places, progress_bar)
        progress_bar.empty()

        # セッションに保存
        st.session_state["df"]       = df
        st.session_state["region"]   = region
        st.session_state["industry"] = industry
        for idx in df.index:
            st.session_state[f"check_{idx}"] = False

    # ── 結果表示 ─────────────────────────────
    if "df" not in st.session_state:
        return

    df       = st.session_state["df"]
    region   = st.session_state["region"]
    industry = st.session_state["industry"]

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

    # 各会社カード
    for i, row in df.iterrows():
        if f"check_{i}" not in st.session_state:
            st.session_state[f"check_{i}"] = False

        with st.expander(f"🏢 {row['社名']}", expanded=False):
            st.session_state[f"check_{i}"] = st.checkbox(
                "✅ この会社を出力対象に含める",
                value=st.session_state[f"check_{i}"],
                key=f"cb_{i}",
            )
            st.markdown(f"**住所：** {row['住所']}")
            st.markdown(f"**TEL：** {row['TEL']}")
            if row["WebサイトURL"] != "情報なし":
                st.markdown(f"**URL：** [{row['WebサイトURL']}]({row['WebサイトURL']})")
            else:
                st.markdown("**URL：** 情報なし")

    # ── 出力エリア ───────────────────────────
    st.divider()
    selected_indices = [i for i in df.index if st.session_state.get(f"check_{i}", False)]
    selected_count   = len(selected_indices)

    st.subheader(f"📤 CSV出力（{selected_count} 件選択中）")

    if selected_count == 0:
        st.info("会社のチェックボックスにチェックを入れるとCSV出力できます。")
        return

    export_df = df.loc[selected_indices, ["社名", "住所", "TEL", "WebサイトURL"]].reset_index(drop=True)

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
