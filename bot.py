import os
import json
import discord
from discord.ext import commands, tasks
from discord.utils import get
from datetime import datetime, timedelta

# =========================
# BOT SETUP & DATA STORAGE
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=",", intents=intents)

STATS_FILE = "stats.json"

def load_stats():
    """Loads stats and LOA data from the JSON file."""
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                content = json.load(f)
                if "mods" not in content: content["mods"] = {}
                if "active_loas" not in content: content["active_loas"] = {}
                return content
        except:
            return {"mods": {}, "active_loas": {}}
    return {"mods": {}, "active_loas": {}}

def save_stats(data):
    """Saves tracking and LOA data back to the JSON file."""
    with open(STATS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def log_action(mod_id, action_type):
    """Increments daily, weekly, monthly, and total logs for a specific mod."""
    data = load_stats()
    stats = data["mods"]
    mod_key = str(mod_id)
    current_date = datetime.utcnow()
    
    if mod_key not in stats:
        stats[mod_key] = {
            "warns": {"daily": 0, "weekly": 0, "monthly": 0, "total": 0},
            "mutes": {"daily": 0, "weekly": 0, "monthly": 0, "total": 0},
            "jails": {"daily": 0, "weekly": 0, "monthly": 0, "total": 0},
            "last_update": current_date.strftime("%Y-%m-%d")
        }

    mod_data = stats[mod_key]
    last_update_str = mod_data.get("last_update", current_date.strftime("%Y-%m-%d"))
    last_update = datetime.strptime(last_update_str, "%Y-%m-%d")

    days_diff = (current_date - last_update).days
    is_new_day = days_diff >= 1
    is_new_week = current_date.strftime("%V") != last_update.strftime("%V") or days_diff >= 7
    is_new_month = current_date.month != last_update.month or days_diff >= 30

    for cat in ["warns", "mutes", "jails"]:
        if is_new_day: 
            stats[mod_key][cat]["daily"] = 0
        if is_new_week: 
            stats[mod_key][cat]["weekly"] = 0
        if is_new_month: 
            stats[mod_key][cat]["monthly"] = 0

    if action_type in ["warns", "mutes", "jails"]:
        stats[mod_key][action_type]["daily"] += 1
        stats[mod_key][action_type]["weekly"] += 1
        stats[mod_key][action_type]["monthly"] += 1
        stats[mod_key][action_type]["total"] += 1

    stats[mod_key]["last_update"] = current_date.strftime("%Y-%m-%d")
    data["mods"] = stats
    save_stats(data)

def parse_duration(duration_str):
    """Parses time strings like 1m, 2h, 3d, 1w into a timedelta object."""
    try:
        amount = int(''.join(filter(str.isdigit, duration_str)))
        unit = ''.join(filter(str.isalpha, duration_str)).lower()
        
        if 'm' in unit and 'o' not in unit:
            return timedelta(minutes=amount)
        elif 'h' in unit:
            return timedelta(hours=amount)
        elif 'd' in unit:
            return timedelta(days=amount)
        elif 'w' in unit:
            return timedelta(weeks=amount)
        elif 'mo' in unit:
            return timedelta(days=amount * 30)
    except:
        return None
    return None

# =========================
# HELPER CHECKS
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

def is_staff():
    """Custom check to ensure only members with the 'Staff' role can view stats."""
    async def predicate(ctx):
        if any(role.name == "Staff" for role in ctx.author.roles):
            return True
        await ctx.send("❌ Only members of the Staff team can view moderation statistics.")
        return False
    return commands.check(predicate)

def has_loa_permissions():
    """Restricts LOA command usage to specifically defined high staff roles."""
    async def predicate(ctx):
        allowed_roles = ["Management", "Administrator", "Head Administrator", "Owner", "Co-Owner"]
        if any(role.name in allowed_roles for role in ctx.author.roles):
            return True
        await ctx.send("❌ You do not hold an authorized hierarchy role to submit an LOA.")
        return False
    return commands.check(predicate)

# =========================
# BACKGROUND LOA EXPIRATION TRACKER
# =========================

@tasks.loop(minutes=1)
async def check_expired_loas():
    """Background loop running every minute checking for ended leaves."""
    await bot.wait_until_ready()
    data = load_stats()
    
    if "active_loas" not in data or not data["active_loas"]:
        return

    current_time = datetime.utcnow()
    updated_loas = data["active_loas"].copy()
    changes_made = False

    for user_id_str, expiry_time_str in list(data["active_loas"].items()):
        expiry_time = datetime.strptime(expiry_time_str, "%Y-%m-%d %H:%M:%S")
        
        if current_time >= expiry_time:
            for guild in bot.guilds:
                member = guild.get_member(int(user_id_str))
                if member:
                    loa_role = get(guild.roles, name="LOA")
                    if loa_role and loa_role in member.roles:
                        try:
                            await member.remove_roles(loa_role)
                            embed = discord.Embed(
                                title="📅 LOA Expired",
                                description=f"Your Leave of Absence duration in **{guild.name}** has concluded. Your LOA role has been removed automatically.",
                                color=discord.Color.orange()
                            )
                            await member.send(embed=embed)
                        except:
                            pass
            
            if user_id_str in updated_loas:
                del updated_loas[user_id_str]
                changes_made = True

    if changes_made:
        data["active_loas"] = updated_loas
        save_stats(data)

# =========================
# READY EVENT
# =========================

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    await bot.change_presence(
        activity=discord.Game(name="Scorpion Bot | Made by Kaizen")
    )
    if not check_expired_loas.is_running():
        check_expired_loas.start()

# =========================
# PING COMMAND
# =========================

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

# =========================
# MODERATOR STATISTICS (MS) COMMAND
# =========================

@bot.command()
@is_staff() # Restricts access to the Staff Team role
async def ms(ctx, member: discord.Member = None):
    target = member or ctx.author
    data = load_stats()
    stats = data.get("mods", {})
    mod_key = str(target.id)

    if mod_key not in stats:
        mod_data = {
            "warns": {"daily": 0, "weekly": 0, "monthly": 0, "total": 0},
            "mutes": {"daily": 0, "weekly": 0, "monthly": 0, "total": 0},
            "jails": {"daily": 0, "weekly": 0, "monthly": 0, "total": 0}
        }
    else:
        mod_data = stats[mod_key]

    daily_total = mod_data["warns"]["daily"] + mod_data["mutes"]["daily"] + mod_data["jails"]["daily"]
    weekly_total = mod_data["warns"]["weekly"] + mod_data["mutes"]["weekly"] + mod_data["jails"]["weekly"]
    monthly_total = mod_data["warns"]["monthly"] + mod_data["mutes"]["monthly"] + mod_data["jails"]["monthly"]
    all_time_total = mod_data["warns"]["total"] + mod_data["mutes"]["total"] + mod_data["jails"]["total"]

    embed = discord.Embed(
        title="Moderation Statistics",
        color=discord.Color.from_rgb(47, 49, 54)
    )
    embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)

    embed.add_field(
        name="Warns",
        value=f"Daily: {mod_data['warns']['daily']} | Weekly: {mod_data['warns']['weekly']} | Monthly: {mod_data['warns']['monthly']} | Total: {mod_data['warns']['total']}",
        inline=False
    )
    embed.add_field(
        name="Mutes",
        value=f"Daily: {mod_data['mutes']['daily']} | Weekly: {mod_data['mutes']['weekly']} | Monthly: {mod_data['mutes']['monthly']} | Total: {mod_data['mutes']['total']}",
        inline=False
    )
    embed.add_field(
        name="Jails",
        value=f"Daily: {mod_data['jails']['daily']} | Weekly: {mod_data['jails']['weekly']} | Monthly: {mod_data['jails']['monthly']} | Total: {mod_data['jails']['total']}",
        inline=False
    )
    embed.add_field(
        name="Total Actions",
        value=f"Daily: {daily_total}\nWeekly: {weekly_total}\nMonthly: {monthly_total}\nAll-time: {all_time_total}",
        inline=False
    )
    embed.set_footer(text=f"Built by Kaizen | Today at {datetime.utcnow().strftime('%H:%M')}")

    await ctx.send(embed=embed)

