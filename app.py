from flask import Flask, request, jsonify
from datetime import datetime
import cloudscraper
import json
import os
import gzip
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BASE_URL  = "https://www.ivasms.com"
LOGIN_URL = "https://www.ivasms.com/login"
EMAIL     = os.getenv("IVAS_EMAIL",    "powerxdeveloper@gmail.com")
PASSWORD  = os.getenv("IVAS_PASSWORD", "Khang1.com")

# Hardcoded cookies - Android/Pydroid ke liye
COOKIES = {
    "ivas_sms_session": "eyJpdiI6Inh0VnpZQW9TZGY2U0psT1p3TGFObmc9PSIsInZhbHVlIjoieVplSGdDNDhQWEJISjh3aERSMFVPZnF4SFlEeTFaUGF2alpNc29TMWhMb21ZdHMxa1lCaExuVlh3czZQTEpjSkd0aHhsUmdZbDlRMFFLeTk3VmtoczErREEwL1dXOHhoUk1zWXRUZml0dlpaWHhIdm15aGJ5b1lMMGlmcVNKSzQiLCJtYWMiOiI5YWRkMzdlZmY3ODg2MDhjZGI4Y2VmMTI0ODFlMmY1MDJjODdmOGE0ZTk1NTBmZmJjNmQwNTI1YWE3MjllYjEzIiwidGFnIjoiIn0=",
    "XSRF-TOKEN": "eyJpdiI6IklkQ3JOZERERXpOWTE5d3FQSXd4Wnc9PSIsInZhbHVlIjoiZ3VuMk9PTXR1RlhMbVpZK1RMN1BIYXhrSTM5aXh4TStzQk1QZmZKbjhIZDI0aENQU3AwQ3JXdW5NbERmaUpqaFkrMW9UL0JhbzVFOXhTME1yTmp1UkFZRHhEaEpZRGJkRHRZZ2RaM0VPSFR2SjUvQkxucm9IUW1reTE4clBLSUoiLCJtYWMiOiJmNDg0ZTU1Y2MwMzhjZGZmMTIyNjA2ODQ5YjAxYjI3MzgwYjRlY2QwODVhMjBiMzA5NWI4MGI2M2Q1ZmQ3YTI0IiwidGFnIjoiIn0="
}


