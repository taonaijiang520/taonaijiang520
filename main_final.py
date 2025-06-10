import os, time, logging, sqlite3, random
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand
)
from apscheduler.schedulers.background import BackgroundScheduler

# ───── 环境变量 ─────────────────────────
TOKEN            = os.getenv("TOKEN")
ADMIN_CHAT_ID    = int(os.getenv("ADMIN_CHAT_ID"))
PORT             = int(os.getenv("PORT", "10000"))
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE","").rstrip("/")
WEBHOOK_PATH     = "/webhook"

# ───── 日志 & 用户数据库 ───────────────────
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

# ───── Bot + Flask 初始化 ──────────────────
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ───── Slash Command 列表（输入“/”时可预览） ───
bot.set_my_commands([
    BotCommand("start",  "开始"),
    BotCommand("status", "状态"),
    BotCommand("balance","余额"),
    BotCommand("talkto", "传话"),
    BotCommand("pending","待传话"),
    BotCommand("reply",  "回复"),
    BotCommand("add",    "加款"),
    BotCommand("baccarat","百家乐"),
    BotCommand("签到",   "每日签到"),
])

# ───── 心跳 & 看门狗 ───────────────────────
last_hb = time.time()
def heartbeat(): global last_hb; last_hb = time.time()
def watchdog():
    if time.time()-last_hb>60:
        logging.error("看门狗：60s 无心跳，自杀重启")
        os._exit(1)
sched = BackgroundScheduler()
sched.add_job(heartbeat, "interval", seconds=15)
sched.add_job(watchdog,  "interval", seconds=30)
sched.start()

# ───── 全局状态 ───────────────────────────
pending = set()     # 等待传话的用户
user_data = {}      # {uid:{"balance":int,"username":str}}
user_signins = {}   # {uid: date}

def record_user(msg):
    try:
        u=msg.from_user; uid,u_nm,u_name=u.id,u.username or "",u.first_name or ""
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('SELECT 1 FROM users WHERE id=?',(uid,))
        if c.fetchone():
            c.execute('UPDATE users SET username=?,name=?,last_ts=? WHERE id=?',
                      (u_nm,u_name,now,uid))
        else:
            c.execute('INSERT INTO users(id,username,name,first_ts,last_ts) VALUES(?,?,?,?,?)',
                      (uid,u_nm,u_name,now,now))
        conn.commit()
    except:
        logging.exception("record_user error")

def get_menu(cid):
    kb=ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("开始"), KeyboardButton("状态"))
    kb.row(KeyboardButton("余额"), KeyboardButton("传话"))
    kb.row(KeyboardButton("中文包"), KeyboardButton("游戏"))
    kb.row(KeyboardButton("签到"))
    if cid==ADMIN_CHAT_ID:
        kb.row(KeyboardButton("待传话"), KeyboardButton("回复"), KeyboardButton("加款"))
    return kb

def exit_kb():
    kb=InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("退出传话",callback_data="exit_talk"))
    return kb

# ───── /start & “开始” ─────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    record_user(msg); heartbeat()
    bot.send_message(msg.chat.id,
        "每次你点我都会湿成小猫，快来试试我的湿身中文包♡",
        reply_markup=get_menu(msg.chat.id)
    )
@bot.message_handler(func=lambda m:m.text=="开始")
def btn_start(msg): cmd_start(msg)

# ───── /status & “状态” ───────────────────
@bot.message_handler(commands=["status"])
def cmd_status(msg):
    record_user(msg); heartbeat()
    msg.reply("✅ 机器人当前在线。")
@bot.message_handler(func=lambda m:m.text=="状态")
def btn_status(msg): cmd_status(msg)

# ───── /balance & “余额” ───────────────────
@bot.message_handler(commands=["balance"])
def cmd_balance(msg):
    record_user(msg); heartbeat()
    uid=msg.from_user.id
    if uid not in user_data:
        user_data[uid]={"balance":1000,"username":msg.from_user.username or ""}
    bot.reply_to(msg,f"你的余额：💰{user_data[uid]['balance']}")
@bot.message_handler(func=lambda m:m.text=="余额")
def btn_balance(msg): cmd_balance(msg)

