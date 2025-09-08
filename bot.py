# --- Reto Relámpago LATAM (MVP Pro v2) ---
# Evita repeticiones en la ronda + filtros por categoría/dificultad
# Aiogram 3.x + python-dotenv 1.x

import os, json, random, time, asyncio, logging
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --------------- Config ---------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en .env")

FREE_PER_DAY = 3
QUESTIONS_PER_ROUND = 5
SEED_FILE = "data_seed.json"
SCORES_FILE = "scores.json"

# --------------- Bot ---------------
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

# --------------- Estado en memoria ---------------
# USERS[user_id] = {
#   "day": int, "free": int,
#   "round": {"asked":int, "score":int, "current_correct":int, "queue":list, "total_q":int} | None,
#   "total": int,
#   "daily_claim_day": int | None,
#   "name": str,
#   "cfg": {"category": str|None, "difficulty": str|None}
# }
USERS: dict[int, dict] = {}

def today_key() -> int:
    return int(time.time() // 86400)

def ensure_user(m: Message | CallbackQuery):
    u = m.from_user
    uid = u.id
    day = today_key()
    me = USERS.get(uid)
    if not me:
        me = {
            "day": day,
            "free": FREE_PER_DAY,
            "round": None,
            "total": 0,
            "daily_claim_day": None,
            "name": (u.full_name or str(uid))[:50],
            "cfg": {"category": None, "difficulty": None},
        }
        USERS[uid] = me
    if me["day"] != day:  # reset diario
        me["day"] = day
        me["free"] = FREE_PER_DAY
        me["round"] = None
        me["daily_claim_day"] = None
    return uid, me

# --------------- Preguntas ---------------
DEFAULT_QS = [
    {"q":"¿Cuántos minutos tiene una hora?","a":["30","45","90","60"],"correct":3,"category":"General","difficulty":"Fácil"},
    {"q":"¿Cuál es la capital de Argentina?","a":["La Plata","Córdoba","Buenos Aires","Rosario"],"correct":2,"category":"Geografía","difficulty":"Fácil"},
    {"q":"¿Qué plataforma usa Reels?","a":["Twitch","Reddit","Twitter","Instagram"],"correct":3,"category":"Tecnología","difficulty":"Fácil"},
    {"q":"¿Qué metal es líquido a temperatura ambiente?","a":["Hierro","Calcio","Plomo","Mercurio"],"correct":3,"category":"Ciencia","difficulty":"Media"},
    {"q":"¿Qué empresa creó Android?","a":["Apple","Google","Microsoft","Nokia"],"correct":1,"category":"Tecnología","difficulty":"Media"},
    {"q":"¿De qué universo es Iron Man?","a":["Marvel","DC","Image","Dark Horse"],"correct":0,"category":"Entretenimiento","difficulty":"Fácil"},
    {"q":"¿Dónde se ubicó el Imperio Inca?","a":["Chile","Perú","Colombia","México"],"correct":1,"category":"Historia","difficulty":"Fácil"},
    {"q":"¿Capital azteca?","a":["Capital moche","Capital inca","Capital maya","Tenochtitlán"],"correct":3,"category":"Historia","difficulty":"Media"},
]

def normalize_item(it):
    # Asegurar campos y defaults
    q = it.get("q")
    a = it.get("a")
    c = it.get("correct")
    if not isinstance(a, list) or not isinstance(c, int) or q is None:
        return None
    return {
        "q": q,
        "a": a,
        "correct": c,
        "category": it.get("category", "General"),
        "difficulty": it.get("difficulty", "Normal"),
    }

def load_questions():
    try:
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
            norm = []
            for it in items:
                it2 = normalize_item(it)
                if it2:
                    norm.append(it2)
            return norm if norm else [normalize_item(x) for x in DEFAULT_QS]
    except FileNotFoundError:
        with open(SEED_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_QS, f, ensure_ascii=False, indent=2)
        return [normalize_item(x) for x in DEFAULT_QS]

QUESTIONS = load_questions()

def categories_list():
    return sorted(set(it["category"] for it in QUESTIONS))

def difficulties_list():
    return sorted(set(it["difficulty"] for it in QUESTIONS))

def build_pool(me_cfg):
    cat = me_cfg.get("category")
    diff = me_cfg.get("difficulty")
    pool = QUESTIONS
    if cat:
        pool = [it for it in pool if it["category"] == cat]
    if diff:
        pool = [it for it in pool if it["difficulty"] == diff]
    return pool

def make_round_queue(pool, n):
    # Tomar n preguntas SIN repetición y barajar las respuestas
    # Si hay menos de n, usamos todas.
    n = min(n, len(pool))
    chosen = random.sample(pool, n)  # sin repetición
    queue = []
    for it in chosen:
        idxs = list(range(len(it["a"])))
        random.shuffle(idxs)
        answers = [it["a"][i] for i in idxs]
        correct_pos = idxs.index(it["correct"])
        queue.append({"q": it["q"], "answers": answers, "correct": correct_pos})
    return queue

# --------------- Persistencia de puntajes ---------------
def load_scores():
    try:
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for uid_str, v in data.items():
                uid = int(uid_str)
                if uid not in USERS:
                    USERS[uid] = {
                        "day": today_key(), "free": FREE_PER_DAY, "round": None,
                        "total": int(v.get("total", 0)), "daily_claim_day": None,
                        "name": v.get("name", str(uid))[:50],
                        "cfg": {"category": None, "difficulty": None},
                    }
    except FileNotFoundError:
        pass

def save_scores():
    data = {str(uid): {"name": u["name"], "total": u["total"]} for uid, u in USERS.items()}
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

load_scores()

# --------------- Teclado principal ---------------
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="▶️ Jugar (/play)")],
            [KeyboardButton(text="🎁 Cofre diario (/daily)"), KeyboardButton(text="🏆 Ranking (/rank)")],
            [KeyboardButton(text="⚙️ Filtros (/mode)")]
        ],
        resize_keyboard=True
    )

