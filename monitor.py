import requests
import sys
import os
import datetime

# Steam Store API 端点
API_URL = "https://store.steampowered.com/api/appdetails"

# 需要监控的游戏 App ID 列表
APP_IDS = [
    "3472040", 
]

# 日志文件配置
LOG_FILE = "price_log.txt"
MAX_LOG_LINES = 100
RESULT_FILE = "result.md" # 用于邮件发送的临时文件

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

def update_rolling_log(new_lines):
    """
    更新滚动日志文件，保持最大行数限制
    """
    lines = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Error reading log file: {e}")
    
    # 追加新内容
    lines.extend([line + "\n" for line in new_lines])
    
    # 保持最大行数（保留最后的 MAX_LOG_LINES 行）
    if len(lines) > MAX_LOG_LINES:
        lines = lines[-MAX_LOG_LINES:]
        
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"Updated {LOG_FILE} with {len(new_lines)} new lines.")
    except Exception as e:
        print(f"Error writing log file: {e}")

def main():
    print("Starting Steam Price Monitor...\n")
    print(f"Monitoring {len(APP_IDS)} games.")
    print("-" * 50)
    
    log_entries = []
    notify_content = []
    should_notify = False
    
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for app_id in APP_IDS:
        print(f"Checking App ID: {app_id}...")
        details = get_game_price(app_id)
        
        if details:
            name = details.get("name", f"App {app_id}")
            price_overview = details.get("price_overview")
            
            log_line = ""
            
            if price_overview:
                currency = price_overview.get("currency")
                initial = price_overview.get("initial") / 100
                final = price_overview.get("final") / 100
                discount = price_overview.get("discount_percent")
                
                # 构建日志行
                log_line = f"[{current_time}] {name}: {final} {currency}"
                if discount > 0:
                    log_line += f" (SALE -{discount}% | Orig: {initial})"
                    should_notify = True
                    notify_content.append(f"🔥 {name} 正在打折！\n现价: {final} {currency}\n原价: {initial} {currency}\n折扣: {discount}% OFF")
                else:
                    log_line += " (Regular)"
                
                # 打印到控制台
                print(f"Game: {name}")
                print(f"Current Price: {final} {currency}")
                if discount > 0:
                    print(f"Discount: {discount}% OFF!")
                    print("Status: ON SALE!")
                
            else:
                is_free = details.get("is_free", False)
                if is_free:
                    log_line = f"[{current_time}] {name}: Free to Play"
                else:
                    log_line = f"[{current_time}] {name}: No price data"
                
                print(f"Game: {name} (No price/Free)")

            if log_line:
                log_entries.append(log_line)
                    
        print("-" * 50)
    
    # 更新日志文件
    if log_entries:
        update_rolling_log(log_entries)
    
    # 如果需要通知，写入 result.md 供 GitHub Actions 使用
    if should_notify:
        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            f.write("## Steam 价格变动提醒\n\n")
            f.write("\n\n".join(notify_content))
            f.write("\n\n[查看详情](https://store.steampowered.com/)")
        print(f"Notification content written to {RESULT_FILE}")

if __name__ == "__main__":
    main()
