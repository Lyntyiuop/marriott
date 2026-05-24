import json
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains


def get_shanghai_hotels(checkin_date="2026-05-23", checkout_date="2026-05-24"):
    """获取万豪上海酒店列表及所有房型价格"""

    # 注入拦截器 — 捕获所有 JSON API 响应（含 URL），便于定位酒店搜索接口
    interceptor_js = """
        window.__captured = [];

        function _tryCapture(url, text) {
            if (!url || !text) return;
            try {
                const data = JSON.parse(text);
                window.__captured.push({url: url, data: data});
            } catch(e) {}
        }

        // 拦截 fetch
        const _fetch = window.fetch;
        window.fetch = async function(...args) {
            const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
            const resp = await _fetch.apply(this, args);
            if (url && !url.includes('hotelads') && !url.includes('google')) {
                const clone = resp.clone();
                clone.text().then(t => _tryCapture(url, t)).catch(() => {});
            }
            return resp;
        };

        // 拦截 XMLHttpRequest
        const _open = XMLHttpRequest.prototype.open;
        const _send = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function(method, url, ...rest) {
            this.__url = url;
            return _open.apply(this, [method, url, ...rest]);
        };
        XMLHttpRequest.prototype.send = function(...args) {
            this.addEventListener('load', function() {
                _tryCapture(this.__url, this.responseText);
            });
            return _send.apply(this, args);
        };
    """

    driver = uc.Chrome(headless=False, use_subprocess=True, version_main=148)

    try:
        # 在页面加载前注入拦截器（CDP 级别，优先级高于页面 JS）
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": interceptor_js
        })

        # ========== 1. 加载搜索页面 ==========
        search_url = (
            "https://www.marriott.com.cn/search/findHotels.mi"
            f"?fromDate={checkin_date}"
            f"&toDate={checkout_date}"
            "&destinationAddress.destination=上海市"
            "&roomCount=1"
            "&numAdultsPerRoom=1"
            "&marriottBrands=EB,RZ,LC,XR,WH,JW,BG,MC,SI,DE,WI,MD,BR,DS,TX" # 详见万豪品牌id.md
            "&states=CN-Shanghai" # 江苏：&states=CN-%E6%B1%9F%E8%8B%8F%E7%9C%81
        )

        print("正在加载搜索页面...")
        driver.get(search_url)
        time.sleep(2)

        # ========== 2. 处理 Cookie 同意弹窗 ==========
        cookie_dismissed = driver.execute_script("""
            // 通过文本内容查找按钮
            const cookieTexts = '接受所有';
            const candidates = document.querySelectorAll(
                'button, a, [role="button"], .btn, [class*="cookie" i], [id*="cookie" i]'
            );
            for (const el of candidates) {
                if (!el.offsetParent) continue;
                const text = (el.textContent || '').trim();
                if (text === cookieTexts || text.startsWith(cookieTexts) || text.includes(cookieTexts)) {
                    el.click();
                    return true;
                }
            }
            return false;
        """)
        if cookie_dismissed:
            print("  已关闭 Cookie 弹窗")
            time.sleep(0.5)
        else:
            raise Exception("❌ 未找到【接受所有Cookie】按钮，程序终止运行")

        # ========== 3. 点击搜索按钮 ==========
        clicked = driver.execute_script("""
            const searchTexts = '更新搜索';
            const candidates = document.querySelectorAll(
                'button, a, [role="button"], .btn'
            );
            for (const el of candidates) {
                if (!el.offsetParent) continue;
                const text = (el.textContent || '').trim();
                if (text === searchTexts || text.startsWith(searchTexts)) {
                    el.click();
                    return true;
                }
            }
            return false;
        """)
        if clicked:
            print("  已点击搜索按钮")
        else:
            raise Exception("❌ 未找到【更新搜索】按钮，程序终止运行")

        # ========== 4. 等待 API 响应返回 ==========
        print("等待搜索结果...")
        deadline = time.time() + 20
        result = None

        while time.time() < deadline:
            time.sleep(1)
            captured = driver.execute_script("return window.__captured || [];")

            # 查找包含酒店数据的响应
            for entry in captured:
                data = entry.get("data")
                if not data or not isinstance(data, (dict, list)):
                    continue

                # GraphQL: data.search.lowestAvailableRates.searchBy{Destination,Geolocation}.edges[]
                if isinstance(data, dict):
                    inner = data.get("data")
                    if isinstance(inner, dict):
                        search = inner.get("search") or {}
                        lar = search.get("lowestAvailableRates") or {}
                        for geo_key in ("searchByDestination", "searchByGeolocation"):
                            conn = lar.get(geo_key) or {}
                            edges = conn.get("edges") or []
                            if edges:
                                hotels = []
                                for edge in edges:
                                    node = edge.get("node") or {}
                                    if node.get("property"):
                                        hotels.append(node)
                                if hotels:
                                    result = hotels
                                    print(f"  找到酒店列表（GraphQL），{len(hotels)} 家")
                                    break
                    if result:
                        break
            if result:
                break
        else:
            # 超时，打印关键 API 返回的数据结构
            captured = driver.execute_script("return window.__captured || [];")
            if captured:
                # 筛选 Marriott 业务 API（排除广告/分析/CDN）
                biz_apis = [
                    e for e in captured
                    if any(kw in e.get("url", "") for kw in [
                        "findHotels", "phoenixShopDatedSearch", "phoenixShop",
                        "phoenix-common", "getUserDetails",
                    ])
                ]
                print(f"\n  超时，共截获 {len(captured)} 个响应，"
                      f"其中 {len(biz_apis)} 个业务 API：")
                for entry in biz_apis[:6]:
                    url = entry.get("url", "?")[:100]
                    data = entry.get("data")
                    if isinstance(data, dict):
                        keys = list(data.keys())[:10]
                        sample = json.dumps(data, ensure_ascii=False)[:400]
                        print(f"    [{url}]")
                        print(f"    keys: {keys}")
                        print(f"    sample: {sample}")
                        print()
                    elif isinstance(data, list):
                        print(f"    [{url}] 列表，长度 {len(data)}")
                        if data:
                            print(f"    首项 keys: {list(data[0].keys()) if isinstance(data[0], dict) else type(data[0])}")
                            print(f"    sample: {json.dumps(data[0], ensure_ascii=False)[:400]}")
                        print()
            else:
                print("\n  未截获任何 API 响应")

        if result:
            if isinstance(result, list):
                return {"hotels": result}
            return result

        raise RuntimeError("超时20s未找到酒店数据，请检查 API 结构是否变化，或增加等待时间")

    finally:
        try:
            driver.close()
        except Exception:
            pass
        try:
            driver.quit()
        except Exception:
            pass


