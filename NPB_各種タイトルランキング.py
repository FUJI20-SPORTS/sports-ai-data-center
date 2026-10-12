import streamlit as st
import pandas as pd
import requests
import re
from io import StringIO

# ==========================================================
# NPB公式記録ランキング 2026
# セ・リーグ / パ・リーグ
# OPSは対象外
# 規定打席・規定投球回はNPB公式ランキングで判定
# ==========================================================

YEAR = 2026
BASE_URL = f"https://www.npb.jp/bis/{YEAR}/stats"

LEAGUES = {
    "セ・リーグ": "c",
    "パ・リーグ": "p",
}

BATTER_METRICS = {
    "打率": ["打率"],
    "本塁打": ["本塁打"],
    "打点": ["打点"],
    "出塁率": ["出塁率"],
    "安打": ["安打"],
    "盗塁": ["盗塁"],
}

PITCHER_METRICS = {
    "防御率": ["防御率"],
    "勝利": ["勝利"],
    "勝率": ["勝率"],
    "奪三振": ["三振"],
    "セーブ": ["セーブ"],
    "ホールドポイント": ["HP", "ＨＰ", "ホールドポイント"],
}

# NPB公式のチーム略称を正式名称に変換
TEAM_NAMES = {
    "神": "阪神タイガース",
    "デ": "横浜DeNAベイスターズ",
    "巨": "読売ジャイアンツ",
    "中": "中日ドラゴンズ",
    "広": "広島東洋カープ",
    "ヤ": "東京ヤクルトスワローズ",
    "ソ": "福岡ソフトバンクホークス",
    "日": "北海道日本ハムファイターズ",
    "ロ": "千葉ロッテマリーンズ",
    "楽": "東北楽天ゴールデンイーグルス",
    "オ": "オリックス・バファローズ",
    "西": "埼玉西武ライオンズ",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

st.set_page_config(
    page_title="NPB公式記録ランキング",
    page_icon="⚾",
    layout="wide",
)


def normalize(value):
    """列名の空白などを整える"""
    return re.sub(r"\s+", "", str(value)).replace("\u3000", "")


def get_tables(url):
    """NPB公式ページから表を取得する"""
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    return pd.read_html(StringIO(response.text))


def prepare_table(table):
    """HTML表の列名を1段に統一する"""
    df = table.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "".join(
                str(item)
                for item in column
                if str(item) != "nan"
            )
            for column in df.columns
        ]

    df.columns = [normalize(c) for c in df.columns]
    return df


def find_column(df, candidates):
    """候補の列名から該当列を探す"""
    for candidate in candidates:
        candidate = normalize(candidate)

        for column in df.columns:
            if column == candidate:
                return column

    for candidate in candidates:
        candidate = normalize(candidate)

        for column in df.columns:
            if candidate in column:
                return column

    return None


def to_number(value):
    """成績を数値化する"""
    if pd.isna(value):
        return None

    value = str(value).strip()
    value = value.replace(",", "")
    value = value.replace("－", "-")

    if value in ("", "-", "--", "nan", "None"):
        return None

    # 投球回の「180.1」はNPBの表記なので、
    # 防御率などのランキング数値としては通常の小数で扱う。
    match = re.search(r"-?\d+(?:\.\d+)?", value)

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def extract_player_and_team(value):
    """
    公式選手名の末尾にあるチーム略称を取得。
    例：佐藤　輝明(神)
    """
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)

    match = re.search(r"[（(]\s*([^()（）]+)\s*[）)]$", text)

    if match:
        abbreviation = match.group(1).strip()
        player_name = text[:match.start()].strip()
        team_name = TEAM_NAMES.get(abbreviation)

        if team_name:
            return player_name, team_name

    return text, "公式略称を判定できません"


