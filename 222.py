#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coin Wallet - XODE 轻量级钱包客户端
功能：
  1. 自动向主节点注册并维持心跳（参与区块奖励分配）
  2. 本地安全存储私钥，支持离线复活
  3. 内置 Web 界面，浏览器即可完成转账、查询
  4. 自动同步主节点手续费
"""
import hashlib
import json
import requests
import argparse
import threading
import time
import os
from time import time as now
from flask import Flask, request, jsonify, render_template_string
from ecdsa import SigningKey, SECP256k1

# ---------------- 配置 ----------------
MAIN_NODE = "62.234.183.74:9753"  # 主节点地址
HEARTBEAT_INTERVAL = 75           # 心跳间隔（秒）
KEY_FILE = "wallet_key.json"      # 本地密钥文件

# ---------------- HTML 模板（Coin Wallet 界面）----------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Coin Wallet - XODE</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif; 
            background: linear-gradient(135deg, #1a2a6c 0%, #b21f1f 50%, #fdbb2d 100%); 
            min-height: 100vh; color: #333; padding: 20px; 
        }
        .container { max-width: 1200px; margin: 0 auto; }
        header { text-align: center; color: white; margin-bottom: 30px; padding: 20px; }
        .logo { font-size: 2.8em; font-weight: bold; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); margin-bottom: 10px; }
        .subtitle { opacity: 0.95; font-size: 1em; letter-spacing: 1px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
        .card { 
            background: rgba(255,255,255,0.95); border-radius: 20px; padding: 28px; 
            box-shadow: 0 15px 35px rgba(0,0,0,0.2); backdrop-filter: blur(10px);
            transition: transform 0.3s;
        }
        .card:hover { transform: translateY(-5px); box-shadow: 0 20px 40px rgba(0,0,0,0.3); }
        .card-title { 
            font-size: 0.9em; color: #555; text-transform: uppercase; letter-spacing: 2px; 
            margin-bottom: 14px; display: flex; align-items: center; gap: 8px; font-weight: bold;
        }
        .balance-display { 
            font-size: 3.2em; font-weight: bold; color: #1a2a6c; margin: 15px 0; 
            font-family: 'Courier New', monospace; text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
        }
        .address-box { 
            background: #f0f4f8; padding: 14px; border-radius: 10px; font-family: monospace; 
            font-size: 0.9em; word-break: break-all; display: flex; justify-content: space-between; 
            align-items: center; gap: 10px; border: 2px solid #e1e8ed;
        }
        .btn { 
            background: #1a2a6c; color: white; border: none; padding: 10px 20px; border-radius: 8px; 
            cursor: pointer; font-size: 0.9em; transition: all 0.3s; font-weight: 600;
        }
        .btn:hover { background: #b21f1f; transform: scale(1.05); box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
        .btn-secondary { background: #6c757d; }
        .btn-secondary:hover { background: #5a6268; }
        .form-group { margin-bottom: 18px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: #444; font-size: 0.95em; }
        input[type="text"], input[type="number"] { 
            width: 100%; padding: 14px; border: 2px solid #ddd; border-radius: 10px; 
            font-size: 1em; transition: all 0.3s; background: #fafafa;
        }
        input:focus { outline: none; border-color: #b21f1f; background: white; box-shadow: 0 0 0 3px rgba(178,31,31,0.1); }
        .btn-submit { 
            width: 100%; padding: 16px; background: linear-gradient(135deg, #1a2a6c 0%, #b21f1f 100%); 
            color: white; border: none; border-radius: 10px; font-size: 1.2em; font-weight: bold; 
            cursor: pointer; transition: all 0.3s; text-transform: uppercase; letter-spacing: 1px;
        }
        .btn-submit:hover { opacity: 0.95; transform: translateY(-2px); box-shadow: 0 10px 25px rgba(178,31,31,0.3); }
        .btn-submit:disabled { background: #ccc; cursor: not-allowed; opacity: 0.6; transform: none; }
        .tx-list { max-height: 500px; overflow-y: auto; }
        .tx-item { 
            padding: 14px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; 
            align-items: center; transition: all 0.2s; border-radius: 8px; margin-bottom: 4px;
        }
        .tx-item:hover { background: #f8f9fa; transform: translateX(5px); }
        .tx-item:last-child { border-bottom: none; }
        .tx-type { padding: 5px 10px; border-radius: 20px; font-size: 0.75em; font-weight: bold; }
        .tx-in { background: #d4edda; color: #155724; }
        .tx-out { background: #f8d7da; color: #721c24; }
        .tx-pending { background: #fff3cd; color: #856404; }
        .tx-amount { font-weight: bold; font-family: monospace; font-size: 1.1em; }
        .tx-amount.out { color: #dc3545; }
        .tx-amount.in { color: #28a745; }
        .status-bar { 
            position: fixed; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.85); color: white; 
            padding: 14px; display: flex; justify-content: space-between; align-items: center; 
            font-size: 0.9em; backdrop-filter: blur(10px);
        }
        .status-indicator { display: flex; align-items: center; gap: 8px; }
        .dot { width: 10px; height: 10px; border-radius: 50%; background: #28a745; animation: pulse 2s infinite; }
        .dot.offline { background: #dc3545; animation: none; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        .toast { 
            position: fixed; top: 20px; right: 20px; background: white; padding: 20px; border-radius: 12px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.3); display: none; animation: slideIn 0.4s; z-index: 1000; max-width: 350px;
        }
        .toast.show { display: block; }
        .toast.success { border-left: 5px solid #28a745; }
        .toast.error { border-left: 5px solid #dc3545; }
        @keyframes slideIn { from { transform: translateX(100%) scale(0.9); opacity: 0; } to { transform: translateX(0) scale(1); opacity: 1; } }
        .loading { 
            display: inline-block; width: 20px; height: 20px; border: 3px solid #f3f3f3; 
            border-top: 3px solid #b21f1f; border-radius: 50%; animation: spin 1s linear infinite; 
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-top: 20px; }
        .stat-box { text-align: center; padding: 15px; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); border-radius: 12px; }
        .stat-value { font-size: 1.6em; font-weight: bold; color: #1a2a6c; }
        .stat-label { font-size: 0.8em; color: #666; margin-top: 6px; font-weight: 600; }
        .wallet-tag { 
            display: inline-block; background: rgba(26,42,108,0.1); color: #1a2a6c; padding: 4px 12px; 
            border-radius: 20px; font-size: 0.8em; margin-left: 10px; font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">💰 Coin Wallet <span class="wallet-tag">XODE</span></div>
            <div class="subtitle">去中心化轻钱包 | 自动分奖 | 本地私钥保护</div>
        </header>
        <div class="grid">
            <div class="left-panel">
                <div class="card">
                    <div class="card-title">💎 我的资产</div>
                    <div class="balance-display" id="balance">--</div>
                    <div class="address-box">
                        <span id="address">加载中...</span>
                        <button class="btn" onclick="copyAddress()">📋 复制</button>
                    </div>
                    <div class="stats-grid">
                        <div class="stat-box"><div class="stat-value" id="txCount">--</div><div class="stat-label">交易数</div></div>
                        <div class="stat-box"><div class="stat-value" id="nodeCount">--</div><div class="stat-label">在线节点</div></div>
                        <div class="stat-box"><div class="stat-value" id="blockHeight">--</div><div class="stat-label">区块高度</div></div>
                    </div>
                </div>
                <div class="card" style="margin-top: 20px;">
                    <div class="card-title">🚀 转账汇款</div>
                    <form id="sendForm" onsubmit="sendTransaction(event)">
                        <div class="form-group">
                            <label>接收地址 (coin开头)</label>
                            <input type="text" id="recipient" placeholder="coin..." required>
                        </div>
                        <div class="form-group">
                            <label>转账金额 (XODE)</label>
                            <input type="number" id="amount" step="0.000001" min="0.000001" placeholder="0.00" required>
                        </div>
                        <div class="form-group">
                            <label>网络手续费 (默认 2.0)</label>
                            <input type="number" id="fee" step="0.1" min="0.1" value="2.0">
                        </div>
                        <button type="submit" class="btn-submit" id="sendBtn">✈️ 确认转账</button>
                    </form>
                </div>
            </div>
            <div class="right-panel">
                <div class="card" style="height: 100%; min-height: 500px;">
                    <div class="card-title" style="display: flex; justify-content: space-between;">
                        <span>📜 交易明细</span>
                        <button class="btn btn-secondary" onclick="refreshData()">🔄 刷新</button>
                    </div>
                    <div id="txList" class="tx-list"><div style="text-align: center; padding: 40px; color: #999;">加载中...</div></div>
                </div>
            </div>
        </div>
    </div>
    <div class="status-bar">
        <div class="status-indicator"><div class="dot" id="statusDot"></div><span id="statusText">正在连接网络...</span></div>
        <div>主节点: {{ main_node }} | 钱包服务: 127.0.0.1:{{ port }}</div>
    </div>
    <div id="toast" class="toast">
        <div id="toastTitle" style="font-weight: bold; margin-bottom: 6px; font-size: 1.1em;"></div>
        <div id="toastMessage" style="font-size: 0.95em; color: #555;"></div>
    </div>
    <script>
        let myAddress = '';
        let refreshInterval;
        window.onload = function() { initData(); refreshInterval = setInterval(refreshData, 30000); };
        function showToast(title, message, type = 'success') {
            const toast = document.getElementById('toast');
            document.getElementById('toastTitle').textContent = title;
            document.getElementById('toastMessage').textContent = message;
            toast.className = 'toast show ' + type;
            setTimeout(() => { toast.classList.remove('show'); }, 4000);
        }
        async function initData() {
            try {
                const status = await fetch('/api/status').then(r => r.json());
                if (status.code === 200) {
                    myAddress = status.coin_addr;
                    document.getElementById('address').textContent = myAddress;
                    updateStatus(true);
                }
                await refreshData();
            } catch (e) { showToast('连接失败', '无法连接到 Coin Wallet 服务', 'error'); updateStatus(false); }
        }
        async function refreshData() {
            try {
                const [balanceRes, historyRes, chainRes] = await Promise.all([
                    fetch('/api/balance').then(r => r.json()),
                    fetch('/api/history').then(r => r.json()),
                    fetch('/api/chain/stats').then(r => r.json())
                ]);
                if (balanceRes.code === 200) document.getElementById('balance').textContent = parseFloat(balanceRes.balance).toFixed(6);
                if (chainRes.code === 200) {
                    document.getElementById('nodeCount').textContent = chainRes.stats.total_online_nodes;
                    document.getElementById('blockHeight').textContent = chainRes.stats.latest_block_height;
                }
                if (historyRes.code === 200) {
                    renderTxList(historyRes.transactions || []);
                    document.getElementById('txCount').textContent = historyRes.total_transactions || 0;
                }
                updateStatus(true);
            } catch (e) { console.error('刷新失败:', e); updateStatus(false); }
        }
        function renderTxList(transactions) {
            const list = document.getElementById('txList');
            if (!transactions || transactions.length === 0) { list.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;"><p>暂无交易记录</p><p style="font-size: 0.9em; margin-top: 10px;">转账后将在此显示</p></div>'; return; }
            list.innerHTML = transactions.map(tx => {
                const isOut = tx.type === 'outgoing', isPending = tx.status === 'pending';
                const typeClass = isPending ? 'tx-pending' : (isOut ? 'tx-out' : 'tx-in');
                const typeText = isPending ? '确认中' : (isOut ? '转出' : '转入');
                const amountClass = isOut ? 'out' : 'in';
                const sign = isOut ? '-' : '+';
                const counterparty = isOut ? '→ ' + tx.counterparty.substring(0, 14) + '...' : '← ' + tx.counterparty.substring(0, 14) + '...';
                return `<div class="tx-item"><div><span class="tx-type ${typeClass}">${typeText}</span><div style="margin-top: 6px; font-size: 0.9em; color: #555; font-weight: 500;">${counterparty}</div><div style="font-size: 0.8em; color: #999; margin-top: 4px;">${new Date(tx.timestamp * 1000).toLocaleString()}</div></div><div class="tx-amount ${amountClass}">${sign}${parseFloat(tx.amount).toFixed(2)}</div></div>`;
            }).join('');
        }
        async function sendTransaction(e) {
            e.preventDefault();
            const btn = document.getElementById('sendBtn'), originalText = btn.textContent;
            const recipient = document.getElementById('recipient').value, amount = parseFloat(document.getElementById('amount').value), fee = parseFloat(document.getElementById('fee').value);
            if (!recipient.startsWith('coin') || recipient.length !== 20) { showToast('地址格式错误', '请输入有效的 coin 开头地址', 'error'); return; }
            if (amount <= 0) { showToast('金额错误', '转账金额必须大于 0', 'error'); return; }
            if (fee < 0.1) { showToast('手续费过低', '手续费至少 0.1 XODE', 'error'); return; }
            btn.disabled = true; btn.innerHTML = '<div class="loading" style="width: 18px; height: 18px; border-width: 2px; margin-right: 8px;"></div> 处理中...';
            try {
                const res = await fetch('/api/send', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({recipient, amount, fee}) }).then(r => r.json());
                if (res.code === 201) { showToast('转账成功！', `交易ID: ${res.txid.substring(0, 16)}...`, 'success'); document.getElementById('sendForm').reset(); setTimeout(refreshData, 1500); }
                else { showToast('转账失败', res.error || '请检查余额或网络', 'error'); }
            } catch (e) { showToast('网络错误', '无法连接到钱包服务', 'error'); }
            finally { btn.disabled = false; btn.innerHTML = originalText; }
        }
        function copyAddress() { navigator.clipboard.writeText(myAddress).then(() => { showToast('已复制', '钱包地址已复制到剪贴板'); }); }
        function updateStatus(online) {
            const dot = document.getElementById('statusDot'), text = document.getElementById('statusText');
            if (online) { dot.classList.remove('offline'); text.textContent = '已连接 | 在线挖矿中'; }
            else { dot.classList.add('offline'); text.textContent = '离线 | 检查网络连接'; }
        }
    </script>
</body>
</html>
"""

