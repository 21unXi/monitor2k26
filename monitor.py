import requests
import os
import datetime
import re
import json

# Steam Store API 端点
API_URL = "https://store.steampowered.com/api/appdetails"

# 需要监控的游戏 App ID 列表
APP_IDS = [
    "3472040", # NBA 2K26
    "4356430", # NBA 2K27
    "2828020", # Citystate Metropolis
    "2507950", # 三角洲行动
]

# 日志文件配置
LOG_FILE = "price_log.txt"
MAX_LOG_LINES = 100
RESULT_FILE = "result.md"
PRICE_STATE_FILE = "price_state.json"  # 用于邮件发送的临时文件

# 价格状态常量
PRICE_STATE_PRICE = "PRICE"
PRICE_STATE_FREE = "FREE"
PRICE_STATE_NO_PRICE = "NO_PRICE"




def load_price_state():
    """Load last-known per-package price state from JSON."""
    if not os.path.exists(PRICE_STATE_FILE):
        return {}
    try:
        with open(PRICE_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}




def save_price_state(state):
    """Save current per-package price state to JSON."""
    with open(PRICE_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)




def find_price_changes(current_prices, last_prices):
    """Compare current vs last prices by package name. Returns list of changes."""
    changes = []
    last_map = {p.get("name", "基础版"): p for p in last_prices}
    curr_map = {p.get("name", "基础版"): p for p in current_prices}


    for name, curr in curr_map.items():
        if name in last_map:
            old = last_map[name]
            if curr["amount"] != old["amount"]:
                changes.append({
                    "name": name,
                    "old_amount": old["amount"],
                    "new_amount": curr["amount"],
                    "currency": curr["currency"],
                    "old_discount": old.get("discount_percent", 0),
                    "new_discount": curr.get("discount_percent", 0),
                })
        else:
            changes.append({
                "name": name,
                "old_amount": None,
                "new_amount": curr["amount"],
                "currency": curr["currency"],
                "old_discount": 0,
                "new_discount": curr.get("discount_percent", 0),
            })


    for name, old in last_map.items():
        if name not in curr_map:
            changes.append({
                "name": name,
                "old_amount": old["amount"],
                "new_amount": None,
                "currency": old["currency"],
                "old_discount": old.get("discount_percent", 0),
                "new_discount": 0,
            })


    return changes




def get_release_date(details):
    """从 Steam API 响应中提取发售日期信息。"""
    release_date = details.get("release_date", {})
    coming_soon = release_date.get("coming_soon", False)
    date_str = release_date.get("date", None)
    return {
        "coming_soon": coming_soon,
        "date": date_str,
    }


def is_game_released(release_date_info):
    """判断游戏是否已发售（有日期且不是即将发售）。"""
    if release_date_info is None:
        return True  # 无信息视为已发售
    if release_date_info.get("coming_soon", False):
        return False
    if release_date_info.get("date") is None:
        return True  # 无日期但 coming_soon=False，视为已发售
    return True


