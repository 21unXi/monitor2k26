import requests
import os
import datetime
import re

# Steam Store API 端点
API_URL = "https://store.steampowered.com/api/appdetails"

# 需要监控的游戏 App ID 列表
APP_IDS = [
    "3472040", # NBA 2K26
    "2828020", # Citystate Metropolis
    "2507950", # 三角洲行动
]

# 日志文件配置
LOG_FILE = "price_log.txt"
MAX_LOG_LINES = 100
RESULT_FILE = "result.md"  # 用于邮件发送的临时文件

# 价格状态常量
PRICE_STATE_PRICE = "PRICE"
PRICE_STATE_FREE = "FREE"
PRICE_STATE_NO_PRICE = "NO_PRICE"


def format_price_object(details):
    """从 Steam API 响应中标准化当前价格信息。"""
    price_overview = details.get("price_overview")
    if price_overview:
        currency = price_overview.get("currency", "CNY")
        initial = price_overview.get("initial", 0) / 100
        final = price_overview.get("final", 0) / 100
        return {
            "state": PRICE_STATE_PRICE,
            "amount": final,
            "currency": currency,
            "initial": initial,
            "discount_percent": price_overview.get("discount_percent", 0),
            "display": f"{final:.2f} {currency}",
        }

    if details.get("is_free", False):
        return {
            "state": PRICE_STATE_FREE,
            "display": "Free to Play",
        }

    return {
        "state": PRICE_STATE_NO_PRICE,
        "display": "No price data",
    }


def format_price_text(price_obj):
    if not price_obj:
        return "Unknown"
    return price_obj.get("display", "Unknown")


def are_price_states_equal(a, b):
    if a is None or b is None:
        return False
    if a["state"] != b["state"]:
        return False
    if a["state"] == PRICE_STATE_PRICE:
        return a["amount"] == b["amount"] and a["currency"] == b["currency"]
    return True


def parse_log_price_line(line):
    """从日志文本行中解析最近的价格状态。"""
    if "Free to Play" in line:
        return {"state": PRICE_STATE_FREE, "display": "Free to Play"}
    if "No price data" in line:
        return {"state": PRICE_STATE_NO_PRICE, "display": "No price data"}

    match = re.search(r":\s*([\d\.]+)\s*([A-Z]+)", line)
    if match:
        amount = float(match.group(1))
        currency = match.group(2)
        return {
            "state": PRICE_STATE_PRICE,
            "amount": amount,
            "currency": currency,
            "display": f"{amount:.2f} {currency}",
        }

    return None


def build_notification_message(game_name, current_price, last_price):
    """根据当前价格和历史价格生成通知文本。"""
    current_text = format_price_text(current_price)
    last_text = format_price_text(last_price)

    if last_price["state"] == PRICE_STATE_PRICE and current_price["state"] == PRICE_STATE_PRICE:
        if current_price["amount"] < last_price["amount"]:
            title = "🔻 降价提醒！"
            diff = last_price["amount"] - current_price["amount"]
            extra = f"降幅: {diff:.2f} {current_price['currency']}"
        elif current_price["amount"] > last_price["amount"]:
            title = "🔺 涨价提醒！"
            diff = current_price["amount"] - last_price["amount"]
            extra = f"涨幅: {diff:.2f} {current_price['currency']}"
        else:
            title = "📌 价格变动提醒"
            extra = "价格类型相同，但显示值发生变化。"
    elif last_price["state"] == PRICE_STATE_NO_PRICE and current_price["state"] == PRICE_STATE_PRICE:
        title = "🚀 上架/新价格发布！"
        extra = "当前已获取到价格信息。"
    elif last_price["state"] == PRICE_STATE_PRICE and current_price["state"] == PRICE_STATE_NO_PRICE:
        title = "❗ 价格信息丢失"
        extra = "当前无法获取到价格数据。"
    elif last_price["state"] == PRICE_STATE_FREE and current_price["state"] == PRICE_STATE_PRICE:
        title = "💰 从免费恢复收费"
        extra = "当前已恢复为付费版本。"
    elif last_price["state"] == PRICE_STATE_PRICE and current_price["state"] == PRICE_STATE_FREE:
        title = "🎉 现在免费游玩！"
        extra = "游戏已转为免费。"
    else:
        title = "💡 价格状态改变"
        extra = "价格状态发生变化。"

    lines = [title, f"游戏: {game_name}", f"旧价格: {last_text}", f"新价格: {current_text}"]

    if current_price["state"] == PRICE_STATE_PRICE and current_price.get("discount_percent", 0) > 0:
        lines.append(f"当前折扣: {current_price['discount_percent']}%")
    if current_price["state"] == PRICE_STATE_PRICE and current_price.get("initial", 0) > current_price["amount"]:
        lines.append(f"原价: {current_price['initial']:.2f} {current_price['currency']}")
    lines.append(extra)

    return "\n".join(lines)