# ---------------- 加密/工具函数 ----------------
def gen_keypair():
    sk = SigningKey.generate(curve=SECP256k1)
    pk_bytes = sk.get_verifying_key().to_string()
    pk_hash = hashlib.sha256(pk_bytes).hexdigest()[:16]
    addr = f'coin{pk_hash}'
    return sk.to_string().hex(), addr, pk_bytes

def sign(sk_hex: str, payload: bytes) -> str:
    sk = SigningKey.from_string(bytes.fromhex(sk_hex), curve=SECP256k1)
    return sk.sign(payload).hex()

def tx_payload(sender: str, recipient: str, amount: float, nonce: int, fee: float) -> bytes:
    core_data = dict(sender=sender, recipient=recipient, amount=amount, nonce=nonce, fee=fee)
    core_payload = json.dumps(core_data, sort_keys=True, separators=(',', ':')).encode()
    core_txid = hashlib.sha256(core_payload).hexdigest()[:16]
    sign_data = dict(core_txid=core_txid, **core_data)
    return json.dumps(sign_data, sort_keys=True, separators=(',', ':')).encode()

# ---------------- Coin Wallet 核心类 ----------------
class CoinWallet:
    def __init__(self):
        self.sk_hex = None
        self.coin_addr = None
        self.pk_bytes = None
        self.last_nonce = -1
        self.tx_fee = 2.0
        self.load_or_create_key()
        self.running = True
        
    def load_or_create_key(self):
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, 'r', encoding='utf-8') as f:
                dat = json.load(f)
            self.sk_hex = dat['sk_hex']
            self.coin_addr = dat['coin_addr']
            self.pk_bytes = bytes.fromhex(dat['pubkey_hex'])
            self.last_nonce = dat.get('last_nonce', -1)
            print(f"✅ Coin Wallet 已加载 | 地址: {self.coin_addr}")
        else:
            self.sk_hex, self.coin_addr, self.pk_bytes = gen_keypair()
            self.save_key()
            print(f"🆕 Coin Wallet 新创建 | 地址: {self.coin_addr}")
    
    def save_key(self):
        with open(KEY_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'sk_hex': self.sk_hex,
                'coin_addr': self.coin_addr,
                'pubkey_hex': self.pk_bytes.hex(),
                'last_nonce': self.last_nonce
            }, f, indent=2)
    
    def get_network_fee(self):
        try:
            resp = requests.get(f"http://{MAIN_NODE}/chain/stats", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 200:
                    return data.get('stats', {}).get('tx_fee', 2.0)
        except:
            pass
        return 2.0
    
    def heartbeat_loop(self):
        self.tx_fee = self.get_network_fee()
        print(f"💰 当前网络手续费: {self.tx_fee} XODE")
        
        while self.running:
            try:
                self.register()
                if int(now()) % 300 == 0:
                    new_fee = self.get_network_fee()
                    if new_fee != self.tx_fee:
                        print(f"💰 手续费更新: {self.tx_fee} → {new_fee}")
                        self.tx_fee = new_fee
                for _ in range(HEARTBEAT_INTERVAL):
                    if not self.running:
                        break
                    time.sleep(1)
            except Exception as e:
                print(f"⚠️ 心跳异常: {e}")
                time.sleep(10)
    
    def get_public_ip(self):
        try:
            services = ['https://api.ipify.org', 'https://ipinfo.io/ip', 'https://icanhazip.com']
            for svc in services:
                try:
                    ip = requests.get(svc, timeout=5).text.strip()
                    if ip and ip != '127.0.0.1':
                        return ip
                except:
                    continue
            return '127.0.0.1'
        except:
            return '127.0.0.1'
    
    def register(self):
        try:
            ip = self.get_public_ip()
            real_address = f"{ip}:0"
            
            resp = requests.post(
                f"http://{MAIN_NODE}/heartbeat",
                json={
                    "real_address": real_address,
                    "coin_addr": self.coin_addr,
                    "pubkey_hex": self.pk_bytes.hex()
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if resp.status_code == 200:
                data = resp.json()
                server_addr = data.get('coin_addr')
                if server_addr != self.coin_addr:
                    print(f"❌ 地址不一致！本地：{self.coin_addr}，服务端：{server_addr}")
                    return False
                return True
            elif resp.status_code == 429:
                return True
            else:
                return False
        except:
            return False
    
    def get_balance(self):
        try:
            resp = requests.get(f"http://{MAIN_NODE}/balance/{self.coin_addr}", timeout=10)
            if resp.status_code == 200:
                return resp.json().get('balance', 0)
            return 0
        except:
            return 0
    
    def get_history(self):
        try:
            resp = requests.get(f"http://{MAIN_NODE}/address/transactions?addr={self.coin_addr}&size=50", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 200:
                    return data.get('data', {})
            return {'transactions': [], 'total': 0}
        except:
            return {'transactions': [], 'total': 0}
    
    def send(self, recipient, amount, fee=None):
        try:
            amount = round(float(amount), 6)
            tx_fee = round(float(fee), 6) if fee is not None else self.tx_fee
            
            balance = self.get_balance()
            if balance < amount + tx_fee:
                return {"error": f"余额不足（当前：{balance}，需要：{round(amount + tx_fee, 6)}）"}
            
            self.last_nonce += 1
            nonce = self.last_nonce
            
            payload = tx_payload(self.coin_addr, recipient, amount, nonce, tx_fee)
            signature = sign(self.sk_hex, payload)
            
            tx_data = {
                "sender": self.coin_addr,
                "recipient": recipient,
                "amount": amount,
                "nonce": nonce,
                "signature": signature
            }
            
            resp = requests.post(
                f"http://{MAIN_NODE}/transactions/new",
                json=tx_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            result = resp.json()
            
            if resp.status_code == 201:
                self.save_key()
                return {"success": True, "txid": result.get('txid'), "pending_block": result.get('pending_block'), "nonce": nonce, "fee": tx_fee, "amount": amount}
            else:
                self.last_nonce -= 1
                return {"error": result.get('error', '发送失败')}
        except Exception as e:
            self.last_nonce -= 1
            return {"error": str(e)}

# ---------------- Flask API ----------------
app = Flask(__name__)
wallet = None
local_port = 8080

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, main_node=MAIN_NODE, port=local_port)

@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify({"code": 200, "coin_addr": wallet.coin_addr, "status": "active", "main_node": MAIN_NODE, "tx_fee": wallet.tx_fee})

@app.route('/api/balance', methods=['GET'])
def api_balance():
    balance = wallet.get_balance()
    return jsonify({"code": 200, "balance": balance, "coin_addr": wallet.coin_addr})

@app.route('/api/history', methods=['GET'])
def api_history():
    data = wallet.get_history()
    return jsonify({"code": 200, "transactions": data.get('transactions', []), "total_transactions": data.get('total', 0)})

@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.json or {}
    recipient = data.get('recipient')
    amount = data.get('amount')
    fee = data.get('fee')
    
    if not recipient or amount is None:
        return jsonify({"code": 400, "error": "缺少参数"}), 400
    
    try:
        amount = float(amount)
        fee = float(fee) if fee is not None else None
        if amount <= 0:
            return jsonify({"code": 400, "error": "金额必须大于0"}), 400
    except:
        return jsonify({"code": 400, "error": "金额格式错误"}), 400
    
    result = wallet.send(recipient, amount, fee)
    
    if "error" in result:
        return jsonify({"code": 400, "error": result["error"]}), 400
    
    return jsonify({
        "code": 201, 
        "success": True, 
        "txid": result["txid"], 
        "pending_block": result["pending_block"], 
        "nonce": result["nonce"],
        "fee": result["fee"],
        "amount": result["amount"]
    }), 201

@app.route('/api/chain/stats', methods=['GET'])
def api_chain_stats():
    try:
        resp = requests.get(f"http://{MAIN_NODE}/chain/stats", timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"code": 500, "error": str(e)}), 500

# ---------------- 主函数 ----------------
def main():
    global wallet, local_port
    
    parser = argparse.ArgumentParser(description='Coin Wallet - XODE Wallet Client')
    parser.add_argument('-p', '--port', default=8080, type=int, help='本地Web端口 (默认8080)')
    args = parser.parse_args()
    local_port = args.port
    
    wallet = CoinWallet()
    
    # 启动心跳线程
    hb_thread = threading.Thread(target=wallet.heartbeat_loop, daemon=True)
    hb_thread.start()
    
    print(f"""
╔════════════════════════════════════════════════╗
║              💰 Coin Wallet 已启动              ║
╠════════════════════════════════════════════════╣
║  🌐 Web界面: http://127.0.0.1:{local_port:<4}              ║
║  💳 钱包地址: {wallet.coin_addr:<20}    ║
║  🔗 主节点:  {MAIN_NODE:<25}    ║
╠════════════════════════════════════════════════╣
║  功能: 余额查询 | 转账汇款 | 自动参与区块奖励    ║
║  安全: 私钥本地存储，不上传服务器               ║
║  备份: 请妥善保管 {KEY_FILE:<16} 文件      ║
╚════════════════════════════════════════════════╝
    """)
    
    try:
        import webbrowser
        webbrowser.open(f'http://127.0.0.1:{local_port}')
        print("🌐 已自动打开浏览器")
    except:
        pass
    
    app.run(host='0.0.0.0', port=local_port, debug=False, threaded=True, use_reloader=False)

if __name__ == '__main__':
    main()