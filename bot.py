# --- Reto Relámpago LATAM (versión PRO) ---
import os, json, random, time, sqlite3, logging, asyncio
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ----------------- Config -----------------
load_dotenv()  # Lee .env si existe

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en variables de entorno o .env")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
FREE_PER_DAY = 3             # rondas gratis por día
QUESTIONS_PER_ROUND = 5      # preguntas por ronda

# Bonus de puntos por dificultad
DIFF_BONUS = {"facil": 1, "media": 2, "dificil": 3}

# Categorías y niveles permitidos (para validación y ayuda)
CATEGORIES = {"geografia","ciencia","entretenimiento","historia","tecnologia","arte","deportes"}
LEVELS = {"facil","media","dificil"}

SEED_FILE = "data_seed.json"
DB_FILE = "scores.db"

# Memoria de sesión por usuario (para la ronda en curso)
SESSIONS = {}  # uid -> {"n": int, "score": int, "cat": str|None, "diff": str|None}

# ----------------- DB -----------------
def db():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            total_pts   INTEGER DEFAULT 0,
            day_key     INTEGER DEFAULT 0,
            free_left   INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def today_key():
    return int(time.time() // 86400)

def get_user(uid: int, username: str):
    conn = db()
    cur = conn.cursor()
    row = cur.execute("SELECT user_id, username, total_pts, day_key, free_left FROM users WHERE user_id=?",
                      (uid,)).fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id, username, total_pts, day_key, free_left) VALUES(?,?,?,?,?)",
                    (uid, username, 0, 0, 0))
        conn.commit()
        row = cur.execute("SELECT user_id, username, total_pts, day_key, free_left FROM users WHERE user_id=?",
                          (uid,)).fetchone()

    # Reinicio diario de rondas gratis
    u_id, u_name, pts, dkey, free_left = row
    tkey = today_key()
    if dkey != tkey:
        free_left = FREE_PER_DAY
        dkey = tkey
        cur.execute("UPDATE users SET day_key=?, free_left=?, username=? WHERE user_id=?",
                    (dkey, free_left, username, uid))
        conn.commit()

    conn.close()
    return {"user_id": u_id, "username": u_name, "total_pts": pts, "day_key": dkey, "free_left": free_left}

def dec_free_round(uid: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET free_left = CASE WHEN free_left>0 THEN free_left-1 ELSE 0 END WHERE user_id=?",
                (uid,))
    conn.commit()
    conn.close()

