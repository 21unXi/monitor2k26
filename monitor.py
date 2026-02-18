import requests
import sys
import os
import datetime
import re

# Steam Store API 端点
API_URL = "https://store.steampowered.com/api/appdetails"

# 需要监控的游戏 App ID 列表
APP_IDS = [
    "3472040", # NBA 2K26
    "2828020", # Citystate Metropolis
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

def get_last_price(game_name):
    """
    从日志文件中读取指定游戏上一次记录的价格
    """
    if not os.path.exists(LOG_FILE):
        return None
        
    last_price = None
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # 倒序查找最近的一条记录
            for line in reversed(lines):
                if game_name in line:
                    # 尝试提取价格
                    # 格式1: [Time] Name: 199.0 CNY ...
                    # 格式2: [Time] Name: Free to Play
                    # 格式3: [Time] Name: No price data
                    if "No price data" in line:
                        return "No price data"
                    if "Free to Play" in line:
                        return "Free to Play"
                    
                    # 提取数字价格
                    match = re.search(r": ([\d\.]+) ([A-Z]+)", line)
                    if match:
                        return f"{match.group(1)} {match.group(2)}"
                    
                    return None
    except Exception as e:
        print(f"Error reading log for last price: {e}")
        
    return last_price

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
    
    # 获取当前 UTC 时间并转换为北京时间 (UTC+8)
    utc_now = datetime.datetime.utcnow()
    beijing_time = utc_now + datetime.timedelta(hours=8)
    current_time = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
    
    for app_id in APP_IDS:
        print(f"Checking App ID: {app_id}...")
        details = get_game_price(app_id)
        
        if details:
            name = details.get("name", f"App {app_id}")
            price_overview = details.get("price_overview")
            
            # 获取上一次的价格
            last_price_str = get_last_price(name)
            current_price_str = ""
            
            log_line = ""
            
            if price_overview:
                currency = price_overview.get("currency")
                initial = price_overview.get("initial") / 100
                final = price_overview.get("final") / 100
                discount = price_overview.get("discount_percent")
                
                current_price_str = f"{final} {currency}"
                
                # 构建日志行
                log_line = f"[{current_time}] {name}: {final} {currency}"
                if discount > 0:
                    log_line += f" (SALE -{discount}% | Orig: {initial})"
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
                    current_price_str = "Free to Play"
                    log_line = f"[{current_time}] {name}: Free to Play"
                else:
                    current_price_str = "No price data"
                    log_line = f"[{current_time}] {name}: No price data"
                
                print(f"Game: {name} (No price/Free)")

            # 比较价格，决定是否通知
            if last_price_str != current_price_str:
                print(f"Price changed! Old: {last_price_str}, New: {current_price_str}")
                should_notify = True
                
                change_desc = ""
                if last_price_str == "No price data" and current_price_str != "No price data":
                     change_desc = "🚀 新发售/公布价格！"
                elif last_price_str is None:
                     change_desc = "✨ 首次监控" # 第一次运行不一定非要发邮件，看需求，这里暂不视为变动或视为新监控
                else:
                     change_desc = "💰 价格变动！"

                # 只有当不是None（首次）或者确实有变动时才记录（排除第一次运行全部发邮件的情况，或者保留）
                # 这里逻辑是：只要不相等且last_price不是None，就发邮件。如果是None（第一次），暂不发，避免刷屏。
                if last_price_str is not None:
                    msg = f"{change_desc}\n游戏: {name}\n旧价格: {last_price_str}\n新价格: {current_price_str}"
                    if price_overview and price_overview.get("discount_percent", 0) > 0:
                        msg += f"\n折扣: {price_overview.get('discount_percent')}% OFF"
                    notify_content.append(msg)
            else:
                print("Price unchanged.")

            if log_line:
                log_entries.append(log_line)
                    
        print("-" * 50)
    
    # 更新日志文件
    if log_entries:
        update_rolling_log(log_entries)
    
    # 如果需要通知，写入 result.md 供 GitHub Actions 使用
    if should_notify and notify_content:
        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            f.write("## Steam 价格变动提醒\n\n")
            f.write("\n\n---\n\n".join(notify_content))
            f.write("\n\n[查看详情](https://store.steampowered.com/)")
        print(f"Notification content written to {RESULT_FILE}")
    elif os.path.exists(RESULT_FILE):
        # 如果没有通知内容，但文件存在（可能是上次残留），删除它以免误发
        os.remove(RESULT_FILE)

if __name__ == "__main__":
    main()
