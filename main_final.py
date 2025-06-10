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

# ───── 环境变量 ─────────────────────────────────
TOKEN            = os.getenv("TOKEN")                       # Telegram Bot Token
ADMIN_CHAT_ID    = int(os.getenv("ADMIN_CHAT_ID"))          # 管理员 Chat ID
PORT             = int(os.getenv("PORT", 5000))             # Flask 监听端口
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE", "").rstrip("/")  # 你的 https://*.onrender.com
WEBHOOK_PATH     = "/webhook"  # 不要改

# ───── 日志 & DB ──────────────────────────────────
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

# ───── Flask + TeleBot ─────────────────────────────
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# 心跳 & 看门狗
last_update = time.time()
def heartbeat():
    global last_update
    last_update = time.time()
def watchdog():
    if time.time() - last_update > 60:
        logging.error("看门狗：超过 60s 未收到消息，自杀重启")
        os._exit(1)

sched = BackgroundScheduler()
sched.add_job(heartbeat, "interval", seconds=15)
sched.add_job(watchdog,  "interval", seconds=30)
sched.start()

# 双向传话管理
forward_sessions = {}
session_ts = {}
SESSION_TIMEOUT = 300

def record(msg):
    try:
        u, now = msg.from_user, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        uid, uname, nm = u.id, u.username or "", u.first_name or ""
        c.execute('SELECT 1 FROM users WHERE id=?',(uid,))
        if c.fetchone():
            c.execute('UPDATE users SET username=?,name=?,last_ts=? WHERE id=?',
                      (uname,nm,now,uid))
        else:
            c.execute('INSERT INTO users(id,username,name,first_ts,last_ts) VALUES(?,?,?,?,?)',
                      (uid,uname,nm,now,now))
        conn.commit()
    except:
        logging.exception("record error")

def get_menu(cid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🐾 桃奈语"),KeyboardButton("🐾 双向传话"))
    if cid==ADMIN_CHAT_ID:
        kb.row(KeyboardButton("🐾 开发者入口"),KeyboardButton("/status"))
    return kb

def exit_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("退出双向传话",callback_data="exit_forward"))
    return kb

# ───── /start 欢迎 ───────────────────────────────
@bot.message_handler(commands=["start"])
def on_start(msg):
    record(msg); heartbeat()
    cid = msg.chat.id
    bot.send_message(cid,
        "每次你点我都会湿成小猫，快来试试我的湿身中文包♡",
        reply_markup=get_menu(cid))
    kb = InlineKeyboardMarkup(); kb.add(
        InlineKeyboardButton("🐾 桃奈语",url="https://t.me/setlanguage/zhcncc"))
    bot.send_message(cid,
        "点下面的「🐾 桃奈语」立即切换到【桃奈湿身语】",
        reply_markup=kb)
    if cid==ADMIN_CHAT_ID:
        bot.send_message(ADMIN_CHAT_ID,"✅ 机器人上线通知")

# ───── /status ───────────────────────────────────
@bot.message_handler(commands=["status"])
def on_status(msg):
    record(msg); heartbeat()
    msg.reply("✅ 桃奈酱机器人当前在线。")

# ───── 文本 & 双向传话 ───────────────────────────
@bot.message_handler(func=lambda m:True,content_types=["text"])
def on_text(msg):
    record(msg); heartbeat()
    cid, txt, now = msg.chat.id, msg.text.strip(), datetime.utcnow()

    if txt=="🐾 桃奈语":
        kb=InlineKeyboardMarkup(); kb.add(
            InlineKeyboardButton("🐾 桃奈语",url="https://t.me/setlanguage/zhcncc"))
        return bot.send_message(cid,
            "点下面的「🐾 桃奈语」立即切换到【桃奈湿身语】",reply_markup=kb)

    if txt=="🐾 双向传话":
        forward_sessions[cid]="PENDING"
        session_ts[cid]=now
        return bot.send_message(cid,"请发送要传达给主人的内容：",reply_markup=get_menu(cid))

    if txt=="🐾 开发者入口" and cid==ADMIN_CHAT_ID:
        rows=c.execute('SELECT id,username,name,first_ts,last_ts FROM users').fetchall()
        lines=["📊 用户列表："]
        for i,(uid,un,nm,ft,lt) in enumerate(rows,1):
            lines.append(f"{i}.ID:{uid}|@{un or '—'}|{nm or '—'}")
            lines.append(f"   首次:{ft}|最近:{lt}")
        return bot.send_message(cid,"\n".join(lines),reply_markup=get_menu(cid))

    state=forward_sessions.get(cid)
    if state=="PENDING":
        forward_sessions[cid]=ADMIN_CHAT_ID
        forward_sessions[ADMIN_CHAT_ID]=cid
        session_ts[cid]=session_ts[ADMIN_CHAT_ID]=now
        bot.send_message(ADMIN_CHAT_ID,
            f"→ 来自 @{msg.from_user.username or msg.from_user.first_name}：{txt}",
            reply_markup=exit_kb())
        return bot.send_message(cid,
            "✅ 已发送，双向传话模式",reply_markup=get_menu(cid))

    if state and state!="PENDING":
        partner=state
        session_ts[cid]=session_ts[partner]=now
        return bot.send_message(partner,
            f"← 来自 @{msg.from_user.username or msg.from_user.first_name}：{txt}",
            reply_markup=exit_kb())

    bot.send_message(cid,"🐾 未识别指令，请从菜单选择",reply_markup=get_menu(cid))

