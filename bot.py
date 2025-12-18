# bot_corregedoria_system.py

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import io
import asyncio
import json
import os
import re
from datetime import datetime, timezone

# ================= CONFIG =================
ID_DO_SERVIDOR = 1343398652336537654
CANAL_ID = 1450353353845510175
CARGO_AUTORIZADO_ID = 1449985109116715008

CATEGORIA_CONVOCACAO = 1450353156662890516
CATEGORIA_PAD = 1450353156662890516
CATEGORIA_IPM = 1450353156662890516

LOG_CONVOCACAO = 1450353434967671016
LOG_PAD = 1450353523949830278
LOG_IPM = 1450353608812924988

CARGO_PAD_I = 1450355744590401680
CARGO_PAD_II = 1450355802828181586
CARGO_PAD_III = 1450355821123993662
CARGO_NOVATO = 1345435302285545652

DATA_FILE = "dpm_data.json"

# 🔴 DEFINA SUA API
API_URL = "https://sua-api-aqui.com/endpoint"

# ================= BOT =================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

class MyBot(commands.Bot):
    async def setup_hook(self):
        guild = discord.Object(id=ID_DO_SERVIDOR)
        synced = await self.tree.sync(guild=guild)
        print("✅ Slash sincronizados:", [c.name for c in synced])

bot = MyBot(command_prefix="!", intents=intents)

# ================= API =================
async def enviar_api(tipo, dados):
    body = dados.copy()
    body["tipo"] = tipo
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, json=body, timeout=10):
                pass
    except Exception as e:
        print("Erro API:", e)

# ================= JSON =================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"convocacoes": [], "pads": [], "ipms": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_record(tipo, record):
    data = load_data()
    data[tipo].append(record)
    save_data(data)

def get_counts():
    data = load_data()
    return {
        "convocacoes": len(data["convocacoes"]),
        "pads": len(data["pads"]),
        "ipms": len(data["ipms"])
    }

def get_member_history(member_id):
    data = load_data()
    history = []
    for tipo in ["convocacoes", "pads", "ipms"]:
        for r in data[tipo]:
            if r.get("target_id") == member_id:
                history.append(r)
    return history

# ================= UTIL =================
def extract_number(name):
    m = re.search(r"\d+", name)
    return int(m.group()) if m else 99999

# ================= VIEW PAGINADA =================
class PaginadoMemberView(discord.ui.View):
    def __init__(self, membros, callback):
        super().__init__(timeout=300)
        membros = sorted(membros, key=lambda m: extract_number(m.display_name))
        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in membros[:25]
        ]
        select = discord.ui.Select(placeholder="Selecione o policial", options=options)

        async def cb(interaction):
            await callback(interaction, int(select.values[0]))

        select.callback = cb
        self.add_item(select)

# ================= BOTÕES =================
class TicketButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="👮 Convocar", style=discord.ButtonStyle.secondary)
    async def convocar(self, interaction, _):
        if CARGO_AUTORIZADO_ID not in [r.id for r in interaction.user.roles]:
            return await interaction.response.send_message("Sem permissão", ephemeral=True)

        categoria = interaction.guild.get_channel(CATEGORIA_CONVOCACAO)
        canal = await interaction.guild.create_text_channel(
            f"convocacao-{interaction.user.name}",
            category=categoria
        )

        membros = [m for m in interaction.guild.members if not m.bot]

        async def processar(inter, membro_id):
            convocado = inter.guild.get_member(membro_id)
            await canal.send("Data da convocação:")
            data = await bot.wait_for("message", check=lambda m: m.channel == canal)
            await canal.send("Hora:")
            hora = await bot.wait_for("message", check=lambda m: m.channel == canal)

            record = {
                "target_id": convocado.id,
                "data": data.content,
                "hora": hora.content,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            add_record("convocacoes", record)

            await canal.delete()

        await canal.send("Selecione o policial:", view=PaginadoMemberView(membros, processar))
        await interaction.response.defer(ephemeral=True)

# ================= SLASH =================
@bot.tree.command(name="dashboard", guild=discord.Object(id=ID_DO_SERVIDOR))
async def dashboard(interaction):
    counts = get_counts()
    embed = discord.Embed(title="📊 Dashboard")
    embed.add_field(name="Convocações", value=counts["convocacoes"])
    embed.add_field(name="PADs", value=counts["pads"])
    embed.add_field(name="IPMs", value=counts["ipms"])
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= READY =================
@bot.event
async def on_ready():
    print(f"🔥 Conectado como {bot.user}")
    canal = bot.get_channel(CANAL_ID)
    if canal:
        await canal.send(
            embed=discord.Embed(
                title="DPM | Corregedoria",
                description="Use os botões abaixo"
            ),
            view=TicketButtons()
        )

# ================= RUN =================
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
