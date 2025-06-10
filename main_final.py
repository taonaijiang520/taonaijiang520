import os
import time
import logging
import sqlite3
import random
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from apscheduler.schedulers.background import BackgroundScheduler

# ─── 环境变量 ─────────────────────────────
TOKEN = os.getenv("TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
PORT = int(os.getenv("PORT", 5000))
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE", "").rstrip("/")
WEBHOOK_PATH = "/webhook"

# ─── 日志与数据库 ───────────────────────────
logging.basicConfig(level=logging.INFO, filename="bot.log",
                    format="%(asctime)s %(levelname)s %(message)s")
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

# ─── Flask + TeleBot 初始化 ───────────────────
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ─── 心跳 & 看门狗 ───────────────────────────
last_heartrate = time.time()
def heartbeat():
    global last_heartrate
    last_heartrate = time.time()

def watchdog():
    if time.time() - last_heartrate > 60:
        logging.error("看门狗：60s 无心跳，自杀重启")
        os._exit(1)

sched = BackgroundScheduler()
sched.add_job(heartbeat, "interval", seconds=15)
sched.add_job(watchdog,  "interval", seconds=30)
sched.start()

# ─── 会话管理 & 余额管理 ─────────────────────
pending_sessions = set()   # 正在等待对话的用户
user_data = {}             # {uid: {"balance":int, "username":str}}

def record_message(msg):
    try:
        u = msg.from_user
        uid, uname, name = u.id, u.username or "", u.first_name or ""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('SELECT 1 FROM users WHERE id=?',(uid,))
        if c.fetchone():
            c.execute('UPDATE users SET username=?,name=?,last_ts=? WHERE id=?',
                      (uname,name,now,uid))
        else:
            c.execute('INSERT INTO users(id,username,name,first_ts,last_ts) VALUES(?,?,?,?,?)',
                      (uid,uname,name,now,now))
        conn.commit()
    except Exception:
        logging.exception("record_message error")

def get_main_menu(cid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("/start"), KeyboardButton("/status"))
    kb.row(KeyboardButton("/balance"), KeyboardButton("/talkto"))
    if cid == ADMIN_CHAT_ID:
        kb.row(KeyboardButton("/pending"), KeyboardButton("/reply"))
        kb.row(KeyboardButton("/add"))
    return kb

# ─── /start 欢迎 ─────────────────────────────
@bot.message_handler(commands=["start"])
def handle_start(msg):
    record_message(msg); heartbeat()
    cid = msg.chat.id
    bot.send_message(cid,
        "每次你点我都会湿成小猫，快来试试我的湿身中文包♡",
        reply_markup=get_main_menu(cid)
    )

# ─── /status 在线检查 ────────────────────────
@bot.message_handler(commands=["status"])
def handle_status(msg):
    record_message(msg); heartbeat()
    msg.reply("✅ 桃奈酱机器人当前在线。")

# ─── /balance & /add 余额管理 ─────────────────
@bot.message_handler(commands=["balance"])
def handle_balance(msg):
    record_message(msg); heartbeat()
    uid = msg.from_user.id
    if uid not in user_data:
        user_data[uid] = {"balance": 1000, "username": msg.from_user.username or ""}
    bot.reply_to(msg, f"你的余额：💰{user_data[uid]['balance']}")

@bot.message_handler(commands=["add"])
def handle_add(msg):
    record_message(msg); heartbeat()
    if msg.from_user.id != ADMIN_CHAT_ID:
        return
    parts = msg.text.split()
    if len(parts) != 3:
        return bot.reply_to(msg, "格式：/add @用户名 金额")
    mention = msg.entities[1]
    uname = msg.text[mention.offset:mention.offset+mention.length][1:]
    try:
        amt = int(parts[-1])
    except:
        return bot.reply_to(msg, "金额必须是整数")
    for uid,info in user_data.items():
        if info.get("username") == uname:
            info["balance"] += amt
            return bot.reply_to(msg, f"已为 {uname} 增加 {amt} 💰")
    bot.reply_to(msg, f"未找到用户 {uname}")

# ─── 双向传话 ────────────────────────────────
@bot.message_handler(commands=["talkto"])
def handle_talkto(msg):
    record_message(msg); heartbeat()
    uid = msg.from_user.id
    pending_sessions.add(uid)
    bot.send_message(uid, "✅ 已加入传话队列，请发送消息给我。", reply_markup=get_main_menu(uid))
    bot.send_message(ADMIN_CHAT_ID, f"👤 用户 {uid} 请求传话")

@bot.message_handler(commands=["pending"])
def handle_pending(msg):
    record_message(msg); heartbeat()
    if msg.from_user.id != ADMIN_CHAT_ID:
        return
    if not pending_sessions:
        return bot.reply_to(msg, "当前没有等待的用户")
    lst = "\n".join(str(u) for u in pending_sessions)
    bot.reply_to(msg, "等待列表：\n" + lst)

@bot.message_handler(commands=["exit"])
def handle_exit(msg):
    record_message(msg); heartbeat()
    uid = msg.from_user.id
    if uid in pending_sessions:
        pending_sessions.remove(uid)
        bot.send_message(uid, "✅ 已退出传话模式", reply_markup=get_main_menu(uid))
    elif uid == ADMIN_CHAT_ID:
        # 管理员退出不操作
        pass

@bot.message_handler(func=lambda m: m.chat.id in pending_sessions, content_types=["text"])
def handle_user_toward_admin(msg):
    record_message(msg); heartbeat()
    uid, text = msg.chat.id, msg.text
    bot.send_message(ADMIN_CHAT_ID, f"→ 来自 {uid}：{text}")

@bot.message_handler(commands=["reply"])
def handle_reply(msg):
    record_message(msg); heartbeat()
    if msg.from_user.id != ADMIN_CHAT_ID:
        return
    parts = msg.text.split(maxsplit=2)
    if len(parts) < 3:
        return bot.reply_to(msg, "格式：/reply 用户ID 内容")
    try:
        target = int(parts[1])
    except:
        return bot.reply_to(msg, "用户ID无效")
    text = parts[2]
    bot.send_message(target, f"← 来自 主人：{text}")
    bot.reply_to(msg, "✅ 已回复")

# ─── 百家乐玩法 ───────────────────────────────
def deal_cards():
    return [random.randint(1,9) for _ in range(2)], [random.randint(1,9) for _ in range(2)]

def baccarat_result(p,b):
    return ("player" if sum(p)%10>sum(b)%10 else
            "banker" if sum(b)%10>sum(p)%10 else "tie")

def check_super_six(b,w):
    t = sum(b)%10
    if w=="banker" and t==6:
        return True, (20 if len(b)==3 else 12)
    return False,0

def parse_bets(txt):
    m={"闲":"player","庄":"banker","和":"tie",
       "庄对":"banker_pair","闲对":"player_pair",
       "超6":"super_six","大":"big","小":"small"}
    bets={}
    for part in txt.replace("/baccarat","").split():
        for cn,en in m.items():
            if part.startswith(cn):
                try: amt=int(part[len(cn):])
                except: continue
                if amt>0: bets[en]=amt
    return bets

@bot.message_handler(commands=["baccarat"])
def handle_baccarat(msg):
    record_message(msg); heartbeat()
    uid=msg.from_user.id
    if uid not in user_data:
        user_data[uid]={"balance":1000,"username":msg.from_user.username or ""}
    bets = parse_bets(msg.text)
    if not bets:
        return bot.reply_to(msg,"用法：/baccarat 闲100 庄对20 超610 …")
    total = sum(bets.values())
    if total>user_data[uid]["balance"]:
        return bot.reply_to(msg,"余额不足～")
    p,b=deal_cards(); res=baccarat_result(p,b); s6,rt=check_super_six(b,res)
    pay=0; text=f"🎴 发牌：闲{p} vs 庄{b}\n结果：{res.upper()}\n"
    for k,a in bets.items():
        win,gain=False,0
        if k=="player" and res=="player": win,gain=True,a
        elif k=="banker" and res=="banker": win,gain=True,int(a*0.95)
        elif k=="tie" and res=="tie": win,gain=True,a*8
        elif k=="player_pair" and p[0]==p[1]: win,gain=True,a*11
        elif k=="banker_pair" and b[0]==b[1]: win,gain=True,a*11
        elif k=="super_six" and s6: win,gain=True,a*rt
        elif k=="big" and len(p+b) in (5,6): win,gain=True,int(a*0.54)
        elif k=="small" and len(p+b)==4: win,gain=True,int(a*1.5)
        if win:
            pay += gain + a
            text+=f"✅ 赢[{k}] 获{gain}💰\n"
        else:
            text+=f"❌ 输[{k}]\n"
    user_data[uid]["balance"] -= total
    user_data[uid]["balance"] += pay
    text += f"当前余额：💰{user_data[uid]['balance']}"
    bot.reply_to(msg, text)

# ─── Webhook 路由 ───────────────────────────────
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    raw = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(raw)
    bot.process_new_updates([update])
    heartbeat()
    return "", 200

# ─── 启动 Flask Webhook ─────────────────────────
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_PATH)
    logging.info("Webhook 已设置: " + WEBHOOK_URL_BASE + WEBHOOK_PATH)
    app.run(host="0.0.0.0", port=PORT)
