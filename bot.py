# bot_corregedoria_system.py
# Versão atualizada: adiciona dashboard, status de militar e armazenamento em JSON.
# IMPORTANTE: Defina a variável de ambiente DISCORD_TOKEN com o token do bot.
# Ex: (Windows PowerShell) $env:DISCORD_TOKEN="seu_token_aqui"
#     (Linux/macOS) export DISCORD_TOKEN="seu_token_aqui"
import aiohttp
import discord
from discord.ext import commands
import re
import aiohttp
import io
import asyncio
import json
import os
from datetime import datetime, timezone

from discord import app_commands

import requests

import requests



# ---------- CONFIGURAÇÃO ----------
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

ID_DO_SERVIDOR = 1343398652336537654

intents = discord.Intents.default()
intents.members = True

class MyBot(commands.Bot):
    async def setup_hook(self):
        guild = discord.Object(id=ID_DO_SERVIDOR)
        await self.tree.sync(guild=guild)
        print("✅ Slash commands sincronizados com sucesso")

bot = MyBot(command_prefix="!", intents=intents)

# IDs - ajuste conforme seu servidor
ID_DO_SERVIDOR = 1343398652336537654  # Troque pelo ID real do seu servidor
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

DATA_FILE = "dpm_data.json"  # arquivo local para armazenar processos

# ---------- UTILITÁRIOS DE DADOS ----------
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
    key = {"convocacao": "convocacoes", "pad": "pads", "ipm": "ipms"}[tipo]
    data[key].append(record)
    save_data(data)

def get_counts():
    data = load_data()
    return {
        "convocacoes_abertas": sum(1 for r in data["convocacoes"] if r.get("status") == "open"),
        "pads_abertos": sum(1 for r in data["pads"] if r.get("status") == "open"),
        "ipms_abertos": sum(1 for r in data["ipms"] if r.get("status") == "open"),
    }

def get_member_history(member_id, limit=10):
    data = load_data()
    items = []
    for tipo, key in [("Convocação", "convocacoes"), ("PAD", "pads"), ("IPM", "ipms")]:
        for r in data[key]:
            if r.get("target_id") == member_id:
                items.append({"type": tipo, "timestamp": r.get("timestamp"), "summary": r.get("summary"), "status": r.get("status")})
    items_sorted = sorted(items, key=lambda x: x["timestamp"], reverse=True)
    return items_sorted[:limit]

# ---------- FUNÇÕES AUXILIARES ----------
def extract_number(name):
    match = re.search(r'\d+', name)
    return int(match.group()) if match else float('inf')

# ---------- VIEW PAGINADA DE MEMBROS (melhorada) ----------
class PaginadoMemberView(discord.ui.View):
    def __init__(self, membros, callback_func, pagina=0):
        super().__init__(timeout=300)
        # Ordena removendo None
        self.membros = sorted([m for m in membros if m is not None], key=lambda m: extract_number(m.display_name or m.name))
        self.callback_func = callback_func
        self.pagina = pagina
        self.atualizar_menu()

    def atualizar_menu(self):
        self.clear_items()
        inicio = self.pagina * 25
        fim = inicio + 25
        membros_pagina = self.membros[inicio:fim]

        options = [
            discord.SelectOption(label=member.display_name or member.name, value=str(member.id))
            for member in membros_pagina
        ]

        select = discord.ui.Select(placeholder="Selecione um policial", options=options, max_values=1)

        async def select_callback(interaction: discord.Interaction):
            membro_id = int(select.values[0])
            await self.callback_func(interaction, membro_id)

        select.callback = select_callback
        self.add_item(select)

        if self.pagina > 0:
            self.add_item(PaginaAnteriorButton(self))
        if fim < len(self.membros):
            self.add_item(ProximaPaginaButton(self))

class PaginaAnteriorButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="⬅️ Anterior", style=discord.ButtonStyle.secondary)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.pagina = max(0, self.view_ref.pagina - 1)
        self.view_ref.atualizar_menu()
        await interaction.response.edit_message(view=self.view_ref)

class ProximaPaginaButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="Próximo ➡️", style=discord.ButtonStyle.secondary)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.pagina += 1
        self.view_ref.atualizar_menu()
        await interaction.response.edit_message(view=self.view_ref)

