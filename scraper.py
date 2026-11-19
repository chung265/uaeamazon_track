import os
import re
import requests
from datetime import datetime, timezone
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def extract_asin(url: str) -> str | None:
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    return match.group(1) if match else None

def fetch_amazon_ae_data(asin: str) -> dict:
    """
    [UAE amazon.ae 데이터 수집 어댑터]
    실제 수집 API 키가 연결되기 전까지는 가짜 가격을 표시하지 않습니다.
    """
    if not SCRAPER_API_KEY:
        return {
            "title": None,
            "buybox_price": None,
            "buybox_seller": "수집 API 키 미설정 (연결 대기)",
            "lowest_offer_price": None,
            "status": "NO_API_KEY"
        }

    # 추후 Rainforest API / Bringits 등 확정된 API 연동 코드 위치
    return {
        "title": None,
        "buybox_price": None,
        "buybox_seller": "API 파싱 연동 대기",
        "lowest_offer_price": None,
        "status": "PENDING"
    }

def run_batch_update():
    supabase = get_supabase()
    res = supabase.table("products").select("*").limit(50).execute()
    products = res.data or []

    print(f"[{datetime.now(timezone.utc)}] 총 {len(products)}개 상품 수집 시작...")

    for item in products:
        asin = item["asin"]
        data = fetch_amazon_ae_data(asin)

        if data.get("title") and item.get("title") == "수집 대기 중...":
            supabase.table("products").update({"title": data["title"]}).eq("asin", asin).execute()

        supabase.table("price_history").insert({
            "asin": asin,
            "buybox_price": data["buybox_price"],
            "buybox_seller": data["buybox_seller"],
            "lowest_offer_price": data["lowest_offer_price"],
            "status": data["status"]
        }).execute()

    print("수집 완료.")

if __name__ == "__main__":
    run_batch_update()