@bot.callback_query_handler(lambda cq:cq.data=="exit_forward")
def on_exit(cq):
    cid=cq.message.chat.id; partner=forward_sessions.pop(cid,None)
    session_ts.pop(cid,None)
    if partner:
        forward_sessions.pop(partner,None); session_ts.pop(partner,None)
        bot.send_message(partner,"🚪 对方已退出传话",reply_markup=get_menu(partner))
    bot.edit_message_reply_markup(cid,cq.message.message_id,reply_markup=None)
    bot.send_message(cid,"🚪 退出传话",reply_markup=get_menu(cid))
    bot.answer_callback_query(cq.id)

# ───── 百家乐 ────────────────────────────────────
def deal(): return [random.randint(1,9) for _ in range(2)], [random.randint(1,9) for _ in range(2)]
def result(p,b):
    return "player" if sum(p)%10>sum(b)%10 else "banker" if sum(b)%10>sum(p)%10 else "tie"
def super6(b,w):
    t=sum(b)%10
    return (True,20 if len(b)==3 else 12) if w=="banker" and t==6 else (False,0)
def parse_bets(txt):
    m={"闲":"player","庄":"banker","和":"tie","庄对":"banker_pair",
       "闲对":"player_pair","超6":"super_six","大":"big","小":"small"}
    bets={}
    for part in txt.replace("/baccarat","").split():
        for k,v in m.items():
            if part.startswith(k):
                try: a=int(part[len(k):])
                except: continue
                if a>0: bets[v]=a
    return bets

@bot.message_handler(commands=["balance"])
def on_bal(m):
    uid=m.from_user.id
    if uid not in user_data: user_data[uid]={"balance":1000,"username":m.from_user.username or ""}
    bot.reply_to(m,f"你的余额：💰{user_data[uid]['balance']}")

@bot.message_handler(commands=["add"])
def on_add(m):
    if m.from_user.id!=ADMIN_CHAT_ID: return
    try:
        parts=m.text.split(); ent=m.entities[1]
        un=m.text[ent.offset:ent.offset+ent.length][1:]; a=int(parts[-1])
        for uid,info in user_data.items():
            if info.get("username")==un:
                info["balance"]+=a
                return bot.reply_to(m,f"已为 {un} 增加 {a} 💰")
        bot.reply_to(m,f"未找到用户 {un}")
    except Exception as e:
        bot.reply_to(m,f"加钱失败：{e}")

@bot.message_handler(commands=["baccarat"])
def on_bac(m):
    uid=m.from_user.id
    if uid not in user_data: user_data[uid]={"balance":1000,"username":m.from_user.username or ""}
    bets=parse_bets(m.text)
    if not bets: return bot.reply_to(m,"用法：/baccarat 闲100 庄对20 超610")
    tot=sum(bets.values())
    if tot>user_data[uid]["balance"]: return bot.reply_to(m,"余额不足")
    p,b=deal(); r=result(p,b); s6,rt=super6(b,r)
    pay=0; txt=f"🎴 发牌：闲{p} vs 庄{b}\n结果：{r.upper()}\n"
    for k,a in bets.items():
        w,g=False,0
        if k=="player" and r=="player": w,g=True,a
        elif k=="banker" and r=="banker": w,g=True,int(a*0.95)
        elif k=="tie" and r=="tie": w,g=True,a*8
        elif k=="player_pair" and p[0]==p[1]: w,g=True,a*11
        elif k=="banker_pair" and b[0]==b[1]: w,g=True,a*11
        elif k=="super_six" and s6: w,g=True,a*rt
        elif k=="big" and len(p+b) in (5,6): w,g=True,int(a*0.54)
        elif k=="small" and len(p+b)==4: w,g=True,int(a*1.5)
        if w: pay+=g+a; txt+=f"✅ 赢[{k}] 获{g}💰\n"
        else: txt+=f"❌ 输[{k}]\n"
    user_data[uid]["balance"]-=tot; user_data[uid]["balance"]+=pay
    txt+=f"当前余额：💰{user_data[uid]['balance']}"
    bot.reply_to(m,txt)

# ───── Webhook 启动 ──────────────────────────────
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    raw=request.get_data().decode("utf-8")
    update=telebot.types.Update.de_json(raw)
    bot.process_new_updates([update])
    heartbeat()
    return "",200

if __name__=="__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL_BASE+WEBHOOK_PATH)
    logging.info(f"Webhook 已设置: {WEBHOOK_URL_BASE+WEBHOOK_PATH}")
    # 等待 Telegram 推送
    app.run(host="0.0.0.0", port=PORT)
