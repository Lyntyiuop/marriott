import json
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

# 修复 Windows 上 GC 回收 Chrome 对象时重复 quit() 导致 OSError 的问题
_del = uc.Chrome.__del__
def _patched_del(self):
    try:
        _del(self)
    except OSError:
        pass
uc.Chrome.__del__ = _patched_del


def get_china_hotels(checkin_date="2026-05-23", checkout_date="2026-05-24", destination="中国"):
    """获取万豪中国酒店列表及所有房型价格"""

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
        state_param = 'CN-Shanghai' if destination == "上海市" else ""
        search_url = (
            "https://www.marriott.com.cn/search/findHotels.mi"
            f"?fromDate={checkin_date}"
            f"&toDate={checkout_date}"
            f"&destinationAddress.destination={destination}"
            "&roomCount=1"
            "&numAdultsPerRoom=1"
            "&marriottBrands=EB,RZ,LC,XR,WH,JW,BG,MC,SI,DE,WI,MD,BR,DS,TX" # 详见万豪品牌id.md
            f"&states={state_param}" # 酒店所在省
        )

        print("正在加载搜索页面...")
        driver.get(search_url)
        time.sleep(2)

        # ========== 2. 处理 Cookie 同意弹窗（OneTrust otCenterRounded 模板） ==========
        count = 0
        while True:
            cookie_dismissed = driver.execute_script("""
                // 优先使用 OneTrust 专用按钮 ID
                const btn = document.querySelector('#onetrust-accept-btn-handler');
                if (btn) { btn.click(); return 'id'; }
                // 兜底：OneTrust JS API
                if (typeof Optanon !== 'undefined' && typeof Optanon.AcceptAll === 'function') {
                    Optanon.AcceptAll();
                    return 'api';
                }
                return false;
            """)
            if cookie_dismissed:
                print(f"  已关闭 Cookie 弹窗（{cookie_dismissed}）")
                break
            count += 1
            if count >= 5:
                print("❌ 未找到 Cookie 同意按钮")
                break

        # ========== 3. 点击搜索按钮 ==========
        count = 0
        while True:
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
                break
            else:
                count += 1
                time.sleep(1)
                if count >= 10:
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

        if result:
            if isinstance(result, list):
                return {"hotels": result}
            return result

        raise RuntimeError("超时未找到酒店数据，请检查 API 结构是否变化，或增加等待时间")

    finally:
        try:
            driver.quit()
        except Exception:
            pass


def parse_all_room_types(api_response):
    """从 API 返回的 JSON 中提取每个酒店的所有房型及价格"""
    hotels_data = []
    hotel_list = []

    hotel_list = api_response.get("hotels")

    for hotel in hotel_list:
        # ---- GraphQL node 格式：{property: {...}, rates: [...]} ----
        prop = hotel.get("property") or {}
        info = prop.get("basicInformation") or {}
        hotel_id = prop.get("id") or ""
        hotel_name = info.get("name") or ""
        hotel_name_en = info.get("nameInDefaultLanguage") or ""
        info_brand = info.get("brand") or {}
        hotel_brand = info_brand.get("name") or ""
        open_date = info.get("openingDate") or ""
        lat = prop.get("latitude") or ""
        lng = prop.get("longitude") or ""

        rooms = []

        for rate_item in hotel.get("rates") or []:
            modes = rate_item.get("rateModes") or {}
            lar = modes.get("lowestAverageRate") or {}

            # totalAmount = 含所有费用和税的总价
            amt_total = lar.get("totalAmount") or {}
            raw_amount = amt_total.get("amount")
            decimal_pt = amt_total.get("decimalPoint")
            currency = amt_total.get("currency")
            actual_price = raw_amount / (10 ** decimal_pt)

            # 费率类别
            category = rate_item.get("rateCategory") or {}
            rate_plan = category.get("code")
            if rate_plan == "StandardRates":
                rate_plan = "标准价"
            rooms.append({
                "name": "最低含税价",
                "price": actual_price,
                "currency": currency,
                "rate_plan": rate_plan,
            })

        hotels_data.append({
            "hotel_id": hotel_id,
            "hotel_name": hotel_name,
            "hotel_name_en": hotel_name_en,
            "hotel_brand": hotel_brand,
            "opening_date": open_date,
            "latitude": lat,
            "longitude": lng,
            "rooms": rooms,
        })

    return hotels_data


PROVINCES = [
    ("上海市", "shanghai"),
    ("北京市", "beijing"),
    ("天津市", "tianjin"),
    ("重庆市", "chongqing"),
    ("河北省", "hebei"),
    ("山西省", "shanxi"),
    ("内蒙古自治区", "neimenggu"),
    ("辽宁省", "liaoning"),
    ("吉林省", "jilin"),
    ("黑龙江省", "heilongjiang"),
    ("江苏省", "jiangsu"),
    ("浙江省", "zhejiang"),
    ("安徽省", "anhui"),
    ("福建省", "fujian"),
    ("江西省", "jiangxi"),
    ("山东省", "shandong"),
    ("河南省", "henan"),
    ("湖北省", "hubei"),
    ("湖南省", "hunan"),
    ("广东省", "guangdong"),
    ("广西壮族自治区", "guangxi"),
    ("海南省", "hainan"),
    ("四川省", "sichuan"),
    # ("贵州省", "guizhou"),
    ("云南省", "yunnan"),
    ("西藏自治区", "xizang"),
    ("陕西省", "shaanxi"),
    ("甘肃省", "gansu"),
    # ("青海省", "qinghai"),
    ("宁夏回族自治区", "ningxia"),
    ("新疆维吾尔自治区", "xinjiang"),
    ("香港特别行政区", "hongkong"),
    ("澳门特别行政区", "macau"),
    ("台湾省", "taiwan"),
]

if __name__ == "__main__":
    from datetime import date, timedelta, datetime

    today = date.today()
    checkin = today.isoformat()
    checkout = (today + timedelta(days=1)).isoformat()
    print(f"记录时间：{datetime.now().isoformat()}")
    print(f"入住日期：{checkin} → {checkout}")

    for destination, destination_en in PROVINCES:
        output_path = f"data/marriott_{destination_en}_hotels.json"
        print(f"\n{'='*50}")
        print(f"正在获取万豪{destination}各酒店最低价...")

        try:
            raw_data = get_china_hotels(checkin, checkout, destination)
            hotels_with_rooms = parse_all_room_types(raw_data)

            record = {
                "record_time": datetime.now().isoformat(),
                "checkin_date": checkin,
                "checkout_date": checkout,
                "destination": destination,
                "hotels": hotels_with_rooms,
            }

            with open(output_path, "a", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            print(f"  ✓ {destination}: {len(hotels_with_rooms)} 家酒店，已保存到 {output_path}")

        except Exception as e:
            print(f"  ✗ {destination}: 获取失败 - {e}")
