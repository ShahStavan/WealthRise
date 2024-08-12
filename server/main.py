from flask import Flask, jsonify
from flask_cors import CORS
import asyncio
import aiohttp
import requests
import json
import math
import time
from datetime import datetime
from threading import Thread

app = Flask(__name__)
CORS(app)

# Utility Functions
def round_nearest(x, num=50): return int(math.ceil(float(x)/num)*num)
def nearest_strike_bnf(x): return round_nearest(x, 100)
def nearest_strike_nf(x): return round_nearest(x, 50)

url_oc = "https://www.nseindia.com/option-chain"
url_bnf = 'https://www.nseindia.com/api/option-chain-indices?symbol=BANKNIFTY'
url_nf = 'https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY'
url_indices = "https://www.nseindia.com/api/allIndices"

headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36',
    'accept-language': 'en,gu;q=0.9,hi;q=0.8',
    'accept-encoding': 'gzip, deflate, br'
}

cookies = dict()

# Global Variables to Store Data
nifty_data = {}
bank_nifty_data = {}

def set_cookie():
    sess = requests.Session()
    request = sess.get(url_oc, headers=headers, timeout=5)
    return dict(request.cookies)

async def get_data(url, session):
    global cookies
    async with session.get(url, headers=headers, timeout=5, cookies=cookies) as response:
        if response.status == 401:
            cookies = set_cookie()
            async with session.get(url, headers=headers, timeout=5, cookies=cookies) as response:
                return await response.text()
        elif response.status == 200:
            return await response.text()
        return ""

async def fetch_all_data():
    async with aiohttp.ClientSession() as session:
        indices_data = await get_data(url_indices, session)
        bnf_data = await get_data(url_bnf, session)
        nf_data = await get_data(url_nf, session)
    return indices_data, bnf_data, nf_data

def process_indices_data(data):
    global bnf_ul, nf_ul, bnf_nearest, nf_nearest
    data = json.loads(data)
    for index in data["data"]:
        if index["index"] == "NIFTY 50":
            nf_ul = index["last"]
        if index["index"] == "NIFTY BANK":
            bnf_ul = index["last"]
    bnf_nearest = nearest_strike_bnf(bnf_ul)
    nf_nearest = nearest_strike_nf(nf_ul)

def process_oi_data(data, nearest, step, num):
    data = json.loads(data)
    currExpiryDate = data["records"]["expiryDates"][0]
    oi_data = []
    for item in data['records']['data']:
        if item["expiryDate"] == currExpiryDate:
            if nearest - step*num <= item["strikePrice"] <= nearest + step*num:
                oi_data.append({
                    "strikePrice": item["strikePrice"],
                    "CE_openInterest": item["CE"]["openInterest"],
                    "CE_changeInOI": item["CE"]["changeinOpenInterest"],
                    "CE_volume": item["CE"]["totalTradedVolume"],
                    "CE_IV": item["CE"]["impliedVolatility"],
                    "PE_openInterest": item["PE"]["openInterest"],
                    "PE_changeInOI": item["PE"]["changeinOpenInterest"],
                    "PE_volume": item["PE"]["totalTradedVolume"],
                    "PE_IV": item["PE"]["impliedVolatility"]
                })
    return oi_data

def calculate_support_resistance(oi_data):
    highest_oi_ce = max(oi_data, key=lambda x: x["CE_openInterest"])
    highest_oi_pe = max(oi_data, key=lambda x: x["PE_openInterest"])
    return highest_oi_ce["strikePrice"], highest_oi_pe["strikePrice"]

async def update_data():
    global nifty_data, bank_nifty_data, cookies

    while True:
        cookies = set_cookie()
        indices_data, bnf_data, nf_data = await fetch_all_data()
        
        process_indices_data(indices_data)

        nifty_oi_data = process_oi_data(nf_data, nf_nearest, 50, 10)
        bank_nifty_oi_data = process_oi_data(bnf_data, bnf_nearest, 100, 10)

        nifty_support, nifty_resistance = calculate_support_resistance(nifty_oi_data)
        bank_nifty_support, bank_nifty_resistance = calculate_support_resistance(bank_nifty_oi_data)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        nifty_data = {
            "timestamp": timestamp,
            "support": nifty_support,
            "resistance": nifty_resistance,
            "oi_data": nifty_oi_data
        }

        bank_nifty_data = {
            "timestamp": timestamp,
            "support": bank_nifty_support,
            "resistance": bank_nifty_resistance,
            "oi_data": bank_nifty_oi_data
        }

        await asyncio.sleep(30)  # Fetch data every 30 seconds

def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(update_data())

@app.route('/nifty', methods=['GET'])
def get_nifty_data():
    return jsonify(nifty_data)

@app.route('/banknifty', methods=['GET'])
def get_bank_nifty_data():
    return jsonify(bank_nifty_data)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    t = Thread(target=start_background_loop, args=(loop,))
    t.start()
    app.run(debug=True, use_reloader=False)
