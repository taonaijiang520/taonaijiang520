# ========== aiogram 启动提醒、掉线重启、/status ==========
from aiogram import Bot as AioBot, Dispatcher, types
from aiogram.utils import executor
import asyncio
import os
import time

API_TOKEN = os.getenv("BOT_TOKEN", "你的AiogramToken")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "1149975148"))

aiobot = AioBot(token=API_TOKEN)
dp = Dispatcher(aiobot)

last_heartbeat = time.time()

async def on_startup(_):
    await aiobot.send_message(ADMIN_CHAT_ID, "✅ 桃奈酱机器人已上线！")
    asyncio.create_task(heartbeat())
    asyncio.create_task(watchdog())

async def on_shutdown(_):
    await aiobot.send_message(ADMIN_CHAT_ID, "❌ 桃奈酱机器人已掉线！")

async def heartbeat():
    global last_heartbeat
    while True:
        last_heartbeat = time.time()
        await asyncio.sleep(15)

async def watchdog():
    global last_heartbeat
    while True:
        await asyncio.sleep(30)
        if time.time() - last_heartbeat > 40:
            print("⛔️ 掉线检测触发，Render 将自动重启")
            os._exit(1)

@dp.message_handler(commands=["status"])
async def status_handler(message: types.Message):
    await message.reply("✅ 桃奈酱机器人当前在线。")


# ========== Flask + Telebot 主体 ==========
import logging
import sqlite3
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

TOKEN = os.getenv("TOKEN", "你的TelebotToken")
PORT = int(os.getenv("PORT", 5000))
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE", "").rstrip("/")
WEBHOOK_PATH = "/webhook"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

logging.basicConfig(filename='bot.log', level=logging.INFO)