def format_price_object(details):
    """从 Steam API 响应中标准化当前价格信息。"""
    release_date_info = get_release_date(details)
    price_overview = details.get("price_overview")

    # Convert all_prices from fen to yuan
    all_prices_raw = details.get("all_prices", [])
    all_prices_display = []
    for p in all_prices_raw:
        all_prices_display.append({
            "amount": p.get("price", 0) / 100,
            "initial": p.get("initial", 0) / 100,
            "discount_percent": p.get("discount_percent", 0),
            "currency": p.get("currency", "CNY"),
        })

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
            "release_date": release_date_info.get("date"),
            "coming_soon": release_date_info.get("coming_soon", False),
            "all_prices": all_prices_display,
        }

    if details.get("is_free", False):
        return {
            "state": PRICE_STATE_FREE,
            "display": "Free to Play",
            "release_date": release_date_info.get("date"),
            "coming_soon": release_date_info.get("coming_soon", False),
            "all_prices": all_prices_display,
        }

    return {
        "state": PRICE_STATE_NO_PRICE,
        "display": "No price data",
        "release_date": release_date_info.get("date"),
        "coming_soon": release_date_info.get("coming_soon", False),
        "all_prices": all_prices_display,
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
    # 去除可能存在的预购标记以便匹配价格
    clean_line = re.sub(r"\[预购\|发售:[^\]]*\]", "", line)
    clean_line = re.sub(r"\[预购\]", "", clean_line)

    if "Free to Play" in clean_line:
        return {"state": PRICE_STATE_FREE, "display": "Free to Play"}
    if "No price data" in clean_line:
        return {"state": PRICE_STATE_NO_PRICE, "display": "No price data"}

    match = re.search(r":\s*([\d\.]+)\s*([A-Z]+)", clean_line)
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


def build_notification_message(game_name, current_price, changes):
    """Build a detailed notification showing per-package price changes."""
    coming_soon = current_price.get("coming_soon", False)
    release_date = current_price.get("release_date")

    title = "📌 " + game_name + " 价格变动"
    if coming_soon:
        title += " [预购]"

    lines = [title]

    if coming_soon and release_date:
        lines.append(f"发售日期: {release_date}")

    lines.append("")

    # Show changed packages
    lines.append("变动明细:")
    for ch in changes:
        pname = ch["name"]
        curr = ch["currency"]
        if ch["old_amount"] is None:
            lines.append(f"  🆕 新增 {pname}: {ch['new_amount']:.2f} {curr}")
        elif ch["new_amount"] is None:
            lines.append(f"  ❌ 下架 {pname}: {ch['old_amount']:.2f} {curr}")
        elif ch["new_amount"] < ch["old_amount"]:
            diff = ch["old_amount"] - ch["new_amount"]
            lines.append(f"  🔻 {pname}: {ch['old_amount']:.2f} → {ch['new_amount']:.2f} {curr} (-{diff:.2f})")
        else:
            diff = ch["new_amount"] - ch["old_amount"]
            lines.append(f"  🔺 {pname}: {ch['old_amount']:.2f} → {ch['new_amount']:.2f} {curr} (+{diff:.2f})")

    # Show all current prices with package names
    all_prices = current_price.get("all_prices", [])
    if all_prices:
        lines.append("")
        lines.append("📦 当前所有套餐:")
        for i, p in enumerate(all_prices, 1):
            pname = p.get("name", "基础版")
            amt = p.get("amount", 0)
            disc = p.get("discount_percent", 0)
            orig = p.get("initial", 0)
            if disc > 0:
                lines.append(f"  {i}. [{pname}] {amt:.2f} {p['currency']} (SALE -{disc}% | 原价: {orig:.2f})")
            else:
                lines.append(f"  {i}. [{pname}] {amt:.2f} {p['currency']}")

    return "\n".join(lines)


def get_game_price(app_id):
    """\n    获取指定 Steam App ID 的价格信息，确保获取包含游戏本体的最低价格套餐。\n    包括同捆包在内的所有包含游戏本体的选择。\n    """
    params = {
        "appids": app_id,
        "cc": "cn",  # 货币国家代码 (cn = 中国/人民币)
        "filters": "price_overview,basic,package_groups,packages,release_date" # 获取价格、基本信息、套餐组和发售日期
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
                "name": "基础版",
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
                                "name": sub.get("description", "套餐"),
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
                                        "name": package_details.get("name", "同捆包"),
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
            # Deduplicate by name (keep lowest price per name)
            seen = {}
            for p in all_prices:
                n = p.get("name", "基础版")
                if n not in seen or p["price"] < seen[n]["price"]:
                    seen[n] = p
            all_prices = list(seen.values())

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
            
            # Store all package prices for notification display
            data_content['all_prices'] = all_prices
        
        return data_content
        
    except requests.RequestException as e:
        print(f"[Error] Network error for App ID {app_id}: {e}")
        return None

def get_last_price(game_name):
    """\n    从日志文件中读取指定游戏上一次记录的价格信息。\n    返回标准化的价格对象，而不是简单字符串，便于准确比较。\n    """
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
    """\n    更新滚动日志文件，保持最大行数限制\n    """
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

    utc_now = datetime.datetime.utcnow()
    beijing_time = utc_now + datetime.timedelta(hours=8)
    current_time = beijing_time.strftime("%Y-%m-%d %H:%M:%S")

    # Load previous per-package price state
    price_state = load_price_state()

    for app_id in APP_IDS:
        print(f"Checking App ID: {app_id}...")
        details = get_game_price(app_id)

        if details:
            name = details.get("name", f"App {app_id}")
            current_price = format_price_object(details)

            # Build name tag for log
            coming_soon = current_price.get("coming_soon", False)
            release_date = current_price.get("release_date")
            name_tag = name
            if coming_soon and release_date:
                name_tag = f"{name} [预购|发售:{release_date}]"
            elif coming_soon:
                name_tag = f"{name} [预购]"

            # Build log line with all package prices and names
            log_line = ""
            if current_price["state"] == PRICE_STATE_PRICE:
                all_prices_log = current_price.get("all_prices", [])
                if all_prices_log:
                    parts = []
                    for p in all_prices_log:
                        pname = p.get("name", "基础版")
                        part = f"{pname}:{p['amount']:.2f}{p['currency']}"
                        if p["discount_percent"] > 0:
                            part += f"(-{p['discount_percent']}%)"
                        parts.append(part)
                    log_line = f"[{current_time}] {name_tag}: " + " | ".join(parts)
                else:
                    log_line = f"[{current_time}] {name_tag}: {format_price_text(current_price)}"

                print(f"Game: {name_tag}")
                print(f"Current Price: {format_price_text(current_price)}")
            else:
                log_line = f"[{current_time}] {name_tag}: {format_price_text(current_price)}"
                print(f"Game: {name_tag} ({format_price_text(current_price)})")

            # Compare per-package prices with previous state
            current_all = current_price.get("all_prices", [])
            last_all = price_state.get(name, [])

            if last_all:
                changes = find_price_changes(current_all, last_all)
                if changes:
                    print(f"  -> {len(changes)} package(s) changed!")
                    for ch in changes:
                        if ch["old_amount"] is None:
                            print(f"     NEW: {ch['name']} = {ch['new_amount']:.2f}")
                        elif ch["new_amount"] is None:
                            print(f"     REMOVED: {ch['name']}")
                        else:
                            direction = "down" if ch["new_amount"] < ch["old_amount"] else "up"
                            print(f"     {ch['name']}: {ch['old_amount']:.2f} -> {ch['new_amount']:.2f} ({direction})")
                    notify_content.append(
                        build_notification_message(name, current_price, changes)
                    )
                    should_notify = True
                else:
                    print("  -> All package prices unchanged.")
            else:
                print(f"  -> No history for {name}, recording current state.")

            # Update state with current per-package prices
            price_state[name] = [
                {"name": p.get("name", "基础版"), "amount": p["amount"], "currency": p["currency"],
                 "discount_percent": p.get("discount_percent", 0)}
                for p in current_all
            ]

            if log_line:
                log_entries.append(log_line)

        print("-" * 50)

    # Save updated price state
    save_price_state(price_state)

    # Update log file
    if log_entries:
        update_rolling_log(log_entries)

    # Write notification file
    if should_notify and notify_content:
        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            f.write("## Steam 价格变动提醒\n\n")
            f.write("\n\n---\n\n".join(notify_content))
            f.write("\n\n[查看详情](https://store.steampowered.com/)")
        print(f"Notification content written to {RESULT_FILE}")
    elif os.path.exists(RESULT_FILE):
        os.remove(RESULT_FILE)


if __name__ == "__main__":
    main()
