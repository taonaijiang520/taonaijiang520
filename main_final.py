import os, time, logging, sqlite3, random
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from apscheduler.schedulers.background import BackgroundScheduler

# ───── 环境变量 ─────────────────────────
TOKEN            = os.getenv("TOKEN")
ADMIN_CHAT_ID    = int(os.getenv("ADMIN_CHAT_ID"))
PORT             = int(os.getenv("PORT", "10000"))
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE","").rstrip("/")
WEBHOOK_PATH     = "/webhook"

# ───── 日志 & 数据库 ─────────────────────
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
'''); conn.commit()

# ───── Flask + TeleBot ────────────────────
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ───── 心跳 & 看门狗 ───────────────────────
last_hb = time.time()
def heartbeat(): global last_hb; last_hb = time.time()
def watchdog():
    if time.time() - last_hb > 60:
        logging.error("看门狗：60s 无心跳，自杀重启")
        os._exit(1)

sched = BackgroundScheduler()
sched.add_job(heartbeat, "interval", seconds=15)
sched.add_job(watchdog,  "interval", seconds=30)
sched.start()

# ───── 会话 & 余额数据 ─────────────────────
pending = set()
user_data = {}

def record(msg):
    try:
        u = msg.from_user; uid=u.id
        uname, nm = u.username or "", u.first_name or ""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('SELECT 1 FROM users WHERE id=?',(uid,))
        if c.fetchone():
            c.execute('UPDATE users SET username=?,name=?,last_ts=? WHERE id=?',
                      (uname,nm,now,uid))
        else:
            c.execute('INSERT INTO users VALUES(?,?,?,?,?)',
                      (uid,uname,nm,now,now))
        conn.commit()
    except:
        logging.exception("record error")

def get_menu(cid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("开始"), KeyboardButton("状态"))
    kb.row(KeyboardButton("余额"), KeyboardButton("传话"))
    kb.row(KeyboardButton("中文包"), KeyboardButton("游戏"))
    if cid==ADMIN_CHAT_ID:
        kb.row(KeyboardButton("待传话"), KeyboardButton("回复"), KeyboardButton("加款"))
    return kb

def exit_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("退出传话",callback_data="exit"))
    return kb

# ───── /start 欢迎 ─────────────────────────
@bot.message_handler(commands=["start"])
def on_start(msg):
    record(msg); heartbeat()
    cid = msg.chat.id
    bot.send_message(cid,
        "每次你点我都会湿成小猫，快来试试我的湿身中文包♡",
        reply_markup=get_menu(cid)
    )

# ───── /状态 ───────────────────────────────
@bot.message_handler(commands=["状态","status"])
def on_status(msg):
    record(msg); heartbeat()
    msg.reply("✅ 机器人当前在线。")

# ───── /余额 & /加款 ─────────────────────────
@bot.message_handler(commands=["余额","balance"])
def on_balance(msg):
    record(msg); heartbeat()
    uid=msg.from_user.id
    if uid not in user_data:
        user_data[uid]={"balance":1000,"username":msg.from_user.username or ""}
    bot.reply_to(msg,f"你的余额：💰{user_data[uid]['balance']}")

@bot.message_handler(commands=["加款","add"])
def on_add(msg):
    record(msg); heartbeat()
    if msg.from_user.id!=ADMIN_CHAT_ID: return
    parts=msg.text.split(); ent=msg.entities[1]
    name=msg.text[ent.offset:ent.offset+ent.length][1:]
    try: amt=int(parts[-1])
    except: return bot.reply_to(msg,"金额输入不正确")
    for uid,info in user_data.items():
        if info.get("username")==name:
            info["balance"]+=amt
            return bot.reply_to(msg,f"已为 {name} 增加 {amt} 💰")
    bot.reply_to(msg,f"未找到用户 {name}")

# ───── 中文包 按钮 ─────────────────────────
@bot.message_handler(func=lambda m:m.text=="中文包")
def on_chinese(msg):
    record(msg); heartbeat()
    kb=InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("切换桃奈湿身语",url="https://t.me/setlanguage/zhcncc"))
    bot.send_message(msg.chat.id,"点击下方按钮切换▶",reply_markup=kb)

# ───── 游戏菜单 ─────────────────────────────
@bot.message_handler(func=lambda m:m.text=="游戏")
def on_game_menu(msg):
    record(msg); heartbeat()
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎲 百家赌局",callback_data="play_baccarat"))
    bot.send_message(msg.chat.id,"请选择游戏▶",reply_markup=kb)

@bot.callback_query_handler(lambda cq:cq.data=="play_baccarat")
def on_play_baccarat(cq):
    bot.send_message(cq.message.chat.id,
        "输入格式：\n/baccarat 闲100 庄对20 超610 等\n👉 多项可连写")

# ───── 双向传话 ─────────────────────────────
@bot.message_handler(commands=["传话","talkto"])
def on_talkto(msg):
    record(msg); heartbeat()
    uid=msg.chat.id; pending.add(uid)
    bot.send_message(uid,"✅ 已加入传话队列，请发送内容",reply_markup=get_menu(uid))
    bot.send_message(ADMIN_CHAT_ID,f"用户 {uid} 请求传话")

@bot.message_handler(commands=["待传话","pending"])
def on_pending(msg):
    record(msg); heartbeat()
    if msg.from_user.id!=ADMIN_CHAT_ID: return
    if not pending: return bot.reply_to(msg,"当前无请求")
    bot.reply_to(msg,"等待用户：\n"+ "\n".join(str(u) for u in pending))

@bot.message_handler(commands=["回复","reply"])
def on_reply(msg):
    record(msg); heartbeat()
    if msg.from_user.id!=ADMIN_CHAT_ID: return
    parts=msg.text.split(maxsplit=2)
    if len(parts)<3: return bot.reply_to(msg,"格式：/reply 用户ID 内容")
    try: target=int(parts[1])
    except: return bot.reply_to(msg,"用户ID错误")
    bot.send_message(target,f"← 主人回复：{parts[2]}")
    bot.reply_to(msg,"✅ 已回复")

@bot.message_handler(func=lambda m:m.chat.id in pending,content_types=["text"])
def user_to_admin(msg):
    record(msg); heartbeat()
    bot.send_message(ADMIN_CHAT_ID,f"→ 来自 {msg.chat.id}：{msg.text}")

@bot.callback_query_handler(lambda cq:cq.data=="exit")
def on_exit(cq):
    uid=cq.message.chat.id; pending.discard(uid)
    bot.edit_message_reply_markup(uid,cq.message.message_id,reply_markup=None)
    bot.send_message(uid,"🚪 已退出传话模式",reply_markup=get_menu(uid))
    bot.answer_callback_query(cq.id)

# ───── 百家乐玩法 ───────────────────────────
def deal_cards(): return [random.randint(1,9) for _ in range(2)], [random.randint(1,9) for _ in range(2)]
def baccarat_result(p,b): return ("player" if sum(p)%10>sum(b)%10 else "banker" if sum(b)%10>sum(p)%10 else "tie")
def check_super_six(b,w):
    t=sum(b)%10
    if w=="banker" and t==6: return True, (20 if len(b)==3 else 12)
    return False,0
def parse_bets(txt):
    m={"闲":"player","庄":"banker","和":"tie","庄对":"banker_pair","闲对":"player_pair","超6":"super_six","大":"big","小":"small"}
    bets={}
    for part in txt.replace("/baccarat","").split():
        for cn,en in m.items():
            if part.startswith(cn):
                try: a=int(part[len(cn):])
                except: continue
                if a>0: bets[en]=a
    return bets

@bot.message_handler(commands=["baccarat"])
def on_baccarat(msg):
    record(msg); heartbeat()
    uid=msg.from_user.id
    if uid not in user_data: user_data[uid]={"balance":1000,"username":msg.from_user.username or ""}
    bets=parse_bets(msg.text)
    if not bets: return bot.reply_to(msg,"用法：/baccarat 闲100 庄对20 超610 …")
    total=sum(bets.values())
    if total>user_data[uid]["balance"]: return bot.reply_to(msg,"余额不足～")
    p,b=deal_cards(); r=baccarat_result(p,b); s6,rt=check_super_six(b,r)
    payout=0; txt=f"🎴 发牌：闲{p} vs 庄{b}\n结果：{r.upper()}\n"
    for k,a in bets.items():
        win,g= False,0
        if k=="player" and r=="player": win,g=True,a
        elif k=="banker" and r=="banker": win,g=True,int(a*0.95)
        elif k=="tie" and r=="tie": win,g=True,a*8
        elif k=="player_pair" and p[0]==p[1]: win,g=True,a*11
        elif k=="banker_pair" and b[0]==b[1]: win,g=True,a*11
        elif k=="super_six" and s6: win,g=True,a*rt
        elif k=="big" and len(p+b) in (5,6): win,g=True,int(a*0.54)
        elif k=="small" and len(p+b)==4: win,g=True,int(a*1.5)
        if win: payout+=g+a; txt+=f"✅ 赢[{k}] 获{g}💰\n"
        else: txt+=f"❌ 输[{k}]\n"
    user_data[uid]["balance"]-=total; user_data[uid]["balance"]+=payout
    txt+=f"当前余额：💰{user_data[uid]['balance']}"
    bot.reply_to(msg,txt)

# ───── Webhook 接收 ───────────────────────────
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    raw=request.get_data().decode("utf-8")
    update=telebot.types.Update.de_json(raw)
    bot.process_new_updates([update])
    heartbeat()
    return "",200

# ───── 启动 Webhook ───────────────────────────
if __name__=="__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL_BASE+WEBHOOK_PATH)
    logging.info("Webhook 已设置: "+WEBHOOK_URL_BASE+WEBHOOK_PATH)
    app.run(host="0.0.0.0",port=PORT)
