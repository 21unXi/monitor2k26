import requests

# Steam Store API 端点
API_URL = "https://store.steampowered.com/api/appdetails"

# 需要监控的游戏 App ID 列表
# 3472040: NBA 2K26 (基于搜索结果的占位符，请确认)
# 你可以在此列表中添加更多 App ID
APP_IDS = [
    "3472040", 
]

def get_game_price(app_id):
    """
    获取指定 Steam App ID 的价格信息。
    """
    params = {
        "appids": app_id,
        "cc": "cn",  # 货币国家代码 (cn = 中国/人民币)
        "filters": "price_overview,basic" # 仅获取价格和基本信息（名称）
    }
    
    try:
        response = requests.get(API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if str(app_id) not in data:
            print(f"[Error] No data found for App ID {app_id}")
            return None
            
        game_data = data[str(app_id)]
        
        if not game_data.get("success"):
            print(f"[Error] Request failed for App ID {app_id}: {game_data.get('data')}")
            return None
            
        return game_data["data"]
        
    except requests.RequestException as e:
        print(f"[Error] Network error for App ID {app_id}: {e}")
        return None

def main():
    print("Starting Steam Price Monitor...\n")
    print(f"Monitoring {len(APP_IDS)} games.")
    print("-" * 50)
    
    for app_id in APP_IDS:
        print(f"Checking App ID: {app_id}...")
        details = get_game_price(app_id)
        
        if details:
            name = details.get("name", f"App {app_id}")
            price_overview = details.get("price_overview")
            
            if price_overview:
                currency = price_overview.get("currency")
                initial = price_overview.get("initial") / 100  # 转换为标准单位（元）
                final = price_overview.get("final") / 100
                discount = price_overview.get("discount_percent")
                
                print(f"Game: {name}")
                print(f"Current Price: {final} {currency}")
                
                if discount > 0:
                    print(f"Original Price: {initial} {currency}")
                    print(f"Discount: {discount}% OFF!")
                    print("Status: ON SALE!")
                else:
                    print("Status: Regular Price")
            else:
                # 免费游戏或尚未发布价格
                is_free = details.get("is_free", False)
                release_date = details.get("release_date", {}).get("date", "Unknown")
                
                print(f"Game: {name}")
                if is_free:
                    print("Price: Free to Play")
                else:
                    print("Price: Not available (Pre-order or not listed)")
                    print(f"Release Date: {release_date}")
                    
        print("-" * 50)

if __name__ == "__main__":
    main()
