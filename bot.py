import os
import discord
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
# HELPER CHECK (STAFF BYPASS PROTECTION)
# =========================

def is_target_staff():
    """Custom check to ensure the target member does not have the 'Staff' role."""
    async def predicate(ctx):
        args = ctx.message.content.split()
        if len(args) > 1:
            converter = commands.MemberConverter()
            try:
                member = await converter.convert(ctx, args[1])
                if any(role.name == "Staff" for role in member.roles):
                    await ctx.send("❌ You cannot punish a member of the Staff team!")
                    return False
            except commands.BadArgument:
                pass
        return True
    return commands.check(predicate)

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
# PING / MS COMMANDS
# =========================

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.command()
async def ms(ctx):
    await ctx.send(f"⚡ Connection Speed: `{round(bot.latency * 1000)}ms`")

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

    embed.add_field(name=",ping / ,ms", value="Show bot ping and latency", inline=False)
    embed.add_field(name=",warn @user <reason>", value="Warn a member (Reason required)", inline=False)
    embed.add_field(name=",mute @user <reason>", value="Mute a member (Reason required)", inline=False)
    embed.add_field(name=",unmute @user <reason>", value="Unmute a member (Reason required)", inline=False)
    embed.add_field(name=",jail USER_ID <reason>", value="Jail user using ID only (Reason required)", inline=False)
    embed.add_field(name=",unjail USER_ID <reason>", value="Unjail user using ID only (Reason required)", inline=False)
    embed.add_field(name=",clear amount", value="Delete messages (Max 100)", inline=False)
    embed.add_field(name=",loa <duration> <reason>", value="Log LOA & get the LOA role", inline=False)
    embed.add_field(name=",return", value="Remove LOA role and return to duty", inline=False)

    await ctx.send(embed=embed)

# =========================
# WARN COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_messages=True)
@is_target_staff()
async def warn(ctx, member: discord.Member, *, reason: str):

    embed = discord.Embed(
        title="⚠ Warning",
        description=f"{member.mention} has been warned.",
        color=discord.Color.orange()
    )

    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)

    await ctx.send(embed=embed)

# =========================
# MUTE COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_roles=True)
@is_target_staff()
async def mute(ctx, member: discord.Member, *, reason: str):

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
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)

    await ctx.send(embed=embed)

# =========================
# UNMUTE COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_roles=True)
@is_target_staff()
async def unmute(ctx, member: discord.Member, *, reason: str):

    muted_role = get(ctx.guild.roles, name="Muted")

    if muted_role in member.roles:
        await member.remove_roles(muted_role)

    embed = discord.Embed(
        title="🔊 User Unmuted",
        description=f"{member.mention} has been unmuted.",
        color=discord.Color.green()
    )
    embed.add_field(name="Reason for Unmute", value=reason, inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)

    await ctx.send(embed=embed)

# =========================
# JAIL COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_roles=True)
@is_target_staff()
async def jail(ctx, user_id: int, *, reason: str):

    member = ctx.guild.get_member(user_id)

    if member is None:
        await ctx.send("❌ User not found in this server.")
        return

    if any(role.name == "Staff" for role in member.roles):
        await ctx.send("❌ You cannot punish a member of the Staff team!")
        return

    jailed_role = get(ctx.guild.roles, name="Jailed")

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
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)

    await ctx.send(embed=embed)

# =========================
# UNJAIL COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_roles=True)
@is_target_staff()
async def unjail(ctx, user_id: int, *, reason: str):

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
    embed.add_field(name="Reason for Release", value=reason, inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)

    await ctx.send(embed=embed)

# =========================
# CLEAR COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):

    if amount > 100:
        await ctx.send("⚠ You can only delete up to 100 messages at a time.", delete_after=3)
        return

    await ctx.channel.purge(limit=amount + 1)

    msg = await ctx.send(f"🧹 Cleared {amount} messages")
    await msg.delete(delay=3)

# =========================
# LOA COMMAND (LEAVE OF ABSENCE)
# =========================

@bot.command()
async def loa(ctx, duration: str, *, reason: str):
    """Logs a staff Leave of Absence and assigns the LOA role."""
    
    loa_role = get(ctx.guild.roles, name="LOA")
    if loa_role is None:
        loa_role = await ctx.guild.create_role(name="LOA", reason="Automated LOA role creation")

    if loa_role not in ctx.author.roles:
        await ctx.author.add_roles(loa_role)

    embed = discord.Embed(
        title="📅 Leave of Absence Logged",
        description=f"Staff member {ctx.author.mention} is now on LOA.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Duration", value=duration, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text=f"Logged on {ctx.message.created_at.strftime('%Y-%m-%d')}")

    await ctx.send(embed=embed)

# =========================
# RETURN COMMAND
# =========================

@bot.command(name="return")
async def return_staff(ctx):
    """Allows staff to end their LOA and removes the LOA role."""
    
    loa_role = get(ctx.guild.roles, name="LOA")
    
    if loa_role is None or loa_role not in ctx.author.roles:
        await ctx.send("❌ You don't currently have the LOA role!", delete_after=3)
        return

    await ctx.author.remove_roles(loa_role)

    embed = discord.Embed(
        title="👋 Welcome Back!",
        description=f"{ctx.author.mention} has returned from their Leave of Absence and their LOA role has been removed.",
        color=discord.Color.green()
    )
    
    await ctx.send(embed=embed)

# =========================
# ERROR HANDLER
# =========================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You do not have permission to run this command.")

    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠ Missing arguments! Check your format.")
        
    elif isinstance(error, commands.CheckFailure):
        pass

# =========================
# BOT TOKEN
# =========================

bot.run(os.getenv('DISCORD_BOT_TOKEN'))