# --------------- Flujo de ronda ---------------
async def start_round(m: Message):
    uid, me = ensure_user(m)
    if me["free"] <= 0:
        await m.answer("Ya usaste tus partidas gratis hoy. Vuelve mañana o usa /daily.", reply_markup=main_kb())
        return

    pool = build_pool(me["cfg"])
    if not pool:
        await m.answer("No hay preguntas con esos filtros. Ajusta con /cat y /diff", reply_markup=main_kb())
        return

    queue = make_round_queue(pool, QUESTIONS_PER_ROUND)
    if not queue:
        await m.answer("No hay suficientes preguntas para comenzar.", reply_markup=main_kb())
        return

    me["free"] -= 1
    me["round"] = {
        "asked": 0, "score": 0, "current_correct": None,
        "queue": queue, "total_q": len(queue)
    }

    await m.answer(f"▶️ ¡Comienza la ronda! ({len(queue)} preguntas)")
    await ask_next_question(m, me)

async def ask_next_question(m: Message, me: dict):
    r = me["round"]
    i = r["asked"]
    item = r["queue"][i]
    r["current_correct"] = item["correct"]

    kb = InlineKeyboardBuilder()
    for j, txt in enumerate(item["answers"]):
        kb.button(text=txt, callback_data=f"ans:{j}")
    kb.adjust(2)

    await m.answer(f"❓ *Pregunta:*\n{item['q']}", reply_markup=kb.as_markup(), parse_mode="Markdown")

async def finish_round(m: Message, uid: int, me: dict):
    r = me["round"]
    pts = r["score"]
    total_q = r["total_q"]
    me["total"] += pts
    me["round"] = None
    save_scores()

    await m.answer(f"🏁 Ronda terminada: *{pts}/{total_q}* pts.\n"
                   f"Tu puntaje total: *{me['total']}*.",
                   parse_mode="Markdown",
                   reply_markup=main_kb())

# --------------- Handlers básicos ---------------
@dp.message(Command("start"))
async def cmd_start(m: Message):
    uid, me = ensure_user(m)
    await m.answer(
        "¡Bienvenido a *Reto Relámpago LATAM*! ⚡\n\n"
        f"Tienes *{me['free']}* partidas gratis hoy.\n"
        "Comandos:\n"
        "• /play – jugar 1 ronda\n"
        "• /daily – cofre diario (+1 partida)\n"
        "• /rank – ver ranking\n"
        "• /cat – elegir categoría\n"
        "• /diff – elegir dificultad\n"
        "• /mode – ver filtros actuales\n"
        "• /help – ayuda",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )

@dp.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer("Responde 5 preguntas por ronda (sin repetirse). Usa /cat y /diff para filtrar. ¡Suerte!", reply_markup=main_kb())

@dp.message(Command("play"))
async def cmd_play(m: Message):
    await start_round(m)

@dp.message(F.text.startswith("▶️ Jugar"))
async def btn_play(m: Message):
    await start_round(m)