def parse_all_room_types(api_response):
    """从 API 返回的 JSON 中提取每个酒店的所有房型及价格"""
    hotels_data = []
    hotel_list = []

    if isinstance(api_response, dict):
        hotel_list = api_response.get("hotels") or []
        if not hotel_list:
            inner = api_response.get("data")
            if isinstance(inner, dict):
                hotel_list = inner.get("hotelList") or []

    if not hotel_list:
        print("无法识别的响应结构，请检查 raw_data 的 keys:",
              api_response.keys() if isinstance(api_response, dict) else type(api_response))
        return []

    # if hotel_list:  # DEBUG
    #     first = hotel_list[0]
    #     print(f"\n  [调试] 首项 keys: {list(first.keys())}")
    #     print(f"  [调试] 首项完整数据: {json.dumps(first, ensure_ascii=False)[:600]}")
    #     rates_sample = first.get("rates") or []
    #     if rates_sample:
    #         print(f"  [调试] rates 数组长度: {len(rates_sample)}")
    #         print(f"  [调试] rates[0] keys: {list(rates_sample[0].keys())}")
    #         print(f"  [调试] rates[0] 数据: {json.dumps(rates_sample[0], ensure_ascii=False)[:500]}")

    for hotel in hotel_list:
        # ---- GraphQL node 格式：{property: {...}, rates: [...]} ----
        prop = hotel.get("property") or {}
        if isinstance(prop, dict):
            info = prop.get("basicInformation") or {}
            hotel_id = prop.get("id") or ""
            hotel_name = info.get("name") or prop.get("name") or ""
            lat = prop.get("latitude") or ""
            lng = prop.get("longitude") or ""
        else:
            hotel_id = hotel.get("hotelId") or hotel.get("marriottId") or ""
            hotel_name = hotel.get("name") or hotel.get("hotelName") or hotel.get("brandName") or ""
            lat, lng = "", ""

        rooms = []

        # GraphQL: node 上的 rates 数组
        node_rates = hotel.get("rates") or []

        # roomTypes
        room_types = hotel.get("roomTypes") or (prop if isinstance(prop, dict) else {}).get("roomTypes") or []

        if node_rates:
            # if not hasattr(parse_all_room_types, "_debug_printed"):  # DEBUG
            #     first_rate = node_rates[0] if node_rates else {}
            #     first_modes = first_rate.get("rateModes") or {}
            #     first_lar = first_modes.get("lowestAverageRate") or {}
            #     print(f"\n  [调试] lowestAverageRate keys: {list(first_lar.keys())}")
            #     print(f"  [调试] lowestAverageRate 全文: {json.dumps(first_lar, ensure_ascii=False)[:800]}")
            #     for key in first_lar:
            #         val = first_lar[key]
            #         if isinstance(val, dict) and "amount" in val:
            #             print(f"  [调试]   {key}.amount = {val['amount']} (decimalPoint={val.get('decimalPoint')})")
            #     parse_all_room_types._debug_printed = True

            for rate_item in node_rates:
                modes = rate_item.get("rateModes") or {}
                lar = modes.get("lowestAverageRate") or {}

                # totalAmount = 含所有费用和税的总价，amount = 税前基价
                amt_total = lar.get("totalAmount") or {}
                amt_base = lar.get("amount") or {}
                amt = amt_total if amt_total.get("amount") is not None else amt_base

                raw_amount = amt.get("amount")
                decimal_pt = amt.get("decimalPoint") or 0
                currency = amt.get("currency") or "CNY"

                if raw_amount is not None:
                    actual_price = raw_amount / (10 ** decimal_pt)
                else:
                    actual_price = None

                # 费率类别
                category = rate_item.get("rateCategory") or {}
                rate_plan = category.get("code") or category.get("value") or "标准价"
                if rate_plan == "StandardRates":
                    rate_plan = "标准价"
                rooms.append({
                    "name": "最低总价",
                    "price": actual_price,
                    "currency": currency,
                    "rate_plan": rate_plan,
                })
        elif room_types:
            for rt in room_types:
                room_name = rt.get("roomTypeName") or rt.get("roomName") or rt.get("name") or ""
                rt_rates = rt.get("rates") or []
                if not rt_rates:
                    price = rt.get("price") or rt.get("displayPrice")
                    if price:
                        rooms.append({
                            "name": room_name,
                            "price": price,
                            "currency": rt.get("currency") or "CNY",
                            "rate_plan": "标准价",
                        })
                else:
                    for rate in rt_rates:
                        price = rate.get("price") or rate.get("totalPrice") or rate.get("displayPrice")
                        rooms.append({
                            "name": room_name,
                            "price": price,
                            "currency": rate.get("currency") or "CNY",
                            "rate_plan": rate.get("ratePlanName") or rate.get("description") or "标准价",
                        })
        else:
            # ratePlans（旧格式）
            for rp in hotel.get("ratePlans") or []:
                rooms.append({
                    "name": rp.get("roomTypeName") or rp.get("roomName") or rp.get("description") or "",
                    "price": rp.get("totalPrice") or rp.get("price") or rp.get("displayPrice"),
                    "currency": rp.get("currency") or "CNY",
                    "rate_plan": rp.get("ratePlanName") or "标准价",
                })
            # lowestAvailableRate 兜底
            if not rooms:
                lar = hotel.get("lowestAvailableRate") or {}
                if lar:
                    price = lar.get("rate") or lar.get("price") or lar.get("totalPrice")
                    room_name = lar.get("roomTypeName") or lar.get("roomName") or "最低价"
                    if price:
                        rooms.append({
                            "name": room_name,
                            "price": price,
                            "currency": lar.get("currency") or lar.get("currencyCode") or "CNY",
                            "rate_plan": lar.get("ratePlanName") or "标准价",
                        })

        hotels_data.append({
            "hotel_id": hotel_id,
            "hotel_name": hotel_name,
            "latitude": lat,
            "longitude": lng,
            "rooms": rooms,
        })

    return hotels_data