class IVASClient:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser':  'chrome',
                'platform': 'windows',
                'desktop':  True,
                'mobile':   False
            },
            delay=5
        )
        self.logged_in  = False
        self.csrf_token = None
        self._set_headers()

    def _set_headers(self):
        self.scraper.headers.update({
            "User-Agent":                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language":           "en-US,en;q=0.9",
            "Accept-Encoding":           "gzip, deflate, br",
            "Connection":                "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "sec-ch-ua":                 '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile":          "?0",
            "sec-ch-ua-platform":        '"Windows"',
            "Sec-Fetch-Dest":            "document",
            "Sec-Fetch-Mode":            "navigate",
            "Sec-Fetch-Site":            "none",
            "Sec-Fetch-User":            "?1",
            "Cache-Control":             "max-age=0",
        })

    def decompress(self, response):
        try:
            enc = response.headers.get("Content-Encoding", "").lower()
            if enc == "gzip":
                return gzip.decompress(response.content).decode("utf-8", errors="replace")
            try:
                import brotli
                if enc == "br":
                    return brotli.decompress(response.content).decode("utf-8", errors="replace")
            except:
                pass
        except:
            pass
        return response.text

    def login(self):
        logger.info("Login try kar raha hoon...")
        # Pehle cookies try karo
        if self._cookie_login():
            return True
        # Cookies fail ho gayi toh direct login try karo
        logger.info("Cookies fail - direct login try kar raha hoon...")
        return self._direct_login()

    def _cookie_login(self):
        """Cookie se login - Android/Pydroid ke liye"""
        try:
            logger.info("Cookie login try kar raha hoon...")
            # Pehle cookies.json file check karo
            cookies = None
            if os.getenv("COOKIES_JSON"):
                cookies = json.loads(os.getenv("COOKIES_JSON"))
                logger.debug("Cookies ENV se load ki")
            elif os.path.exists("cookies.json"):
                with open("cookies.json") as f:
                    cookies = json.load(f)
                logger.debug("Cookies file se load ki")
            else:
                cookies = COOKIES
                logger.debug("Hardcoded cookies use ho rahi hain")

            # Cookies set karo
            if isinstance(cookies, dict):
                for k, v in cookies.items():
                    self.scraper.cookies.set(k, v, domain="www.ivasms.com")
            elif isinstance(cookies, list):
                for c in cookies:
                    self.scraper.cookies.set(c["name"], c["value"], domain="www.ivasms.com")

            # Portal access karo
            resp = self.scraper.get(f"{BASE_URL}/portal/sms/received", timeout=30)
            html = self.decompress(resp)
            soup = BeautifulSoup(html, "html.parser")
            token = soup.find("input", {"name": "_token"})

            if token:
                self.csrf_token = token["value"]
                self.logged_in  = True
                logger.info("Cookie login successful!")
                return True
            else:
                logger.error("Cookies expired ya invalid!")
                return False
        except Exception as e:
            logger.error(f"Cookie login error: {e}")
            return False

    def _direct_login(self):
        """Direct email/password login - Vercel/Server ke liye"""
        try:
            resp = self.scraper.get(LOGIN_URL, timeout=30)
            logger.debug(f"Login page status: {resp.status_code}")

            if resp.status_code != 200:
                logger.error(f"Login page nahi mili: {resp.status_code}")
                return False

            html = self.decompress(resp)
            soup = BeautifulSoup(html, "html.parser")
            csrf = soup.find("input", {"name": "_token"})

            if not csrf:
                logger.error("CSRF token nahi mila!")
                return False

            self.scraper.headers.update({
                "Content-Type":   "application/x-www-form-urlencoded",
                "Referer":        LOGIN_URL,
                "Origin":         BASE_URL,
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-User": "?1",
                "Sec-Fetch-Dest": "document",
            })

            resp2 = self.scraper.post(
                LOGIN_URL,
                data={
                    "_token":   csrf["value"],
                    "email":    EMAIL,
                    "password": PASSWORD,
                },
                timeout=30,
                allow_redirects=True
            )

            logger.debug(f"Login response: {resp2.status_code} | URL: {resp2.url}")
            html2 = self.decompress(resp2)

            if "logout" in html2.lower() or "portal" in resp2.url or "dashboard" in resp2.url:
                soup2 = BeautifulSoup(html2, "html.parser")
                token = soup2.find("input", {"name": "_token"})

                if not token:
                    r3    = self.scraper.get(f"{BASE_URL}/portal/sms/received", timeout=30)
                    soup3 = BeautifulSoup(self.decompress(r3), "html.parser")
                    token = soup3.find("input", {"name": "_token"})

                if token:
                    self.csrf_token = token["value"]
                    self.logged_in  = True
                    logger.info("Direct login successful!")
                    return True

            logger.error("Direct login failed!")
            return False

        except Exception as e:
            logger.error(f"Direct login exception: {e}")
            return False

    def ensure_login(self):
        if not self.logged_in:
            return self.login()
        return True

    def post_ajax(self, url, data):
        self.scraper.headers.update({
            "Accept":             "text/html, */*; q=0.01",
            "Content-Type":       "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With":   "XMLHttpRequest",
            "Origin":             BASE_URL,
            "Referer":            f"{BASE_URL}/portal/sms/received",
            "Sec-Fetch-Site":     "same-origin",
            "Sec-Fetch-Mode":     "cors",
            "Sec-Fetch-Dest":     "empty",
        })
        return self.scraper.post(url, data=data, timeout=20)

    def check_otps(self, from_date="", to_date=""):
        try:
            resp = self.post_ajax(
                f"{BASE_URL}/portal/sms/received/getsms",
                {"from": from_date, "to": to_date, "_token": self.csrf_token}
            )
            if resp.status_code != 200:
                logger.error(f"check_otps: {resp.status_code}")
                return None

            soup = BeautifulSoup(self.decompress(resp), "html.parser")
            def t(s): return soup.select_one(s).text.strip() if soup.select_one(s) else "0"

            details = []
            for item in soup.select("div.item"):
                try:
                    cn   = item.select_one(".col-sm-4").text.strip()
                    cols = item.select(".col-3 p")
                    details.append({
                        "country_number": cn,
                        "count":          cols[0].text.strip() if cols else "0",
                        "paid":           cols[1].text.strip() if len(cols) > 1 else "0",
                        "unpaid":         cols[2].text.strip() if len(cols) > 2 else "0",
                    })
                except:
                    pass

            return {
                "count_sms":   t("#CountSMS"),
                "paid_sms":    t("#PaidSMS"),
                "unpaid_sms":  t("#UnpaidSMS"),
                "revenue":     t("#RevenueSMS").replace(" USD", ""),
                "sms_details": details,
            }
        except Exception as e:
            logger.error(f"check_otps error: {e}")
            return None

    def get_sms_details(self, phone_range, from_date, to_date):
        try:
            resp = self.post_ajax(
                f"{BASE_URL}/portal/sms/received/getsms/number",
                {"_token": self.csrf_token, "start": from_date, "end": to_date, "range": phone_range}
            )
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(self.decompress(resp), "html.parser")
            nums = []
            for item in soup.select("div.card.card-body"):
                try:
                    pn  = item.select_one(".col-sm-4").text.strip()
                    oc  = item.select_one(".col-sm-4").get("onclick", "")
                    idn = oc.split("'")[3] if oc and len(oc.split("'")) > 3 else ""
                    nums.append({"phone_number": pn, "id_number": idn})
                except:
                    pass
            return nums
        except:
            return []

    def get_otp_message(self, phone_number, phone_range, from_date, to_date):
        try:
            resp = self.post_ajax(
                f"{BASE_URL}/portal/sms/received/getsms/number/sms",
                {
                    "_token": self.csrf_token,
                    "start":  from_date,
                    "end":    to_date,
                    "Number": phone_number,
                    "Range":  phone_range,
                }
            )
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(self.decompress(resp), "html.parser")
            msg  = soup.select_one(".col-9.col-sm-6 p")
            return msg.text.strip() if msg else None
        except:
            return None

    def get_all_otps(self, sms_details, from_date, to_date, limit=None):
        all_otp = []
        for detail in sms_details:
            pr = detail["country_number"]
            for nd in self.get_sms_details(pr, from_date, to_date):
                if limit and len(all_otp) >= limit:
                    return all_otp
                msg = self.get_otp_message(nd["phone_number"], pr, from_date, to_date)
                if msg:
                    all_otp.append({
                        "range":        pr,
                        "phone_number": nd["phone_number"],
                        "otp_message":  msg,
                    })
        return all_otp

    def get_live_sms(self):
        try:
            self.scraper.headers.update({
                "Referer":        f"{BASE_URL}/portal",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
            })
            resp = self.scraper.get(f"{BASE_URL}/portal/live/my_sms", timeout=30)
            if resp.status_code != 200:
                return []

            soup     = BeautifulSoup(self.decompress(resp), "html.parser")
            messages = []

            rows = soup.select("table tbody tr")
            if rows:
                for row in rows:
                    cols = [td.text.strip() for td in row.find_all("td")]
                    if cols:
                        messages.append({"data": cols})

            if not messages:
                for card in soup.select(".sms-item,.message-item,.list-group-item"):
                    t = card.text.strip()
                    if t and len(t) > 5:
                        messages.append({"text": t[:300]})

            return messages
        except Exception as e:
            logger.error(f"live_sms error: {e}")
            return []