def get_game_price(app_id):
    """
    获取指定 Steam App ID 的价格信息，确保获取包含游戏本体的最低价格套餐。
    包括同捆包在内的所有包含游戏本体的选择。
    """
    params = {
        "appids": app_id,
        "cc": "cn",  # 货币国家代码 (cn = 中国/人民币)
        "filters": "price_overview,basic,package_groups,packages" # 获取价格、基本信息、套餐组和套餐
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
            
        data_content = game_data["data"]
        game_name = data_content.get("name", "")
        
        # 收集所有包含游戏本体的套餐价格（统一以分为单位）
        all_prices = []
        
        # 首先检查是否有price_overview（通常是基础版价格，包含游戏本体）
        if 'price_overview' in data_content:
            price_overview = data_content['price_overview']
            all_prices.append({
                "price": price_overview.get('final', 0),  # 已经是分
                "currency": price_overview.get('currency', 'CNY'),
                "initial": price_overview.get('initial', 0),  # 已经是分
                "discount_percent": price_overview.get('discount_percent', 0)
            })
        
        # 从package_groups中获取所有包含游戏本体的套餐价格
        if 'package_groups' in data_content:
            package_groups = data_content['package_groups']
            for group in package_groups:
                if 'subs' in group:
                    for sub in group['subs']:
                        # 检查套餐是否有价格
                        if sub.get('price'):
                            all_prices.append({
                                "price": sub.get('price', 0),  # 已经是分
                                "currency": "CNY",
                                "initial": sub.get('price', 0),  # 假设初始价格与当前价格相同
                                "discount_percent": sub.get('discount_percent', 0)
                            })
        
        # 尝试获取所有套餐的详细信息，包括同捆包
        if 'packages' in data_content:
            packages = data_content['packages']
            for package_id in packages:
                # 获取套餐详情
                package_url = f"https://store.steampowered.com/api/packagedetails"
                package_params = {
                    "packageids": package_id,
                    "cc": "cn"
                }
                try:
                    package_response = requests.get(package_url, params=package_params, timeout=5)
                    package_response.raise_for_status()
                    package_data = package_response.json()
                    
                    if str(package_id) in package_data:
                        package_info = package_data[str(package_id)]
                        if package_info.get('success'):
                            package_details = package_info['data']
                            # 检查套餐是否包含当前游戏
                            apps = package_details.get('apps', [])
                            if any(app.get('id') == int(app_id) for app in apps):
                                # 获取套餐价格
                                package_price = package_details.get('price', {})
                                final_price = package_price.get('final', 0)
                                if final_price:
                                    all_prices.append({
                                        "price": final_price,  # 价格 已经是分 
                                        "currency": "CNY", # 货币
                                        "initial": package_price.get('initial', final_price),  # 原始价格 已经是分 
                                        "discount_percent": package_price.get('discount_percent', 0) # 折扣百分比
                                    })
                except requests.RequestException as e:
                    # 忽略套餐详情获取失败的情况
                    pass
        
        # 手动添加同捆包价格（如果存在）
        # 这里可以根据实际情况添加已知的同捆包信息
        # 例如，NBA 2K26 + PGA TOUR 2K25 同捆包
        # if app_id == "3472040":  # 只对NBA 2K26添加同捆包价格
        #     all_prices.append({
        #         "price": 17284,  # 172.84 CNY 转换为分
        #         "currency": "CNY",
        #         "initial": 17284,  # 假设初始价格与当前价格相同
        #         "discount_percent": 42  # 假设折扣为42%
        #     })

        # 如果收集到了价格，选择最低的
        if all_prices:
            # 按价格排序，获取最低价格
            all_prices.sort(key=lambda x: x.get('price', 0))
            lowest_price = all_prices[0]
            
            # 构建price_overview结构
            price_overview = {
                "currency": lowest_price.get('currency', 'CNY'),
                "initial": lowest_price.get('initial', 0),  # 已经是分
                "final": lowest_price.get('price', 0),  # 已经是分
                "discount_percent": lowest_price.get('discount_percent', 0)
            }
            data_content['price_overview'] = price_overview
        
        return data_content
        
    except requests.RequestException as e:
        print(f"[Error] Network error for App ID {app_id}: {e}")
        return None

def get_last_price(game_name):
    """
    从日志文件中读取指定游戏上一次记录的价格信息。
    返回标准化的价格对象，而不是简单字符串，便于准确比较。
    """
    if not os.path.exists(LOG_FILE):
        return None

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in reversed(f.readlines()):
                if game_name in line:
                    parsed = parse_log_price_line(line)
                    if parsed:
                        return parsed
                    break
    except Exception as e:
        print(f"Error reading log for last price: {e}")

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
    # notify_content 仅在实际价格状态差异时填充，避免首次运行或无变化时误发通知。
    
    # 获取当前 UTC 时间并转换为北京时间 (UTC+8)
    utc_now = datetime.datetime.utcnow()
    beijing_time = utc_now + datetime.timedelta(hours=8)
    current_time = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
    
    for app_id in APP_IDS:
        print(f"Checking App ID: {app_id}...")
        details = get_game_price(app_id)
        
        if details:
                name = details.get("name", f"App {app_id}")
                current_price = format_price_object(details)
                last_price = get_last_price(name)
                log_line = ""

                if current_price["state"] == PRICE_STATE_PRICE:
                    currency = current_price["currency"]
                    final = current_price["amount"]
                    discount = current_price["discount_percent"]
                    log_line = f"[{current_time}] {name}: {final:.2f} {currency}"
                    if discount > 0:
                        log_line += f" (SALE -{discount}% | Orig: {current_price['initial']:.2f})"
                    else:
                        log_line += " (Regular)"

                    print(f"Game: {name}")
                    print(f"Current Price: {final:.2f} {currency}")
                    if discount > 0:
                        print(f"Discount: {discount}% OFF!")
                        print("Status: ON SALE!")
                else:
                    if current_price["state"] == PRICE_STATE_FREE:
                        log_line = f"[{current_time}] {name}: Free to Play"
                    else:
                        log_line = f"[{current_time}] {name}: No price data"
                    print(f"Game: {name} (No price/Free)")

                if last_price is None:
                    print(f"No history for {name}, recording current status.")
                elif are_price_states_equal(current_price, last_price):
                    print("Price unchanged.")
                else:
                    print(f"Price changed! Old: {format_price_text(last_price)}, New: {format_price_text(current_price)}")
                    notify_content.append(build_notification_message(name, current_price, last_price))
                    should_notify = True

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
