import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from pages_impl._shared import render_page_header, render_kpi_row
from pages_impl._data import load_full_table, render_filter_bar

CATEGORY_ORDER = ["MA", "RA", "SA", "VRV"]

LEGEND_TOP = dict(orientation="h", y=1.22, x=0, font=dict(size=9))
MARGIN = dict(t=6, b=6, l=6, r=6)
DONUT_H = 220


def render():
    render_page_header("01")

    df_all = load_full_table()
    if df_all.empty:
        st.warning("目前讀不到資料，請確認 Secrets 設定（gcp_service_account）是否正確。")
        return

    df = render_filter_bar(df_all, key_prefix="p01")

    # ── 去重後的證書表：一張證書（同一個證書編號）只算一次，符合「張數」的字面意義 ──
    df_cert_unique = df[df["商品驗證現行有效"]].drop_duplicates("商品驗證證書編號")
    df_badge_unique = df[df["標章覆蓋狀態"] == "標章有效"].drop_duplicates("節能標章證書編號")

    cert_valid = len(df_cert_unique)
    badge_valid = len(df_badge_unique)
    due_90 = int(
        ((df["商品驗證風險狀態"] == "90天內") | (df["節能標章風險狀態"] == "90天內")).sum()
    )
    valid_models = int(df.loc[df["商品驗證現行有效"], "室外機型號"].nunique())
    badge_models = int(df.loc[df["商品驗證現行有效"] & df["有節能標章"], "室外機型號"].nunique())
    coverage_rate_num = (badge_models / valid_models * 100) if valid_models else 0
    coverage_rate = f"{coverage_rate_num:.1f}%" if valid_models else "—"

    render_kpi_row([
        ("商品驗證有效張數", cert_valid),
        ("節能標章有效張數", badge_valid),
        ("90天內到期張數", due_90),
        ("有效商品型號數", valid_models),
        ("已取得標章型號數", badge_models),
        ("整體標章取得率", coverage_rate),
    ])

    st.markdown('<div style="height:.2rem"></div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)

    # ── 區塊 1：商品驗證登錄證書有效張數（環狀圖，去重）──
    with col1, st.container(key="chart_card_01_1"):
        st.markdown('<div class="block-card-title">1　商品驗證登錄證書有效張數</div>', unsafe_allow_html=True)
        g1 = df_cert_unique.groupby("類別").size().reindex(CATEGORY_ORDER, fill_value=0)
        labels1 = [f"{k}, {v}" for k, v in g1.items()]
        fig1 = go.Figure(data=[go.Pie(
            labels=labels1, values=g1.values, hole=0.72,
            textinfo="label", textposition="inside", insidetextorientation="horizontal",
            textfont=dict(size=9, color="#1E293B", family="Microsoft JhengHei, sans-serif"),
            marker=dict(colors=["#9EE0F5"] * len(g1), line=dict(color="#FFFFFF", width=3)),
            showlegend=False, sort=False,
        )])
        fig1.add_annotation(text=f"<b>{cert_valid}</b> <span style='font-size:16px;'>張</span>",
                             x=0.5, y=0.5, font=dict(size=32, color="#1E293B", family="Microsoft JhengHei, sans-serif"), showarrow=False)
        fig1.update_layout(height=DONUT_H, margin=dict(t=10, b=10, l=10, r=10),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(family="Microsoft JhengHei, sans-serif"))
        st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})

    # ── 區塊 2：節能標章有效張數（原「各類別能效分級數量統計」環狀圖，去重）──
    with col2, st.container(key="chart_card_01_2"):
        st.markdown('<div class="block-card-title">2　節能標章有效張數</div>', unsafe_allow_html=True)
        g3 = df_badge_unique.groupby("類別").size().reindex(CATEGORY_ORDER, fill_value=0)
        total_badge_certs = int(g3.sum())
        labels3 = [f"{k}: {v}張" for k, v in g3.items()]
        fig3 = go.Figure(data=[go.Pie(
            labels=labels3, values=g3.values, hole=0.72,
            textinfo="label", textposition="inside", insidetextorientation="horizontal",
            textfont=dict(size=9, color="#1E293B", family="Microsoft JhengHei, sans-serif"),
            marker=dict(colors=["#A7F3D0", "#93C5FD", "#FDE68A", "#DDD6FE"], line=dict(color="#FFFFFF", width=3)),
            showlegend=False, sort=False,
        )])
        fig3.add_annotation(text=f"<b>{total_badge_certs}</b> <span style='font-size:16px;'>張</span>",
                             x=0.5, y=0.5, font=dict(size=32, color="#1E293B", family="Microsoft JhengHei, sans-serif"), showarrow=False)
        fig3.update_layout(height=DONUT_H, margin=dict(t=10, b=10, l=10, r=10),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(family="Microsoft JhengHei, sans-serif"))
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})

    # ── 區塊 3：節能標章取得百分比（同心圓環，型號覆蓋率，不去重）──
    with col3, st.container(key="chart_card_01_3"):
        st.markdown('<div class="block-card-title">3　節能標章取得百分比</div>', unsafe_allow_html=True)
        cert_valid_sub = df[df["商品驗證現行有效"]]
        badge_cnt = cert_valid_sub[cert_valid_sub["有節能標章"]].groupby("類別")["室外機型號"].nunique().reindex(CATEGORY_ORDER, fill_value=0)
        valid_cnt = cert_valid_sub.groupby("類別")["室外機型號"].nunique().reindex(CATEGORY_ORDER, fill_value=0)
        rates = {}
        for cat in CATEGORY_ORDER:
            tot = valid_cnt.get(cat, 0)
            rates[cat] = (badge_cnt.get(cat, 0) / tot * 100) if tot > 0 else 0

        fig2 = go.Figure()
        ring_cfgs = [
            {"cat": "MA", "color": "#A7F3D0", "r_out": 1.00, "hole": (1.00 - 0.16) / 1.00, "label_y": 0.04},
            {"cat": "VRV", "color": "#DDD6FE", "r_out": 0.82, "hole": (0.82 - 0.16) / 0.82, "label_y": 0.13},
            {"cat": "SA", "color": "#FDE68A", "r_out": 0.64, "hole": (0.64 - 0.16) / 0.64, "label_y": 0.22},
            {"cat": "RA", "color": "#93C5FD", "r_out": 0.46, "hole": (0.46 - 0.16) / 0.46, "label_y": 0.31},
        ]
        for cfg in ring_cfgs:
            c_name = cfg["cat"]
            val = rates.get(c_name, 0)
            r_out = cfg["r_out"]
            fig2.add_trace(go.Pie(
                values=[val, max(0, 100 - val)],
                text=[f"{c_name}: {val:.1f}%", ""],
                hole=cfg["hole"], sort=False, direction="clockwise", rotation=90,
                marker=dict(colors=[cfg["color"], "#FBFCFD"], line=dict(color="#FFFFFF", width=1.5)),
                textinfo="text", textposition="inside", insidetextorientation="horizontal",
                textfont=dict(size=9, color="#1E293B", family="Microsoft JhengHei, sans-serif"),
                hoverinfo="text",
                domain=dict(x=[0.5 - r_out / 2, 0.5 + r_out / 2], y=[0.5 - r_out / 2, 0.5 + r_out / 2]),
                showlegend=False,
            ))
        fig2.add_annotation(text=f"<b>{coverage_rate_num:.0f}%</b>", x=0.5, y=0.5,
                             font=dict(size=24, color="#1E293B", family="Microsoft JhengHei, sans-serif"), showarrow=False)
        fig2.update_layout(height=DONUT_H, margin=dict(t=10, b=10, l=10, r=10),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(family="Microsoft JhengHei, sans-serif"))
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    # ══════════════════════════════════════════════
    # 區塊 4/5/6：組1（固定圖表）／組2（每個帳號自訂）左右切換
    # ══════════════════════════════════════════════
    if "p01_g2_page" not in st.session_state:
        st.session_state["p01_g2_page"] = 1

    with st.container(key="p01_nav_arrows"):
        nav_l, nav_mid, nav_r = st.columns([1, 12, 1])
        with nav_l:
            if st.button("◀", key="p01_prev_group", use_container_width=True,
                          disabled=(st.session_state["p01_g2_page"] == 1)):
                st.session_state["p01_g2_page"] = 1
                st.rerun()
        with nav_mid:
            st.markdown(
                f"<div style='text-align:center;color:#8A9AA3;font-size:.75rem;'>"
                f"第 {st.session_state['p01_g2_page']} / 2 組</div>",
                unsafe_allow_html=True,
            )
        with nav_r:
            if st.button("▶", key="p01_next_group", use_container_width=True,
                          disabled=(st.session_state["p01_g2_page"] == 2)):
                st.session_state["p01_g2_page"] = 2
                st.rerun()

    if st.session_state["p01_g2_page"] == 1:
        _render_group1(df, df_cert_unique, df_badge_unique)
    else:
        _render_group2()


