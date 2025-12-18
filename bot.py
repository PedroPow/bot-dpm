# bot_corregedoria_system.py

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import io
import json
import os
import re
from datetime import datetime, timezone

# =======================
# CONFIG GERAL
# =======================
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

# 👉 evita crash da API
API_URL = "https://exemplo.api/endpoint"

# =======================
# BOT
# =======================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

class MyBot(commands.Bot):
    async def setup_hook(self):
        guild = discord.Object(id=ID_DO_SERVIDOR)
        synced = await self.tree.sync(guild=guild)
        print(f"✅ Slash sincronizados: {[cmd.name for cmd in synced]}")

bot = MyBot(command_prefix="!", intents=intents)

# =======================
# DADOS
# =======================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"convocacoes": [], "pads": [], "ipms": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"convocacoes": [], "pads": [], "ipms": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_record(tipo, record):
    data = load_data()
    mapa = {"convocacao": "convocacoes", "pad": "pads", "ipm": "ipms"}
    data[mapa[tipo]].append(record)
    save_data(data)

def get_counts():
    d = load_data()
    return {
        "convocacoes_abertas": sum(1 for r in d["convocacoes"] if r["status"] == "open"),
        "pads_abertos": sum(1 for r in d["pads"] if r["status"] == "open"),
        "ipms_abertos": sum(1 for r in d["ipms"] if r["status"] == "open"),
    }

def get_member_history(member_id, limit=10):
    d = load_data()
    out = []
    for nome, chave in [("Convocação", "convocacoes"), ("PAD", "pads"), ("IPM", "ipms")]:
        for r in d[chave]:
            if r.get("target_id") == member_id:
                out.append({
                    "type": nome,
                    "timestamp": r["timestamp"],
                    "summary": r["summary"],
                    "status": r["status"]
                })
    return sorted(out, key=lambda x: x["timestamp"], reverse=True)[:limit]

# =======================
# API
# =======================
async def enviar_api(tipo, dados):
    body = dados | {"tipo": tipo}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(API_URL, json=body) as r:
                print("API:", r.status)
    except Exception as e:
        print("API erro:", e)

# =======================
# HELPERS
# =======================
def extract_number(name):
    m = re.search(r'\d+', name)
    return int(m.group()) if m else 999999

# =======================
# VIEW MEMBROS
# =======================
class PaginadoMemberView(discord.ui.View):
    def __init__(self, membros, callback):
        super().__init__(timeout=300)
        self.membros = sorted([m for m in membros if m], key=lambda m: extract_number(m.display_name))
        self.callback = callback
        self.page = 0
        self.render()

    def render(self):
        self.clear_items()
        inicio = self.page * 25
        fim = inicio + 25
        opts = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in self.membros[inicio:fim]
        ]
        select = discord.ui.Select(placeholder="Selecione um policial", options=opts)
        async def cb(inter):
            await self.callback(inter, int(select.values[0]))
        select.callback = cb
        self.add_item(select)

# =======================
# BOTÕES
# =======================
class TicketButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="👮 Convocar Policial", style=discord.ButtonStyle.secondary)
    async def conv(self, interaction: discord.Interaction, _):
        if not any(r.id == CARGO_AUTORIZADO_ID for r in interaction.user.roles):
            return await interaction.response.send_message("Sem permissão.", ephemeral=True)

        categoria = interaction.guild.get_channel(CATEGORIA_CONVOCACAO)
        canal = await interaction.guild.create_text_channel(
            f"convocacao-{interaction.user.name}",
            category=categoria
        )

        membros = [m for m in interaction.guild.members if not m.bot]

        async def proc(inter, mid):
            alvo = inter.guild.get_member(mid)
            await canal.send(f"Convocado: {alvo.mention}")
            record = {
                "id": f"conv-{int(datetime.now().timestamp())}",
                "target_id": alvo.id,
                "author_id": interaction.user.id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "open",
                "summary": "Convocação aberta"
            }
            add_record("convocacao", record)
            await canal.delete()

        await canal.send("Selecione o policial:", view=PaginadoMemberView(membros, proc))

# =======================
# SLASH COMMANDS
# =======================
@bot.tree.command(name="dashboard", guild=discord.Object(id=ID_DO_SERVIDOR))
async def dashboard(interaction: discord.Interaction):
    if not any(r.id == CARGO_AUTORIZADO_ID for r in interaction.user.roles):
        return await interaction.response.send_message("Sem permissão.", ephemeral=True)

    c = get_counts()
    e = discord.Embed(title="📊 Dashboard")
    e.add_field(name="Convocações", value=c["convocacoes_abertas"])
    e.add_field(name="PADs", value=c["pads_abertos"])
    e.add_field(name="IPMs", value=c["ipms_abertos"])
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="mensagem", guild=discord.Object(id=ID_DO_SERVIDOR))
async def mensagem(interaction: discord.Interaction):
    await interaction.response.send_message("Modal funcionando.", ephemeral=True)

# =======================
# READY
# =======================
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

# =======================
# RUN
# =======================
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