# ───── /add & “加款” ───────────────────────
@bot.message_handler(commands=["add"])
def cmd_add(msg):
    record_user(msg); heartbeat()
    if msg.from_user.id!=ADMIN_CHAT_ID: return
    parts=msg.text.split(); ent=msg.entities[1]
    name=msg.text[ent.offset:ent.offset+ent.length][1:]
    try: amt=int(parts[-1])
    except: return bot.reply_to(msg,"金额必须为整数")
    for uid,info in user_data.items():
        if info.get("username")==name:
            info["balance"]+=amt
            return bot.reply_to(msg,f"已为 {name} 增加 {amt} 💰")
    bot.reply_to(msg,f"未找到用户 {name}")
@bot.message_handler(func=lambda m:m.text=="加款")
def btn_add(msg): cmd_add(msg)

# ───── “中文包” ───────────────────────────
@bot.message_handler(func=lambda m:m.text=="中文包")
def btn_chinese(msg):
    record_user(msg); heartbeat()
    kb=InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("切换桃奈湿身语",url="https://t.me/setlanguage/zhcncc"))
    bot.send_message(msg.chat.id,"点击按钮切换▶",reply_markup=kb)

# ───── “游戏” 子菜单 ─────────────────────
@bot.message_handler(func=lambda m:m.text=="游戏")
def btn_game(msg):
    record_user(msg); heartbeat()
    kb=InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🎲 百家玩法说明",callback_data="baccarat_help"),
        InlineKeyboardButton("🃏 押注游戏说明",callback_data="bet_help")
    )
    bot.send_message(msg.chat.id,"请选择游戏▶",reply_markup=kb)

@bot.callback_query_handler(lambda cq:cq.data=="baccarat_help")
def cb_bac_help(cq):
    heartbeat()
    text=(
        "🎲 百家玩法：\n"
        "闲 1:1  庄 0.95:1  和 8:1\n"
        "闲对/庄对 11:1  超6 12/20:1\n"
        "大 0.54:1  小 1.5:1\n\n"
        "示例：/baccarat 闲100 庄200 和50"
    )
    bot.send_message(cq.message.chat.id,text)

@bot.callback_query_handler(lambda cq:cq.data=="bet_help")
def cb_bet_help(cq):
    heartbeat()
    text=(
        "🃏 押注游戏：\n"
        "命令：押注 牌序[1~3]/豆子额度\n"
        "例: 押注 2/15 或 押注 1/梭哈\n"
        "全押需谨慎，查询余额发送“余额”"
    )
    bot.send_message(cq.message.chat.id,text)

# ───── /签到 & “签到” ───────────────────────
@bot.message_handler(commands=["签到"])
def cmd_sign(msg):
    record_user(msg); heartbeat()
    uid=msg.chat.id; today=datetime.utcnow().date()
    last=user_signins.get(uid)
    if last==today:
        return bot.reply_to(msg,"❌ 今日已签到")
    user_signins[uid]=today
    bal=user_data.setdefault(uid,{"balance":1000})["balance"]
    user_data[uid]["balance"]=bal+10000
    bot.reply_to(msg,f"✅ 签到成功 +10000豆子\n当前余额：{user_data[uid]['balance']}")
@bot.message_handler(func=lambda m:m.text=="签到")
def btn_sign(msg): cmd_sign(msg)

# ───── 双向传话 ───────────────────────────
@bot.message_handler(commands=["talkto"])
def cmd_talkto(msg):
    record_user(msg); heartbeat()
    uid=msg.chat.id; pending.add(uid)
    bot.send_message(uid,"✅ 已加入传话队列，请发送内容",reply_markup=get_menu(uid))
    bot.send_message(ADMIN_CHAT_ID,f"用户 {uid} 请求传话")
@bot.message_handler(func=lambda m:m.text=="传话")
def btn_talkto(msg): cmd_talkto(msg)

@bot.message_handler(commands=["pending"])
def cmd_pending(msg):
    record_user(msg); heartbeat()
    if msg.from_user.id!=ADMIN_CHAT_ID: return
    bot.reply_to(msg,"等待用户：\n"+("\n".join(str(u) for u in pending)) or "无")

