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
    """Rainforest API를 통해 UAE 현지 기준으로 Buy Box 가격 및 판매자를 다중 추적"""
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
        "asin": asin,
        "customer_location": "ae"  # UAE 현지 배송 기준으로 강제 조회
    }

    try:
        res = requests.get("https://api.rainforestapi.com/request", params=params, timeout=30)
        data = res.json()

        if not data.get("request_info", {}).get("success"):
            err_msg = data.get("request_info", {}).get("message", "API 호출 실패")
            return {
                "title": None,
                "buybox_price": None,
                "buybox_seller": f"API 오류: {err_msg[:30]}",
                "lowest_offer_price": None,
                "status": "API_ERROR"
            }

        product = data.get("product", {})
        buybox = product.get("buybox_winner", {})
        price_info = buybox.get("price", {})
        seller_info = buybox.get("seller", {})
        fulfillment = buybox.get("fulfillment", {})
        more_buying = product.get("more_buying_choices", [])

        # --- 판매자 이름 4단계 추적 로직 ---
        seller_name = seller_info.get("name")

        # 1단계: Amazon.ae 공식 직매입 여부 확인
        if not seller_name:
            if fulfillment.get("is_sold_by_amazon") or buybox.get("is_amazon_fulfilled") and not seller_info:
                seller_name = "Amazon.ae"

        # 2단계: merchant_info 텍스트에서 추출 (예: "Sold by XYZ and Fulfilled by Amazon")
        if not seller_name and product.get("merchant_info"):
            seller_name = product.get("merchant_info")

        # 3단계: more_buying_choices 첫 번째 판매자에서 추출
        if not seller_name and more_buying:
            first_seller = more_buying[0].get("seller", {}).get("name")
            if first_seller:
                seller_name = first_seller

        # 4단계: 가격은 있는데 판매자명만 누락된 경우
        if not seller_name:
            seller_name = "판매자 미표기 (품절 또는 옵션 선택 필요)"

        # 최저가 Offer 계산
        offer_prices = [item.get("price", {}).get("value") for item in more_buying if item.get("price", {}).get("value")]
        lowest_offer = min(offer_prices) if offer_prices else price_info.get("value")

        return {
            "title": product.get("title"),
            "buybox_price": price_info.get("value"),
            "buybox_seller": seller_name,
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
