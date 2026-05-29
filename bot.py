import discord
import os
from discord.ext import commands
from discord.utils import get

# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=",", intents=intents)

# =========================
# READY EVENT
# =========================

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

    await bot.change_presence(
        activity=discord.Game(name="Scorpion Bot | Made by Kaizen")
    )

# =========================
# PING COMMAND
# =========================

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

# =========================
# HELP COMMAND
# =========================

@bot.command()
async def helpme(ctx):

    embed = discord.Embed(
        title="🦂 Scorpion Bot Commands",
        description="This bot is made by Kaizen",
        color=discord.Color.red()
    )

    embed.add_field(name=",ping", value="Show bot ping", inline=False)
    embed.add_field(name=",warn @user reason", value="Warn a member", inline=False)
    embed.add_field(name=",mute @user", value="Mute a member", inline=False)
    embed.add_field(name=",unmute @user", value="Unmute a member", inline=False)
    embed.add_field(name=",jail USER_ID", value="Jail user using ID only", inline=False)
    embed.add_field(name=",unjail USER_ID", value="Unjail user using ID only", inline=False)
    embed.add_field(name=",clear amount", value="Delete messages", inline=False)

    await ctx.send(embed=embed)

# =========================
# WARN COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason="No reason"):

    embed = discord.Embed(
        title="⚠ Warning",
        description=f"{member.mention} has been warned.",
        color=discord.Color.orange()
    )

    embed.add_field(name="Reason", value=reason)
    embed.add_field(name="Moderator", value=ctx.author.mention)

    await ctx.send(embed=embed)

# =========================
# MUTE COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member):

    muted_role = get(ctx.guild.roles, name="Muted")

    if muted_role is None:

        muted_role = await ctx.guild.create_role(name="Muted")

        for channel in ctx.guild.channels:
            await channel.set_permissions(
                muted_role,
                send_messages=False,
                speak=False
            )

    await member.add_roles(muted_role)

    embed = discord.Embed(
        title="🔇 User Muted",
        description=f"{member.mention} has been muted.",
        color=discord.Color.red()
    )

    await ctx.send(embed=embed)

# =========================
# UNMUTE COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):

    muted_role = get(ctx.guild.roles, name="Muted")

    if muted_role in member.roles:
        await member.remove_roles(muted_role)

    embed = discord.Embed(
        title="🔊 User Unmuted",
        description=f"{member.mention} has been unmuted.",
        color=discord.Color.green()
    )

    await ctx.send(embed=embed)

# =========================
@bot.command()
@commands.has_permissions(manage_roles=True)
async def jail(ctx, user_id: int, *, reason="No reason provided"):

    member = ctx.guild.get_member(user_id)

    if member is None:
        await ctx.send("❌ User not found in this server.")
        return

    jailed_role = get(ctx.guild.roles, name="⚠️Jailed")

    if jailed_role is None:
        jailed_role = await ctx.guild.create_role(name="Jailed")

        for channel in ctx.guild.channels:
            await channel.set_permissions(
                jailed_role,
                send_messages=False,
                speak=False
            )

    await member.add_roles(jailed_role)

    embed = discord.Embed(
        title="🚔 User Jailed",
        description=f"{member.mention} has been jailed.",
        color=discord.Color.dark_red()
    )

    embed.add_field(name="User ID", value=str(user_id), inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)

    await ctx.send(embed=embed)


# =========================
# UNJAIL COMMAND (USER ID ONLY)
# =========================

@bot.command()
@commands.has_permissions(manage_roles=True)
async def unjail(ctx, user_id: int):

    member = ctx.guild.get_member(user_id)

    if member is None:
        await ctx.send("❌ User not found in this server.")
        return

    jailed_role = get(ctx.guild.roles, name="Jailed")

    if jailed_role in member.roles:
        await member.remove_roles(jailed_role)

    embed = discord.Embed(
        title="✅ User Released",
        description=f"{member.mention} has been released from jail.",
        color=discord.Color.green()
    )

    embed.add_field(name="User ID", value=str(user_id), inline=False)

    await ctx.send(embed=embed)

# =========================
# CLEAR COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):

    await ctx.channel.purge(limit=amount + 1)

    msg = await ctx.send(f"🧹 Cleared {amount} messages")
    await msg.delete(delay=3)

# =========================
# ERROR HANDLER
# =========================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You do not have permission.")

    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("⚠ Missing arguments.")

# =========================
# BOT TOKEN
# =========================

bot.run(os.getenv("DISCORD_TOKEN"))
