import streamlit as st
import re
from datetime import datetime

st.set_page_config(
    page_title="Amazon UAE Buy Box Tracker",
    page_icon="🇦🇪",
    layout="centered"
)

# 임시 저장소 (브라우저 세션 유지)
if "products" not in st.session_state:
    st.session_state.products = []

def extract_asin(url: str):
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    return match.group(1) if match else None

st.title("🇦🇪 Amazon UAE Buy Box Tracker")
st.caption("Marketplace: amazon.ae | Currency: AED | Interval: 30 min")

col1, col2 = st.columns(2)
col1.metric("등록 상품", f"{len(st.session_state.products)} / 50")
col2.metric("상태", "대시보드 준비 완료")

st.divider()

# 상품 등록 폼
with st.form("add_form", clear_on_submit=True):
    url_input = st.text_input("Amazon.ae 상품 URL 붙여넣기", placeholder="https://www.amazon.ae/dp/B0XXXXXXXX")
    submitted = st.form_submit_button("상품 등록하기", use_container_width=True)

    if submitted:
        asin = extract_asin(url_input.strip())
        if not asin:
            st.error("올바른 Amazon 상품 URL이 아닙니다. (/dp/ 뒤 10자리 코드 확인)")
        elif any(p["asin"] == asin for p in st.session_state.products):
            st.warning("이미 등록된 상품입니다.")
        elif len(st.session_state.products) >= 50:
            st.error("최대 50개까지만 등록할 수 있습니다.")
        else:
            st.session_state.products.append({
                "asin": asin,
                "url": url_input.strip(),
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            st.success(f"ASIN `{asin}` 등록 완료!")
            st.rerun()

st.subheader("📊 추적 중인 상품 목록")

if not st.session_state.products:
    st.info("아직 등록된 상품이 없습니다. 위 칸에 amazon.ae 상품 주소를 넣어보세요.")
else:
    for idx, item in enumerate(st.session_state.products):
        with st.container(border=True):
            st.markdown(f"**ASIN:** `{item['asin']}`")
            st.markdown(f"[Amazon.ae에서 상품 보기]({item['url']})")
            st.caption(f"등록 시간: {item['added_at']} | 상태: 데이터 수집 API 연결 대기 중")
            if st.button("삭제", key=f"del_{item['asin']}"):
                st.session_state.products.pop(idx)
                st.rerun()
