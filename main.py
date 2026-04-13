import discord
from discord import app_commands, ui
from discord.ext import commands
import os
import io
import json
import asyncio
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# ─────────────────────────────────────────────
# КОНФИГ — вставь свои URL и тексты
# ─────────────────────────────────────────────

# Гифка при одобрении заявки (в ЛС)
APPROVE_GIF_URL = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExZ3VyczN2em04d3JxNTB1eWlvaWJnczl4dTdpeTZjY2g2MTFwN3NveiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3ndAvMC5LFPNMCzq7m/giphy.gif"

# Фото в АФК-панели (embed)
AFK_IMAGE_URL = "https://i.imgur.com/umswh4i.gif"

FOOTER_ICON = "https://i.imgur.com/nS7FHDR.png"

DEFAULT_TICKET_TITLE = "📋 Вступление в DIAMOND"
DEFAULT_TICKET_DESC  = (
    "**TICKET OPEN MURRIETA**\n"
    "Набор в семью открыт на серверах: **Murrieta**\n\n"
    "Для тех кто играет **ВЗП**:\n"
    "Полный откат с 2 терр обновленного ВЗП и откат любого ДМ/архивы взп не позднее месячной давности.\n"
    "Для тех кто играет **РП**:\n"
    "Откаты с поставок/взх и откат любого ДМ не позднее месячной давности."
)
DEFAULT_TICKET_IMAGE = "https://i.imgur.com/umswh4i.gif"

# ─────────────────────────────────────────────
# ХРАНИЛИЩЕ
# ─────────────────────────────────────────────
DATA_FILE = "data.json"

# { message_id: { "title": str, "max": int, "slots": {slot_num: user_id|None},
#                 "image_url": str|None, "note": str|None, "channel_id": int,
#                 "thread_id": int|None, "thread_msg_id": int|None } }
event_lists: dict = {}

# { guild_id: { "message_id": int, "channel_id": int } }
afk_panels: dict = {}

# 📣 РОЛЬ ДЛЯ ТЕГА В РЕАКИ
# { guild_id: int (role_id) }
event_roles: dict = {}

# { guild_id: { user_id: { "reason": str, "return_time": str, "since": datetime } } }
afk_list: dict = {}

# { guild_id: { "message_id": int, "channel_id": int } }
inactive_panels: dict = {}

# { guild_id: { user_id: { "reason": str, "return_date": str, "since": datetime } } }
inactive_list: dict = {}

# 💰 БАЛЛЫ И ШТРАФЫ
# { guild_id: { user_id: int } }
points_db: dict = {}

# { guild_id: { user_id: { "warns": int, "reason": str, "moderator": int } } }
warns_db: dict = {}

# { guild_id: { 1: role_id, 2: role_id, 3: role_id } }
warn_roles: dict = {}

# 🛒 ПАНЕЛЬ МАГАЗИНА
# { guild_id: { "channel_id": int, "message_id": int } }
shop_panels: dict = {}

# 🎫 ПАНЕЛЬ ТИКЕТОВ
# { guild_id: { "panel_channel_id": int, "review_channel_id": int, "message_id": int } }
ticket_panels: dict = {}

# 🎫 ТЕКСТ ПАНЕЛИ ТИКЕТОВ { guild_id: { "title": str, "desc": str, "image": str } }
ticket_texts: dict = {}

# 🎫 СЧЁТЧИК ТИКЕТОВ { guild_id: int }
ticket_counters: dict = {}

# 📋 КАНАЛ ЛОГОВ ОТКАЗОВ { guild_id: channel_id }
reject_log_channels: dict = {}

# 🎫 РОЛЬ ТИКЕТ-МЕНЕДЖЕРА (может одобрять/отклонять) { guild_id: role_id }
ticket_manager_roles: dict = {}

# 🎫 РОЛИ С ДОСТУПОМ К ТИКЕТУ (видят канал) { guild_id: [role_id, ...] }
ticket_viewer_roles: dict = {}

# 🎫 РОЛЬ ДЛЯ ТЕГА В ТИКЕТЕ { guild_id: role_id }
ticket_ping_role: dict = {}

# 🏎 РОЛЬ МП { guild_id: role_id }
mp_roles: dict = {}

# 🔫 РОЛЬ ВЗП { guild_id: role_id }
vzp_roles: dict = {}

# 🎯 РОЛИ ДОСТУПА К КОМАНДАМ СБОРОВ { guild_id: { "взп": [role_id,...], "мп": [...], "реаки": [...] } }
event_command_roles: dict = {}

# 🔒 ПРИВАТНЫЕ КОМНАТЫ
# { guild_id: { "create_channel_id": int, "category_id": int, "panel_channel_id": int } }
private_vc_settings: dict = {}

# { vc_channel_id: { "owner_id": int, "guild_id": int, "panel_msg_id": int|None, "panel_channel_id": int|None } }
private_vcs: dict = {}

# 🛒 ТОВАРЫ МАГАЗИНА per-guild
# { guild_id: { item_id: { "name": str, "price": int, "emoji": str, "description": str,
#               "action": "remove_warn"|"give_role"|"notify", "role_id": int|None } } }
guild_shop_items: dict = {}

# 🔑 РОЛЬ АДМИНИСТРАТОРА { guild_id: role_id }
admin_roles: dict = {}


# ─────────────────────────────────────────────
# ПРОВЕРКИ ПРАВ
# ─────────────────────────────────────────────
def is_admin(interaction: discord.Interaction) -> bool:
    """Для slash-команд. Если роль не настроена — требует Discord-администратора."""
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    admin_role_id = admin_roles.get(interaction.guild_id)
    if admin_role_id:
        return any(role.id == admin_role_id for role in member.roles)
    return member.guild_permissions.administrator

def is_admin_ctx(ctx) -> bool:
    """Для prefix-команд. Если роль не настроена — требует Discord-администратора."""
    admin_role_id = admin_roles.get(ctx.guild.id)
    if admin_role_id:
        return any(r.id == admin_role_id for r in ctx.author.roles)
    return ctx.author.guild_permissions.administrator

def can_run_event(ctx, event_type: str) -> bool:
    """Проверка доступа к командам сборов (!взп, !мп, !реаки). Админ всегда может."""
    if is_admin_ctx(ctx):
        return True
    allowed = event_command_roles.get(ctx.guild.id, {}).get(event_type, [])
    return any(r.id in allowed for r in ctx.author.roles)

