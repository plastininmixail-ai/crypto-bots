import requests
import time
import hmac
import hashlib
import json
import logging
from pathlib import Path
from urllib.parse import urlencode, quote

# === НАСТРОЙКИ ===
API_KEY = "tw4LSsmbJRPV3yfBer"
API_SECRET = "IChQQftqlIhm8hHdmM4C8QbJ0yMS2cP2vVrX"
BASE_URL = "https://api.bybit.com"

STOP_LOSS_PCT = 0.3
TAKE_PROFIT_PCT = None  # TP НЕ ставим - Signal Inverter уже выставил 3%
CHECK_INTERVAL = 30

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(Path(r"C:\Users\79245\.openclaw\workspace\stop_loss_manager.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

_offset = [0]

def get_offset():
    try:
        r = requests.get(BASE_URL + '/v5/market/time', timeout=5)
        server_ts = int(r.json().get('result', {}).get('timeNano', 0)) // 1_000_000
        _offset[0] = int(time.time() * 1000) - server_ts
        return _offset[0]
    except:
        return _offset[0]

def sign(ts, rw, payload_str):
    """HMAC-SHA256"""
    return hmac.new(API_SECRET.encode(), f"{ts}{API_KEY}{rw}{payload_str}".encode(), hashlib.sha256).hexdigest()

def api_request(method, endpoint, params=None):
    params = params or {}
    ts = str(int(time.time() * 1000) - get_offset())
    rw = '10000'
    
    if method == 'GET':
        # Для GET: payload = простой sorted query string (без URL-encoding для подписи)
        payload_parts = []
        for k, v in sorted(params.items()):
            if v is not None:
                payload_parts.append(f'{k}={v}')
        payload_str = '&'.join(payload_parts)
    else:
        # Для POST: payload = JSON string
        payload_str = json.dumps(params)
    
    sig = sign(ts, rw, payload_str)
    
    headers = {
        'X-BAPI-API-KEY': API_KEY,
        'X-BAPI-TIMESTAMP': ts,
        'X-BAPI-RECV-WINDOW': rw,
        'X-BAPI-SIGN': sig
    }
    
    if method == 'GET':
        r = requests.get(BASE_URL + endpoint, headers=headers, params=params, timeout=10)
    else:
        r = requests.post(BASE_URL + endpoint, headers=headers, json=params, timeout=10)
    
    return r.json()

def get_open_positions():
    # Без курсора - просто берём до 200 позиций
    params = {'category': 'linear', 'settleCoin': 'USDT'}
    r = api_request('GET', '/v5/position/list', params)
    if r.get('retCode') != 0:
        logger.error(f"Ошибка позиций: {r.get('retMsg', '')}")
        return []
    positions = r.get('result', {}).get('list', [])
    return [p for p in positions if float(p.get('size', 0)) > 0]

def set_stop(symbol, sl_price, tp_price, side, position_idx):
    body = {
        'category': 'linear',
        'symbol': symbol,
        'positionIdx': position_idx,
        'stopLoss': str(round(sl_price, 6))
    }
    if tp_price:
        body['takeProfit'] = str(round(tp_price, 6))
    
    r = api_request('POST', '/v5/position/trading-stop', body)
    rc = r.get('retCode')
    if rc == 0:
        logger.info(f">>> {symbol}: SL={sl_price}, TP={tp_price} OK")
    elif rc in (10003, 34040):
        logger.info(f">>> {symbol}: uzhe ustanovlen")
    else:
        logger.warning(f">>> {symbol}: {r.get('retMsg', '')}")
    return rc

def process():
    positions = get_open_positions()
    if not positions:
        logger.info("Открытых позиций нет")
        return
    
    logger.info(f"Открытых: {len(positions)}")
    for pos in positions:
        sym = pos.get('symbol', '')
        side = pos.get('side', '')
        entry = float(pos.get('avgPrice', 0) or pos.get('markPrice', 0))
        curr = float(pos.get('markPrice', 0))
        
        if entry <= 0:
            logger.warning(f"{sym}: net tseny, propusk")
            continue
        
        # Определяем positionIdx для hedge mode
        pidx = 1 if side == 'Buy' else 2
        
        # Вычисляем уровни
        # Для Buy: SL ниже цены (от мин. из entry/current)
        # Для Sell: SL выше цены (от макс. из entry/current)
        if side == 'Buy':
            ref_price = min(entry, curr) if curr > 0 else entry
            sl = round(ref_price * (1 - STOP_LOSS_PCT / 100), 6)
            tp = round(entry * (1 + TAKE_PROFIT_PCT / 100), 6) if TAKE_PROFIT_PCT else None
        else:
            ref_price = max(entry, curr) if curr > 0 else entry
            sl = round(ref_price * (1 + STOP_LOSS_PCT / 100), 6)
            tp = round(entry * (1 - TAKE_PROFIT_PCT / 100), 6) if TAKE_PROFIT_PCT else None
        
        logger.info(f"{sym}: {side} entry={entry} curr={curr} SL={sl} TP={tp}")
        set_stop(sym, sl, tp, side, pidx)

if __name__ == '__main__':
    print("Stop Loss Manager v1.3 - запущен")
    print(f"SL: {STOP_LOSS_PCT}%, TP: не ставим (Signal Inverter уже выставил 3%)")
    get_offset()
    print(f"Clock offset: {_offset[0]}ms")
    print()
    process()