# Global client
client = IVASClient()


# =================== ROUTES ===================

@app.before_request
def init_client():
    """Har request se pehle login check karo"""
    if not client.logged_in:
        client.login()


@app.route("/")
def welcome():
    return jsonify({
        "message":      "IVAS SMS API",
        "status":       "alive ✅",
        "login_status": "logged_in ✅" if client.logged_in else "not logged in ❌",
        "developer":    "@ArslanMD Official",
        "endpoints": {
            "/status":                              "Login status check",
            "/sms?date=13/03/2026":                "OTP by date",              # ✅ SIRF YAHAN DATE CHANGED HUI
            "/sms?date=13/03/2026&limit=5":        "OTP with limit",           # ✅ SIRF YAHAN DATE CHANGED HUI
            "/sms?date=01/02/2026&to_date=28/02/2026": "OTP by date range",
            "/live":                                "Live SMS",
        }
    })


@app.route("/status")
def status():
    return jsonify({
        "logged_in":  client.logged_in,
        "csrf_token": "present ✅" if client.csrf_token else "missing ❌",
    })


@app.route("/sms")
def get_sms():
    date_str = request.args.get("date")
    to_date  = request.args.get("to_date", "")
    limit    = request.args.get("limit")

    if not date_str:
        return jsonify({"error": "date required. Format: DD/MM/YYYY"}), 400

    try:
        datetime.strptime(date_str, "%d/%m/%Y")
        if to_date:
            datetime.strptime(to_date, "%d/%m/%Y")
    except:
        return jsonify({"error": "Invalid date format. Use DD/MM/YYYY"}), 400

    if limit:
        try:
            limit = int(limit)
            if limit <= 0:
                return jsonify({"error": "limit must be positive"}), 400
        except:
            return jsonify({"error": "limit must be integer"}), 400
    else:
        limit = None

    if not client.logged_in:
        if not client.login():
            return jsonify({"error": "Login failed - check credentials"}), 401

    result = client.check_otps(from_date=date_str, to_date=to_date)
    if not result:
        # Re-login try karo
        client.logged_in = False
        if client.login():
            result = client.check_otps(from_date=date_str, to_date=to_date)
    if not result:
        return jsonify({"error": "Failed to fetch data from IVAS"}), 500

    otps = client.get_all_otps(result["sms_details"], date_str, to_date, limit)

    return jsonify({
        "status":    "success",
        "from_date": date_str,
        "to_date":   to_date or "Not specified",
        "limit":     limit if limit is not None else "Not specified",
        "sms_stats": {
            "count_sms":  result["count_sms"],
            "paid_sms":   result["paid_sms"],
            "unpaid_sms": result["unpaid_sms"],
            "revenue":    result["revenue"],
        },
        "otp_messages": otps,
    })


@app.route("/live")
def live_sms():
    if not client.logged_in:
        if not client.login():
            return jsonify({"error": "Login failed"}), 401

    messages = client.get_live_sms()
    return jsonify({
        "status":   "success",
        "count":    len(messages),
        "messages": messages,
    })


# Vercel ke liye zaroori
application = app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
