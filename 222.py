#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
区块链极简钱包 -coin版
地址格式：coinxxxxxxxxxxxxxxxx（20位固定：coin+16位字符）
核心功能：查询余额 | 发送交易 | 查询区块高度
"""
import hashlib
import json
import requests
import socket
import threading
import time
import os
from time import time as now

# -------------------------- 仅需配置这1行！填写你的公网节点地址 --------------------------
MAIN_NODE_URL = "http://62.234.183.74:9753"  # 例：http://123.45.67.89:9753
# ----------------------------------------------------------------------------------------

# 核心配置（无需修改）
HEARTBEAT_INTERVAL = 30  # 后台自动心跳，保线用
API_TIMEOUT = 5
WALLET_FILE = "simple_wallet.json"  # 本地钱包文件，保存Coin地址
COIN_ADDR_LEN = 20  # 钱包地址固定长度：coin+16位=20位

# 全局状态
wallet_address = ""  # Coin地址（coinxxxxxxxxxxxxxxxx）
real_address = ""    # 设备真实地址
is_connected = False # 是否连接主节点

# ---------------- 核心工具：生成Coin地址（和公网节点完全一致）----------------
def gen_fixed_addr(real_addr: str) -> str:
    """生成Coin地址：coin + 16位字母数字（和公网节点算法一致）"""
    h = hashlib.sha256(real_addr.encode()).hexdigest()
    short_part = ''.join([c for c in h if c.isalnum()])[:16]
    return f"coin{short_part}"  # 去掉下划线，直接拼接

def get_local_real_address():
    """自动获取设备真实网络地址（适配内网/公网，随机端口防占用）"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        random_port = 9000 + int(time.time() % 1000)
        return f"{local_ip}:{random_port}"
    except:
        return f"127.0.0.1:{9000 + int(time.time() % 1000)}"

def save_wallet():
    """保存Coin地址到本地，重启自动加载"""
    wallet_info = {
        "wallet_address": wallet_address,
        "real_address": real_address,
        "create_time": now()
    }
    with open(WALLET_FILE, 'w', encoding='utf-8') as f:
        json.dump(wallet_info, f, ensure_ascii=False, indent=2)

def load_wallet():
    """从本地加载Coin地址，无则新建"""
    global wallet_address, real_address
    if os.path.exists(WALLET_FILE):
        try:
            with open(WALLET_FILE, 'r', encoding='utf-8') as f:
                info = json.load(f)
            wallet_address = info["wallet_address"]
            real_address = info["real_address"]
            # 校验地址格式（20位）
            if not (wallet_address.startswith("coin") and len(wallet_address)==COIN_ADDR_LEN):
                raise Exception("地址格式错误")
            print(f"✅ 加载本地钱包成功 | 你的Coin地址：{wallet_address}")
            return True
        except:
            os.remove(WALLET_FILE)
            print("⚠️  本地钱包文件损坏，将创建新钱包")
    # 新建钱包
    real_address = get_local_real_address()
    wallet_address = gen_fixed_addr(real_address)
    save_wallet()
    print(f"🆕 新建钱包成功 | 你的Coin地址：{wallet_address}（固定20位，请勿泄露）")
    return False

def auto_heartbeat():
    """后台自动心跳保线，断连自动重试，不影响前台操作"""
    global is_connected
    while True:
        try:
            res = requests.post(
                f"{MAIN_NODE_URL}/heartbeat",
                json={"real_address": real_address},
                headers={"Content-Type": "application/json"},
                timeout=API_TIMEOUT
            )
            is_connected = res.json().get('code') == 200
        except:
            is_connected = False
            time.sleep(10)
            continue
        time.sleep(HEARTBEAT_INTERVAL)

def check_main_node():
    """启动前验证主节点是否可达"""
    try:
        requests.get(f"{MAIN_NODE_URL}/nodes/info", timeout=API_TIMEOUT)
        return True
    except:
        print(f"❌ 主节点连接失败！请检查：")
        print(f"  1. MAIN_NODE_URL 是否填对（例：http://123.45.67.89:9753）")
        print(f"  2. 云服务器9753端口是否开放")
        print(f"  3. 公网节点是否已启动")
        input("按回车键退出...")
        os._exit(1)

# -------------------------- 三大核心功能（Coin地址适配）--------------------------
def query_balance():
    """功能1：查询自身Coin地址余额"""
    if not is_connected:
        print("❌ 钱包未连接主节点，正在重试...")
        time.sleep(2)
        if not is_connected:
            print("❌ 连接失败，请检查网络后重启钱包！")
            return
    try:
        res = requests.get(f"{MAIN_NODE_URL}/balance/{wallet_address}", timeout=API_TIMEOUT)
        if res.json().get('code') == 200:
            balance = round(res.json()["balance"], 6)
            print(f"\n💰 你的Coin地址：{wallet_address}")
            print(f"💰 当前钱包余额：{balance}")
        else:
            print(f"❌ 查询失败：{res.json().get('error', '未知错误')}")
    except Exception as e:
        print(f"❌ 查询失败：{str(e)[:30]}")

