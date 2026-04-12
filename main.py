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

# Панель заявок — заголовок, текст, фото
TICKET_TITLE     = "📋 Вступление в DIAMOND"
TICKET_DESC      = "**TICKET OPEN MURRIETA**\nНабор в семью открыт на серверах: **Murrieta**\nДля тех кто играет ВЗП:\nПолный откат с 2 терр обновленного ВЗП и откат любого ДМ/архивы взп не позднее месячной давности.\nДля тех кто играет РП:\nОткаты с поставок/взх и откат любого ДМ не позднее месячной давности."
TICKET_IMAGE_URL = "https://i.imgur.com/umswh4i.gif"
FOOTER_ICON      = "https://i.imgur.com/nS7FHDR.png"

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

# 💰 БАЛЛЫ И ШТРАФЫ
# { guild_id: { user_id: int } }
points_db: dict = {}

# { guild_id: { user_id: { "warns": int, "reason": str, "moderator": int } } }
warns_db: dict = {}

# 🛒 ПАНЕЛЬ МАГАЗИНА
# { guild_id: { "channel_id": int, "message_id": int } }
shop_panels: dict = {}

# 🎫 ПАНЕЛЬ ТИКЕТОВ
# { guild_id: { "panel_channel_id": int, "review_channel_id": int, "message_id": int } }
ticket_panels: dict = {}

# 🎫 СЧЁТЧИК ТИКЕТОВ { guild_id: int }
ticket_counters: dict = {}

# 📋 КАНАЛ ЛОГОВ ОТКАЗОВ { guild_id: channel_id }
reject_log_channels: dict = {}

# 🎫 РОЛЬ ТИКЕТ-МЕНЕДЖЕРА { guild_id: role_id }
ticket_manager_roles: dict = {}

# 🏎 РОЛЬ МП { guild_id: role_id }
mp_roles: dict = {}

# 🔫 РОЛЬ ВЗП { guild_id: role_id }
vzp_roles: dict = {}

# 🛒 МАГАЗИН
SHOP_ITEMS = {
    "remove_warn": {"name": "Снять warn", "price": 500, "emoji": "⚠️"},
}


# ─────────────────────────────────────────────
# КОНСТАНТЫ
# ─────────────────────────────────────────────
ADMIN_ROLE_ID = 1203160883048484965  # Роль Администратор
MEMBER_ROLE_ID = 1074477117405925486  # Роль Участник