# =========================
# HELP COMMAND
# =========================

@bot.command()
async def helpme(ctx):
    embed = discord.Embed(
        title="🦂 Scorpion Bot Commands",
        description="**Developer:** Kaizen\n**Prefix:** `,`\n\n*Note: All moderation commands require a reason and cannot target staff members.*",
        color=discord.Color.red()
    )

    embed.add_field(name="⚙ Utility", value="`,ping` • Show bot ping\n`,ms [@staff]` • View moderator metrics (Staff Only)", inline=False)
    embed.add_field(name="🛡 Moderation", value="`,warn @user <reason>` • Warn a member\n`,mute @user <reason>` • Mute a member\n`,unmute @user <reason>` • Unmute a member", inline=False)
    embed.add_field(name="🚔 Deep Freeze", value="`,jail USER_ID <reason>` • Jail user via ID\n`,unjail USER_ID <reason>` • Unjail user via ID", inline=False)
    embed.add_field(name="🧹 Chat Management", value="`,clear <amount>` • Delete messages (Max 100)", inline=False)
    embed.add_field(name="📅 Staff Logistics", value="`,loa <duration> <reason>` • Log absence (Elite Roles Only)\n`,return` • End LOA manually", inline=False)

    await ctx.send(embed=embed)

# =========================
# WARN COMMAND
# =========================

