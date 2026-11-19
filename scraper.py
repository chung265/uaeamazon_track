import os
import re
import json
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

    # UAE 현지(두바이) 접속 기준으로 Buy Box 노출 강제
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

        # --- 판매자 이름 다중 경로 추적 ---
        seller_name = (
            seller_info.get("name")
            or third_party.get("name")
        )

        # Amazon.ae 직매입인 경우
        if not seller_name and fulfillment.get("is_sold_by_amazon"):
            seller_name = "Amazon.ae"

        # merchant_info 텍스트에서 "Sold by XXX" 파싱 (예: "Ships from Amazon.ae. Sold by VT Cosmetics UAE.")
        merchant_info = product.get("merchant_info", "")
        if not seller_name and merchant_info:
            sold_match = re.search(r"Sold by\s+([^.]+)", merchant_info)
            seller_name = sold_match.group(1).strip() if sold_match else merchant_info

        # more_buying_choices 첫 번째 판매자 확인
        if not seller_name and more_buying:
            seller_name = more_buying[0].get("seller", {}).get("name")

        # 여전히 비어있을 경우 원본 구조 출력
        if not seller_name:
            debug_info = {
                "buybox_keys": list(buybox.keys()),
                "fulfillment": fulfillment,
                "merchant_info": merchant_info,
                "avail": buybox.get("availability", {}).get("raw")
            }
            seller_name = f"진단: {json.dumps(debug_info, ensure_ascii=False)[:250]}"

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
