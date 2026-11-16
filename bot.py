import aiohttp, asyncio, os, random, time, math, json, hmac, hashlib, html
from pathlib import Path
from urllib.parse import parse_qsl
import asyncpg
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M, WebAppInfo, MenuButtonWebApp, LabeledPrice

TOKEN, DSN = os.environ["BOT_TOKEN"], os.environ["DATABASE_URL"]
ADMIN, URL, START = int(os.getenv("ADMIN_ID", "0")), (os.getenv("WEBAPP_URL") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/"), int(os.getenv("START_BAL", "0"))
RTP, CASE_RTP, UP_RTP, SELL, MINWD, MAXBET, RATE = .95, .9, .9, .85, 50, 1000, .12
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
pool: asyncpg.Pool
games, locks = {}, {}

# ---------- каталог ----------
ITEMS = {}
# обычные подарки Telegram (цены в звёздах — правь под себя)
for k, e, n, v in [("bear", "🧸", "Мишка", 15), ("heart", "💝", "Сердце", 15), ("rose", "🌹", "Роза", 25), ("gift", "🎁", "Подарок", 25),
                   ("cake", "🎂", "Торт", 50), ("bouquet", "💐", "Букет", 50), ("rocket", "🚀", "Ракета", 50), ("champ", "🍾", "Шампанское", 50),
                   ("tree", "🎄", "Ёлка", 50), ("fire", "🎆", "Фейерверк", 50), ("pumpkin", "🎃", "Тыква", 50),
                   ("trophy", "🏆", "Кубок", 100), ("ring", "💍", "Кольцо", 100), ("diamond", "💎", "Алмаз", 100)]:
    ITEMS[k] = {"e": e, "n": n, "v": v, "t": "gift"}
# NFT-подарки
for k, e, n, v in [("nlol", "🍭", "Lol Pop", 120), ("ncane", "🍬", "Candy Cane", 150), ("ncal", "📅", "Desk Calendar", 200), ("ncookie", "🍪", "Cookie Heart", 250),
                   ("nbunny", "🐰", "Jelly Bunny", 300), ("nwine", "🍷", "Spiced Wine", 350), ("nsanta", "🎅", "Santa Hat", 400), ("nbear", "🧸", "Toy Bear", 600),
                   ("ncat", "🐱", "Scared Cat", 900), ("neye", "🧿", "Evil Eye", 1000), ("nlocket", "💖", "Heart Locket", 1500), ("nlamp", "🪔", "Genie Lamp", 2000),
                   ("nwatch", "⌚", "Swiss Watch", 2500), ("ntop", "🎩", "Top Hat", 3000), ("nperf", "🧴", "Perfume Bottle", 3500), ("ncap", "🧢", "Durov's Cap", 4000),
                   ("nskull", "💀", "Electric Skull", 5000), ("npeach", "🍑", "Precious Peach", 6000), ("nsnoop", "🐶", "Snoop Dogg", 8000),
                   ("nrose", "🥀", "Eternal Rose", 9000), ("nsig", "💠", "Signet Ring", 10000), ("ngem", "🔷", "Ion Gem", 12000), ("npepe", "🐸", "Plush Pepe", 15000)]:
    ITEMS[k] = {"e": e, "n": n, "v": v, "t": "nft"}
for s in (10, 25, 50, 100, 250, 500, 1000):
    ITEMS[f"s{s}"] = {"e": "⭐", "n": f"{s} звёзд", "v": s, "t": "star"}


def mkcase(n, col, d):  # цена считается из матожидания → RTP ≈ 90%
    tot = sum(w for _, w in d)
    ev = sum(ITEMS[i]["v"] * w for i, w in d) / tot
    return {"n": n, "c": col, "price": math.ceil(ev / CASE_RTP), "drops": [[i, w / tot] for i, w in sorted(d, key=lambda x: -ITEMS[x[0]]["v"])]}


CASES = sorted([
    mkcase("🧸 Новичок", "#4ade80", [("bear", 30), ("heart", 25), ("rose", 15), ("gift", 15), ("s10", 10), ("cake", 5)]),
    mkcase("🎁 Подарки", "#38bdf8", [("bear", 30), ("heart", 22), ("rose", 14), ("gift", 12), ("cake", 8), ("rocket", 7), ("trophy", 4), ("ring", 3)]),
    mkcase("💐 Романтика", "#fb7185", [("heart", 25), ("rose", 22), ("bouquet", 18), ("ring", 12), ("diamond", 10), ("nlol", 6), ("nlocket", 4), ("ncookie", 3)]),
    mkcase("🍾 Праздник", "#f59e0b", [("cake", 22), ("champ", 20), ("tree", 12), ("fire", 12), ("pumpkin", 10), ("ncane", 8), ("nsanta", 6), ("nwine", 6), ("nbunny", 4)]),
    mkcase("🏆 Золотой", "#facc15", [("trophy", 25), ("ring", 20), ("diamond", 20), ("s100", 15), ("s250", 8), ("nbunny", 7), ("nbear", 5)]),
    mkcase("⭐ Звёздный", "#fde047", [("s10", 25), ("s25", 25), ("s50", 20), ("s100", 15), ("s250", 9), ("s500", 5), ("s1000", 1)]),
    mkcase("💎 Премиум", "#a78bfa", [("s25", 30), ("cake", 20), ("trophy", 18), ("ring", 14), ("s100", 10), ("nbunny", 6), ("nbear", 2)]),
    mkcase("🔮 NFT", "#c084fc", [("s50", 40), ("ring", 20), ("nbunny", 18), ("nbear", 12), ("nlocket", 7), ("ncap", 2.5), ("npepe", .5)]),
    mkcase("🐸 Легенда", "#f43f5e", [("nlocket", 30), ("ncap", 25), ("nlamp", 15), ("ntop", 12), ("nskull", 8), ("nsnoop", 6), ("npepe", 3), ("ngem", 1)]),
], key=lambda c: c["price"])

ACH = {
    "first": ("🎮", "Первая игра", lambda r: r["games"] >= 1), "g50": ("🕹", "50 игр", lambda r: r["games"] >= 50),
    "dep": ("💳", "Первое пополнение", lambda r: r["deps"] >= 1), "case10": ("📦", "10 кейсов", lambda r: r["cases"] >= 10),
    "nft": ("🖼", "Выбил NFT", lambda r: r["nfts"] >= 1), "x10": ("🚀", "Краш x10", lambda r: r["best"] >= 10),
    "up3": ("⬆️", "3 апгрейда", lambda r: r["upg"] >= 3), "wag": ("🔥", "Оборот 1000⭐", lambda r: r["wagered"] >= 1000),
}


class Err(Exception):
    pass


# ---------- db ----------
async def add(uid, n):
    await pool.execute("UPDATE users SET bal=bal+$1 WHERE id=$2", n, uid)


async def charge(uid, n):
    if not await pool.fetchval("UPDATE users SET bal=bal-$1,wagered=wagered+$1 WHERE id=$2 AND bal>=$1 RETURNING 1", n, uid):
        raise Err("Недостаточно звёзд")


def bet_of(p):
    b = int(p["bet"])
    if not 1 <= b <= MAXBET:
        raise Err(f"Ставка 1–{MAXBET}⭐")
    return b


async def check(uid, r):
    have = {x["code"] for x in await pool.fetch("SELECT code FROM ach WHERE uid=$1", uid)}
    new = [c for c, a in ACH.items() if c not in have and a[2](r)]
    for c in new:
        await pool.execute("INSERT INTO ach VALUES($1,$2) ON CONFLICT DO NOTHING", uid, c)
    return new, have | set(new)


def verify(init):
    d = dict(parse_qsl(init, keep_blank_values=True))
    h = d.pop("hash", None)
    if not h or "user" not in d:
        return None
    key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    chk = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
    if not hmac.compare_digest(hmac.new(key, chk.encode(), hashlib.sha256).hexdigest(), h) or time.time() - int(d.get("auth_date", 0)) > 86400:
        return None
    return json.loads(d["user"])


# ---------- краш: общие раунды ----------
CR = {"id": 0, "phase": "bet", "end": 0, "t0": 0, "cp": 1.0, "bets": {}, "hist": []}


def cm():
    return math.exp(RATE * (time.time() - CR["t0"]))


async def cash(uid, b, m):
    b["out"] = m  # помечаем до await — нет двойной выплаты
    await add(uid, int(b["amt"] * m))
    await pool.execute("UPDATE users SET best=GREATEST(best,$1) WHERE id=$2", m, uid)


async def crash_loop():
    while True:
        try:
            CR.update(id=CR["id"] + 1, phase="bet", end=time.time() + 8, bets={}, cp=max(1.0, round(RTP / (1 - random.random()), 2)))
            await asyncio.sleep(8)
            CR.update(phase="run", t0=time.time())
            while cm() < CR["cp"]:
                await asyncio.sleep(.1)
                m = cm()
                for uid, b in list(CR["bets"].items()):
                    if not b["out"] and b["auto"] and b["auto"] <= m and b["auto"] < CR["cp"]:
                        await cash(uid, b, b["auto"])
            CR.update(phase="end", hist=(CR["hist"] + [CR["cp"]])[-12:])
            await asyncio.sleep(4)
        except Exception as e:
            print("crash_loop", e)
            await asyncio.sleep(2)


async def h_cr_state(uid, p):
    c, b = CR, CR["bets"].get(uid)
    d = {"id": c["id"], "phase": c["phase"], "hist": c["hist"], "mine": b and {"amt": b["amt"], "out": b["out"]},
         "bets": [[x["name"], x["amt"], x["out"]] for x in list(c["bets"].values())[-30:]]}
    if c["phase"] == "bet":
        d["left"] = max(0, c["end"] - time.time())
    elif c["phase"] == "run":
        d["age"] = time.time() - c["t0"]
    else:
        d["cp"] = c["cp"]
    return d


async def h_cr_bet(uid, p):
    if CR["phase"] != "bet" or uid in CR["bets"]:
        raise Err("Ставки сейчас не принимаются")
    b, rid = bet_of(p), CR["id"]
    await charge(uid, b)
    if CR["id"] != rid or CR["phase"] != "bet":
        await add(uid, b)
        raise Err("Раунд уже начался")
    auto = float(p.get("auto") or 0)
    CR["bets"][uid] = {"amt": b, "auto": auto if auto >= 1.1 else 0, "out": 0, "name": await pool.fetchval("SELECT name FROM users WHERE id=$1", uid)}
    await pool.execute("UPDATE users SET games=games+1 WHERE id=$1", uid)
    return {}


async def h_cr_out(uid, p):
    b = CR["bets"].get(uid)
    if CR["phase"] != "run" or not b or b["out"] or cm() >= CR["cp"]:
        raise Err("Поздно")
    await cash(uid, b, cm())
    return {}


# ---------- остальные игры ----------
async def h_cfg(uid, p):
    return {"items": ITEMS, "cases": CASES, "ach": {c: [a[0], a[1]] for c, a in ACH.items()}, "rate": RATE, "up": UP_RTP, "sell": SELL, "minwd": MINWD}


async def h_me(uid, p):
    return {}


async def h_case(uid, p):
    c, n = CASES[int(p["i"])], int(p.get("n", 1))
    if n not in (1, 3, 5):
        raise Err("Неверное количество")
    await charge(uid, c["price"] * n)
    out, nfts = [], 0
    for _ in range(n):
        item = random.choices([i for i, _ in c["drops"]], [w for _, w in c["drops"]])[0]
        it, iid = ITEMS[item], None
        if it["t"] == "star":
            await add(uid, it["v"])
        else:
            iid = await pool.fetchval("INSERT INTO inv(uid,item) VALUES($1,$2) RETURNING id", uid, item)
        nfts += it["t"] == "nft"
        out.append({"item": item, "iid": iid})
    await pool.execute("UPDATE users SET cases=cases+$3,games=games+$3,nfts=nfts+$1 WHERE id=$2", nfts, uid, n)
    return {"items": out}


def mm(n, k):
    r = RTP
    for i in range(k):
        r *= (16 - i) / (16 - n - i)
    return r


async def h_state(uid, p):
    g = games.get(uid)
    return {"n": g["n"], "open": sorted(g["open"]), "m": mm(g["n"], len(g["open"]))} if g else {}


async def h_mn_start(uid, p):
    n = int(p["n"])
    if uid in games or n not in (1, 3, 5):
        raise Err("Игра уже идёт")
    b = bet_of(p)
    await charge(uid, b)
    games[uid] = {"b": b, "n": n, "mines": set(random.sample(range(16), n)), "open": set()}
    await pool.execute("UPDATE users SET games=games+1 WHERE id=$1", uid)
    return {}


async def mn_end(uid, g, win):
    games.pop(uid, None)
    w = int(g["b"] * mm(g["n"], len(g["open"]))) if win else 0
    if w:
        await add(uid, w)
    return {"over": True, "w": w, "mines": sorted(g["mines"]), "open": sorted(g["open"])}


async def h_mn_open(uid, p):
    g, i = games.get(uid), int(p["i"])
    if not g or not 0 <= i < 16:
        raise Err("Нет игры")
    if i in g["mines"]:
        return await mn_end(uid, g, False)
    g["open"].add(i)
    if len(g["open"]) == 16 - g["n"]:
        return await mn_end(uid, g, True)
    return {"open": sorted(g["open"]), "m": mm(g["n"], len(g["open"]))}


async def h_mn_cash(uid, p):
    g = games.get(uid)
    if not g or not g["open"]:
        raise Err("Открой хотя бы одну клетку")
    return await mn_end(uid, g, True)


async def h_roul(uid, p):
    if p["pick"] not in ("r", "b", "g"):
        raise Err("Неверно")
    b = bet_of(p)
    await charge(uid, b)
    n = random.randint(0, 14)
    col = "g" if n == 0 else "r" if n <= 7 else "b"
    w = b * (14 if col == "g" else 2) if p["pick"] == col else 0
    if w:
        await add(uid, w)
    await pool.execute("UPDATE users SET games=games+1 WHERE id=$1", uid)
    return {"n": n, "col": col, "w": w}


async def h_up(uid, p):  # апгрейдер: предмет → дороже предмет, шанс = RTP * цена / цена цели
    to = ITEMS[p["to"]]
    cur = await pool.fetchval("DELETE FROM inv WHERE id=$1 AND uid=$2 RETURNING item", int(p["id"]), uid)
    if not cur or to["t"] == "star" or to["v"] <= ITEMS[cur]["v"] * 1.2:
        if cur:
            await pool.execute("INSERT INTO inv(uid,item) VALUES($1,$2)", uid, cur)
        raise Err("Неверная цель")
    ok = random.random() < UP_RTP * ITEMS[cur]["v"] / to["v"]
    if ok:
        await pool.execute("INSERT INTO inv(uid,item) VALUES($1,$2)", uid, p["to"])
    await pool.execute("UPDATE users SET upg=upg+$1,games=games+1,nfts=nfts+$2 WHERE id=$3", int(ok), int(ok and to["t"] == "nft"), uid)
    return {"ok": ok, "item": p["to"]}


async def h_sell(uid, p):
    item = await pool.fetchval("DELETE FROM inv WHERE id=$1 AND uid=$2 RETURNING item", int(p["id"]), uid)
    if not item:
        raise Err("Нет предмета")
    got = int(ITEMS[item]["v"] * SELL)
    await add(uid, got)
    return {"got": got}


async def h_dep(uid, p):
    n = int(p["n"])
    if not 1 <= n <= 10000:
        raise Err("1–10000⭐")
    return {"link": await bot.create_invoice_link(title="Пополнение", description=f"{n} звёзд на баланс", payload=f"dep{n}",
                                                  currency="XTR", prices=[LabeledPrice(label="Звёзды", amount=n)])}


async def notify(wid, uid, txt):
    if ADMIN:
        await bot.send_message(ADMIN, f"💸 #{wid} · {uid} · {txt}", reply_markup=M(inline_keyboard=[[
            B(text="✅ Выплачено", callback_data=f"wa:{wid}"), B(text="❌ Отклонить", callback_data=f"wr:{wid}")]]))


async def h_wd(uid, p):
    n = int(p["n"])
    if n < MINWD:
        raise Err(f"Минимум {MINWD}⭐")
    if not await pool.fetchval("UPDATE users SET bal=bal-$1 WHERE id=$2 AND bal>=$1 RETURNING 1", n, uid):
        raise Err("Недостаточно звёзд")
    wid = await pool.fetchval("INSERT INTO wd(uid,kind,amt) VALUES($1,'stars',$2) RETURNING id", uid, n)
    await notify(wid, uid, f"{n}⭐")
    return {"msg": "⏳ Заявка отправлена"}


async def h_wd_item(uid, p):
    item = await pool.fetchval("DELETE FROM inv WHERE id=$1 AND uid=$2 RETURNING item", int(p["id"]), uid)
    if not item:
        raise Err("Нет предмета")
    wid = await pool.fetchval("INSERT INTO wd(uid,kind,item) VALUES($1,'item',$2) RETURNING id", uid, item)
    await notify(wid, uid, f"{ITEMS[item]['e']} {ITEMS[item]['n']}")
    return {"msg": "⏳ Заявка на вывод отправлена"}


H = {k[2:]: v for k, v in list(globals().items()) if k.startswith("h_")}
LIGHT = {"cfg", "cr_state"}


async def api(req):
    u = verify(req.headers.get("X-Init", ""))
    fn = H.get(req.match_info["act"])
    if not u or not fn:
        return web.json_response({"e": "Открой через Telegram"}, status=401)
    uid = u["id"]
    try:
        p = await req.json() if req.can_read_body else {}
        if req.match_info["act"] in LIGHT:
            return web.json_response(await fn(uid, p))
        async with locks.setdefault(uid, asyncio.Lock()):
            await pool.execute("INSERT INTO users(id,name,bal) VALUES($1,$2,$3) ON CONFLICT DO NOTHING", uid, html.escape(u.get("first_name", "Игрок"))[:20], START)
            out = await fn(uid, p)
            r = await pool.fetchrow("SELECT * FROM users WHERE id=$1", uid)
            new, have = await check(uid, r)
            inv = await pool.fetch("SELECT id,item FROM inv WHERE uid=$1 ORDER BY id DESC LIMIT 300", uid)
            out["me"] = {"name": r["name"], "bal": r["bal"], "wag": r["wagered"], "games": r["games"], "best": r["best"],
                         "ach": sorted(have), "inv": [[x["id"], x["item"]] for x in inv]}
            if new:
                out["new"] = new
            return web.json_response(out)
    except Err as e:
        return web.json_response({"e": str(e)})
    except (ValueError, IndexError, KeyError, TypeError):
        return web.json_response({"e": "Неверный запрос"})


# ---------- бот ----------
@dp.message(CommandStart())
async def start(m):
    await pool.execute("INSERT INTO users(id,name,bal) VALUES($1,$2,$3) ON CONFLICT DO NOTHING", m.from_user.id, html.escape(m.from_user.first_name)[:20], START)
    await m.answer("🎰 Жми, чтобы играть", reply_markup=M(inline_keyboard=[[B(text="🎰 Играть", web_app=WebAppInfo(url=URL))]]))


@dp.pre_checkout_query()
async def pre(q):
    await q.answer(ok=True)


@dp.message(F.successful_payment)
async def paid(m):
    sp, uid = m.successful_payment, m.from_user.id
    if await pool.fetchval("INSERT INTO pay VALUES($1,$2,$3) ON CONFLICT DO NOTHING RETURNING 1", sp.telegram_payment_charge_id, uid, sp.total_amount):
        await pool.execute("UPDATE users SET bal=bal+$1,deps=deps+1 WHERE id=$2", sp.total_amount, uid)
        await m.answer(f"✅ Зачислено {sp.total_amount}⭐")


@dp.callback_query(F.data.regexp(r"^w[ar]:\d+$"))
async def wadm(c):
    if c.from_user.id != ADMIN:
        return await c.answer()
    ok = c.data[1] == "a"
    r = await pool.fetchrow("UPDATE wd SET st=$2 WHERE id=$1 AND st='new' RETURNING *", int(c.data[3:]), "paid" if ok else "rej")
    if not r:
        return await c.answer("Уже обработана")
    if not ok:  # возврат при отказе
        if r["kind"] == "stars":
            await add(r["uid"], r["amt"])
        else:
            await pool.execute("INSERT INTO inv(uid,item) VALUES($1,$2)", r["uid"], r["item"])
    await bot.send_message(r["uid"], "✅ Вывод выполнен" if ok else "❌ Вывод отклонён, всё возвращено")
    await c.message.edit_text(c.message.text + ("\n✅ Выплачено" if ok else "\n❌ Отклонено"))


@dp.message(Command("give"))
async def give(m, command: CommandObject):
    if m.from_user.id == ADMIN:
        try:
            uid, n = map(int, command.args.split())
            await add(uid, n)
            await m.answer("ok")
        except (AttributeError, ValueError):
            await m.answer("/give id сумма")


async def keepalive():  # не даём бесплатному Render-сервису засыпать
    base = os.getenv("RENDER_EXTERNAL_URL")
    if not base:
        return
    async with aiohttp.ClientSession() as ses:
        while True:
            await asyncio.sleep(540)
            try:
                await ses.get(base + "/health")
            except Exception as e:
                print("keepalive", e)


async def main():
    global pool
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=5)
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS users(id BIGINT PRIMARY KEY,name TEXT,bal BIGINT DEFAULT 0,wagered BIGINT DEFAULT 0,games INT DEFAULT 0,
            cases INT DEFAULT 0,upg INT DEFAULT 0,nfts INT DEFAULT 0,deps INT DEFAULT 0,best REAL DEFAULT 0,created TIMESTAMPTZ DEFAULT now());
        CREATE TABLE IF NOT EXISTS inv(id BIGSERIAL PRIMARY KEY,uid BIGINT,item TEXT);
        CREATE INDEX IF NOT EXISTS inv_uid ON inv(uid);
        CREATE TABLE IF NOT EXISTS ach(uid BIGINT,code TEXT,PRIMARY KEY(uid,code));
        CREATE TABLE IF NOT EXISTS pay(id TEXT PRIMARY KEY,uid BIGINT,stars INT);
        CREATE TABLE IF NOT EXISTS wd(id BIGSERIAL PRIMARY KEY,uid BIGINT,kind TEXT,amt INT,item TEXT,st TEXT DEFAULT 'new');""")
    app = web.Application()
    page = Path(__file__).parent / "static" / "index.html"
    app.router.add_get("/", lambda r: web.FileResponse(page, headers={"Cache-Control": "no-cache"}))
    app.router.add_get("/health", lambda r: web.Response(text="ok"))
    app.router.add_post("/api/{act}", api)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "10000"))).start()
    if URL:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🎰 Играть", web_app=WebAppInfo(url=URL)))
    asyncio.create_task(crash_loop())
    asyncio.create_task(keepalive())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