def add_points(uid: int, delta: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET total_pts = total_pts + ? WHERE user_id=?", (delta, uid))
    conn.commit()
    conn.close()

def top_users(limit=10):
    conn = db()
    cur = conn.cursor()
    rows = cur.execute("SELECT username, total_pts FROM users ORDER BY total_pts DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows

# ----------------- Preguntas -----------------
def load_questions():
    try:
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
    except FileNotFoundError:
        items = []
    norm = []
    for it in items:
        if all(k in it for k in ("q","a","correct","category","difficulty")):
            norm.append({"q": it["q"], "a": it["a"], "correct": it["correct"],
                         "category": it["category"].lower(), "difficulty": it["difficulty"].lower()})
    return norm

QUESTIONS = load_questions()

def pick_question(category: str|None = None, difficulty: str|None = None):
    pool = QUESTIONS
    if category:
        pool = [q for q in pool if q["category"] == category]
    if difficulty:
        pool = [q for q in pool if q["difficulty"] == difficulty]
    if not pool:
        pool = QUESTIONS[:]  # fallback a todo
    item = random.choice(pool)
    # barajar respuestas
    idxs = list(range(len(item["a"])))
    random.shuffle(idxs)
    answers = [ item["a"][i] for i in idxs ]
    correct_new_pos = idxs.index(item["correct"])
    return item["q"], answers, correct_new_pos, item["difficulty"]

# ----------------- Bot -----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

def fmt_cmds():
    return (
        "Comandos:\n"
        "• /play [categoria] [nivel] – jugar 1 ronda (5 preguntas)\n"
        "   Ej: /play ciencia media\n"
        "• /daily – reclamar regalo diario (+1 ronda)\n"
        "• /rank – ver ranking\n"
        "• /help – ayuda\n\n"
        f"Categorías: {', '.join(sorted(CATEGORIES))}\n"
        f"Dificultades: {', '.join(sorted(LEVELS))}"
    )

@dp.message(Command("start"))
async def cmd_start(m: Message):
    u = get_user(m.from_user.id, m.from_user.username or m.from_user.full_name)
    await m.answer(
        f"¡Bienvenido a Reto Relámpago LATAM! ⚡\n\n"
        f"Tienes {u['free_left']} partidas gratis hoy.\n\n" + fmt_cmds()
    )

@dp.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer("Ayuda 📖\n\n" + fmt_cmds())

@dp.message(Command("daily"))
async def cmd_daily(m: Message):
    # +1 ronda gratis por día (una vez al día)
    u = get_user(m.from_user.id, m.from_user.username or m.from_user.full_name)
    # Regla simple: si ya reclamó (tiene FREE_PER_DAY tras reset), no sumes infinito
    # aquí permitimos sumar +1 hasta un máximo de FREE_PER_DAY+1
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET free_left = MIN(free_left + 1, ?) WHERE user_id=?",
                (FREE_PER_DAY + 1, u["user_id"]))
    conn.commit()
    conn.close()
    u2 = get_user(m.from_user.id, m.from_user.username or m.from_user.full_name)
    await m.answer(f"🎁 ¡Cofre diario reclamado! Partidas disponibles hoy: {u2['free_left']}")

def parse_play_args(args: str|None):
    cat = diff = None
    if args:
        parts = [p.strip().lower() for p in args.split() if p.strip()]
        for p in parts:
            if p in CATEGORIES: cat = p
            if p in LEVELS:     diff = p
    return cat, diff

async def ask_next(m: Message, uid: int):
    s = SESSIONS[uid]
    q, answers, correct_pos, q_diff = pick_question(s["cat"], s["diff"])
    # guardar correct_pos para esta pregunta
    s["correct"] = correct_pos
    SESSIONS[uid] = s

    kb = InlineKeyboardBuilder()
    for i, ans in enumerate(answers):
        kb.button(text=ans, callback_data=f"ans:{correct_pos}:{i}:{uid}")
    kb.adjust(2,2)

    await m.answer(f"❓ *Pregunta*:\n{q}", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.message(Command("play"))
async def cmd_play(m: Message, command: CommandObject):
    uid = m.from_user.id
    uname = m.from_user.username or m.from_user.full_name
    u = get_user(uid, uname)

    if u["free_left"] <= 0:
        await m.answer("Hoy ya usaste tus partidas gratis. Vuelve mañana o usa /daily para ganar una ronda extra.")
        return

    # parsear filtros opcionales
    cat, diff = parse_play_args(command.args)
    if cat and cat not in CATEGORIES:
        await m.answer(f"Categoría no válida. Usa: {', '.join(sorted(CATEGORIES))}")
        return
    if diff and diff not in LEVELS:
        await m.answer(f"Dificultad no válida. Usa: {', '.join(sorted(LEVELS))}")
        return

    # descontar la ronda
    dec_free_round(uid)
    SESSIONS[uid] = {"n": 0, "score": 0, "cat": cat, "diff": diff}

    await m.answer(f"▶️ ¡Comienza la ronda! (5 preguntas)\n"
                   f"Filtros: "
                   f"{'categoría='+cat if cat else 'categoría: todas'} | "
                   f"{'nivel='+diff if diff else 'nivel: todos'}")

    await ask_next(m, uid)

@dp.callback_query(F.data.startswith("ans:"))
async def on_answer(cb: CallbackQuery):
    try:
        _, correct_pos, chosen, uid_s = cb.data.split(":")
        correct_pos = int(correct_pos); chosen = int(chosen); uid = int(uid_s)
    except Exception:
        await cb.answer()
        return

    # ignorar si no es su sesión
    if cb.from_user.id != uid or uid not in SESSIONS:
        await cb.answer()
        return

    s = SESSIONS[uid]
    # evaluar
    if chosen == s["correct"]:
        s["score"] += 1
        await cb.message.answer("✅ ¡Correcto!")
    else:
        await cb.message.answer("❌ Incorrecto. ¡A la próxima!")

    s["n"] += 1
    SESSIONS[uid] = s
    await cb.answer()

    if s["n"] < QUESTIONS_PER_ROUND:
        await ask_next(cb.message, uid)
    else:
        # fin de ronda
        puntos = s["score"]
        # bonus por dificultad si hubo filtro
        if s["diff"] in DIFF_BONUS:
            puntos += DIFF_BONUS[s["diff"]]
        add_points(uid, puntos)
        await cb.message.answer(f"🏁 Ronda terminada: {s['score']}/{QUESTIONS_PER_ROUND} pts.\n"
                                f"Bonus dificultad: {DIFF_BONUS.get(s['diff'],0)}\n"
                                f"Total agregado: {puntos} pts.\n"
                                f"Usa /rank para ver el marcador.")
        del SESSIONS[uid]

@dp.message(Command("rank"))
async def cmd_rank(m: Message):
    rows = top_users(10)
    if not rows:
        await m.answer("No hay puntajes aún. ¡Juega con /play!")
        return
    txt = ["🏆 Ranking semanal"]
    pos = 1
    for name, pts in rows:
        alias = name or "Jugador"
        txt.append(f"{pos}. {alias} — {pts} pts")
        pos += 1
    await m.answer("\n".join(txt))

async def main():
    init_db()
    # Log de identidad del bot
    me = await bot.me()
    logging.info(f"Conectado como @{me.username} (id {me.id})")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
