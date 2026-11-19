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
    if not SCRAPER_API_KEY:
        return {
            "title": None,
            "buybox_price": None,
            "buybox_seller": "수집 API 키 미설정",
            "lowest_offer_price": None,
            "status": "NO_API_KEY"
        }

    params = {
        "api_key": SCRAPER_API_KEY,
        "type": "product",
        "amazon_domain": "amazon.ae",
        "asin": asin,
        "customer_location": "ae",
        "language": "en_AE"
    }

    try:
        res = requests.get("https://api.rainforestapi.com/request", params=params, timeout=30)
        data = res.json()

        if not data.get("request_info", {}).get("success"):
            err_msg = data.get("request_info", {}).get("message", "API 호출 실패")
            return {
                "title": None,
                "buybox_price": None,
                "buybox_seller": f"API 오류: {err_msg}",
                "lowest_offer_price": None,
                "status": "API_ERROR"
            }

        product = data.get("product", {})
        buybox = product.get("buybox_winner", {})
        price_info = buybox.get("price", {})
        seller_info = buybox.get("seller", {})
        fulfillment = buybox.get("fulfillment", {})
        third_party = fulfillment.get("third_party_seller", {})
        more_buying = product.get("more_buying_choices", [])

        # 1. 가격 추출
        bb_price = price_info.get("value")
        new_offers_from = buybox.get("new_offers_from", {}).get("value")

        offer_prices = [item.get("price", {}).get("value") for item in more_buying if item.get("price", {}).get("value")]
        lowest_offer = min(offer_prices) if offer_prices else (new_offers_from or bb_price)

        # 2. 판매자 이름 다중 추적
        seller_name = seller_info.get("name") or third_party.get("name")

        # Amazon.ae 직매입 (1P / Shipper & Seller: Amazon.ae) 판별 강화
        if not seller_name:
            if (
                fulfillment.get("is_sold_by_amazon")
                or fulfillment.get("type") == "1p"
                or "amazon.ae" in product.get("merchant_info", "").lower()
            ):
                seller_name = "Amazon.ae"

        # merchant_info 텍스트에서 "Sold by XXX" 파싱
        merchant_info = product.get("merchant_info", "")
        if not seller_name and merchant_info:
            sold_match = re.search(r"Sold by\s+([^.]+)", merchant_info)
            seller_name = sold_match.group(1).strip() if sold_match else merchant_info

        # 메인 Buy Box가 숨겨진 경우 -> more_buying_choices 첫 번째 판매자로 대체
        if not seller_name and more_buying:
            first_seller = more_buying[0].get("seller", {}).get("name")
            if first_seller:
                seller_name = f"{first_seller} (오퍼 1위)"

        # 3. 상태 및 최종 예외 정리
        offers_count = buybox.get("new_offers_count", 0)
        in_cart_only = buybox.get("price_only_available_in_cart", False)

        if bb_price is not None:
            status = "SUCCESS"
            # Buy Box 가격이 정상 존재하는데 3자 판매자명이 전혀 없는 경우는 Amazon.ae 직매입(Shipper/Seller) 구조
            if not seller_name:
                seller_name = "Amazon.ae"
        elif in_cart_only:
            status = "IN_CART_ONLY"
            seller_name = seller_name or "장바구니 가격확인 상품"
        elif offers_count > 0 or lowest_offer is not None:
            status = "NO_BUYBOX_OFFERS"
            seller_name = seller_name or f"Buy Box 없음 (판매자 {offers_count}명 경쟁 중)"
        else:
            status = "OUT_OF_STOCK"
            seller_name = "품절 (재고 없음)"

        return {
            "title": product.get("title"),
            "buybox_price": bb_price,
            "buybox_seller": seller_name,
            "lowest_offer_price": lowest_offer,
            "status": status
        }

    except Exception as e:
        return {
            "title": None,
            "buybox_price": None,
            "buybox_seller": f"오류: {str(e)[:50]}",
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
