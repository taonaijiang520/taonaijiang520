import os
import time
import logging
import sqlite3
import random
from datetime import datetime
from threading import Thread
from flask import Flask, request
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from apscheduler.schedulers.background import BackgroundScheduler

# ───── 环境变量 ─────────────────────────────────
TOKEN = os.getenv("TOKEN")                       # Telegram Bot Token
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))  # 管理员 Chat ID
PORT = int(os.getenv("PORT", 5000))              # Flask 端口（如果不使用 webhook，可忽略）
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE", "").rstrip("/")
WEBHOOK_PATH = "/webhook"

# ───── 日志 & 数据库 ─────────────────────────────
logging.basicConfig(level=logging.INFO, filename="bot.log",
                    format="%(asctime)s %(levelname)s %(message)s")
conn = sqlite3.connect("users.db", check_same_thread=False)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    username TEXT, name TEXT,
    first_ts TEXT, last_ts TEXT
)
''')
conn.commit()

# ───── 全局状态 ─────────────────────────────────
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# 心跳与重启检测
last_update_time = time.time()
HEARTBEAT_INTERVAL = 15
WATCHDOG_INTERVAL = 30
WATCHDOG_THRESHOLD = 40

# 双向传话会话
forward_sessions = {}
session_timestamp = {}
SESSION_TIMEOUT = 300

# 用户余额
user_data = {}

# ───── 辅助函数 ─────────────────────────────────
def record_message(msg):
    """记录用户到 SQLite"""
    try:
        u, now = msg.from_user, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        uid, uname, name = u.id, u.username or "", u.first_name or ""
        c.execute('SELECT 1 FROM users WHERE id=?', (uid,))
        if c.fetchone():
            c.execute('UPDATE users SET username=?,name=?,last_ts=? WHERE id=?',
                      (uname, name, now, uid))
        else:
            c.execute('INSERT INTO users(id,username,name,first_ts,last_ts) VALUES(?,?,?,?,?)',
                      (uid, uname, name, now, now))
        conn.commit()
    except Exception:
        logging.exception("record_message error")

def get_main_menu(chat_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🐾 桃奈语"), KeyboardButton("🐾 双向传话"))
    if chat_id == ADMIN_CHAT_ID:
        kb.row(KeyboardButton("🐾 开发者入口"), KeyboardButton("/status"))
    return kb

def exit_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("退出双向传话", callback_data="exit_forward"))
    return kb

# ───── 心跳 & 看门狗 ─────────────────────────────
def heartbeat_job():
    global last_update_time
    last_update_time = time.time()

def watchdog_job():
    if time.time() - last_update_time > WATCHDOG_THRESHOLD:
        logging.error("掉线检测：超过阈值，进程自杀重启")
        os._exit(1)

sched = BackgroundScheduler()
sched.add_job(heartbeat_job, "interval", seconds=HEARTBEAT_INTERVAL)
sched.add_job(watchdog_job, "interval", seconds=WATCHDOG_INTERVAL)
sched.start()

# ───── /start 欢迎 ─────────────────────────────────
@bot.message_handler(commands=["start"])
def handle_start(msg):
    record_message(msg)
    heartbeat_job()
    cid = msg.chat.id
    bot.send_message(
        cid,
        "每次你点我都会湿成小猫，快来试试我的湿身中文包♡",
        reply_markup=get_main_menu(cid)
    )
    link_kb = InlineKeyboardMarkup()
    link_kb.add(InlineKeyboardButton("🐾 桃奈语", url="https://t.me/setlanguage/zhcncc"))
    bot.send_message(
        cid,
        "点下面的「🐾 桃奈语」立即切换到【桃奈湿身语】",
        reply_markup=link_kb
    )
    if cid == ADMIN_CHAT_ID:
        bot.send_message(ADMIN_CHAT_ID, "✅ 机器人已上线（通过 /start）")

# ───── /status 命令 ───────────────────────────────
@bot.message_handler(commands=["status"])
def handle_status(msg):
    record_message(msg)
    heartbeat_job()
    msg.reply("✅ 桃奈酱机器人当前在线。")

# ───── 文本消息处理（双向传话 & 菜单） ───────────
@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(msg):
    record_message(msg)
    heartbeat_job()
    cid, text, now = msg.chat.id, msg.text.strip(), datetime.utcnow()
    # 桃奈语
    if text == "🐾 桃奈语":
        link_kb = InlineKeyboardMarkup()
        link_kb.add(InlineKeyboardButton("🐾 桃奈语", url="https://t.me/setlanguage/zhcncc"))
        return bot.send_message(cid, "点下面的「🐾 桃奈语」立即切换到【桃奈湿身语】", reply_markup=link_kb)
    # 双向传话
    if text == "🐾 双向传话":
        forward_sessions[cid] = "PENDING"
        session_timestamp[cid] = now
        return bot.send_message(cid, "请发送要传达给主人的内容：", reply_markup=get_main_menu(cid))
    # 开发者入口
    if text == "🐾 开发者入口" and cid == ADMIN_CHAT_ID:
        rows = c.execute('SELECT id,username,name,first_ts,last_ts FROM users').fetchall()
        lines = ["📊 用户列表："]
        for i,(uid,un,name,ft,lt) in enumerate(rows,1):
            lines.append(f"{i}. ID:{uid} 姓名:{name} 用户名:@{un}")
            lines.append(f"   首次:{ft} 最近:{lt}")
        return bot.send_message(cid, "\n".join(lines), reply_markup=get_main_menu(cid))
    # 双向传话中
    state = forward_sessions.get(cid)
    if state == "PENDING":
        forward_sessions[cid] = ADMIN_CHAT_ID
        forward_sessions[ADMIN_CHAT_ID] = cid
        session_timestamp[cid] = session_timestamp[ADMIN_CHAT_ID] = now
        bot.send_message(ADMIN_CHAT_ID, f"→ 来自 @{msg.from_user.username or msg.from_user.first_name}：{text}", 
                         reply_markup=exit_keyboard())
        return bot.send_message(cid, "✅ 已发送，进入双向传话。", reply_markup=get_main_menu(cid))
    if state and state != "PENDING":
        partner = state
        session_timestamp[cid] = session_timestamp[partner] = now
        return bot.send_message(partner, f"← 来自 @{msg.from_user.username or msg.from_user.first_name}：{text}", 
                                reply_markup=exit_keyboard())
    # 未识别
    bot.send_message(cid, "🐾 未识别指令，请从菜单选择", reply_markup=get_main_menu(cid))

@bot.callback_query_handler(lambda cq: cq.data=="exit_forward")
def handle_exit(cq):
    cid = cq.message.chat.id
    partner = forward_sessions.pop(cid, None)
    session_timestamp.pop(cid, None)
    if partner:
        forward_sessions.pop(partner, None)
        session_timestamp.pop(partner, None)
        bot.send_message(partner, "🚪 对方已退出传话模式", reply_markup=get_main_menu(partner))
    bot.edit_message_reply_markup(cid, cq.message.message_id, reply_markup=None)
    bot.send_message(cid, "🚪 已退出传话模式", reply_markup=get_main_menu(cid))
    bot.answer_callback_query(cq.id)

# ───── 百家乐游戏 ─────────────────────────────────
def deal_cards():
    return [random.randint(1,9) for _ in range(2)], [random.randint(1,9) for _ in range(2)]

def baccarat_result(p,b):
    return ("player" if sum(p)%10>sum(b)%10 else
            "banker" if sum(b)%10>sum(p)%10 else "tie")

def check_super_six(b,w):
    t=sum(b)%10
    if w=="banker" and t==6: return True, (20 if len(b)==3 else 12)
    return False,0

def parse_bets(txt):
    m={"闲":"player","庄":"banker","和":"tie","庄对":"banker_pair",
       "闲对":"player_pair","超6":"super_six","大":"big","小":"small"}
    bets={}
    for part in txt.replace("/baccarat","").split():
        for k,v in m.items():
            if part.startswith(k):
                try: amt=int(part[len(k):]); 
                except: continue
                if amt>0: bets[v]=amt
    return bets

@bot.message_handler(commands=["balance"])
def handle_balance(msg):
    uid=msg.from_user.id
    if uid not in user_data: user_data[uid]={"balance":1000,"username":msg.from_user.username or ""}
    bot.reply_to(msg,f"你的余额：💰{user_data[uid]['balance']}")

@bot.message_handler(commands=["add"])
def handle_add(msg):
    if msg.from_user.id!=ADMIN_CHAT_ID: return
    try:
        parts=msg.text.split(); ent=msg.entities[1]
        uname=msg.text[ent.offset:ent.offset+ent.length][1:]
        amt=int(parts[-1])
        for uid,info in user_data.items():
            if info.get("username")==uname:
                info["balance"]+=amt
                return bot.reply_to(msg,f"已为 {uname} 增加 {amt} 💰")
        bot.reply_to(msg,f"未找到用户 {uname}")
    except Exception as e:
        bot.reply_to(msg,f"加钱失败：{e}")

@bot.message_handler(commands=["baccarat"])
def handle_baccarat(msg):
    uid=msg.from_user.id
    if uid not in user_data: user_data[uid]={"balance":1000,"username":msg.from_user.username or ""}
    bets=parse_bets(msg.text)
    if not bets: return bot.reply_to(msg,"用法：/baccarat 闲100 庄对20 超610")
    total=sum(bets.values())
    if total>user_data[uid]["balance"]: return bot.reply_to(msg,"余额不足～")
    p,b=deal_cards(); res=baccarat_result(p,b); s6,rate6=check_super_six(b,res)
    pay=0; txt=f"🎴 发牌：闲{p} vs 庄{b}\n结果：{res.upper()}\n"
    for k,amt in bets.items():
        win=gain=False
        if k=="player" and res=="player": win,gain=True,amt
        elif k=="banker" and res=="banker": win,gain=True,int(amt*0.95)
        elif k=="tie" and res=="tie": win,gain=True,amt*8
        elif k=="player_pair" and p[0]==p[1]: win,gain=True,amt*11
        elif k=="banker_pair" and b[0]==b[1]: win,gain=True,amt*11
        elif k=="super_six" and s6: win,gain=True,amt*rate6
        elif k=="big" and len(p+b) in (5,6): win,gain=True,int(amt*0.54)
        elif k=="small" and len(p+b)==4: win,gain=True,int(amt*1.5)
        if win:
            pay+=gain+amt; txt+=f"✅ 赢[{k}] 获{gain}💰\n"
        else:
            txt+=f"❌ 输[{k}]\n"
    user_data[uid]["balance"]-=total; user_data[uid]["balance"]+=pay
    txt+=f"当前余额：💰{user_data[uid]['balance']}"
    bot.reply_to(msg,txt)

# ───── 启动 ─────────────────────────────────────
def start_polling():
    bot.remove_webhook()
    # 如果未来用 webhook，可在这里设置：
    # if WEBHOOK_URL_BASE: bot.set_webhook(url=WEBHOOK_URL_BASE+WEBHOOK_PATH)
    bot.send_message(ADMIN_CHAT_ID,"✅ 桃奈酱机器人已启动（polling）")
    bot.infinity_polling(timeout=30, long_polling_timeout=5)

if __name__=="__main__":
    Thread(target=start_polling,daemon=True).start()
    # Flask 如不用 webhook，可删以下两行
    @app.route(WEBHOOK_PATH,methods=["POST"])
    def webhook(): return "",200
    app.run(host="0.0.0.0",port=PORT)
