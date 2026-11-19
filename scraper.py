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
    """Rainforest API를 통해 실제 Amazon.ae 상품명, Buy Box 가격 및 판매자 수집"""
    if not SCRAPER_API_KEY:
        return {
            "title": None,
            "buybox_price": None,
            "buybox_seller": "수집 API 키 미설정 (연결 대기)",
            "lowest_offer_price": None,
            "status": "NO_API_KEY"
        }

    params = {
        "api_key": SCRAPER_API_KEY,
        "type": "product",
        "amazon_domain": "amazon.ae",
        "asin": asin
    }

    try:
        res = requests.get("https://api.rainforestapi.com/request", params=params, timeout=30)
        data = res.json()

        if not data.get("request_info", {}).get("success"):
            return {
                "title": None,
                "buybox_price": None,
                "buybox_seller": "API 호출 실패",
                "lowest_offer_price": None,
                "status": "API_ERROR"
            }

        product = data.get("product", {})
        buybox = product.get("buybox_winner", {})
        price_info = buybox.get("price", {})
        seller_info = buybox.get("seller", {})

        # 최저가 Offer 추출 (있을 경우)
        more_buying = product.get("more_buying_choices", [])
        offer_prices = [item.get("price", {}).get("value") for item in more_buying if item.get("price", {}).get("value")]
        lowest_offer = min(offer_prices) if offer_prices else price_info.get("value")

        return {
            "title": product.get("title"),
            "buybox_price": price_info.get("value"),
            "buybox_seller": seller_info.get("name", "판매자 정보 없음 (품절 등)"),
            "lowest_offer_price": lowest_offer,
            "status": "SUCCESS" if price_info.get("value") else "OUT_OF_STOCK"
        }

    except Exception as e:
        return {
            "title": None,
            "buybox_price": None,
            "buybox_seller": f"오류: {str(e)[:30]}",
            "lowest_offer_price": None,
            "status": "ERROR"
        }

def run_batch_update():
    supabase = get_supabase()
    res = supabase.table("products").select("*").limit(50).execute()
    products = res.data or []

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

if __name__ == "__main__":
    run_batch_update()
