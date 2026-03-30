"""
Signal Inverter - инвертирует TradingView для Cryptorg
Меняет strategy: long <-> short
Меняет TP: 1% -> 3% (для инвертированных сделок)
SL ставит stop_loss_manager (0.3%)
"""
from flask import Flask, request, jsonify
import requests
import json
from datetime import datetime

app = Flask(__name__)

CRYPTORG_WEBHOOK_URL = "https://api3.cryptorg.net/crazy/hook/495554319:8C3-EFEIZUxqEDKW-31aDAb9iLF2LdnP12bZW5L3ffSd17s3f"


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    
    if not data:
        return jsonify({"error": "No data"}), 400
    
    action = data.get('action', '').lower()
    if not action:
        return jsonify({"error": "No action"}), 400
    
    # Строим cryptorg_data
    cryptorg_data = {"action": action}
    
    if 'params' in data:
        params = data.get('params', {}).copy()
        
        # Инвертируем strategy: long -> short, short -> long
        strategy = params.get('strategy', '').lower()
        if strategy == 'long':
            params['strategy'] = 'short'
        elif strategy == 'short':
            params['strategy'] = 'long'
        
        # Оригинальные настройки
        if 'open' in params:
            params['open']['leverage'] = 10
            params['open']['orderVolume'] = "10"

        # Меняем TP и SL в структуре close/stop
        # TP: close.value (1% -> 3%)
        # SL: stop.value (0.5% -> 0.3%)
        if 'close' in params and params['close'].get('event') == 'percentage':
            old_tp = params['close'].get('value', '0')
            try:
                old_tp_float = float(old_tp)
                if old_tp_float > 0:
                    params['close']['value'] = '3'
                    with open('C:/Users/79245/.openclaw/workspace/tp_change_log.txt', 'a') as log:
                        log.write(f"{datetime.now()} | TP changed: {old_tp} -> 3.0\n")
            except:
                pass

        if 'stop' in params and params['stop'].get('event') == 'percentage':
            old_sl = params['stop'].get('value', '0')
            try:
                old_sl_float = float(old_sl)
                if old_sl_float > 0:
                    params['stop']['value'] = '0.3'
                    with open('C:/Users/79245/.openclaw/workspace/sl_change_log.txt', 'a') as log:
                        log.write(f"{datetime.now()} | SL changed: {old_sl} -> 0.3\n")
            except:
                pass

        cryptorg_data["params"] = params
    
    # Логируем
    with open('C:/Users/79245/.openclaw/workspace/webhook_log.txt', 'a') as f:
        f.write(f"\n{datetime.now()} | RECEIVED: {json.dumps(data)}\n")
        f.write(f"{datetime.now()} | SENDING: {json.dumps(cryptorg_data)}\n")
    
    # Отправляем в Cryptorg
    try:
        response = requests.post(CRYPTORG_WEBHOOK_URL, json=cryptorg_data)
        return jsonify({
            "status": "ok",
            "strategy_inverted": True,
            "cryptorg_response": response.status_code
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