def get_ranking(league_name, player_type, category):
    league_code = LEAGUES[league_name]

    if player_type == "打者":
        url = f"{BASE_URL}/bat_{league_code}.html"
        metric_candidates = BATTER_METRICS[category]
    else:
        url = f"{BASE_URL}/pit_{league_code}.html"
        metric_candidates = PITCHER_METRICS[category]

    tables = get_tables(url)

    selected_df = None
    selected_metric = None
    selected_player = None

    for table in tables:
        df = prepare_table(table)

        metric_col = find_column(df, metric_candidates)

        if player_type == "打者":
            player_col = find_column(df, ["選手"])
        else:
            player_col = find_column(df, ["投手"])

        if player_col is None:
            player_col = find_column(df, ["選手", "投手"])

        if metric_col and player_col:
            # 規定以上の公式ランキング表を優先して使用
            selected_df = df
            selected_metric = metric_col
            selected_player = player_col
            break

    if selected_df is None:
        raise ValueError(
            "公式ランキング表から必要な列を特定できませんでした。\n"
            f"URL: {url}\n"
            f"項目: {category}\n"
            "NPB公式ページの構成が変更された可能性があります。"
        )

    records = []

    for _, row in selected_df.iterrows():
        original_name = row[selected_player]
        score = to_number(row[selected_metric])

        if score is None or pd.isna(original_name):
            continue

        player_name, team_name = extract_player_and_team(
            original_name
        )

        if not player_name or player_name.lower() == "nan":
            continue

        records.append({
            "選手名": player_name,
            "チーム": team_name,
            "成績数値": score,
        })

    if not records:
        raise ValueError("公式ランキングの選手データがありません。")

    result = pd.DataFrame(records)

    # 防御率は低い順。それ以外は高い順。
    ascending = category == "防御率"

    result = result.sort_values(
        "成績数値",
        ascending=ascending,
        kind="stable",
    ).reset_index(drop=True)

    # 同じ成績は同順位にする
    result.insert(
        0,
        "順位",
        result["成績数値"].rank(
            method="min",
            ascending=ascending,
        ).astype(int),
    )

    result["成績"] = result["成績数値"].map(
        lambda x: f"{x:.3f}".rstrip("0").rstrip(".")
    )

    result = result[["順位", "選手名", "チーム", "成績"]]

    return result, url


# ==========================================================
# アプリ画面
# ==========================================================

st.title("⚾ NPB公式記録ランキング")

st.caption(
    "2026年度 | NPB公式記録 | OPSは対象外"
)

st.write(
    "リーグ、打者・投手、タイトルを選択してランキングを表示します。"
)

col1, col2, col3 = st.columns(3)

with col1:
    league_name = st.selectbox(
        "① リーグ",
        list(LEAGUES.keys()),
    )

with col2:
    player_type = st.selectbox(
        "② 部門",
        ["打者", "投手"],
    )

with col3:
    if player_type == "打者":
        categories = list(BATTER_METRICS.keys())
    else:
        categories = list(PITCHER_METRICS.keys())

    category = st.selectbox(
        "③ ランキング項目",
        categories,
    )

if player_type == "打者":
    st.info(
        "対象：NPB公式の「個人打撃成績（規定打席以上）」ページ"
    )
else:
    st.info(
        "対象：NPB公式の「個人投手成績（規定投球回以上）」ページ"
    )

if st.button("ランキングを取得", type="primary"):
    try:
        with st.spinner("NPB公式記録を取得しています..."):
            ranking, source_url = get_ranking(
                league_name,
                player_type,
                category,
            )

        st.session_state["ranking_data"] = ranking
        st.session_state["ranking_title"] = (
            f"{YEAR}年 {league_name} "
            f"{player_type} {category}ランキング"
        )
        st.session_state["ranking_url"] = source_url

    except Exception as error:
        st.error("ランキングを取得できませんでした。")
        st.code(str(error))
        st.markdown(
            f"[NPB公式記録ページを開く]({BASE_URL}/)"
        )

if "ranking_data" in st.session_state:
    st.subheader(st.session_state["ranking_title"])

    ranking = st.session_state["ranking_data"]

    st.dataframe(
        ranking,
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = ranking.to_csv(
        index=False,
    ).encode("utf-8-sig")

    filename = (
        f"NPB_{YEAR}_{league_name}_"
        f"{player_type}_{category}.csv"
    )

    st.download_button(
        "CSVをダウンロード（Excel用）",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
    )

    st.markdown(
        f"出典：[NPB公式記録]({st.session_state['ranking_url']})"
    )

    st.caption(
        "チーム名は選手名に付記されたNPB公式略称から変換しています。"
        "略称を判定できない選手はその旨を表示します。"
    )

st.divider()

st.caption(
    "取得元：NPB.jp 日本野球機構。"
    "公式ページから取得できない場合、架空の成績は表示しません。"
)
