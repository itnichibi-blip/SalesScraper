import os
import requests
import streamlit as st
import pandas as pd
import json

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────
API_KEY        = st.secrets.get("GOOGLE_PLACES_API_KEY", os.getenv("GOOGLE_PLACES_API_KEY", ""))
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
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

# 業種別サブキーワード
SUB_KEYWORDS = {
    "卸売業":     ["（絞り込みなし）", "食品卸", "建材卸", "機械卸", "医薬品卸", "繊維卸", "電気卸"],
    "小売業":     ["（絞り込みなし）", "スーパー", "ドラッグストア", "ホームセンター", "電器店"],
    "製造業":     ["（絞り込みなし）", "食品製造", "金属加工", "印刷", "化学", "電子部品"],
    "建設業":     ["（絞り込みなし）", "土木", "内装", "電気工事", "管工事", "塗装"],
    "飲食業":     ["（絞り込みなし）", "レストラン", "居酒屋", "カフェ", "弁当", "ファストフード"],
    "医療・福祉": ["（絞り込みなし）", "病院", "クリニック", "歯科", "介護", "薬局"],
    "不動産業":   ["（絞り込みなし）", "賃貸", "売買", "管理", "開発"],
    "情報通信業": ["（絞り込みなし）", "システム開発", "Web制作", "通信", "データセンター"],
}

# ─────────────────────────────────────────────
# Google Places API
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
        rows.append({
            "社名":         place.get("displayName", {}).get("text", "情報なし"),
            "住所":         place.get("formattedAddress", "情報なし"),
            "TEL":          place.get("nationalPhoneNumber", "情報なし"),
            "WebサイトURL": place.get("websiteUri", "情報なし"),
        })
        progress_bar.progress((i + 1) / total, text=f"処理中… {i + 1} / {total} 件")
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# OpenAI AI分析
# ─────────────────────────────────────────────