def send_transaction():
    """功能2：发送交易（向其他Coin地址转币），带严格格式校验"""
    if not is_connected:
        print("❌ 钱包未连接主节点，无法发送交易！")
        return
    print("\n📤 发送交易（仅支持Coin地址，格式：coinxxxxxxxxxxxxxxxx，20位）")
    try:
        # 输入收款地址（严格校验20位coin开头）
        to_addr = input("请输入收款Coin地址：").strip()
        if not (to_addr.startswith("coin") and len(to_addr)==COIN_ADDR_LEN):
            print(f"❌ 收款地址格式错误！必须是20位，以coin开头的地址（例：coin1234567890abcdef）")
            return
        if to_addr == wallet_address:
            print("❌ 不能向自身地址转币！")
            return
        # 输入转账金额
        amount = input("请输入转账金额（正数，例：10.5）：").strip()
        amount = float(amount)
        if amount <= 0:
            print("❌ 转账金额必须大于0！")
            return
        # 发送交易（直接用Coin地址）
        res = requests.post(
            f"{MAIN_NODE_URL}/transactions/new",
            json={"sender": wallet_address, "recipient": to_addr, "amount": amount},
            headers={"Content-Type": "application/json"},
            timeout=API_TIMEOUT
        )
        if res.json().get('code') == 201:
            block_index = res.json()["tx"]["pending_block"]
            print(f"✅ 交易提交成功！")
            print(f"✅ 待第{block_index}个区块确认后到账（约{int(MAIN_NODE_URL.split(':')[-1].split('/')[-1]) or 120}秒）")
        else:
            print(f"❌ 交易失败：{res.json().get('error', '余额不足/地址错误')}")
    except ValueError:
        print("❌ 金额格式错误！请输入数字（例：10.5，支持小数）")
    except KeyboardInterrupt:
        print("\n✅ 已取消发送交易，返回菜单")
    except Exception as e:
        print(f"❌ 交易失败：{str(e)[:30]}")

def query_block_height():
    """功能3：查询全网最新区块高度+在线节点数"""
    if not is_connected:
        print("❌ 钱包未连接主节点，正在重试...")
        time.sleep(2)
        if not is_connected:
            print("❌ 连接失败，请检查网络后重启钱包！")
            return
    try:
        res = requests.get(f"{MAIN_NODE_URL}/nodes/info", timeout=API_TIMEOUT)
        if res.json().get('code') == 200:
            height = res.json()["total_block"]
            online_count = res.json()["online_node"]
            main_coin = res.json()["main_node_coin_addr"]
            print(f"\n📊 全网最新区块高度：{height}")
            print(f"📊 全网在线节点数：{online_count}台")
            print(f"⛏️  出块主节点Coin：{main_coin[-10:]}（后10位）")
        else:
            print(f"❌ 查询失败：{res.json().get('error', '未知错误')}")
    except Exception as e:
        print(f"❌ 查询失败：{str(e)[:30]}")

# -------------------------- 中文交互式主菜单 --------------------------
def main_menu():
    """中文交互式主菜单，按数字选择功能"""
    while True:
        print("\n" + "="*60)
        print("          🚀 区块链极简钱包 - Coin地址版")
        print("="*60)
        print(f"          🔑 你的钱包地址：{wallet_address[-10:]}（后10位）")
        print("="*60)
        print("            1 → 查询我的钱包余额（精准到6位小数）")
        print("            2 → 发送交易（转币给其他Coin地址）")
        print("            3 → 查询全网区块高度+在线节点数")
        print("            0 → 安全退出钱包")
        print("="*60)
        try:
            choice = input("请输入数字选择功能（0-3）：").strip()
            if choice == "1":
                query_balance()
            elif choice == "2":
                send_transaction()
            elif choice == "3":
                query_block_height()
            elif choice == "0":
                print("\n👋 钱包已安全退出，下次启动自动加载地址！")
                os._exit(0)
            else:
                print("❌ 输入错误！请输入0、1、2、3中的一个数字")
        except KeyboardInterrupt:
            print("\n👋 钱包已安全退出，下次启动自动加载地址！")
            os._exit(0)
        except Exception as e:
            print(f"❌ 操作异常：{str(e)[:30]}，请重新选择")
        # 操作后暂停，让用户看清结果
        input("\n按回车键返回主菜单...")

def main():
    """钱包主入口：启动"""
    print("="*60)
    print("🚀 区块链极简钱包 - 启动中...")
    print(f"💡 地址格式：coinxxxxxxxxxxxxxxxx（固定20位，无下划线）")
    print("💡 核心功能：查余额 | 发交易 | 查区块高度")
    print("💡 操作方式：纯中文交互式，按数字选择即可")
    print("="*60)

    # 1. 检查主节点配置
    if MAIN_NODE_URL == "http://你的云服务器公网IP:9753":
        print("❌ 请先配置主节点地址！打开代码修改 MAIN_NODE_URL 为你的公网IP:9753")
        input("按回车键退出...")
        os._exit(1)
    # 2. 验证主节点可达
    check_main_node()
    # 3. 加载/新建Coin地址钱包
    load_wallet()
    # 4. 启动后台心跳线程（保线用，不影响前台）
    threading.Thread(target=auto_heartbeat, daemon=True).start()
    # 5. 等待心跳连接成功
    time.sleep(2)
    print(f"\n✅ 钱包启动完成！当前连接状态：{'✅ 已连接' if is_connected else '❌ 连接中'}")
    # 6. 进入主菜单
    main_menu()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 钱包启动失败：{str(e)[:50]}")
        input("按回车键退出...")