def _render_group1(df, df_cert_unique, df_badge_unique):
    col4, col5, col6 = st.columns(3)

    # ── 區塊 4：90天內到期的商品驗證登錄證書清單（只列商品驗證，去重）──
    with col4, st.container(key="chart_card_01_4"):
        st.markdown('<div class="block-card-title">4　90天內到期的商品驗證登錄證書清單</div>', unsafe_allow_html=True)
        cert_due = df[df["商品驗證風險狀態"] == "90天內"].copy()
        cert_due = cert_due.drop_duplicates(subset=["商品驗證證書編號"], keep="first")
        cert_due = cert_due.sort_values("商品驗證剩餘天數")
        if not cert_due.empty:
            cert_due_df = cert_due[["商品驗證證書編號", "室外機型號", "商品驗證有效期限"]].rename(columns={
                "商品驗證證書編號": "證書編號", "室外機型號": "型號", "商品驗證有效期限": "有效日期",
            })
        else:
            cert_due_df = pd.DataFrame(columns=["證書編號", "型號", "有效日期"])
        st.dataframe(cert_due_df, use_container_width=True, hide_index=True, height=DONUT_H)

    # ── 區塊 5：90天內即將到期清單（商品驗證＋節能標章混合，去重）──
    with col5, st.container(key="chart_card_01_5"):
        st.markdown('<div class="block-card-title">5　90天內即將到期清單</div>', unsafe_allow_html=True)
        due = df[(df["商品驗證風險狀態"] == "90天內") | (df["節能標章風險狀態"] == "90天內")].copy()
        rows = []
        for _, r in due.iterrows():
            if r["商品驗證風險狀態"] == "90天內":
                rows.append({
                    "證書類型": "商品驗證", "證書編號": r["商品驗證證書編號"],
                    "型號": r["室外機型號"], "有效日期": r["商品驗證有效期限"],
                    "剩餘天數": int(r["商品驗證剩餘天數"]) if pd.notna(r["商品驗證剩餘天數"]) else None,
                })
            if r["節能標章風險狀態"] == "90天內":
                rows.append({
                    "證書類型": "節能標章", "證書編號": r["節能標章證書編號"],
                    "型號": r["室外機型號"], "有效日期": r["節能標章有效日期"],
                    "剩餘天數": int(r["節能標章剩餘天數"]) if pd.notna(r["節能標章剩餘天數"]) else None,
                })
        due_df = pd.DataFrame(rows).sort_values("剩餘天數") if rows else pd.DataFrame(
            columns=["證書類型", "證書編號", "型號", "有效日期", "剩餘天數"])
        due_df = due_df.drop_duplicates(subset=["證書編號"], keep="first")
        due_df = due_df.drop(columns=["剩餘天數"])
        st.dataframe(due_df, use_container_width=True, hide_index=True, height=DONUT_H)

    # ── 區塊 6：未來半年每月到期張數統計（橫軸改月份，去重後計算）──
    with col6, st.container(key="chart_card_01_6"):
        st.markdown('<div class="block-card-title">6　未來半年每月到期張數統計</div>', unsafe_allow_html=True)
        today = pd.Timestamp.now().normalize()
        month_starts = [today.replace(day=1) + pd.DateOffset(months=i) for i in range(6)]
        month_labels = [m.strftime("%Y/%m") for m in month_starts]

        def _month_label(dt):
            if pd.isna(dt):
                return None
            label = dt.strftime("%Y/%m")
            return label if label in month_labels else None

        cert_future = df_cert_unique[df_cert_unique["商品驗證有效期限_dt"] >= today].copy()
        badge_future = df_badge_unique[df_badge_unique["節能標章有效日期_dt"] >= today].copy()
        cert_future["月份"] = cert_future["商品驗證有效期限_dt"].apply(_month_label)
        badge_future["月份"] = badge_future["節能標章有效日期_dt"].apply(_month_label)

        c1 = cert_future.groupby("月份").size().reindex(month_labels, fill_value=0)
        c2 = badge_future.groupby("月份").size().reindex(month_labels, fill_value=0)

        fig = go.Figure()
        fig.add_bar(name="商品驗證到期張數", x=month_labels, y=c1.values, marker_color="#4472C4")
        fig.add_bar(name="節能標章到期張數", x=month_labels, y=c2.values, marker_color="#82BE7E")
        fig.update_layout(barmode="group", height=DONUT_H, margin=MARGIN, legend=LEGEND_TOP,
                           plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_group2():
    from pages_impl import _custom_widgets as cw

    username = st.session_state.get("username", "unknown")
    settings = cw.load_user_settings(username)

    if settings["顯示模式"] == "wide":
        with st.container(key="chart_card_01_wide_custom"):
            _render_display_only(cw, username, "wide", "image")
            col_spacer, col_pop = st.columns([6, 1])
            with col_pop:
                _render_settings_popover(cw, username, settings)
    else:
        col4, col5, col6 = st.columns(3)
        with col4, st.container(key="chart_card_01_4_custom"):
            _render_display_only(cw, username, "4", settings.get("區塊4", "note"), settings.get("便條4", ""))
        with col5, st.container(key="chart_card_01_5_custom"):
            _render_display_only(cw, username, "5", settings.get("區塊5", "note"), settings.get("便條5", ""))
        with col6, st.container(key="chart_card_01_6_custom"):
            _render_display_only(cw, username, "6", settings.get("區塊6", "note"), settings.get("便條6", ""))
            col_spacer, col_pop = st.columns([6, 1])
            with col_pop:
                _render_settings_popover(cw, username, settings)


def _render_display_only(cw, username, slot, content_type, note_text=""):
    """主畫面只顯示內容本身（便條紙文字或圖片），沒有任何編輯用的按鈕/選單，也不顯示提示文字"""
    if content_type == "image":
        existing = cw.load_custom_image(username, slot)
        if existing:
            st.markdown(
                f"""<div style="height:{DONUT_H}px; display:flex; align-items:center;
                justify-content:center; overflow:hidden;">
                <img src="data:image/png;base64,{cw.load_custom_image_b64(username, slot)}"
                style="max-width:none; max-height:none;" /></div>""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f'<div style="height:{DONUT_H}px;"></div>', unsafe_allow_html=True)
    else:
        if note_text:
            text_html = note_text.replace("\n", "<br>")
            st.markdown(
                f"""<div style="height:{DONUT_H}px; padding:.6rem; overflow-y:auto;
                color:#33414A; font-size:.85rem; line-height:1.6; white-space:pre-wrap;">
                {text_html}</div>""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f'<div style="height:{DONUT_H}px;"></div>', unsafe_allow_html=True)


def _render_settings_popover(cw, username, settings):
    """所有編輯功能都收在這一個選單裡：顯示模式切換 + 各區塊內容設定"""
    with st.popover("⋯", use_container_width=False):
        st.caption(
            f"顯示範圍限制：高度固定 {DONUT_H}px；寬度不是固定值，"
            "會隨瀏覽器視窗大小自動調整（個別區塊模式約為整排寬度的 1/3，整列大圖模式為整排寬度）。"
        )
        st.divider()

        st.markdown("**顯示模式**")
        mode_label = st.radio(
            "顯示模式", ["個別區塊", "整列大圖"],
            index=0 if settings["顯示模式"] != "wide" else 1,
            key="p01_mode_radio", label_visibility="collapsed",
        )
        new_mode = "wide" if mode_label == "整列大圖" else "individual"
        if new_mode != settings["顯示模式"]:
            settings["顯示模式"] = new_mode
            try:
                cw.save_user_settings(username, settings)
            except Exception as e:
                st.error(f"儲存失敗：{e}")
            st.rerun()

        st.divider()

        if settings["顯示模式"] == "wide":
            st.markdown("**整列大圖**")
            _render_image_uploader_control(cw, username, "wide")
        else:
            for slot in ["4", "5", "6"]:
                st.markdown(f"**區塊{slot}**")
                type_label = st.selectbox(
                    f"區塊{slot}內容", ["便條紙", "圖片"],
                    index=0 if settings.get(f"區塊{slot}", "note") != "image" else 1,
                    key=f"p01_slot_type_{slot}", label_visibility="collapsed",
                )
                new_type = "image" if type_label == "圖片" else "note"
                if new_type != settings.get(f"區塊{slot}", "note"):
                    settings[f"區塊{slot}"] = new_type
                    try:
                        cw.save_user_settings(username, settings)
                    except Exception as e:
                        st.error(f"儲存失敗：{e}")
                    st.rerun()

                if new_type == "note":
                    current = settings.get(f"便條{slot}", "")
                    new_text = st.text_area(
                        f"便條{slot}", value=current, max_chars=cw.NOTE_MAX_CHARS, height=100,
                        key=f"p01_note_{slot}", label_visibility="collapsed",
                    )
                    if st.button("💾 儲存", key=f"p01_note_save_{slot}", use_container_width=True):
                        settings[f"便條{slot}"] = new_text
                        try:
                            cw.save_user_settings(username, settings)
                            st.success("已儲存")
                            st.rerun()
                        except Exception as e:
                            st.error(f"儲存失敗：{e}")
                else:
                    _render_image_uploader_control(cw, username, slot)
                if slot != "6":
                    st.divider()


def _render_image_uploader_control(cw, username, slot):
    uploaded = st.file_uploader(
        f"上傳圖片（區塊{slot}）", type=["png", "jpg", "jpeg"],
        key=f"p01_img_upload_{slot}", label_visibility="collapsed",
    )
    if uploaded is not None:
        try:
            cw.upload_custom_image(username, slot, uploaded.read())
            st.success("圖片已更新")
            st.rerun()
        except Exception as e:
            st.error(f"上傳失敗：{e}")