def is_admin(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if isinstance(member, discord.Member):
        return any(role.id == ADMIN_ROLE_ID for role in member.roles)
    return False

def is_ticket_manager(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    tm_role_id = ticket_manager_roles.get(interaction.guild_id)
    return any(role.id in (ADMIN_ROLE_ID, tm_role_id) for role in member.roles if tm_role_id or role.id == ADMIN_ROLE_ID)
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


def set_warn(guild_id: int, user_id: int, reason: str, moderator_id: int):
    if guild_id not in warns_db:
        warns_db[guild_id] = {}
    warns_db[guild_id][user_id] = {
        "warns": warns_db[guild_id].get(user_id, {}).get("warns", 0) + 1,
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


def build_shop_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🛒 Магазин DIAMOND",
        description=(
            "Трать заработанные баллы на полезные товары.\n"
            "Свой баланс смотри командой `/баланс`\n\u200B"
        ),
        color=discord.Color.gold(),
        timestamp=datetime.now(),
    )
    for item_id, item in SHOP_ITEMS.items():
        embed.add_field(
            name=f"{item['emoji']} {item['name']}",
            value=f"Цена: **{item['price']}** 💎\n*Нажми кнопку ниже*",
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
    hours    = ui.TextInput(label="Кол-во часов в игре",       placeholder="2500",                required=True)
    age      = ui.TextInput(label="Возраст",                   placeholder="18",                  required=True)
    families = ui.TextInput(label="В каких семьях был?",       style=discord.TextStyle.paragraph, required=True)
    recoil   = ui.TextInput(label="Откат со стрельбой",        placeholder="DM, Архив, YouTube",  required=True)

    def __init__(self, category_id: int):
        super().__init__()
        self.category_id = category_id

    async def on_submit(self, interaction: discord.Interaction):
        guild      = interaction.guild
        applicant  = interaction.user
        category   = guild.get_channel(self.category_id)
        admin_role   = guild.get_role(ADMIN_ROLE_ID)
        tm_role_id   = ticket_manager_roles.get(guild.id)
        tm_role      = guild.get_role(tm_role_id) if tm_role_id else None

        ticket_counters[guild.id] = ticket_counters.get(guild.id, 0) + 1
        ticket_num = ticket_counters[guild.id]
        save_data()

        ticket_perms = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            applicant: discord.PermissionOverwrite(
                view_channel=True, send_messages=False, read_message_history=True
            ),
        }
        if admin_role:
            overwrites[admin_role] = ticket_perms
        if tm_role:
            overwrites[tm_role] = ticket_perms

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
        embed.add_field(name="👤 Пользователь",      value=f"{applicant.mention} ({applicant})", inline=True)
        embed.add_field(name="🎮 Ник | Статик",       value=str(self.nickname),  inline=True)
        embed.add_field(name="\u200B",                value="\u200B",            inline=True)
        embed.add_field(name="⏱️ Часов в игре",       value=str(self.hours),     inline=True)
        embed.add_field(name="🎂 Возраст",            value=str(self.age),       inline=True)
        embed.add_field(name="\u200B",                value="\u200B",            inline=True)
        embed.add_field(name="🏠 Был в семьях",       value=str(self.families),  inline=False)
        embed.add_field(name="🎯 Откат со стрельбой", value=str(self.recoil),    inline=False)
        embed.set_footer(text=f"DIAMOND • {applicant.id}", icon_url=FOOTER_ICON)

        view = ApplicationReviewView(applicant.id)
        pings = tm_role.mention if tm_role else None
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
# МАГАЗИН - КНОПКИ
# ─────────────────────────────────────────────
class ShopView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Снять warn", style=discord.ButtonStyle.danger, emoji="⚠️", custom_id="shop_remove_warn")
    async def remove_warn(self, interaction: discord.Interaction, button: ui.Button):
        guild_id = interaction.guild_id
        user_id = interaction.user.id
        
        item = SHOP_ITEMS["remove_warn"]
        points = get_points(guild_id, user_id)
        
        if points < item["price"]:
            return await interaction.response.send_message(
                f"❌ Недостаточно баллов! Нужно **{item['price']}** 💎, у вас **{points}** 💎",
                ephemeral=True
            )
        
        warn_data = get_warns(guild_id, user_id)
        if not warn_data:
            return await interaction.response.send_message(
                "✅ У вас нет warn'ов для снятия!",
                ephemeral=True
            )
        
        # Снять warn и списать баллы
        remove_warn(guild_id, user_id)
        add_points(guild_id, user_id, -item["price"])
        
        embed = discord.Embed(
            title="✅ Warn снят!",
            description=f"С вас списано **{item['price']}** 💎",
            color=discord.Color.green(),
            timestamp=datetime.now(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)




# ─────────────────────────────────────────────
# СЛЭШ-КОМАНДЫ
# ─────────────────────────────────────────────
@bot.command(name="роль_реаки")
async def set_event_role(ctx, роль: discord.Role):
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
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


async def _create_event_message(channel, guild, title: str, max_count: int, image_file=None, image_ref: str | None = None, content: str | None = None):
    """Создаёт сбор: эмбед + тред. <= 24 слотов → кнопки-цифры, > 24 → одна кнопка ✅."""
    if not (1 <= max_count <= 100):
        await channel.send("❌ Количество слотов: от 1 до 100!", delete_after=5)
        return

    join_mode = max_count > 24
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
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
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
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
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
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
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
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
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


@bot.command(name="реаки")
async def реаки_cmd(ctx, количество: int = 10, *, название: str = "Мероприятие"):
    """!реаки [количество] [название] — сбор на мероприятие (от лица бота)"""
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
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

    await _create_event_message(ctx.channel, ctx.guild, название, количество, image_file, image_ref)


@bot.command(name="афк")
async def create_afk(ctx):
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
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


@tree.command(name="тикет", description="Создать панель заявок")
@app_commands.describe(
    канал_панели="Канал, куда отправить кнопку заявки",
    категория="Категория, где будут создаваться каналы-тикеты",
)
async def slash_ticket(interaction: discord.Interaction, канал_панели: discord.TextChannel, категория: discord.CategoryChannel):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Недостаточно прав!", ephemeral=True)
    embed = discord.Embed(
        title=TICKET_TITLE,
        description=TICKET_DESC,
        color=discord.Color.red(),
    )
    if TICKET_IMAGE_URL:
        embed.set_image(url=TICKET_IMAGE_URL)
    embed.set_footer(text="DIAMOND", icon_url="https://i.imgur.com/nS7FHDR.png")

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
    embed = build_shop_embed()
    view  = ShopView()
    msg   = await interaction.channel.send(embed=embed, view=view)
    shop_panels[interaction.guild_id] = {"channel_id": interaction.channel_id, "message_id": msg.id}
    await interaction.response.send_message("✅ Панель магазина развёрнута!", ephemeral=True)


@bot.command(name="дать")
async def give_points_cmd(ctx, пользователь: discord.Member, количество: int):
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
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
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
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
async def warn_user(ctx, пользователь: discord.Member, *, причина: str):
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
        return await ctx.message.delete()
    """!warn @пользователь причина — выдать варн"""
    set_warn(ctx.guild.id, пользователь.id, причина, ctx.author.id)
    warns_count = get_warns(ctx.guild.id, пользователь.id)["warns"]

    embed = discord.Embed(
        title="⚠️ WARN",
        description=f"{пользователь.mention} получил warn!",
        color=discord.Color.red(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="Причина", value=причина, inline=False)
    embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
    embed.add_field(name="Всего warn'ов", value=f"**{warns_count}**", inline=True)
    embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
    await ctx.send(embed=embed)

    try:
        dm_embed = discord.Embed(
            title="⚠️ Вы получили warn",
            description=f"**Причина:** {причина}",
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )
        dm_embed.add_field(name="Модератор", value=ctx.author.mention)
        dm_embed.set_footer(text="DIAMOND", icon_url=FOOTER_ICON)
        await пользователь.send(embed=dm_embed)
    except Exception:
        pass


@bot.command(name="снять_варн")
async def admin_remove_warn(ctx, пользователь: discord.Member):
    if not any(r.id == ADMIN_ROLE_ID for r in ctx.author.roles):
        return await ctx.message.delete()
    """!снять_варн @пользователь — снять варн"""
    if remove_warn(ctx.guild.id, пользователь.id):
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


@bot.command(name="замена")
async def замена_cmd(ctx, кого: int, на_кого: int = 0):
    """!замена <айди_кого> <айди_на_кого> — заменить участника в слоте (0 = убрать). Используется в треде сбора."""
    if not any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
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


@bot.event
async def on_ready():
    load_data()
    bot.add_view(AfkView())
    bot.add_view(ShopView())
    bot.add_view(ApplicationReviewView())
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