def is_ticket_manager(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    if is_admin(interaction):
        return True
    tm_role_id = ticket_manager_roles.get(interaction.guild_id)
    return tm_role_id is not None and any(role.id == tm_role_id for role in member.roles)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def declension(n: int) -> str:
    mod10, mod100 = n % 10, n % 100
    if 11 <= mod100 <= 19:
        return "человек"
    if mod10 == 1:
        return "человек"
    if 2 <= mod10 <= 4:
        return "человека"
    return "человек"



def build_event_embed(
    title: str,
    max_count: int,
    slots: dict,
    image_url: str = None,
    note: str = None,
    join_mode: bool = False,
) -> discord.Embed:
    filled = sum(1 for v in slots.values() if v is not None)
    color  = discord.Color.red() if filled >= max_count else discord.Color.green()

    lines = []
    for i in range(1, max_count + 1):
        uid = slots.get(i)
        lines.append(f"`{str(i).zfill(2)}.` {'<@' + str(uid) + '>' if uid else '*свободно*'}")

    text = "\n".join(lines)
    if join_mode:
        description = f"Нажми ✅ чтобы записаться\n\n**Участники ({filled}/{max_count}):**\n{text}"
    else:
        description = f"Нажми кнопку с нужным номером слота\n\n**Слоты ({filled}/{max_count}):**\n{text}"
    if note:
        description += f"\n\n📌 **Заметка:** {note}"

    embed = discord.Embed(
        title=f"📋 Сбор: {title}",
        description=description,
        color=color,
        timestamp=datetime.now(),
    )
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    if image_url:
        embed.set_image(url=image_url)
    return embed


def build_thread_list(title: str, max_count: int, slots: dict) -> str:
    filled = sum(1 for v in slots.values() if v is not None)
    lines  = [f"**📋 Список: {title} ({filled}/{max_count})**\n"]
    for i in range(1, max_count + 1):
        uid = slots.get(i)
        lines.append(f"`{str(i).zfill(2)}.` {'<@' + str(uid) + '>' if uid else 'свободно'}")
    return "\n".join(lines)


async def update_thread_list(message_id: int):
    data = event_lists.get(message_id)
    if not data or not data.get("thread_msg_id"):
        return
    try:
        thread = bot.get_channel(data["thread_id"])
        if not thread:
            return
        msg = await thread.fetch_message(data["thread_msg_id"])
        await msg.edit(content=build_thread_list(data["title"], data["max"], data["slots"]))
    except Exception:
        pass


def build_inactive_embed(guild_id: int) -> discord.Embed:
    entries = list(inactive_list.get(guild_id, {}).items())
    count   = len(entries)

    if entries:
        lines = "\n\n".join(
            f"**{i+1})** <@{uid}> Причина: {d['reason']}\nВернусь: `{d['return_date']}`"
            for i, (uid, d) in enumerate(entries)
        )
    else:
        lines = "*Список пуст — никто не в инактиве*"

    embed = discord.Embed(
        title="📅 Люди, находящиеся в инактиве:",
        description=f"• Всего в инактиве **{count}** {declension(count)}\n\n{lines}",
        color=discord.Color.orange(),
        timestamp=datetime.now(),
    )
    if AFK_IMAGE_URL:
        embed.set_image(url=AFK_IMAGE_URL)
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    return embed


def build_afk_embed(guild_id: int) -> discord.Embed:
    entries = list(afk_list.get(guild_id, {}).items())
    count   = len(entries)

    if entries:
        lines = "\n\n".join(
            f"**{i+1})** <@{uid}> Причина: {d['reason']}\nВернусь в: `{d['return_time']}`"
            for i, (uid, d) in enumerate(entries)
        )
    else:
        lines = "*Список пуст — никто не в АФК*"

    embed = discord.Embed(
        title="⏳ Люди, находящиеся в АФК:",
        description=f"• Всего в АФК **{count}** {declension(count)}\n\n{lines}",
        color=discord.Color.blurple(),
        timestamp=datetime.now(),
    )
    if AFK_IMAGE_URL:
        embed.set_image(url=AFK_IMAGE_URL)
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    return embed


def get_points(guild_id: int, user_id: int) -> int:
    return points_db.get(guild_id, {}).get(user_id, 0)


def set_points(guild_id: int, user_id: int, amount: int):
    if guild_id not in points_db:
        points_db[guild_id] = {}
    points_db[guild_id][user_id] = amount
    save_data()


def add_points(guild_id: int, user_id: int, amount: int):
    current = get_points(guild_id, user_id)
    set_points(guild_id, user_id, current + amount)


def get_warns(guild_id: int, user_id: int) -> dict:
    return warns_db.get(guild_id, {}).get(user_id, None)


def set_warn(guild_id: int, user_id: int, count: int, reason: str, moderator_id: int):
    if guild_id not in warns_db:
        warns_db[guild_id] = {}
    warns_db[guild_id][user_id] = {
        "warns": count,
        "reason": reason,
        "moderator": moderator_id,
        "timestamp": datetime.now(),
    }
    save_data()


def remove_warn(guild_id: int, user_id: int) -> bool:
    if guild_id in warns_db and user_id in warns_db[guild_id]:
        del warns_db[guild_id][user_id]
        save_data()
        return True
    return False


def build_points_embed(guild_id: int, user_id: int) -> discord.Embed:
    points = get_points(guild_id, user_id)
    warn_data = get_warns(guild_id, user_id)
    warns = warn_data["warns"] if warn_data else 0
    
    embed = discord.Embed(
        title="💰 Ваш баланс",
        color=discord.Color.gold(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="Баллы", value=f"**{points}** 💎", inline=True)
    embed.add_field(name="Warns", value=f"**{warns}** ⚠️", inline=True)
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    return embed


def build_shop_embed(guild_id: int) -> discord.Embed:
    items = guild_shop_items.get(guild_id, {})
    embed = discord.Embed(
        title="🛒 Магазин",
        description=(
            "Трать заработанные баллы на полезные товары.\n"
            "Свой баланс смотри командой `!баланс`\n\u200B"
        ),
        color=discord.Color.gold(),
        timestamp=datetime.now(),
    )
    if not items:
        embed.add_field(name="Пусто", value="*Товары ещё не добавлены*", inline=False)
    for item_id, item in items.items():
        action_label = {"remove_warn": "Снимает варн", "give_role": "Выдаёт роль", "notify": "Ручная выдача"}.get(item["action"], "")
        embed.add_field(
            name=f"{item['emoji']} {item['name']}",
            value=f"Цена: **{item['price']}** 💎\n{item.get('description', '')}\n*{action_label}*",
            inline=True,
        )
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    return embed


def save_data():
    """Сохраняет баллы, варны и роли на диск."""
    warns_serial = {}
    for g, users in warns_db.items():
        warns_serial[str(g)] = {}
        for u, info in users.items():
            warns_serial[str(g)][str(u)] = {
                k: (v.isoformat() if isinstance(v, datetime) else v)
                for k, v in info.items()
            }
    data = {
        "points":        {str(g): {str(u): v for u, v in us.items()} for g, us in points_db.items()},
        "warns":         warns_serial,
        "event_roles":   {str(g): v for g, v in event_roles.items()},
        "ticket_panels":      {str(g): v for g, v in ticket_panels.items()},
        "ticket_counters":    {str(g): v for g, v in ticket_counters.items()},
        "reject_log_channels":  {str(g): v for g, v in reject_log_channels.items()},
        "ticket_manager_roles": {str(g): v for g, v in ticket_manager_roles.items()},
        "mp_roles":             {str(g): v for g, v in mp_roles.items()},
        "vzp_roles":            {str(g): v for g, v in vzp_roles.items()},
        "warn_roles":           {str(g): {str(k): v for k, v in wr.items()} for g, wr in warn_roles.items()},
        "admin_roles":          {str(g): v for g, v in admin_roles.items()},
        "ticket_viewer_roles":  {str(g): v for g, v in ticket_viewer_roles.items()},
        "ticket_ping_role":     {str(g): v for g, v in ticket_ping_role.items()},
        "guild_shop_items":     {str(g): v for g, v in guild_shop_items.items()},
        "event_command_roles":  {str(g): v for g, v in event_command_roles.items()},
        "private_vc_settings":  {str(g): v for g, v in private_vc_settings.items()},
        "ticket_texts":         {str(g): v for g, v in ticket_texts.items()},
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_data():
    """Загружает данные с диска при старте."""
    global points_db, warns_db
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        points_db = {
            int(g): {int(u): v for u, v in us.items()}
            for g, us in data.get("points", {}).items()
        }
        for g, users in data.get("warns", {}).items():
            warns_db[int(g)] = {}
            for u, info in users.items():
                warns_db[int(g)][int(u)] = {
                    k: (datetime.fromisoformat(v) if k == "timestamp" and v else v)
                    for k, v in info.items()
                }
        for g, v in data.get("event_roles", {}).items():
            event_roles[int(g)] = v
        for g, v in data.get("ticket_panels", {}).items():
            ticket_panels[int(g)] = v
        for g, v in data.get("ticket_counters", {}).items():
            ticket_counters[int(g)] = v
        for g, v in data.get("reject_log_channels", {}).items():
            reject_log_channels[int(g)] = v
        for g, v in data.get("ticket_manager_roles", {}).items():
            ticket_manager_roles[int(g)] = v
        for g, v in data.get("mp_roles", {}).items():
            mp_roles[int(g)] = v
        for g, v in data.get("vzp_roles", {}).items():
            vzp_roles[int(g)] = v
        for g, wr in data.get("warn_roles", {}).items():
            warn_roles[int(g)] = {int(k): v for k, v in wr.items()}
        for g, v in data.get("admin_roles", {}).items():
            admin_roles[int(g)] = v
        for g, v in data.get("ticket_viewer_roles", {}).items():
            ticket_viewer_roles[int(g)] = v
        for g, v in data.get("ticket_ping_role", {}).items():
            ticket_ping_role[int(g)] = v
        for g, v in data.get("guild_shop_items", {}).items():
            guild_shop_items[int(g)] = v
        for g, v in data.get("event_command_roles", {}).items():
            event_command_roles[int(g)] = v
        for g, v in data.get("private_vc_settings", {}).items():
            private_vc_settings[int(g)] = v
        for g, v in data.get("ticket_texts", {}).items():
            ticket_texts[int(g)] = v
        print("OK: Data loaded from data.json")
    except Exception as e:
        print(f"WARNING: Failed to load data: {e}")


async def refresh_afk_message(guild: discord.Guild):
    panel = afk_panels.get(guild.id)
    if not panel:
        return
    try:
        channel = guild.get_channel(panel["channel_id"])
        msg     = await channel.fetch_message(panel["message_id"])
        await msg.edit(embed=build_afk_embed(guild.id))
    except Exception:
        pass


async def refresh_inactive_message(guild: discord.Guild):
    panel = inactive_panels.get(guild.id)
    if not panel:
        return
    try:
        channel = guild.get_channel(panel["channel_id"])
        msg     = await channel.fetch_message(panel["message_id"])
        await msg.edit(embed=build_inactive_embed(guild.id))
    except Exception:
        pass


# ─────────────────────────────────────────────
# СБОР — СЛОТЫ
# ─────────────────────────────────────────────
class SlotButton(ui.Button):
    def __init__(self, slot_num: int, message_id: int, taken_by: int | None):
        super().__init__(
            label=str(slot_num),
            style=discord.ButtonStyle.danger if taken_by else discord.ButtonStyle.success,
            custom_id=f"slot_{message_id}_{slot_num}",
        )
        self.slot_num = slot_num
        self.message_id = message_id

    async def callback(self, interaction: discord.Interaction):
        data = event_lists.get(self.message_id)
        if not data:
            return await interaction.response.send_message("❌ Сбор уже недоступен!", ephemeral=True)

        user_id = interaction.user.id
        slots   = data["slots"]

        if slots.get(self.slot_num) == user_id:
            # Покинуть слот
            slots[self.slot_num] = None
            msg_text = f"❌ Вы покинули слот **{self.slot_num}**"
        elif slots.get(self.slot_num) is not None:
            return await interaction.response.send_message(
                f"❌ Слот **{self.slot_num}** уже занят!", ephemeral=True
            )
        else:
            # Освободить предыдущий слот если есть
            for s, uid in slots.items():
                if uid == user_id:
                    slots[s] = None
                    break
            slots[self.slot_num] = user_id
            msg_text = f"✅ Вы заняли слот **{self.slot_num}**!"

        new_view = EventView(self.message_id)
        embed    = build_event_embed(data["title"], data["max"], slots, data.get("image_url"), data.get("note"))
        await interaction.response.defer()
        await interaction.message.edit(embed=embed, view=new_view)
        await update_thread_list(self.message_id)
        await interaction.followup.send(msg_text, ephemeral=True)


class EventView(ui.View):
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id
        data = event_lists.get(message_id)
        if not data:
            return
        slots     = data.get("slots", {})
        max_count = data.get("max", 0)

        slot_count = min(max_count, 25)
        for i in range(1, slot_count + 1):
            self.add_item(SlotButton(i, message_id, slots.get(i)))


class JoinButton(ui.Button):
    """Одна кнопка ✅ для записи/выхода — используется когда слотов > 24."""
    def __init__(self, message_id: int):
        super().__init__(
            label="Записаться",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"join_{message_id}",
        )
        self.message_id = message_id

    async def callback(self, interaction: discord.Interaction):
        data = event_lists.get(self.message_id)
        if not data:
            return await interaction.response.send_message("❌ Сбор недоступен!", ephemeral=True)

        user_id = interaction.user.id
        slots   = data["slots"]

        # Уже записан — выйти
        for slot_num, uid in slots.items():
            if uid == user_id:
                slots[slot_num] = None
                embed = build_event_embed(data["title"], data["max"], slots, data.get("image_url"), data.get("note"), join_mode=True)
                await interaction.response.defer()
                await interaction.message.edit(embed=embed)
                await update_thread_list(self.message_id)
                await interaction.followup.send("❌ Вы покинули сбор", ephemeral=True)
                return

        # Найти свободный слот
        for i in range(1, data["max"] + 1):
            if slots.get(i) is None:
                slots[i] = user_id
                embed = build_event_embed(data["title"], data["max"], slots, data.get("image_url"), data.get("note"), join_mode=True)
                await interaction.response.defer()
                await interaction.message.edit(embed=embed)
                await update_thread_list(self.message_id)
                await interaction.followup.send("✅ Вы записались в сбор!", ephemeral=True)
                return

        await interaction.response.send_message("❌ Все места заняты!", ephemeral=True)


class JoinEventView(ui.View):
    """View с одной кнопкой ✅. Для сборов с > 25 слотами."""
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.add_item(JoinButton(message_id))


# ─────────────────────────────────────────────
# МОДАЛКИ
# ─────────────────────────────────────────────
class AfkModal(ui.Modal, title="🕐 Уход в АФК"):
    reason      = ui.TextInput(label="Причина", placeholder="На работе / Учёба / Дела...", required=True)
    return_time = ui.TextInput(label="Вернусь в (например 18:30)", placeholder="18:30", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        user_id  = interaction.user.id

        if guild_id not in afk_list:
            afk_list[guild_id] = {}

        afk_list[guild_id][user_id] = {
            "reason":      str(self.reason),
            "return_time": str(self.return_time),
            "since":       datetime.now(),
        }

        await refresh_afk_message(interaction.guild)

        embed = discord.Embed(
            description=(
                f"🕐 Вы добавлены в АФК-список\n"
                f"**Причина:** {self.reason}\n"
                f"**Вернусь в:** `{self.return_time}`"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class RejectModal(ui.Modal, title="❌ Причина отклонения"):
    reason = ui.TextInput(label="Укажите причину", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, applicant_id: int, original_message: discord.Message):
        super().__init__()
        self.applicant_id     = applicant_id
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        reason = str(self.reason)

        old_embed = self.original_message.embeds[0]
        new_embed = old_embed.copy()
        new_embed.color = discord.Color.red()
        new_embed.add_field(
            name="❌ Статус",
            value=f"Отклонено — {interaction.user.mention}\n**Причина:** {reason}",
            inline=False,
        )
        await self.original_message.edit(embed=new_embed, view=None)

        try:
            target = await interaction.client.fetch_user(self.applicant_id)
            dm_embed = discord.Embed(
                title="❌ Ваша заявка отклонена",
                description=f"**Причина:**\n> {reason}",
                color=discord.Color.red(),
                timestamp=datetime.now(),
            )
            dm_embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y %H:%M"))
            dm_embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
            await target.send(embed=dm_embed)
        except Exception:
            pass

        log_channel_id = reject_log_channels.get(interaction.guild_id)
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                try:
                    log_embed = discord.Embed(
                        title="❌ Заявка отклонена",
                        color=discord.Color.red(),
                        timestamp=datetime.now(),
                    )
                    log_embed.add_field(name="Заявка от пользователя", value=f"<@{self.applicant_id}>", inline=False)
                    log_embed.add_field(name="Причина", value=reason, inline=False)
                    log_embed.add_field(name="Рассматривал", value=interaction.user.mention, inline=False)
                    log_embed.set_thumbnail(url=FOOTER_ICON)
                    log_embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
                    await log_channel.send(embed=log_embed)
                except Exception:
                    pass

        await interaction.response.send_message(
            "✅ Заявка отклонена. Канал закроется через 10 секунд.", ephemeral=True
        )
        await asyncio.sleep(10)
        try:
            await interaction.channel.delete(reason="Заявка отклонена")
        except Exception:
            pass


class ApplicationModal(ui.Modal, title="📋 Подать заявку"):
    nickname = ui.TextInput(label="Ваш ник и статик в игре",  placeholder="Nick Name | 777",     required=True)
    hours_age = ui.TextInput(label="Часов в игре / Возраст",  placeholder="2500 / 18",            required=True)
    families  = ui.TextInput(label="В каких семьях был?",     style=discord.TextStyle.paragraph,  required=True)
    recoil    = ui.TextInput(label="Откат со стрельбой",      placeholder="DM, Архив, YouTube",   required=True)
    content   = ui.TextInput(label="Какой контент симпатизирует?", placeholder="РП / ВЗП",        required=True)

    def __init__(self, category_id: int):
        super().__init__()
        self.category_id = category_id

    async def on_submit(self, interaction: discord.Interaction):
        guild      = interaction.guild
        applicant  = interaction.user
        category   = guild.get_channel(self.category_id)
        admin_role_id = admin_roles.get(guild.id)
        admin_role    = guild.get_role(admin_role_id) if admin_role_id else None
        tm_role_id    = ticket_manager_roles.get(guild.id)
        tm_role       = guild.get_role(tm_role_id) if tm_role_id else None
        ping_role_id  = ticket_ping_role.get(guild.id)
        ping_role     = guild.get_role(ping_role_id) if ping_role_id else tm_role

        ticket_counters[guild.id] = ticket_counters.get(guild.id, 0) + 1
        ticket_num = ticket_counters[guild.id]
        save_data()

        ticket_perms = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            applicant: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
        }
        if admin_role:
            overwrites[admin_role] = ticket_perms
        if tm_role:
            overwrites[tm_role] = ticket_perms
        # Роли с доступом на просмотр
        for rid in ticket_viewer_roles.get(guild.id, []):
            r = guild.get_role(rid)
            if r:
                overwrites[r] = ticket_perms

        try:
            ticket_channel = await guild.create_text_channel(
                name=f"ticket-{str(ticket_num).zfill(4)}",
                category=category,
                overwrites=overwrites,
                reason=f"Заявка от {applicant}",
            )
        except Exception as e:
            return await interaction.response.send_message(
                f"❌ Не удалось создать канал: {e}", ephemeral=True
            )

        embed = discord.Embed(
            title="📋 Новая заявка",
            color=discord.Color.yellow(),
            timestamp=datetime.now(),
        )
        embed.set_thumbnail(url=applicant.display_avatar.url)
        embed.add_field(name="👤 Пользователь",           value=f"{applicant.mention} ({applicant})", inline=True)
        embed.add_field(name="🎮 Ник | Статик",            value=str(self.nickname),   inline=True)
        embed.add_field(name="\u200B",                     value="\u200B",             inline=True)
        embed.add_field(name="⏱️ Часов / Возраст",        value=str(self.hours_age),  inline=True)
        embed.add_field(name="🎯 Откат со стрельбой",     value=str(self.recoil),     inline=True)
        embed.add_field(name="🎮 Контент",                value=str(self.content),    inline=True)
        embed.add_field(name="🏠 Был в семьях",           value=str(self.families),   inline=False)
        embed.set_footer(text=f"DIAMOND • {applicant.id}", icon_url=FOOTER_ICON)

        view = ApplicationReviewView(applicant.id)
        pings = ping_role.mention if ping_role else None
        await ticket_channel.send(content=pings, embed=embed, view=view)

        sent_embed = discord.Embed(
            title="📬 Заявка отправлена!",
            description=(
                "Ваша заявка принята. Ожидайте ответа.\n"
                "Результат придёт в личные сообщения."
            ),
            color=discord.Color.yellow(),
            timestamp=datetime.now(),
        )
        sent_embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
        await interaction.response.send_message(embed=sent_embed, ephemeral=True)


# ─────────────────────────────────────────────
# КНОПКИ (View)
# ─────────────────────────────────────────────
class AfkView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Отошел АФК", style=discord.ButtonStyle.secondary, emoji="🕐", custom_id="afk_away")
    async def afk_away(self, interaction: discord.Interaction, button: ui.Button):
        guild_id = interaction.guild_id
        if guild_id in afk_list and interaction.user.id in afk_list[guild_id]:
            return await interaction.response.send_message("⚠️ Вы уже в АФК-списке!", ephemeral=True)
        await interaction.response.send_modal(AfkModal())

    @ui.button(label="Вернулся из АФК", style=discord.ButtonStyle.success, emoji="✅", custom_id="afk_back")
    async def afk_back(self, interaction: discord.Interaction, button: ui.Button):
        guild_id = interaction.guild_id
        user_id  = interaction.user.id
        if guild_id not in afk_list or user_id not in afk_list[guild_id]:
            return await interaction.response.send_message("⚠️ Вас нет в АФК-списке!", ephemeral=True)

        del afk_list[guild_id][user_id]
        await refresh_afk_message(interaction.guild)
        await interaction.response.send_message("✅ Вы убраны из АФК-списка. С возвращением!", ephemeral=True)


class InactiveModal(ui.Modal, title="📅 Уход в инактив"):
    reason      = ui.TextInput(label="Причина", placeholder="Отпуск / Работа / Дела...", required=True)
    return_date = ui.TextInput(label="Вернусь (например 25.04.2026)", placeholder="25.04.2026", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        user_id  = interaction.user.id

        if guild_id not in inactive_list:
            inactive_list[guild_id] = {}

        inactive_list[guild_id][user_id] = {
            "reason":      str(self.reason),
            "return_date": str(self.return_date),
            "since":       datetime.now(),
        }

        await refresh_inactive_message(interaction.guild)

        embed = discord.Embed(
            description=(
                f"📅 Вы добавлены в список инактива\n"
                f"**Причина:** {self.reason}\n"
                f"**Вернусь:** `{self.return_date}`"
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class InactiveView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Ухожу в инактив", style=discord.ButtonStyle.secondary, emoji="📅", custom_id="inactive_away")
    async def inactive_away(self, interaction: discord.Interaction, button: ui.Button):
        guild_id = interaction.guild_id
        if guild_id in inactive_list and interaction.user.id in inactive_list[guild_id]:
            return await interaction.response.send_message("⚠️ Вы уже в списке инактива!", ephemeral=True)
        await interaction.response.send_modal(InactiveModal())

    @ui.button(label="Вернулся из инактива", style=discord.ButtonStyle.success, emoji="✅", custom_id="inactive_back")
    async def inactive_back(self, interaction: discord.Interaction, button: ui.Button):
        guild_id = interaction.guild_id
        user_id  = interaction.user.id
        if guild_id not in inactive_list or user_id not in inactive_list[guild_id]:
            return await interaction.response.send_message("⚠️ Вас нет в списке инактива!", ephemeral=True)

        del inactive_list[guild_id][user_id]
        await refresh_inactive_message(interaction.guild)
        await interaction.response.send_message("✅ Вы убраны из инактива. С возвращением!", ephemeral=True)


class TicketPanelView(ui.View):
    def __init__(self, category_id: int):
        super().__init__(timeout=None)
        self.category_id = category_id

    @ui.button(label="Подать заявку", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="ticket_apply")
    async def apply(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ApplicationModal(self.category_id))


class ApplicationReviewView(ui.View):
    def __init__(self, applicant_id: int = 0):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id

    def _get_applicant_id(self, message: discord.Message) -> int:
        if self.applicant_id:
            return self.applicant_id
        try:
            footer = message.embeds[0].footer.text  # "DIAMOND • 123..."
            return int(footer.split("• ")[-1].strip())
        except Exception:
            return 0

    @ui.button(label="✅ Одобрить", style=discord.ButtonStyle.success, custom_id="ticket_approve")
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        if not is_ticket_manager(interaction):
            return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)

        applicant_id = self._get_applicant_id(interaction.message)

        old_embed = interaction.message.embeds[0]
        new_embed = old_embed.copy()
        new_embed.color = discord.Color.green()
        new_embed.add_field(
            name="✅ Статус",
            value=f"Одобрено — {interaction.user.mention} ({datetime.now().strftime('%d.%m.%Y %H:%M')})",
            inline=False,
        )
        await interaction.message.edit(embed=new_embed, view=None)

        try:
            target = await interaction.client.fetch_user(applicant_id)
            dm_embed = discord.Embed(
                title="🏆 Добро пожаловать в семью DIAMOND!",
                description=(
                    "Твоя заявка была **одобрена**!\n\n"
                    "Добро пожаловать! 🖤"
                ),
                color=0x2B2D31,
                timestamp=datetime.now(),
            )
            dm_embed.add_field(name="📅 Дата принятия", value=datetime.now().strftime("%d.%m.%Y %H:%M"), inline=True)
            dm_embed.add_field(name="👮 Одобрил", value=interaction.user.mention, inline=True)
            dm_embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
            if APPROVE_GIF_URL:
                dm_embed.set_image(url=APPROVE_GIF_URL)
            await target.send(embed=dm_embed)
        except Exception:
            pass

        await interaction.response.send_message(
            "✅ Заявка одобрена. Канал закроется через 10 секунд.", ephemeral=True
        )
        await asyncio.sleep(10)
        try:
            await interaction.channel.delete(reason="Заявка одобрена")
        except Exception:
            pass

    @ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger, custom_id="ticket_reject")
    async def reject(self, interaction: discord.Interaction, button: ui.Button):
        if not is_ticket_manager(interaction):
            return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
        applicant_id = self._get_applicant_id(interaction.message)
        await interaction.response.send_modal(RejectModal(applicant_id, interaction.message))


# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# МАГАЗИН - КНОПКИ
# ─────────────────────────────────────────────
async def refresh_shop_message(guild: discord.Guild):
    panel = shop_panels.get(guild.id)
    if not panel:
        return
    try:
        channel = guild.get_channel(panel["channel_id"])
        msg     = await channel.fetch_message(panel["message_id"])
        view    = ShopView(guild.id)
        await msg.edit(embed=build_shop_embed(guild.id), view=view)
    except Exception:
        pass


class ShopItemButton(ui.Button):
    def __init__(self, item_id: str, item: dict, guild_id: int):
        super().__init__(
            label=item["name"],
            emoji=item.get("emoji") or None,
            style=discord.ButtonStyle.primary,
            custom_id=f"shop_{guild_id}_{item_id}",
        )
        self.item_id  = item_id
        self.item     = item
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        user_id  = interaction.user.id
        item     = guild_shop_items.get(guild_id, {}).get(self.item_id)

        if not item:
            return await interaction.response.send_message("❌ Товар больше не доступен.", ephemeral=True)

        price  = item["price"]
        points = get_points(guild_id, user_id)

        if points < price:
            return await interaction.response.send_message(
                f"❌ Недостаточно баллов! Нужно **{price}** 💎, у вас **{points}** 💎",
                ephemeral=True,
            )

        action = item.get("action", "notify")

        if action == "remove_warn":
            warn_data = get_warns(guild_id, user_id)
            if not warn_data:
                return await interaction.response.send_message("✅ У вас нет варнов для снятия!", ephemeral=True)
            # Убрать варн-роли
            guild_warn_roles = warn_roles.get(guild_id, {})
            roles_to_remove = [interaction.guild.get_role(rid) for rid in guild_warn_roles.values()]
            try:
                await interaction.user.remove_roles(*[r for r in roles_to_remove if r], reason="Покупка: снятие варна")
            except Exception:
                pass
            remove_warn(guild_id, user_id)
            add_points(guild_id, user_id, -price)
            embed = discord.Embed(title="✅ Варн снят!", description=f"Списано **{price}** 💎", color=discord.Color.green(), timestamp=datetime.now())
            embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        elif action == "give_role":
            role_id = item.get("role_id")
            role    = interaction.guild.get_role(role_id) if role_id else None
            if not role:
                return await interaction.response.send_message("❌ Роль не найдена. Обратитесь к администратору.", ephemeral=True)
            try:
                await interaction.user.add_roles(role, reason=f"Покупка в магазине: {item['name']}")
            except Exception:
                return await interaction.response.send_message("❌ Не удалось выдать роль.", ephemeral=True)
            add_points(guild_id, user_id, -price)
            embed = discord.Embed(title=f"✅ Куплено: {item['name']}", description=f"Роль {role.mention} выдана!\nСписано **{price}** 💎", color=discord.Color.green(), timestamp=datetime.now())
            embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        else:  # notify — ручная выдача
            add_points(guild_id, user_id, -price)
            # Уведомление в лог-канал если есть
            log_channel_id = reject_log_channels.get(guild_id)
            if log_channel_id:
                log_ch = interaction.guild.get_channel(log_channel_id)
                if log_ch:
                    log_embed = discord.Embed(
                        title="🛒 Покупка в магазине",
                        color=discord.Color.gold(),
                        timestamp=datetime.now(),
                    )
                    log_embed.add_field(name="Покупатель", value=interaction.user.mention, inline=True)
                    log_embed.add_field(name="Товар", value=item["name"], inline=True)
                    log_embed.add_field(name="Цена", value=f"{price} 💎", inline=True)
                    log_embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
                    try:
                        await log_ch.send(embed=log_embed)
                    except Exception:
                        pass
            embed = discord.Embed(
                title=f"✅ Куплено: {item['name']}",
                description=f"Списано **{price}** 💎\nАдминистратор скоро свяжется с вами.",
                color=discord.Color.green(),
                timestamp=datetime.now(),
            )
            embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
            return await interaction.response.send_message(embed=embed, ephemeral=True)


class ShopView(ui.View):
    def __init__(self, guild_id: int = 0):
        super().__init__(timeout=None)
        items = guild_shop_items.get(guild_id, {})
        for item_id, item in items.items():
            self.add_item(ShopItemButton(item_id, item, guild_id))




# ─────────────────────────────────────────────
# СЛЭШ-КОМАНДЫ
# ─────────────────────────────────────────────
@bot.command(name="роль_реаки")
async def set_event_role(ctx, роль: discord.Role):
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    """!роль_реаки @роль — настроить роль для тега при !взп и !реаки"""
    event_roles[ctx.guild.id] = роль.id
    save_data()
    embed = discord.Embed(
        title="✅ Роль настроена",
        description=f"При каждом `!взп` и `!реаки` будет тегаться {роль.mention}",
        color=discord.Color.green(),
    )
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    await ctx.send(embed=embed, delete_after=10)
    await ctx.message.delete()


async def _create_event_message(channel, guild, title: str, max_count: int, image_file=None, image_ref: str | None = None, content: str | None = None, force_join_mode: bool = False):
    """Создаёт сбор: эмбед + тред. <= 24 слотов → кнопки-цифры, > 24 → одна кнопка ✅."""
    if not (1 <= max_count <= 100):
        await channel.send("❌ Количество слотов: от 1 до 100!", delete_after=5)
        return

    join_mode = force_join_mode or max_count > 24
    slots     = {i: None for i in range(1, max_count + 1)}

    embed = build_event_embed(title, max_count, slots, image_ref, join_mode=join_mode)

    if image_file:
        msg = await channel.send(content=content, embed=embed, file=image_file)
    else:
        msg = await channel.send(content=content, embed=embed)

    # Для последующих редактирований используем URL из вложения сообщения (стабильнее)
    if image_ref and msg.attachments:
        image_ref = msg.attachments[0].url
        embed.set_image(url=image_ref)

    event_lists[msg.id] = {
        "title": title, "max": max_count, "mode": "join" if join_mode else "buttons",
        "slots": slots, "image_url": image_ref, "note": None,
        "channel_id": channel.id, "thread_id": None, "thread_msg_id": None,
    }

    view = JoinEventView(msg.id) if join_mode else EventView(msg.id)
    await msg.edit(embed=embed, view=view)

    # Тред с живым списком
    try:
        hint = "Нажми ✅ в сообщении выше для записи!" if join_mode else "Выбирай слот кнопкой в сообщении выше!"
        thread = await msg.create_thread(name=f"💬 {title}", auto_archive_duration=1440)
        thread_embed = discord.Embed(
            description=f"📋 Обсуждение сбора **{title}**\n{hint}",
            color=discord.Color.blurple(),
        )
        thread_embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
        await thread.send(embed=thread_embed)
        list_msg = await thread.send(build_thread_list(title, max_count, slots))
        event_lists[msg.id]["thread_id"]     = thread.id
        event_lists[msg.id]["thread_msg_id"] = list_msg.id
    except Exception:
        pass


# ─────────────────────────────────────────────
# PREFIX-КОМАНДЫ СБОРОВ
# ─────────────────────────────────────────────
@bot.command(name="взп")
async def взп_cmd(ctx, количество: int = 10, *, название: str = "ВЗП"):
    """!взп [количество] [название] — сбор с фото (от лица бота)"""
    if not can_run_event(ctx, "взп"):
        return await ctx.message.delete()

    image_file = None
    image_ref  = None
    if ctx.message.attachments:
        att = ctx.message.attachments[0]
        try:
            img_bytes  = await att.read()
            ext        = att.filename.rsplit(".", 1)[-1].lower() if "." in att.filename else "png"
            safe_name  = f"event_image.{ext}"
            image_file = discord.File(io.BytesIO(img_bytes), filename=safe_name)
            image_ref  = f"attachment://{safe_name}"
        except Exception:
            pass

    try:
        await ctx.message.delete()
    except Exception:
        pass

    # Тег: роль ВЗП + роль МП
    mentions = []
    vzp_role_id = vzp_roles.get(ctx.guild.id)
    if vzp_role_id:
        r = ctx.guild.get_role(vzp_role_id)
        if r:
            mentions.append(r.mention)
    mp_role_id = mp_roles.get(ctx.guild.id)
    if mp_role_id:
        r = ctx.guild.get_role(mp_role_id)
        if r:
            mentions.append(r.mention)
    content = " ".join(mentions) if mentions else None

    await _create_event_message(ctx.channel, ctx.guild, название, количество, image_file, image_ref, content=content)


@bot.command(name="мп")
async def мп_cmd(ctx, количество: int = 10, *, название: str = "МП"):
    """!мп [количество] [название] — сбор МП"""
    if not can_run_event(ctx, "мп"):
        return await ctx.message.delete()

    image_file = None
    image_ref  = None
    if ctx.message.attachments:
        att = ctx.message.attachments[0]
        try:
            img_bytes  = await att.read()
            ext        = att.filename.rsplit(".", 1)[-1].lower() if "." in att.filename else "png"
            safe_name  = f"event_image.{ext}"
            image_file = discord.File(io.BytesIO(img_bytes), filename=safe_name)
            image_ref  = f"attachment://{safe_name}"
        except Exception:
            pass

    try:
        await ctx.message.delete()
    except Exception:
        pass

    mp_role_id = mp_roles.get(ctx.guild.id)
    content = None
    if mp_role_id:
        r = ctx.guild.get_role(mp_role_id)
        if r:
            content = r.mention

    await _create_event_message(ctx.channel, ctx.guild, название, количество, image_file, image_ref, content=content)


@bot.command(name="роль_взп")
async def set_vzp_role(ctx, роль: discord.Role):
    """!роль_взп @роль — настроить роль ВЗП для тега в !взп"""
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    vzp_roles[ctx.guild.id] = роль.id
    save_data()
    embed = discord.Embed(
        title="✅ Роль ВЗП настроена",
        description=f"В `!взп` будет тегаться {роль.mention}",
        color=discord.Color.green(),
    )
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    await ctx.send(embed=embed, delete_after=10)
    await ctx.message.delete()


@bot.command(name="роль_мп")
async def set_mp_role(ctx, роль: discord.Role):
    """!роль_мп @роль — настроить роль МП для тега в !взп и !мп"""
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    mp_roles[ctx.guild.id] = роль.id
    save_data()
    embed = discord.Embed(
        title="✅ Роль МП настроена",
        description=f"В `!взп` и `!мп` будет тегаться {роль.mention}",
        color=discord.Color.green(),
    )
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    await ctx.send(embed=embed, delete_after=10)
    await ctx.message.delete()


@tree.command(name="доступ_сбора", description="Добавить роль с доступом к команде сбора")
@app_commands.describe(
    тип="Тип сбора: взп, мп или реаки",
    роль="Роль, которая получит доступ к команде"
)
@app_commands.choices(тип=[
    app_commands.Choice(name="взп", value="взп"),
    app_commands.Choice(name="мп", value="мп"),
    app_commands.Choice(name="реаки", value="реаки"),
])
async def slash_event_access_add(interaction: discord.Interaction, тип: str, роль: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    gid = interaction.guild_id
    if gid not in event_command_roles:
        event_command_roles[gid] = {}
    if тип not in event_command_roles[gid]:
        event_command_roles[gid][тип] = []
    if роль.id not in event_command_roles[gid][тип]:
        event_command_roles[gid][тип].append(роль.id)
    save_data()
    roles_list = ", ".join(f"<@&{rid}>" for rid in event_command_roles[gid][тип])
    await interaction.response.send_message(
        f"✅ {роль.mention} теперь может использовать `!{тип}`\nВсе роли с доступом: {roles_list}",
        ephemeral=True,
    )


@tree.command(name="убрать_доступ_сбора", description="Убрать роль из доступа к команде сбора")
@app_commands.describe(
    тип="Тип сбора: взп, мп или реаки",
    роль="Роль, которую убрать"
)
@app_commands.choices(тип=[
    app_commands.Choice(name="взп", value="взп"),
    app_commands.Choice(name="мп", value="мп"),
    app_commands.Choice(name="реаки", value="реаки"),
])
async def slash_event_access_remove(interaction: discord.Interaction, тип: str, роль: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    gid = interaction.guild_id
    allowed = event_command_roles.get(gid, {}).get(тип, [])
    if роль.id not in allowed:
        return await interaction.response.send_message(f"❌ {роль.mention} и так не в списке для `!{тип}`.", ephemeral=True)
    allowed.remove(роль.id)
    save_data()
    await interaction.response.send_message(f"✅ {роль.mention} убрана из доступа к `!{тип}`.", ephemeral=True)


@bot.command(name="реаки")
async def реаки_cmd(ctx, количество: int = 10, *, название: str = "Реакции"):
    """!реаки [количество] [название] — сбор на мероприятие (от лица бота)"""
    if not can_run_event(ctx, "реаки"):
        return await ctx.message.delete()

    image_file = None
    image_ref  = None
    if ctx.message.attachments:
        att = ctx.message.attachments[0]
        try:
            img_bytes  = await att.read()
            ext        = att.filename.rsplit(".", 1)[-1].lower() if "." in att.filename else "png"
            safe_name  = f"event_image.{ext}"
            image_file = discord.File(io.BytesIO(img_bytes), filename=safe_name)
            image_ref  = f"attachment://{safe_name}"
        except Exception:
            pass

    try:
        await ctx.message.delete()
    except Exception:
        pass

    event_role_id = event_roles.get(ctx.guild.id)
    content = None
    if event_role_id:
        r = ctx.guild.get_role(event_role_id)
        if r:
            content = r.mention

    await _create_event_message(ctx.channel, ctx.guild, название, количество, image_file, image_ref, content=content, force_join_mode=True)


@bot.command(name="афк")
async def create_afk(ctx):
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    """!афк — создать панель АФК в этом канале"""
    guild_id = ctx.guild.id
    if guild_id not in afk_list:
        afk_list[guild_id] = {}

    view  = AfkView()
    embed = build_afk_embed(guild_id)
    msg   = await ctx.send(embed=embed, view=view)
    afk_panels[guild_id] = {"message_id": msg.id, "channel_id": ctx.channel.id}
    await ctx.message.delete()


@bot.command(name="инактив")
async def create_inactive(ctx):
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    """!инактив — создать панель инактива в этом канале"""
    guild_id = ctx.guild.id
    if guild_id not in inactive_list:
        inactive_list[guild_id] = {}

    view  = InactiveView()
    embed = build_inactive_embed(guild_id)
    msg   = await ctx.send(embed=embed, view=view)
    inactive_panels[guild_id] = {"message_id": msg.id, "channel_id": ctx.channel.id}
    await ctx.message.delete()


@tree.command(name="тикет", description="Создать панель заявок")
@app_commands.describe(
    канал_панели="Канал, куда отправить кнопку заявки",
    категория="Категория, где будут создаваться каналы-тикеты",
)
async def slash_ticket(interaction: discord.Interaction, канал_панели: discord.TextChannel, категория: discord.CategoryChannel):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    tt = ticket_texts.get(interaction.guild_id, {})
    embed = discord.Embed(
        title=tt.get("title", DEFAULT_TICKET_TITLE),
        description=tt.get("desc", DEFAULT_TICKET_DESC),
        color=discord.Color.red(),
    )
    img = tt.get("image", DEFAULT_TICKET_IMAGE)
    if img:
        embed.set_image(url=img)
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)

    view = TicketPanelView(категория.id)
    msg  = await канал_панели.send(embed=embed, view=view)

    ticket_panels[interaction.guild_id] = {
        "panel_channel_id": канал_панели.id,
        "category_id":      категория.id,
        "message_id":       msg.id,
    }
    save_data()

    await interaction.response.send_message(
        f"✅ Панель отправлена в {канал_панели.mention}. Тикеты будут создаваться в **{категория.name}**",
        ephemeral=True,
    )


@tree.command(name="тикет_менеджер", description="Назначить роль тикет-менеджера")
@app_commands.describe(роль="Роль, которая тегается в тикетах и может их рассматривать")
async def slash_ticket_manager(interaction: discord.Interaction, роль: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    ticket_manager_roles[interaction.guild_id] = роль.id
    save_data()
    await interaction.response.send_message(
        f"✅ Роль тикет-менеджера установлена: {роль.mention}",
        ephemeral=True,
    )


@tree.command(name="тикет_доступ", description="Добавить роль с доступом к тикетам (видит канал)")
@app_commands.describe(роль="Роль, которая будет видеть канал тикета")
async def slash_ticket_viewer_add(interaction: discord.Interaction, роль: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    gid = interaction.guild_id
    if gid not in ticket_viewer_roles:
        ticket_viewer_roles[gid] = []
    if роль.id not in ticket_viewer_roles[gid]:
        ticket_viewer_roles[gid].append(роль.id)
    save_data()
    roles_list = ", ".join(f"<@&{rid}>" for rid in ticket_viewer_roles[gid])
    await interaction.response.send_message(
        f"✅ {роль.mention} добавлена к тикетам.\nВсе роли с доступом: {roles_list}",
        ephemeral=True,
    )


@tree.command(name="тикет_доступ_убрать", description="Убрать роль из доступа к тикетам")
@app_commands.describe(роль="Роль, которую нужно убрать")
async def slash_ticket_viewer_remove(interaction: discord.Interaction, роль: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    gid = interaction.guild_id
    viewers = ticket_viewer_roles.get(gid, [])
    if роль.id not in viewers:
        return await interaction.response.send_message(f"❌ {роль.mention} и так не в списке доступа.", ephemeral=True)
    viewers.remove(роль.id)
    ticket_viewer_roles[gid] = viewers
    save_data()
    await interaction.response.send_message(f"✅ {роль.mention} убрана из доступа к тикетам.", ephemeral=True)


@tree.command(name="тикет_пинг", description="Роль, которая тегается в сообщении тикета")
@app_commands.describe(роль="Роль для тега (если не задана — тегается тикет-менеджер)")
async def slash_ticket_ping(interaction: discord.Interaction, роль: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    ticket_ping_role[interaction.guild_id] = роль.id
    save_data()
    await interaction.response.send_message(
        f"✅ В тикетах будет тегаться: {роль.mention}",
        ephemeral=True,
    )


class TicketTextModal(ui.Modal, title="✏️ Текст панели заявок"):
    title_input = ui.TextInput(
        label="Заголовок",
        default="📋 Вступление в DIAMOND",
        max_length=256,
        required=True,
    )
    desc_input = ui.TextInput(
        label="Описание",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=True,
    )
    image_input = ui.TextInput(
        label="Ссылка на картинку (оставь пустым — без картинки)",
        required=False,
        placeholder="https://...",
    )

    def __init__(self, guild_id: int):
        super().__init__()
        tt = ticket_texts.get(guild_id, {})
        self.title_input.default = tt.get("title", DEFAULT_TICKET_TITLE)
        self.desc_input.default  = tt.get("desc",  DEFAULT_TICKET_DESC)
        self.image_input.default = tt.get("image", DEFAULT_TICKET_IMAGE)
        self._guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        ticket_texts[self._guild_id] = {
            "title": str(self.title_input),
            "desc":  str(self.desc_input),
            "image": str(self.image_input).strip(),
        }
        save_data()

        # Обновить существующую панель если есть
        panel = ticket_panels.get(self._guild_id, {})
        if panel.get("message_id") and panel.get("panel_channel_id"):
            try:
                ch  = interaction.guild.get_channel(panel["panel_channel_id"])
                msg = await ch.fetch_message(panel["message_id"])
                tt  = ticket_texts[self._guild_id]
                embed = discord.Embed(title=tt["title"], description=tt["desc"], color=discord.Color.red())
                if tt["image"]:
                    embed.set_image(url=tt["image"])
                embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
                await msg.edit(embed=embed)
            except Exception:
                pass

        await interaction.response.send_message("✅ Текст панели обновлён!", ephemeral=True)


@tree.command(name="тикет_текст", description="Изменить заголовок и текст панели заявок")
async def slash_ticket_text(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    await interaction.response.send_modal(TicketTextModal(interaction.guild_id))


@tree.command(name="лог_отказов", description="Настроить канал для логов отклонённых заявок")
@app_commands.describe(канал="Канал, куда будут дублироваться отказы")
async def slash_reject_log(interaction: discord.Interaction, канал: discord.TextChannel):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    reject_log_channels[interaction.guild_id] = канал.id
    save_data()
    await interaction.response.send_message(
        f"✅ Отказы по заявкам теперь дублируются в {канал.mention}",
        ephemeral=True,
    )


# ─────────────────────────────────────────────
# 💰 БАЛЛЫ, WARN, МАГАЗИН — PREFIX-КОМАНДЫ
# ─────────────────────────────────────────────
@bot.command(name="баланс")
async def balance(ctx, пользователь: discord.Member = None):
    """!баланс [@пользователь] — показать баланс"""
    target = пользователь or ctx.author
    embed  = build_points_embed(ctx.guild.id, target.id)
    embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
    await ctx.send(embed=embed)


@tree.command(name="магазин", description="Развернуть панель магазина в этом канале")
async def slash_shop(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    gid  = interaction.guild_id
    embed = build_shop_embed(gid)
    view  = ShopView(gid)
    msg   = await interaction.channel.send(embed=embed, view=view)
    shop_panels[gid] = {"channel_id": interaction.channel_id, "message_id": msg.id}
    await interaction.response.send_message("✅ Панель магазина развёрнута!", ephemeral=True)


class AddItemModal(ui.Modal, title="🛒 Добавить товар"):
    name        = ui.TextInput(label="Название товара", placeholder="Снять варн", required=True)
    price       = ui.TextInput(label="Цена (баллы)", placeholder="500", required=True)
    emoji       = ui.TextInput(label="Эмодзи", placeholder="⚠️", required=False, max_length=8)
    description = ui.TextInput(label="Описание", placeholder="Снимает один варн", required=False)
    action      = ui.TextInput(
        label="Действие: remove_warn / give_role / notify",
        placeholder="notify",
        required=True,
        max_length=50,
    )

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        try:
            price_val = int(str(self.price).strip())
        except ValueError:
            return await interaction.response.send_message("❌ Цена должна быть числом.", ephemeral=True)

        action_val = str(self.action).strip().lower()
        if action_val not in ("remove_warn", "give_role", "notify"):
            return await interaction.response.send_message(
                "❌ Действие должно быть: `remove_warn`, `give_role` или `notify`", ephemeral=True
            )

        if gid not in guild_shop_items:
            guild_shop_items[gid] = {}

        import time
        item_id = str(int(time.time()))
        guild_shop_items[gid][item_id] = {
            "name":        str(self.name).strip(),
            "price":       price_val,
            "emoji":       str(self.emoji).strip() or "🛒",
            "description": str(self.description).strip(),
            "action":      action_val,
            "role_id":     None,
        }
        save_data()
        await refresh_shop_message(interaction.guild)
        await interaction.response.send_message(
            f"✅ Товар **{self.name}** добавлен!\n"
            f"Если действие `give_role` — используй `/товар_роль {item_id} @роль` для привязки роли.",
            ephemeral=True,
        )


@tree.command(name="добавить_товар", description="Добавить товар в магазин")
async def slash_add_item(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    await interaction.response.send_modal(AddItemModal())


@tree.command(name="убрать_товар", description="Удалить товар из магазина")
@app_commands.describe(товар_id="ID товара (виден в /список_товаров)")
async def slash_remove_item(interaction: discord.Interaction, товар_id: str):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    gid   = interaction.guild_id
    items = guild_shop_items.get(gid, {})
    if товар_id not in items:
        return await interaction.response.send_message("❌ Товар не найден.", ephemeral=True)
    name = items[товар_id]["name"]
    del guild_shop_items[gid][товар_id]
    save_data()
    await refresh_shop_message(interaction.guild)
    await interaction.response.send_message(f"✅ Товар **{name}** удалён.", ephemeral=True)


@tree.command(name="список_товаров", description="Список всех товаров в магазине (с ID)")
async def slash_list_items(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    gid   = interaction.guild_id
    items = guild_shop_items.get(gid, {})
    if not items:
        return await interaction.response.send_message("Магазин пуст.", ephemeral=True)
    lines = [f"`{iid}` — {i['emoji']} **{i['name']}** | {i['price']} 💎 | `{i['action']}`" for iid, i in items.items()]
    embed = discord.Embed(title="🛒 Товары магазина", description="\n".join(lines), color=discord.Color.gold())
    embed.set_footer(text="Используй ID для /убрать_товар или /товар_роль")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="товар_роль", description="Привязать роль к товару с действием give_role")
@app_commands.describe(товар_id="ID товара", роль="Роль которая выдаётся при покупке")
async def slash_item_role(interaction: discord.Interaction, товар_id: str, роль: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    gid   = interaction.guild_id
    items = guild_shop_items.get(gid, {})
    if товар_id not in items:
        return await interaction.response.send_message("❌ Товар не найден.", ephemeral=True)
    if items[товар_id]["action"] != "give_role":
        return await interaction.response.send_message("❌ Действие товара не `give_role`.", ephemeral=True)
    guild_shop_items[gid][товар_id]["role_id"] = роль.id
    save_data()
    await interaction.response.send_message(f"✅ Роль {роль.mention} привязана к товару **{items[товар_id]['name']}**.", ephemeral=True)


@bot.command(name="дать")
async def give_points_cmd(ctx, пользователь: discord.Member, количество: int):
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    """!дать @пользователь количество — выдать баллы"""
    if количество < 1:
        return await ctx.send("❌ Количество должно быть больше 0!", delete_after=5)
    add_points(ctx.guild.id, пользователь.id, количество)
    new_balance = get_points(ctx.guild.id, пользователь.id)
    embed = discord.Embed(
        title="💰 Баллы начислены!",
        description=f"{пользователь.mention} получил **{количество}** 💎\nНовый баланс: **{new_balance}** 💎",
        color=discord.Color.green(),
        timestamp=datetime.now(),
    )
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    await ctx.send(embed=embed)


@bot.command(name="снять")
async def remove_points_cmd(ctx, пользователь: discord.Member, количество: int):
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    """!снять @пользователь количество — снять баллы"""
    if количество < 1:
        return await ctx.send("❌ Количество должно быть больше 0!", delete_after=5)
    current     = get_points(ctx.guild.id, пользователь.id)
    new_balance = max(0, current - количество)
    set_points(ctx.guild.id, пользователь.id, new_balance)
    embed = discord.Embed(
        title="💰 Баллы сняты!",
        description=f"У {пользователь.mention} снято **{количество}** 💎\nНовый баланс: **{new_balance}** 💎",
        color=discord.Color.orange(),
        timestamp=datetime.now(),
    )
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    await ctx.send(embed=embed)


@bot.command(name="warn")
async def warn_user(ctx, пользователь: discord.Member, количество: int, *, причина: str):
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    """!warn @пользователь <1-3> причина — выдать варн"""
    if количество not in (1, 2, 3):
        return await ctx.send("❌ Укажи количество варнов: 1, 2 или 3. Пример: `!warn @user 2 причина`", delete_after=6)

    set_warn(ctx.guild.id, пользователь.id, количество, причина, ctx.author.id)

    # Убрать все старые варн-роли и назначить новую
    guild_warn_roles = warn_roles.get(ctx.guild.id, {})
    roles_to_remove = [ctx.guild.get_role(rid) for rid in guild_warn_roles.values() if ctx.guild.get_role(rid)]
    new_role = ctx.guild.get_role(guild_warn_roles.get(количество))
    try:
        await пользователь.remove_roles(*[r for r in roles_to_remove if r], reason="Обновление варн-роли")
        if new_role:
            await пользователь.add_roles(new_role, reason=f"Warn {количество}/3")
    except Exception:
        pass

    embed = discord.Embed(
        title="⚠️ WARN",
        description=f"{пользователь.mention} получил warn!",
        color=discord.Color.red(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="Причина", value=причина, inline=False)
    embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
    embed.add_field(name="Варны", value=f"**{количество}/3**", inline=True)
    if new_role:
        embed.add_field(name="Роль", value=new_role.mention, inline=True)
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    await ctx.send(embed=embed)

    try:
        dm_embed = discord.Embed(
            title="⚠️ Вы получили warn",
            description=f"**Причина:** {причина}\n**Варны:** {количество}/3",
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )
        dm_embed.add_field(name="Модератор", value=ctx.author.mention)
        dm_embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
        await пользователь.send(embed=dm_embed)
    except Exception:
        pass

    try:
        await ctx.message.delete()
    except Exception:
        pass


@bot.command(name="снять_варн")
async def admin_remove_warn(ctx, пользователь: discord.Member):
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    """!снять_варн @пользователь — снять варн"""
    if remove_warn(ctx.guild.id, пользователь.id):
        # Убрать все варн-роли
        guild_warn_roles = warn_roles.get(ctx.guild.id, {})
        roles_to_remove = [ctx.guild.get_role(rid) for rid in guild_warn_roles.values() if ctx.guild.get_role(rid)]
        try:
            await пользователь.remove_roles(*[r for r in roles_to_remove if r], reason="Снятие варна")
        except Exception:
            pass
        embed = discord.Embed(
            title="✅ Warn снят",
            description=f"У {пользователь.mention} снят warn",
            color=discord.Color.green(),
            timestamp=datetime.now(),
        )
        embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ У пользователя нет warn'ов!", delete_after=5)

    try:
        await ctx.message.delete()
    except Exception:
        pass


@bot.command(name="роль_варн")
async def set_warn_role(ctx, номер: int, роль: discord.Role):
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    """!роль_варн <1-3> @роль — привязать роль к уровню варна"""
    if номер not in (1, 2, 3):
        return await ctx.send("❌ Укажи номер 1, 2 или 3. Пример: `!роль_варн 1 @Варн1/3`", delete_after=6)
    if ctx.guild.id not in warn_roles:
        warn_roles[ctx.guild.id] = {}
    warn_roles[ctx.guild.id][номер] = роль.id
    save_data()
    embed = discord.Embed(
        title="✅ Варн-роль настроена",
        description=f"Варн **{номер}/3** → {роль.mention}",
        color=discord.Color.green(),
    )
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    await ctx.send(embed=embed)
    await ctx.message.delete()


@bot.command(name="warnlist")
async def warnlist(ctx):
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()
    """!warnlist — список всех участников с варнами"""
    guild_warns = warns_db.get(ctx.guild.id, {})
    active = {uid: d for uid, d in guild_warns.items() if d.get("warns", 0) > 0}

    if not active:
        return await ctx.send("✅ Ни у кого нет варнов!", delete_after=6)

    lines = []
    for i, (uid, d) in enumerate(active.items(), 1):
        lines.append(
            f"**{i}.** <@{uid}> — **{d['warns']}/3** варн(а)\n"
            f"└ Причина: {d['reason']} | Модератор: <@{d['moderator']}>"
        )

    embed = discord.Embed(
        title="⚠️ Список участников с варнами",
        description="\n\n".join(lines),
        color=discord.Color.red(),
        timestamp=datetime.now(),
    )
    embed.set_footer(text=f"DIAMOND • Всего: {len(active)}", icon_url=FOOTER_ICON)
    await ctx.send(embed=embed)
    await ctx.message.delete()


@bot.command(name="замена")
async def замена_cmd(ctx, кого: int, на_кого: int = 0):
    """!замена <айди_кого> <айди_на_кого> — заменить участника в слоте (0 = убрать). Используется в треде сбора."""
    if not is_admin_ctx(ctx):
        return await ctx.message.delete()

    # Найти сбор по thread_id
    thread_id = ctx.channel.id
    msg_id = None
    for mid, data in event_lists.items():
        if data.get("thread_id") == thread_id:
            msg_id = mid
            break

    if msg_id is None:
        return await ctx.send("❌ Эта команда используется только в треде сбора!", delete_after=6)

    data  = event_lists[msg_id]
    slots = data["slots"]

    # Найти слот кого
    target_slot = None
    for slot_num, uid in slots.items():
        if uid == кого:
            target_slot = slot_num
            break

    if target_slot is None:
        return await ctx.send(f"❌ Пользователь `{кого}` не найден ни в одном слоте!", delete_after=6)

    # Если на_кого уже занимает другой слот — освободить его
    if на_кого:
        for slot_num, uid in slots.items():
            if uid == на_кого:
                slots[slot_num] = None
                break

    slots[target_slot] = на_кого if на_кого else None

    # Обновить эмбед
    try:
        channel = bot.get_channel(data["channel_id"])
        msg = await channel.fetch_message(msg_id)
        join_mode = data.get("mode") == "join"
        embed = build_event_embed(data["title"], data["max"], slots, data.get("image_url"), data.get("note"), join_mode=join_mode)
        view = JoinEventView(msg_id) if join_mode else EventView(msg_id)
        await msg.edit(embed=embed, view=view)
    except Exception:
        pass

    await update_thread_list(msg_id)

    if на_кого:
        await ctx.send(f"✅ Слот **{target_slot}**: <@{кого}> → <@{на_кого}>", delete_after=10)
    else:
        await ctx.send(f"✅ Слот **{target_slot}**: <@{кого}> убран", delete_after=10)
    await ctx.message.delete()


@bot.command(name="роль_админ")
async def set_admin_role(ctx, роль: discord.Role):
    """!роль_админ @роль — установить роль администратора бота (требует Discord-администратора)"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.message.delete()
    admin_roles[ctx.guild.id] = роль.id
    save_data()
    embed = discord.Embed(
        title="✅ Роль администратора установлена",
        description=(
            f"Теперь все команды бота доступны для {роль.mention}.\n\n"
            f"Следующий шаг — настрой остальные роли и панели:\n"
            f"`!роль_взп` `!роль_мп` `!роль_реаки` `!роль_варн`\n"
            f"`/тикет` `/тикет_менеджер` `/магазин` `/настройки`"
        ),
        color=discord.Color.green(),
    )
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    await ctx.send(embed=embed, delete_after=30)
    await ctx.message.delete()


@tree.command(name="настройки", description="Показать текущую конфигурацию бота на этом сервере")
async def slash_settings(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)

    g = interaction.guild

    def role_str(role_id):
        if not role_id:
            return "⚠️ *не задана*"
        r = g.get_role(role_id)
        return r.mention if r else f"⚠️ *удалена (ID: {role_id})*"

    def channel_str(ch_id):
        if not ch_id:
            return "⚠️ *не задан*"
        c = g.get_channel(ch_id)
        return c.mention if c else f"⚠️ *удалён (ID: {ch_id})*"

    gid = g.id
    wr  = warn_roles.get(gid, {})
    tp  = ticket_panels.get(gid, {})

    embed = discord.Embed(
        title="⚙️ Конфигурация бота",
        color=discord.Color.blurple(),
        timestamp=datetime.now(),
    )
    embed.add_field(
        name="🔑 Роли",
        value=(
            f"Администратор: {role_str(admin_roles.get(gid))}\n"
            f"Тикет-менеджер: {role_str(ticket_manager_roles.get(gid))}\n"
            f"Роль ВЗП: {role_str(vzp_roles.get(gid))}\n"
            f"Роль МП: {role_str(mp_roles.get(gid))}\n"
            f"Роль реаки: {role_str(event_roles.get(gid))}\n"
            f"Варн 1/3: {role_str(wr.get(1))}\n"
            f"Варн 2/3: {role_str(wr.get(2))}\n"
            f"Варн 3/3: {role_str(wr.get(3))}"
        ),
        inline=False,
    )
    viewers = ticket_viewer_roles.get(gid, [])
    viewers_str = ", ".join(f"<@&{rid}>" for rid in viewers) if viewers else "⚠️ *не заданы*"
    embed.add_field(
        name="📋 Тикеты",
        value=(
            f"Канал панели: {channel_str(tp.get('panel_channel_id'))}\n"
            f"Тикет-менеджер: {role_str(ticket_manager_roles.get(gid))}\n"
            f"Роль для тега: {role_str(ticket_ping_role.get(gid))}\n"
            f"Роли с доступом: {viewers_str}\n"
            f"Лог отказов: {channel_str(reject_log_channels.get(gid))}\n"
            f"Счётчик тикетов: **{ticket_counters.get(gid, 0)}**"
        ),
        inline=False,
    )
    afk_p = afk_panels.get(gid, {})
    inact_p = inactive_panels.get(gid, {})
    embed.add_field(
        name="📊 Панели",
        value=(
            f"АФК: {channel_str(afk_p.get('channel_id'))}\n"
            f"Инактив: {channel_str(inact_p.get('channel_id'))}"
        ),
        inline=False,
    )
    ecr = event_command_roles.get(gid, {})
    def roles_list_str(type_key):
        ids = ecr.get(type_key, [])
        return ", ".join(f"<@&{rid}>" for rid in ids) if ids else "*только админ*"
    embed.add_field(
        name="🎯 Доступ к сборам",
        value=(
            f"`!взп`: {roles_list_str('взп')}\n"
            f"`!мп`: {roles_list_str('мп')}\n"
            f"`!реаки`: {roles_list_str('реаки')}"
        ),
        inline=False,
    )
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ─────────────────────────────────────────────
# ПРИВАТНЫЕ КОМНАТЫ
# ─────────────────────────────────────────────
def build_private_vc_embed(owner: discord.Member, vc: discord.VoiceChannel) -> discord.Embed:
    limit = str(vc.user_limit) if vc.user_limit else "∞"
    embed = discord.Embed(
        title="🔒 Управление приватной комнатой",
        description=(
            "`+` • Добавить слот             `−` • Убрать слот\n"
            "👥 • Изменить слоты            🔄 • Передать канал\n"
            "🔓 • Открыть канал             🔒 • Закрыть канал\n"
            "👤➕ • Добавить пользователя  👤➖ • Убрать пользователя\n"
            "🙈 • Скрыть канал               👁 • Показать канал\n"
            "✏️ • Переименовать              🚫 • Заблокировать\n\n"
            "*Кнопки работают только для владельца канала.*"
        ),
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="👑 Владелец", value=owner.mention, inline=True)
    embed.add_field(name="🔊 Канал",    value=vc.mention,    inline=True)
    embed.add_field(name="👥 Слоты",   value=limit,          inline=True)
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    return embed


async def resolve_member(guild: discord.Guild, text: str) -> discord.Member | None:
    text = text.strip().lstrip("<@!").rstrip(">")
    try:
        return guild.get_member(int(text)) or await guild.fetch_member(int(text))
    except Exception:
        return discord.utils.find(
            lambda m: m.name.lower() == text.lower() or m.display_name.lower() == text.lower(),
            guild.members,
        )


class PVCRenameModal(ui.Modal, title="✏️ Переименовать канал"):
    name = ui.TextInput(label="Новое название", max_length=100, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        vc, _ = _get_owner_vc(interaction)
        if not vc:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await vc.edit(name=str(self.name))
        await interaction.response.send_message(f"✅ Канал переименован: **{self.name}**", ephemeral=True)

class PVCSlotsModal(ui.Modal, title="👥 Изменить количество слотов"):
    slots = ui.TextInput(label="Количество слотов (0 = без лимита)", placeholder="10", required=True, max_length=3)
    async def on_submit(self, interaction: discord.Interaction):
        vc, _ = _get_owner_vc(interaction)
        if not vc:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        try:
            n = max(0, min(99, int(str(self.slots))))
        except ValueError:
            return await interaction.response.send_message("❌ Введите число.", ephemeral=True)
        await vc.edit(user_limit=n)
        label = str(n) if n else "∞"
        await interaction.response.send_message(f"✅ Слотов: **{label}**", ephemeral=True)

class PVCUserActionModal(ui.Modal):
    user_input = ui.TextInput(label="Упомяните или введите ID пользователя", required=True)
    def __init__(self, action: str):
        titles = {
            "add": "👤➕ Добавить пользователя",
            "remove": "👤➖ Убрать пользователя",
            "transfer": "🔄 Передать канал",
            "block": "🚫 Заблокировать пользователя",
        }
        super().__init__(title=titles.get(action, "Действие"))
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        vc, data = _get_owner_vc(interaction)
        if not vc:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        member = await resolve_member(interaction.guild, str(self.user_input))
        if not member:
            return await interaction.response.send_message("❌ Пользователь не найден.", ephemeral=True)
        if member == interaction.user:
            return await interaction.response.send_message("❌ Нельзя применить к себе.", ephemeral=True)

        if self.action == "add":
            await vc.set_permissions(member, connect=True, view_channel=True)
            await interaction.response.send_message(f"✅ {member.mention} добавлен в канал.", ephemeral=True)

        elif self.action == "remove":
            await vc.set_permissions(member, overwrite=None)
            if member in vc.members:
                await member.move_to(None)
            await interaction.response.send_message(f"✅ {member.mention} убран из канала.", ephemeral=True)

        elif self.action == "transfer":
            private_vcs[vc.id]["owner_id"] = member.id
            await vc.set_permissions(interaction.user, overwrite=None)
            await vc.set_permissions(member, connect=True, manage_channels=True, move_members=True)
            # Обновить панель
            await _refresh_pvc_panel(interaction.guild, vc)
            await interaction.response.send_message(f"✅ Канал передан {member.mention}.", ephemeral=True)

        elif self.action == "block":
            await vc.set_permissions(member, connect=False, view_channel=False)
            if member in vc.members:
                await member.move_to(None)
            await interaction.response.send_message(f"✅ {member.mention} заблокирован.", ephemeral=True)


def _get_owner_vc(interaction: discord.Interaction):
    """Возвращает (VoiceChannel, data) приватного канала владельца."""
    for vc_id, data in private_vcs.items():
        if data["owner_id"] == interaction.user.id and data["guild_id"] == interaction.guild_id:
            vc = interaction.guild.get_channel(vc_id)
            if vc:
                return vc, data
    return None, None


async def _refresh_pvc_panel(guild: discord.Guild, vc: discord.VoiceChannel):
    data = private_vcs.get(vc.id)
    if not data:
        return
    owner = guild.get_member(data["owner_id"])
    if not owner:
        return
    panel_ch = guild.get_channel(data.get("panel_channel_id"))
    if not panel_ch:
        return
    try:
        msg = await panel_ch.fetch_message(data["panel_msg_id"])
        await msg.edit(embed=build_private_vc_embed(owner, vc))
    except Exception:
        pass


class PrivateVCView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(emoji="➕", style=discord.ButtonStyle.secondary, custom_id="pvc_add_slot", row=0)
    async def add_slot(self, interaction: discord.Interaction, button: ui.Button):
        vc, _ = _get_owner_vc(interaction)
        if not vc:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        new_limit = (vc.user_limit or 0) + 1
        await vc.edit(user_limit=new_limit)
        await interaction.response.send_message(f"✅ Слотов: **{new_limit}**", ephemeral=True)

    @ui.button(emoji="➖", style=discord.ButtonStyle.secondary, custom_id="pvc_remove_slot", row=0)
    async def remove_slot(self, interaction: discord.Interaction, button: ui.Button):
        vc, _ = _get_owner_vc(interaction)
        if not vc:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        new_limit = max(0, (vc.user_limit or 1) - 1)
        await vc.edit(user_limit=new_limit)
        label = str(new_limit) if new_limit else "∞"
        await interaction.response.send_message(f"✅ Слотов: **{label}**", ephemeral=True)

    @ui.button(emoji="👥", style=discord.ButtonStyle.secondary, custom_id="pvc_set_slots", row=0)
    async def set_slots(self, interaction: discord.Interaction, button: ui.Button):
        _, data = _get_owner_vc(interaction)
        if not data:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await interaction.response.send_modal(PVCSlotsModal())

    @ui.button(emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="pvc_open", row=0)
    async def open_channel(self, interaction: discord.Interaction, button: ui.Button):
        vc, _ = _get_owner_vc(interaction)
        if not vc:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await vc.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("✅ Канал открыт.", ephemeral=True)

    @ui.button(emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="pvc_close", row=0)
    async def close_channel(self, interaction: discord.Interaction, button: ui.Button):
        vc, _ = _get_owner_vc(interaction)
        if not vc:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await vc.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("✅ Канал закрыт.", ephemeral=True)

    @ui.button(emoji="👤", style=discord.ButtonStyle.secondary, custom_id="pvc_add_user", row=1)
    async def add_user(self, interaction: discord.Interaction, button: ui.Button):
        _, data = _get_owner_vc(interaction)
        if not data:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await interaction.response.send_modal(PVCUserActionModal("add"))

    @ui.button(emoji="🚷", style=discord.ButtonStyle.secondary, custom_id="pvc_remove_user", row=1)
    async def remove_user(self, interaction: discord.Interaction, button: ui.Button):
        _, data = _get_owner_vc(interaction)
        if not data:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await interaction.response.send_modal(PVCUserActionModal("remove"))

    @ui.button(emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="pvc_transfer", row=1)
    async def transfer(self, interaction: discord.Interaction, button: ui.Button):
        _, data = _get_owner_vc(interaction)
        if not data:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await interaction.response.send_modal(PVCUserActionModal("transfer"))

    @ui.button(emoji="🙈", style=discord.ButtonStyle.secondary, custom_id="pvc_hide", row=1)
    async def hide_channel(self, interaction: discord.Interaction, button: ui.Button):
        vc, _ = _get_owner_vc(interaction)
        if not vc:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await vc.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message("✅ Канал скрыт.", ephemeral=True)

    @ui.button(emoji="👁", style=discord.ButtonStyle.secondary, custom_id="pvc_show", row=1)
    async def show_channel(self, interaction: discord.Interaction, button: ui.Button):
        vc, _ = _get_owner_vc(interaction)
        if not vc:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await vc.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message("✅ Канал показан.", ephemeral=True)

    @ui.button(emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="pvc_rename", row=2)
    async def rename(self, interaction: discord.Interaction, button: ui.Button):
        _, data = _get_owner_vc(interaction)
        if not data:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await interaction.response.send_modal(PVCRenameModal())

    @ui.button(emoji="🚫", style=discord.ButtonStyle.secondary, custom_id="pvc_block", row=2)
    async def block_user(self, interaction: discord.Interaction, button: ui.Button):
        _, data = _get_owner_vc(interaction)
        if not data:
            return await interaction.response.send_message("❌ У вас нет приватного канала!", ephemeral=True)
        await interaction.response.send_modal(PVCUserActionModal("block"))


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    settings = private_vc_settings.get(member.guild.id)
    if not settings:
        return

    create_ch_id = settings.get("create_channel_id")

    # Пользователь зашёл в канал-триггер
    if after.channel and after.channel.id == create_ch_id:
        category = member.guild.get_channel(settings.get("category_id"))
        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
            member: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True),
            member.guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True),
        }
        try:
            vc = await member.guild.create_voice_channel(
                name=f"🔒 {member.display_name}",
                category=category,
                user_limit=10,
                overwrites=overwrites,
            )
            await member.move_to(vc)
        except Exception:
            return

        private_vcs[vc.id] = {
            "owner_id": member.id,
            "guild_id": member.guild.id,
            "panel_msg_id": None,
            "panel_channel_id": None,
        }

        panel_ch_id = settings.get("panel_channel_id")
        if panel_ch_id:
            panel_ch = member.guild.get_channel(panel_ch_id)
            if panel_ch:
                try:
                    msg = await panel_ch.send(
                        embed=build_private_vc_embed(member, vc),
                        view=PrivateVCView(),
                    )
                    private_vcs[vc.id]["panel_msg_id"]     = msg.id
                    private_vcs[vc.id]["panel_channel_id"] = panel_ch_id
                except Exception:
                    pass

    # Пользователь вышел из приватного канала — удаляем если пусто
    if before.channel and before.channel.id in private_vcs:
        vc = before.channel
        if len(vc.members) == 0:
            data = private_vcs.pop(vc.id, {})
            try:
                await vc.delete(reason="Приватный канал опустел")
            except Exception:
                pass
            if data.get("panel_msg_id") and data.get("panel_channel_id"):
                panel_ch = member.guild.get_channel(data["panel_channel_id"])
                if panel_ch:
                    try:
                        msg = await panel_ch.fetch_message(data["panel_msg_id"])
                        await msg.delete()
                    except Exception:
                        pass


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.message.delete(delay=0)
    elif isinstance(error, (commands.MemberNotFound, commands.BadArgument)):
        await ctx.send("❌ Неверный аргумент. Пример: `!warn @user причина`", delete_after=6)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Не хватает аргумента: `{error.param.name}`", delete_after=6)



# ─────────────────────────────────────────────
# СТАРТ
# ─────────────────────────────────────────────
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Ошибка выполнения команды.", ephemeral=True)


@tree.command(name="приват", description="Настроить систему приватных комнат")
@app_commands.describe(
    канал_создания="Голосовой канал — зайди сюда, чтобы получить приватную комнату",
    категория="Категория, где создаются приватные каналы",
    канал_панели="Текстовый канал, куда присылается панель управления",
)
async def slash_private_vc(
    interaction: discord.Interaction,
    канал_создания: discord.VoiceChannel,
    категория: discord.CategoryChannel,
    канал_панели: discord.TextChannel,
):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    private_vc_settings[interaction.guild_id] = {
        "create_channel_id": канал_создания.id,
        "category_id":       категория.id,
        "panel_channel_id":  канал_панели.id,
    }
    save_data()
    await interaction.response.send_message(
        f"✅ Приватные комнаты настроены!\n"
        f"Триггер: {канал_создания.mention}\n"
        f"Категория: **{категория.name}**\n"
        f"Панель: {канал_панели.mention}",
        ephemeral=True,
    )


@bot.event
async def on_ready():
    load_data()
    bot.add_view(AfkView())
    bot.add_view(InactiveView())
    bot.add_view(PrivateVCView())
    bot.add_view(ApplicationReviewView())
    for guild_id in guild_shop_items:
        bot.add_view(ShopView(guild_id))
    for guild_id, panel in ticket_panels.items():
        cat_id = panel.get("category_id")
        if cat_id:
            bot.add_view(TicketPanelView(cat_id))
    await tree.sync()
    print(f"Bot online: {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="DIAMOND Helper"
    ))


bot.run(os.getenv("DISCORD_TOKEN"))