if __name__ == "__main__":
    try:
        from datetime import date as _date_

        today = _date_.today().isoformat()
        print(f"今日日期: {today}")

        output_path = "marriott_shanghai_hotels.json"

        # 读取本地缓存（列表格式，每次抓取追加一条记录）
        records = []
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            # 兼容旧格式（单条 dict）和新格式（list）
            if isinstance(cached, list):
                records = cached
            elif isinstance(cached, dict):
                records = [cached]
        except (FileNotFoundError, json.JSONDecodeError):
            print("未找到有效缓存，将重新获取\n")

        # 检查是否需要重新获取：遍历所有记录找最大日期
        need_fetch = True
        max_date = "0000-00-00"
        for rec in records:
            for k in ("checkout_date", "checkin_date"):
                d = rec.get(k) or ""
                if d > max_date:
                    max_date = d
        print(f"本地缓存最大日期: {max_date}")
        if today < max_date:
            need_fetch = False
            print("今日数据已缓存，直接读取本地文件\n")

        if need_fetch:
            print("正在获取万豪上海酒店所有房型价格...")
            checkin = today
            from datetime import timedelta as _td_
            checkout = (_date_.today() + _td_(days=1)).isoformat()

            raw_data = get_shanghai_hotels(checkin, checkout)
            hotels_with_rooms = parse_all_room_types(raw_data)

            # 追加新记录
            records.append({
                "checkin_date": checkin,
                "checkout_date": checkout,
                "destination": "上海市",
                "hotels": hotels_with_rooms,
            })
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            print(f"已追加到 {output_path}（共 {len(records)} 条记录）")
        else:
            hotels_with_rooms = records[-1].get("hotels", []) if records else []

        print("\n=== 上海万豪酒店最低价格 ===")
        for hotel in hotels_with_rooms:
            print(f"\n  {hotel['hotel_name']} (ID: {hotel['hotel_id']})")
            if not hotel["rooms"]:
                print("    暂无房型信息")
            for room in hotel["rooms"]:
                price_str = f"{room['price']} {room['currency']}" if room["price"] else "价格未获取"
                print(f"    {room['name']} : {price_str} ({room['rate_plan']})")

    except Exception as e:
        print(f"运行出错：{e}")