def analyze_company_with_openai(company_name: str, address: str, website: str) -> dict:
    info = {"事業内容推定": "不明", "AI営業ポイント": ""}

    if not OPENAI_API_KEY:
        return info

    prompt = f"""
以下の企業情報をもとに、営業担当者向けの分析を行ってください。

企業名: {company_name}
住所: {address}
WebサイトURL: {website}

以下の項目をJSON形式のみで返答してください。説明文やコードブロックは不要です。
{{
  "事業内容推定": "企業名・業種から推測される事業内容を30文字以内で",
  "AI営業ポイント": "この企業へのIT営業アプローチのポイントを50文字以内で"
}}
"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        text = response.choices[0].message.content.strip()
        if "```" in text:
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else parts[0]
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text.strip())
        info.update(parsed)
    except Exception as e:
        info["AI営業ポイント"] = f"エラー: {str(e)[:80]}"

    return info


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
    st.caption("クラウド版：Google Places API + OpenAI AI分析")

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

        # サブキーワード
        sub_options = SUB_KEYWORDS.get(industry, ["（絞り込みなし）"])
        sub_keyword = st.selectbox(
            "🔍 絞り込みキーワード（任意）",
            options=sub_options,
            help="業種をさらに絞り込む場合に選択してください"
        )

        col_ai, col_btn = st.columns([3, 1])
        with col_ai:
            enable_ai = st.checkbox(
                "🤖 AI分析を行う（事業内容推定・AI営業ポイントを自動生成）",
                value=bool(OPENAI_API_KEY),
                disabled=not bool(OPENAI_API_KEY),
                help="SecretsにOPENAI_API_KEYが設定されている場合のみ有効です",
            )
        with col_btn:
            submitted = st.form_submit_button("🔎 検索する", use_container_width=True)

    # ── 検索実行 ─────────────────────────────
    if submitted:
        if not region or not industry:
            st.warning("地域と業種の両方を入力してください。")
            st.stop()

        if sub_keyword and sub_keyword != "（絞り込みなし）":
            query = f"{region} {sub_keyword}"
        else:
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

        progress_bar = st.progress(0, text="データを整理しています…")
        df = build_dataframe(places, progress_bar)
        progress_bar.empty()

        # ── AI分析 ───────────────────────────
        if enable_ai and OPENAI_API_KEY:
            ai_bar = st.progress(0, text="🤖 AI分析中…")
            total = len(df)
            ai_results = []
            for i, row in df.iterrows():
                result = analyze_company_with_openai(
                    row["社名"], row["住所"], row["WebサイトURL"]
                )
                ai_results.append(result)
                ai_bar.progress((i + 1) / total, text=f"🤖 AI分析中… {i + 1} / {total} 件")
            ai_bar.empty()
            df["事業内容推定"]   = [r["事業内容推定"] for r in ai_results]
            df["AI営業ポイント"] = [r["AI営業ポイント"] for r in ai_results]
            st.success("✅ AI分析完了！")

        # セッションに保存
        st.session_state["df"]           = df
        st.session_state["region"]       = region
        st.session_state["industry"]     = industry
        st.session_state["enable_ai"]    = enable_ai
        st.session_state["current_page"] = 0
        for idx in df.index:
            st.session_state[f"check_{idx}"] = False

    # ── 結果表示 ─────────────────────────────
    if "df" not in st.session_state:
        return

    df        = st.session_state["df"]
    region    = st.session_state["region"]
    industry  = st.session_state["industry"]
    enable_ai = st.session_state.get("enable_ai", False)

    total_pages = max(1, (len(df) + PAGE_SIZE - 1) // PAGE_SIZE)
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = 0
        # ページ遷移時に先頭にスクロール
        if st.session_state.pop("scroll_top", False):
            st.markdown(
                "<script>window.scrollTo(0, 0);</script>",
                unsafe_allow_html=True,
            )

        st.subheader(f"📋 検索結果一覧（{len(df)} 件）")

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

    page      = st.session_state["current_page"]
    start_idx = page * PAGE_SIZE
    end_idx   = min(start_idx + PAGE_SIZE, len(df))
    page_df   = df.iloc[start_idx:end_idx]

    def render_pagination(key_suffix: str):
        col_prev, col_info, col_next = st.columns([1, 3, 1])
        with col_prev:
            if st.button("← 前へ", disabled=(page == 0), key=f"prev_{key_suffix}"):
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
            if st.button("次へ →", disabled=(page >= total_pages - 1), key=f"next_{key_suffix}"):
                st.session_state["current_page"] += 1
                st.rerun()

    render_pagination("top")

    for i, row in page_df.iterrows():
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
            if enable_ai and "AI営業ポイント" in df.columns:
                st.markdown("---")
                st.markdown(f"**事業内容推定：** {row.get('事業内容推定', '不明')}")
                if row.get("AI営業ポイント"):
                    st.info(f"💡 **AI営業ポイント：** {row['AI営業ポイント']}")

    # ── 出力エリア ───────────────────────────
    st.divider()
    selected_indices = [i for i in df.index if st.session_state.get(f"check_{i}", False)]
    selected_count   = len(selected_indices)

    st.subheader(f"📤 CSV出力（{selected_count} 件選択中）")

    if selected_count == 0:
        st.info("会社のチェックボックスにチェックを入れるとCSV出力できます。")
        return

    export_cols = ["社名", "住所", "TEL", "WebサイトURL"]
    if enable_ai and "AI営業ポイント" in df.columns:
        export_cols += ["事業内容推定", "AI営業ポイント"]

    export_df = df.loc[selected_indices, export_cols].reset_index(drop=True)

    st.markdown(f"**出力プレビュー（{len(export_df)} 件）**")
    st.dataframe(export_df, use_container_width=True)

    csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 CSVでダウンロード",
        data=csv_bytes,
        file_name=f"sales_list_{region}_{industry}.csv",
        mime="text/csv",
        use_container_width=True,
    )


if __name__ == "__main__":
    main()