@bot.message_handler(func=lambda m:m.text=="待传话")
def btn_pending(msg): cmd_pending(msg)

@bot.message_handler(commands=["reply"])
def cmd_reply(msg):
    record_user(msg); heartbeat()
    if msg.from_user.id!=ADMIN_CHAT_ID: return
    parts=msg.text.split(maxsplit=2)
    if len(parts)<3: return bot.reply_to(msg,"格式：/reply 用户ID 内容")
    try: target=int(parts[1])
    except: return bot.reply_to(msg,"用户ID错误")
    bot.send_message(target,f"← 主人回复：{parts[2]}")
    bot.reply_to(msg,"✅ 已回复")
@bot.message_handler(func=lambda m:m.text=="回复")
def btn_reply(msg): cmd_reply(msg)

@bot.message_handler(func=lambda m:m.chat.id in pending,content_types=["text"])
def user_to_admin(msg):
    record_user(msg); heartbeat()
    bot.send_message(ADMIN_CHAT_ID,f"→ 来自 {msg.chat.id}：{msg.text}")

@bot.callback_query_handler(lambda cq:cq.data=="exit_talk")
def exit_talk(cq):
    uid=cq.message.chat.id; pending.discard(uid)
    bot.edit_message_reply_markup(uid,cq.message.message_id,reply_markup=None)
    bot.send_message(uid,"🚪 已退出传话模式",reply_markup=get_menu(uid))
    bot.answer_callback_query(cq.id)

# ───── 百家乐玩法 ────────────────────────────
def deal_cards(): return [random.randint(1,9) for _ in range(2)], [random.randint(1,9) for _ in range(2)]
def bac_res(p,b): return ("player" if sum(p)%10>sum(b)%10 else "banker" if sum(b)%10>sum(p)%10 else "tie")
def chk_s6(b,w):
    t=sum(b)%10
    if w=="banker" and t==6: return True,(20 if len(b)==3 else 12)
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
def cmd_baccarat(msg):
    record_user(msg); heartbeat()
    uid=msg.chat.id; data=user_data.setdefault(uid,{"balance":1000})
    bets=parse_bets(msg.text)
    if not bets: return bot.reply_to(msg,"用法：/baccarat 闲100 庄20 和10 …")
    tot=sum(bets.values())
    if tot>data["balance"]: return bot.reply_to(msg,"余额不足")
    data["balance"]-=tot
    p,b=deal_cards(); res=bac_res(p,b); s6,rt=chk_s6(b,res)
    payout=0; txt=f"🎴 发牌：闲{p} vs 庄{b}\n结果：{res.upper()}\n"
    for k,a in bets.items():
        w,g=False,0
        if k=="player" and res=="player": w,g=True,a
        elif k=="banker" and res=="banker": w,g=True,int(a*0.95)
        elif k=="tie" and res=="tie": w,g=True,a*8
        elif k=="player_pair" and p[0]==p[1]: w,g=True,a*11
        elif k=="banker_pair" and b[0]==b[1]: w,g=True,a*11
        elif k=="super_six" and s6: w,g=True,a*rt
        elif k=="big" and len(p+b) in (5,6): w,g=True,int(a*0.54)
        elif k=="small" and len(p+b)==4: w,g=True,int(a*1.5)
        if w: payout+=g+a; txt+=f"✅ 赢[{k}] 获{g}💰\n"
        else: txt+=f"❌ 输[{k}]\n"
    data["balance"]+=payout
    txt+=f"当前余额：💰{data['balance']}"
    bot.reply_to(msg,txt)

# ───── Webhook 路由 ───────────────────────────
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    raw=request.get_data().decode("utf-8")
    update=telebot.types.Update.de_json(raw)
    bot.process_new_updates([update])
    heartbeat()
    return "",200

# ───── 启动 Webhook ────────────────────────────
if __name__=="__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL_BASE+WEBHOOK_PATH)
    logging.info("Webhook 已设置: "+WEBHOOK_URL_BASE+WEBHOOK_PATH)
    app.run(host="0.0.0.0",port=PORT)