conn = sqlite3.connect("users.db", check_same_thread=False)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT,
    first_ts TEXT,
    last_ts TEXT
)
''')
conn.commit()

forward_sessions = {}
session_timestamp = {}
SESSION_TIMEOUT = 300

def cleanup_sessions():
    now = datetime.utcnow()
    for uid, ts in list(session_timestamp.items()):
        if (now - ts).total_seconds() > SESSION_TIMEOUT:
            if forward_sessions.pop(uid, None):
                bot.send_message(uid, "⏰ 会话超时，已退出双向传话模式", reply_markup=get_main_menu(uid))
                bot.send_message(ADMIN_CHAT_ID, f"⏰ 用户 {uid} 的会话超时已结束", reply_markup=get_main_menu(ADMIN_CHAT_ID))
            session_timestamp.pop(uid, None)

sched = BackgroundScheduler()
sched.add_job(cleanup_sessions, "interval", seconds=60)
sched.start()

def get_main_menu(chat_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🐾 桃奈语"), KeyboardButton("🐾 双向传话"))
    if chat_id == ADMIN_CHAT_ID:
        kb.row(KeyboardButton("🐾 开发者入口"))
    return kb

def exit_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("退出双向传话", callback_data="exit_forward"))
    return kb

def record_message(msg):
    try:
        u = msg.from_user
        uid = u.id
        uname = u.username or ''
        name = u.first_name or ''
        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        c.execute('SELECT 1 FROM users WHERE id=?', (uid,))
        if c.fetchone():
            c.execute('UPDATE users SET username=?, name=?, last_ts=? WHERE id=?', (uname, name, now, uid))
        else:
            c.execute('INSERT INTO users(id,username,name,first_ts,last_ts) VALUES(?,?,?,?,?)',
                      (uid, uname, name, now, now))
        conn.commit()
    except Exception:
        logging.exception("record_message error")

@bot.message_handler(commands=['start'])
def on_start(msg):
    try:
        record_message(msg)
        cid = msg.chat.id
        bot.send_message(cid, "每次你点我都会湿成小猫，快来试试我的湿身中文包♡", reply_markup=get_main_menu(cid))
        link_kb = InlineKeyboardMarkup()
        link_kb.add(InlineKeyboardButton("🐾 桃奈语", url="https://t.me/setlanguage/zhcncc"))
        bot.send_message(cid, "点下面的「🐾 桃奈语」立即切换到【桃奈湿身语】", reply_markup=link_kb)
    except Exception:
        logging.exception("on_start error")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def on_text(msg):
    try:
        record_message(msg)
        cid = msg.chat.id
        text = msg.text.strip()
        now = datetime.utcnow()

        if text == "🐾 桃奈语":
            link_kb = InlineKeyboardMarkup()
            link_kb.add(InlineKeyboardButton("🐾 桃奈语", url="https://t.me/setlanguage/zhcncc"))
            bot.send_message(cid, "点下面的「🐾 桃奈语」立即切换到【桃奈湿身语】", reply_markup=link_kb)
            return

        if text == "🐾 双向传话":
            forward_sessions[cid] = "PENDING"
            session_timestamp[cid] = now
            bot.send_message(cid, "请发送要传达给主人的内容：", reply_markup=get_main_menu(cid))
            return

        if text == "🐾 开发者入口" and cid == ADMIN_CHAT_ID:
            c.execute('SELECT id,username,name,first_ts,last_ts FROM users')
            rows = c.fetchall()
            lines = ["📊 开发者入口 · 用户列表："]
            for i, (uid, uname, name, ft, lt) in enumerate(rows, 1):
                lines.append(f"{i}. ID:{uid} | 用户名:@{uname or '—'} | 名称:{name or '—'}")
                lines.append(f"     首次:{ft} | 最近:{lt}")
            bot.send_message(cid, "\n".join(lines), reply_markup=get_main_menu(cid))
            return

        state = forward_sessions.get(cid)
        if state == "PENDING":
            forward_sessions[cid] = ADMIN_CHAT_ID
            forward_sessions[ADMIN_CHAT_ID] = cid
            session_timestamp[cid] = session_timestamp[ADMIN_CHAT_ID] = now
            bot.send_message(ADMIN_CHAT_ID, f"来自 @{msg.from_user.username or msg.from_user.first_name} 的传话：{text}",
                             reply_markup=exit_keyboard())
            bot.send_message(cid, "✅ 已发送，进入双向传话模式，点击「退出双向传话」结束。", reply_markup=get_main_menu(cid))
            return

        if state and state != "PENDING":
            partner = state
            session_timestamp[cid] = session_timestamp[partner] = now
            bot.send_message(partner, f"来自 @{msg.from_user.username or msg.from_user.first_name} 的传话：{text}",
                             reply_markup=exit_keyboard())
            return

        bot.send_message(cid, "🐾 未识别指令，请从菜单选择", reply_markup=get_main_menu(cid))
    except Exception:
        logging.exception("on_text error")

@bot.callback_query_handler(lambda cq: cq.data == "exit_forward")
def on_exit_forward(cq):
    try:
        cid = cq.message.chat.id
        partner = forward_sessions.pop(cid, None)
        session_timestamp.pop(cid, None)
        if partner:
            forward_sessions.pop(partner, None)
            session_timestamp.pop(partner, None)
        bot.edit_message_reply_markup(cid, cq.message.message_id, reply_markup=None)
        bot.send_message(cid, "🚪 已退出双向传话模式", reply_markup=get_main_menu(cid))
        if partner:
            bot.send_message(partner, "🚪 对方已退出双向传话模式", reply_markup=get_main_menu(partner))
        bot.answer_callback_query(cq.id, "会话已结束")
    except Exception:
        logging.exception("on_exit_forward error")

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    try:
        raw = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(raw)
        bot.process_new_updates([update])
    except Exception:
        logging.exception("webhook error")
    return "", 200

# ========== 启动 Flask 与 aiogram ==========
if __name__ == "__main__":
    bot.remove_webhook()
    if WEBHOOK_URL_BASE:
        url = WEBHOOK_URL_BASE + WEBHOOK_PATH
        bot.set_webhook(url=url)
        logging.info(f"✅ Webhook 已设置: {url}")
    else:
        logging.warning("⚠️ 未设置 Webhook URL，跳过")

    from threading import Thread
    Thread(target=lambda: executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)).start()

    app.run(host="0.0.0.0", port=PORT)

# ========== 百家乐游戏 ==========
import random
from telebot.types import Message

user_data = {}

def deal_cards():
    def draw():
        return random.randint(1, 9)
    return [draw(), draw()], [draw(), draw()]

def baccarat_result(player, banker):
    p_total = sum(player) % 10
    b_total = sum(banker) % 10
    if p_total > b_total:
        return 'player'
    elif p_total < b_total:
        return 'banker'
    else:
        return 'tie'

def check_super_six(banker, winner):
    total = sum(banker) % 10
    if winner == "banker" and total == 6:
        if len(banker) == 3:
            return True, 20
        else:
            return True, 12
    return False, 0

def parse_bets(text: str):
    bet_map = {
        "闲": "player",
        "庄": "banker",
        "和": "tie",
        "庄对": "banker_pair",
        "闲对": "player_pair",
        "超6": "super_six",
        "大": "big",
        "小": "small"
    }
    bets = {}
    parts = text.replace("/baccarat", "").strip().split()
    for part in parts:
        for cn, en in bet_map.items():
            if part.startswith(cn):
                try:
                    amount = int(part[len(cn):])
                    if amount > 0:
                        bets[en] = amount
                except:
                    continue
    return bets

@bot.message_handler(commands=['balance'])
def show_balance(message: Message):
    uid = message.from_user.id
    if uid not in user_data:
        user_data[uid] = {"balance": 1000, "username": message.from_user.username or ""}
    balance = user_data[uid]["balance"]
    bot.reply_to(message, f"你的余额为：💰{balance}")

@bot.message_handler(commands=['add'])
def add_balance(message: Message):
    from config import ADMIN_CHAT_ID
    if str(message.from_user.id) != str(ADMIN_CHAT_ID):
        return
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "格式错误，应为 /add @用户名 金额")
            return
        mention = message.entities[1]
        username = message.text[mention.offset:mention.offset + mention.length][1:]
        amount = int(parts[-1])
        for uid in user_data:
            if user_data[uid].get("username") == username:
                user_data[uid]['balance'] += amount
                bot.reply_to(message, f"已增加 {username} 的余额 {amount} 💰")
                return
        bot.reply_to(message, f"未找到用户 {username}")
    except Exception as e:
        bot.reply_to(message, f"发生错误：{e}")

@bot.message_handler(commands=['baccarat'])
def baccarat_game(message: Message):
    uid = message.from_user.id
    username = message.from_user.username or ""
    if uid not in user_data:
        user_data[uid] = {"balance": 1000, "username": username}
    try:
        bets = parse_bets(message.text)
        if not bets:
            bot.reply_to(message, "请使用格式如：/baccarat 闲100 超620 庄对30")
            return
        total_bet = sum(bets.values())
        if total_bet > user_data[uid]["balance"]:
            bot.reply_to(message, "余额不足～")
            return
        player, banker = deal_cards()
        result = baccarat_result(player, banker)
        payout = 0
        result_text = f"🎴发牌：\n闲：{player}（{sum(player)%10}点）\n庄：{banker}（{sum(banker)%10}点）\n结果：{result.upper()}\n"
        super6_win, super6_rate = check_super_six(banker, result)
        for key, amount in bets.items():
            win = False
            gain = 0
            if key == "player" and result == "player":
                win = True
                gain = amount
            elif key == "banker" and result == "banker":
                win = True
                gain = int(amount * 0.95)
            elif key == "tie" and result == "tie":
                win = True
                gain = amount * 8
            elif key == "player_pair" and player[0] == player[1]:
                win = True
                gain = amount * 11
            elif key == "banker_pair" and banker[0] == banker[1]:
                win = True
                gain = amount * 11
            elif key == "super_six" and super6_win:
                win = True
                gain = amount * super6_rate
            elif key == "big" and len(player + banker) in [5, 6]:
                win = True
                gain = amount * 0.54
            elif key == "small" and len(player + banker) == 4:
                win = True
                gain = amount * 1.5
            if win:
                payout += int(gain) + amount
                result_text += f"✅ 赢了下注[{key}]，获得💰{int(gain)}\n"
            else:
                result_text += f"❌ 输了下注[{key}]\n"
        user_data[uid]["balance"] -= total_bet
        user_data[uid]["balance"] += payout
        result_text += f"\n当前余额：💰{user_data[uid]['balance']}"
        bot.reply_to(message, result_text)
    except Exception as e:
        bot.reply_to(message, f"发生错误：{e}")
    