# ---------- BOTÕES INICIAIS (fluxos existentes) ----------
class TicketButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="👮‍♂️ Convocar Policial", style=discord.ButtonStyle.secondary, custom_id="convocar")
    async def convocacao_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == CARGO_AUTORIZADO_ID for role in interaction.user.roles):
            await interaction.response.send_message("Você não tem permissão para usar este botão.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        categoria = interaction.guild.get_channel(CATEGORIA_CONVOCACAO)
        canal = await interaction.guild.create_text_channel(
            name=f"convocacao-{interaction.user.name}",
            category=categoria,
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            },
        )

        membros = [m for m in interaction.guild.members if not m.bot]

        async def processar_convocado(inter: discord.Interaction, membro_id: int):
            convocado = inter.guild.get_member(membro_id)
            await inter.response.send_message(f"Selecionado: {convocado.mention}", ephemeral=True)

            def check(m): return m.channel == canal and m.author == interaction.user

            await canal.send("Informe a **data da convocação** (ex: 25/05/2025):")
            data = await bot.wait_for("message", check=check)
            await data.delete()

            await canal.send("Informe o **horário da convocação** (ex: 14:00):")
            hora = await bot.wait_for("message", check=check)
            await hora.delete()



            embed = discord.Embed(
                title="Segurança Pública | Convocação",
                description=(
                    f"A corregedoria da Policia Militar convoca o Policial Militar {convocado.mention} para prestar esclarecimentos no dia **{data.content}** "
                    f"às **{hora.content}** horário de Brasília. No setor de Atendimento da DPM no BPM.\n\n"
                    f"O não comparecimento sem justificativa acarretará em sanções disciplinares administrativas.\n\n"
                    f"*Assinatura do responsável:* {interaction.user.mention}"
                ),
                color=discord.Color.dark_gray()
            )

            log_channel = interaction.guild.get_channel(LOG_CONVOCACAO)
            if log_channel:
                await log_channel.send(embed=embed)
            await canal.delete()

        await canal.send("Selecione o policial a ser convocado:", view=PaginadoMemberView(membros, processar_convocado))

    @discord.ui.button(label="📄 Preencher PAD", style=discord.ButtonStyle.secondary, custom_id="pad")
    async def pad_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == CARGO_AUTORIZADO_ID for role in interaction.user.roles):
            await interaction.response.send_message("Você não tem permissão para usar este botão.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        categoria = interaction.guild.get_channel(CATEGORIA_PAD)
        canal = await interaction.guild.create_text_channel(
            name=f"pad-{interaction.user.name}",
            category=categoria,
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            },
        )

        membros = [m for m in interaction.guild.members if not m.bot]

        async def processar_investigado(inter: discord.Interaction, membro_id: int):
            investigado = inter.guild.get_member(membro_id)
            await inter.response.send_message(f"Selecionado: {investigado.mention}", ephemeral=True)

            def check(m): return m.channel == canal and m.author == interaction.user

            await canal.send("Informe a **decisão final do PAD**:")
            decisao = await bot.wait_for("message", check=check)
            await decisao.delete()



            embed = discord.Embed(
                title="Segurança Pública | Resultado PAD",
                description=(
                    f"A corregedoria da Policia Militar informa a decisão sobre o inquérito do militar {investigado.mention}:\n\n"
                    f"**Decisão:** {decisao.content}\n\n"
                    f"*Responsável:* {interaction.user.mention}"
                ),
                color=discord.Color.dark_gray()
            )

            guild = inter.guild
            pad_i = guild.get_role(CARGO_PAD_I)
            pad_ii = guild.get_role(CARGO_PAD_II)
            pad_iii = guild.get_role(CARGO_PAD_III)
            novato = guild.get_role(CARGO_NOVATO)

            try:
                if pad_i and pad_ii and pad_iii and novato:
                    if pad_i not in investigado.roles and pad_ii not in investigado.roles and pad_iii not in investigado.roles:
                        await investigado.add_roles(pad_i)
                    elif pad_i in investigado.roles:
                        await investigado.remove_roles(pad_i)
                        await investigado.add_roles(pad_ii)
                    elif pad_ii in investigado.roles:
                        await investigado.remove_roles(pad_ii)
                        await investigado.add_roles(pad_iii)
                    elif pad_iii in investigado.roles:
                        await investigado.remove_roles(pad_iii)
                        await investigado.add_roles(novato)
            except Exception:
                # se não tiver permissão para editar roles, ignorar
                pass

            log_channel = interaction.guild.get_channel(LOG_PAD)
            if log_channel:
                await log_channel.send(embed=embed)
            await canal.delete()

        await canal.send("Selecione o policial alvo do PAD:", view=PaginadoMemberView(membros, processar_investigado))

    @discord.ui.button(label="📘 Preencher IPM", style=discord.ButtonStyle.secondary, custom_id="ipm")
    async def ipm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == CARGO_AUTORIZADO_ID for role in interaction.user.roles):
            await interaction.response.send_message("Você não tem permissão para usar este botão.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        categoria = interaction.guild.get_channel(CATEGORIA_IPM)

        canal = await interaction.guild.create_text_channel(
            name=f"ipm-{interaction.user.name}",
            category=categoria,
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            },
        )

        def check(m): return m.channel == canal and m.author == interaction.user

        await canal.send("Informe o nome do policial investigado:")
        nome = await bot.wait_for("message", check=check)
        await canal.send("Informe o motivo do IPM:")
        motivo = await bot.wait_for("message", check=check)
        await canal.send("Informe a data do fato:")
        data = await bot.wait_for("message", check=check)
        await canal.send("Informe o horário do fato:")
        hora = await bot.wait_for("message", check=check)
        await canal.send("Informe o local do fato:")
        local = await bot.wait_for("message", check=check)
        await canal.send("Informe o responsável pelo IPM:")
        responsavel_ipm = await bot.wait_for("message", check=check)


        embed = discord.Embed(
            title="Segurança Pública | Instauração de IPM",
            description=(
                f"A Corregedoria da Polícia Militar, diante dos fatos apresentados, determina a instauração de Inquérito Policial Militar (IPM) com a finalidade de apurar a conduta do policial militar {nome.content}, referente ao seguinte fato: {motivo.content}.\n\n"
                f"O ocorrido deu-se no dia {data.content}, por volta das {hora.content}, no local identificado como {local.content}. Segundo relatos preliminares, a situação demanda apuração detalhada, considerando a gravidade e a natureza da conduta atribuída ao militar.\n\n"
                f"O responsável pela condução deste IPM será o policial {responsavel_ipm.content}, que deverá realizar todas as diligências necessárias, colher depoimentos, reunir elementos de prova e apresentar relatório conclusivo dentro do prazo legal estabelecido.\n\n"
                f"O presente Inquérito deverá ser conduzido com imparcialidade, responsabilidade e estrita observância aos princípios legais e regulamentares da Instituição."
            ),
            color=discord.Color.dark_gray()
        )

        log_channel = interaction.guild.get_channel(LOG_IPM)
        if log_channel:
            await log_channel.send(embed=embed)
        await canal.delete()

# ---------- EVENTOS ----------
@bot.event
async def on_ready():
    print(f"🤖 Bot conectado como {bot.user}")

    # Envia painel inicial (apenas uma vez)
    canal = bot.get_channel(CANAL_ID)
    if canal:
        # limpa mensagens antigas do bot
        try:
            async for msg in canal.history(limit=10):
                if msg.author == bot.user:
                    try:
                        await msg.delete()
                    except Exception:
                        pass
        except Exception:
            pass

        embed = discord.Embed(
            title="DPM | Sistema de Apuração Disciplinar",
            description=(
                "Bem-vindo ao painel da **DPM - Corregedoria**.\n"
                "Utilize os botões abaixo para iniciar processos disciplinares."
            ),
            color=discord.Color.dark_gray()
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1397830746911277087/1398806716984066159/correge.jpg")
        try:
            await canal.send(embed=embed, view=TicketButtons())
        except Exception:
            pass

    # sincroniza comandos de aplicação para o guild (apenas nesse servidor para testes)
    try:
        print(f"Comandos sincronizados: {[cmd.name for cmd in os.sync]}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

TOKEN = os.getenv("TOKEN")

bot.run(TOKEN)