@bot.command()
@commands.has_permissions(manage_messages=True)
@is_target_staff()
async def warn(ctx, member: discord.Member, *, reason: str):
    
    log_action(ctx.author.id, "warns")

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

    log_action(ctx.author.id, "mutes")

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

    log_action(ctx.author.id, "jails")

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
@has_loa_permissions()
async def loa(ctx, duration: str, *, reason: str):
    """Logs an absence, gives the role, and calculates automated expiry timing."""
    
    time_delta = parse_duration(duration)
    if time_delta is None:
        await ctx.send("❌ Invalid duration layout! Use values like `10m`, `3h`, `5d`, or `2w` (no spaces).")
        return

    loa_role = get(ctx.guild.roles, name="LOA")
    if loa_role is None:
        loa_role = await ctx.guild.create_role(name="LOA", reason="Automated LOA role creation")

    if loa_role not in ctx.author.roles:
        await ctx.author.add_roles(loa_role)

    expiry_time = datetime.utcnow() + time_delta
    data = load_stats()
        
    data["active_loas"][str(ctx.author.id)] = expiry_time.strftime("%Y-%m-%d %H:%M:%S")
    save_stats(data)

    embed = discord.Embed(
        title="📅 Leave of Absence Logged",
        description=f"Staff member {ctx.author.mention} is now on LOA.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Duration", value=duration, inline=True)
    embed.add_field(name="Expires Around (UTC)", value=expiry_time.strftime("%Y-%m-%d %H:%M"), inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text=f"Logged via Management Approval System")

    await ctx.send(embed=embed)

# =========================
# RETURN COMMAND
# =========================

@bot.command(name="return")
async def return_staff(ctx):
    """Allows staff to end their LOA early manually."""
    loa_role = get(ctx.guild.roles, name="LOA")
    
    if loa_role is None or loa_role not in ctx.author.roles:
        await ctx.send("❌ You don't currently have an active LOA role status!", delete_after=3)
        return

    await ctx.author.remove_roles(loa_role)

    data = load_stats()
    if str(ctx.author.id) in data["active_loas"]:
        del data["active_loas"][str(ctx.author.id)]
        save_stats(data)

    embed = discord.Embed(
        title="👋 Welcome Back!",
        description=f"{ctx.author.mention} has manually returned to active duty. LOA file index cleared.",
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
        await ctx.send(f"⚠ Missing arguments! Check your format structure.")
        
    elif isinstance(error, commands.CheckFailure):
        pass

# =========================
# BOT RUN CONFIGURATION
# =========================

bot.run(os.getenv('DISCORD_TOKEN'))
