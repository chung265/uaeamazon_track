import os
import streamlit as st
import pandas as pd
import plotly.express as px
from scraper import get_supabase, extract_asin, run_batch_update

st.set_page_config(
    page_title="Amazon UAE Buy Box Tracker",
    page_icon="🇦🇪",
    layout="centered"
)

# Streamlit Secrets 환경변수 동기화
if "SUPABASE_URL" in st.secrets:
    os.environ["SUPABASE_URL"] = st.secrets["SUPABASE_URL"]
if "SUPABASE_KEY" in st.secrets:
    os.environ["SUPABASE_KEY"] = st.secrets["SUPABASE_KEY"]
if "SCRAPER_API_KEY" in st.secrets:
    os.environ["SCRAPER_API_KEY"] = st.secrets["SCRAPER_API_KEY"]

try:
    supabase = get_supabase()
except Exception:
    st.error("Streamlit Secrets에 SUPABASE_URL과 SUPABASE_KEY를 먼저 등록해 주세요.")
    st.stop()

st.title("🇦🇪 Amazon UAE Buy Box Tracker")
st.caption("Marketplace: amazon.ae | Currency: AED | Interval: 10 min")

products_res = supabase.table("products").select("*").order("created_at", desc=True).execute()
products = products_res.data or []

col1, col2 = st.columns(2)
col1.metric("등록 상품", f"{len(products)} / 50")
col2.metric("추적 상태", "10분 자동 수집 중" if products else "대기 중")

st.divider()

with st.expander("➕ 새 상품 URL 등록하기", expanded=(len(products) == 0)):
    with st.form("add_product_form", clear_on_submit=True):
        url_input = st.text_input("Amazon.ae 상품 URL 붙여넣기", placeholder="https://www.amazon.ae/dp/B0XXXXXXXX")
        submitted = st.form_submit_button("등록하기", use_container_width=True)

        if submitted:
            if len(products) >= 50:
                st.error("최대 50개까지만 등록할 수 있습니다.")
            else:
                asin = extract_asin(url_input.strip())
                if not asin:
                    st.error("유효한 Amazon 상품 URL이 아닙니다. (/dp/ 뒤 10자리 확인)")
                else:
                    try:
                        supabase.table("products").insert({
                            "asin": asin,
                            "url": url_input.strip()
                        }).execute()
                        st.success(f"ASIN `{asin}` 등록 완료! (영구 저장됨)")
                        st.rerun()
                    except Exception:
                        st.warning("이미 등록된 상품이거나 저장 중 오류가 발생했습니다.")

st.subheader("📊 Buy Box 모니터링")

if not products:
    st.info("아직 등록된 상품이 없습니다. 위 칸에 amazon.ae 상품 주소를 넣어보세요.")
else:
    if st.button("🔄 지금 즉시 수동 수집 실행", use_container_width=True):
        with st.spinner("데이터 확인 중..."):
            run_batch_update()
        st.success("수집 기록이 저장되었습니다.")
        st.rerun()

    for p in products:
        asin = p["asin"]
        hist_res = (
            supabase.table("price_history")
            .select("*")
            .eq("asin", asin)
            .order("checked_at", desc=True)
            .limit(144)  # 최근 24시간 (10분 * 144회)
            .execute()
        )
        history = hist_res.data or []
        latest = history[0] if history else None

        with st.container(border=True):
            st.markdown(f"**{p['title']}** (`{asin}`)")
            st.markdown(f"[Amazon.ae 상품 페이지 열기]({p['url']})")

            if latest:
                c1, c2, c3 = st.columns(3)
                price_str = f"AED {latest['buybox_price']}" if latest["buybox_price"] else "-"
                offer_str = f"AED {latest['lowest_offer_price']}" if latest["lowest_offer_price"] else "-"

                c1.metric("Buy Box 가격", price_str)
                c2.metric("최저 Offer", offer_str)
                c3.metric("상태", latest["status"])
                st.caption(f"🏆 Buy Box 판매자: **{latest['buybox_seller']}** | 최근 확인: {latest['checked_at'][:16].replace('T', ' ')} UTC")

                df = pd.DataFrame(history)
                if not df.empty and df["buybox_price"].notna().any():
                    df["checked_at"] = pd.to_datetime(df["checked_at"])
                    fig = px.line(df, x="checked_at", y="buybox_price", markers=True, title="Buy Box 가격 추이 (AED)")
                    fig.update_layout(height=220, margin=dict(l=10, r=10, t=30, b=10))
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("⏳ 첫 번째 10분 수집 주기를 기다리고 있습니다.")

            if st.button("🗑️ 삭제", key=f"del_{asin}"):
                supabase.table("products").delete().eq("asin", asin).execute()
                st.rerun()