@dp.callback_query(F.data.startswith("ans:"))
async def on_answer(cb: CallbackQuery):
    uid, me = ensure_user(cb)
    if not me["round"]:
        await cb.answer("No hay una ronda activa. Usa /play.", show_alert=True)
        return

    try:
        _, choice_str = cb.data.split(":", 1)
        chosen = int(choice_str)
    except Exception:
        await cb.answer()
        return

    correct = me["round"]["current_correct"]
    if correct is None:
        await cb.answer()
        return

    if chosen == correct:
        me["round"]["score"] += 1
        await cb.message.answer("✅ ¡Correcto!")
    else:
        await cb.message.answer("❌ Incorrecto. ¡A la próxima!")

    me["round"]["asked"] += 1
    await cb.answer()

    if me["round"]["asked"] >= me["round"]["total_q"]:
        await finish_round(cb.message, uid, me)
    else:
        await ask_next_question(cb.message, me)

@dp.message(Command("daily"))
async def cmd_daily(m: Message):
    uid, me = ensure_user(m)
    day = today_key()
    if me["daily_claim_day"] == day:
        await m.answer("Ya reclamaste tu cofre diario hoy.", reply_markup=main_kb())
        return
    me["daily_claim_day"] = day
    me["free"] += 1
    await m.answer("🎁 ¡Cofre diario abierto! +1 partida añadida.", reply_markup=main_kb())

@dp.message(F.text.startswith("🎁 Cofre diario"))
async def btn_daily(m: Message):
    await cmd_daily(m)

@dp.message(Command("rank"))
async def cmd_rank(m: Message):
    top = sorted(USERS.items(), key=lambda kv: kv[1].get("total", 0), reverse=True)[:10]
    if not top:
        await m.answer("Aún no hay puntajes. ¡Sé el primero!", reply_markup=main_kb())
        return
    lines = [f"🏆 *Ranking semanal*"]
    for i, (uid, u) in enumerate(top, start=1):
        lines.append(f"{i}. {u['name']} — *{u.get('total',0)}* pts")
    await m.answer("\n".join(lines), parse_mode="Markdown", reply_markup=main_kb())

@dp.message(F.text.startswith("🏆 Ranking"))
async def btn_rank(m: Message):
    await cmd_rank(m)

# --------------- Filtros: categoría/dificultad ---------------
@dp.message(Command("mode"))
async def cmd_mode(m: Message):
    uid, me = ensure_user(m)
    c = me["cfg"]["category"] or "Todas"
    d = me["cfg"]["difficulty"] or "Todas"
    await m.answer(f"⚙️ Filtros actuales:\n• Categoría: *{c}*\n• Dificultad: *{d}*",
                   parse_mode="Markdown", reply_markup=main_kb())

@dp.message(Command("cat"))
async def cmd_cat(m: Message):
    uid, me = ensure_user(m)
    cats = categories_list()
    kb = InlineKeyboardBuilder()
    kb.button(text="Todas", callback_data="setcat:__ALL__")
    for c in cats:
        kb.button(text=c, callback_data=f"setcat:{c}")
    kb.adjust(3)
    await m.answer("Elige categoría:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("setcat:"))
async def on_setcat(cb: CallbackQuery):
    uid, me = ensure_user(cb)
    val = cb.data.split(":",1)[1]
    me["cfg"]["category"] = None if val == "__ALL__" else val
    await cb.message.answer(f"✅ Categoría seleccionada: {me['cfg']['category'] or 'Todas'}")
    await cb.answer()

@dp.message(Command("diff"))
async def cmd_diff(m: Message):
    uid, me = ensure_user(m)
    diffs = difficulties_list() or ["Fácil","Media","Difícil","Normal"]
    kb = InlineKeyboardBuilder()
    kb.button(text="Todas", callback_data="setdiff:__ALL__")
    for d in diffs:
        kb.button(text=d, callback_data=f"setdiff:{d}")
    kb.adjust(3)
    await m.answer("Elige dificultad:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("setdiff:"))
async def on_setdiff(cb: CallbackQuery):
    uid, me = ensure_user(cb)
    val = cb.data.split(":",1)[1]
    me["cfg"]["difficulty"] = None if val == "__ALL__" else val
    await cb.message.answer(f"✅ Dificultad seleccionada: {me['cfg']['difficulty'] or 'Todas'}")
    await cb.answer()

# --------------- Main ---------------
async def main():
    me = await bot.get_me()
    logging.info(f"Conectado como @{me.username} (id {me.id}) - '{me.first_name}'")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
