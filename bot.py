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
JAIL_LOG_CHANNEL_NAME = "✎ᝰjail-logs"
PUNISHMENT_LOG_CHANNEL_NAME = "✎ᝰmembers-punishment"

# Internal memory storage for deleted messages mapping: {channel_id: [list of deleted messages]}
deleted_messages_cache = {}

def load_stats():
    """Loads stats, warnings history, active mutes, and LOA data from the JSON file."""
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                content = json.load(f)
                if "mods" not in content: content["mods"] = {}
                if "active_loas" not in content: content["active_loas"] = {}
                if "active_mutes" not in content: content["active_mutes"] = {}
                if "user_warnings" not in content: content["user_warnings"] = {}
                return content
        except:
            return {"mods": {}, "active_loas": {}, "active_mutes": {}, "user_warnings": {}}
    return {"mods": {}, "active_loas": {}, "active_mutes": {}, "user_warnings": {}}

def save_stats(data):
    """Saves tracking, warnings, mutes, and LOA data back to the JSON file."""
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

def save_user_warning(user_id, mod_id, reason):
    """Saves a detailed warning log for a specific rule breaker."""
    data = load_stats()
    user_key = str(user_id)
    
    if "user_warnings" not in data:
        data["user_warnings"] = {}
        
    if user_key not in data["user_warnings"]:
        data["user_warnings"][user_key] = []
        
    warning_entry = {
        "mod_id": str(mod_id),
        "reason": reason,
        "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    }
    
    data["user_warnings"][user_key].append(warning_entry)
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
    """Custom check to ensure the target member does not have the '🛡️Staff Team' role."""
    async def predicate(ctx):
        args = ctx.message.content.split()
        if len(args) > 1:
            converter = commands.UserConverter()
            try:
                user = await converter.convert(ctx, args[1])
                member = ctx.guild.get_member(user.id)
                if member and any(role.name == "🛡️Staff Team" for role in member.roles):
                    await ctx.send("❌ You cannot punish a member of the Staff team!")
                    return False
            except commands.BadArgument:
                pass
        return True
    return commands.check(predicate)

def is_staff():
    """Custom check to ensure only members with the '🛡️Staff Team' role can access tracking commands."""
    async def predicate(ctx):
        if any(role.name == "🛡️Staff Team" for role in ctx.author.roles):
            return True
        await ctx.send("❌ Only members of the Staff team can access this layout.")
        return False
    return commands.check(predicate)

def has_loa_permissions():
    """Restricts LOA command usage to specifically defined high staff roles."""
    async def predicate(ctx):
        allowed_roles = ["Management", "Administrator", "Head Administrator", "Owner", "Co-Owner"]
        if any(role.name in allowed_roles for role in ctx.author.roles):
            return True
        await ctx.send("❌ You do not hold an authorized hierarchy role to manage an LOA.")
        return False
    return commands.check(predicate)

def has_clear_snipe_permissions():
    """Restricts command usage to Administrator, Co-Owner, or Owner roles."""
    async def predicate(ctx):
        allowed_roles = ["Administrator", "Co-Owner", "Owner"]
        if any(role.name in allowed_roles for role in ctx.author.roles):
            return True
        await ctx.send("❌ You do not have the required role hierarchy to clear logs.")
        return False
    return commands.check(predicate)

# =========================
# DELETED MESSAGE SNIPER LOGIC
# =========================

@bot.event
async def on_message_delete(message):
    """Intercepts and buffers deleted messages into application cache memory."""
    if message.author.bot:
        return
        
    channel_id = message.channel.id
    if channel_id not in deleted_messages_cache:
        deleted_messages_cache[channel_id] = []
        
    log_entry = {
        "author": message.author,
        "content": message.content or "[No text content/Attachment Only]",
        "timestamp": datetime.utcnow().strftime("%H:%M:%S")
    }
    
    deleted_messages_cache[channel_id].append(log_entry)
    
    # Cap memory cache limit per channel to the last 10 entries to stay light
    if len(deleted_messages_cache[channel_id]) > 10:
        deleted_messages_cache[channel_id].pop(0)

# =========================
# INTERACTIVE BUTTONS VIEW
# =========================

class WarningManagementView(discord.ui.View):
    """Adds action buttons directly below the warning history layout."""
    def __init__(self, target_user: discord.User):
        super().__init__(timeout=None)
        self.target_user = target_user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if any(role.name == "🛡️Staff Team" for role in interaction.user.roles):
            return True
        await interaction.response.send_message("❌ Only members of the Staff team can perform actions on infractions.", ephemeral=True)
        return False

    @discord.ui.button(label="Clear Most Recent Warning", style=discord.ButtonStyle.secondary, emoji="🗑️")
    async def clear_recent(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_stats()
        user_key = str(self.target_user.id)
        history = data.get("user_warnings", {}).get(user_key, [])

        if not history:
            await interaction.response.send_message("❌ This user has no warning history to alter.", ephemeral=True)
            return

        removed_entry = history.pop()
        data["user_warnings"][user_key] = history
        save_stats(data)

        updated_embed = create_warnings_embed(self.target_user, history)
        
        if not history:
            for child in self.children:
                child.disabled = True

        await interaction.response.edit_message(embed=updated_embed, view=self)
        await interaction.followup.send(f"✅ Most recent warning for {self.target_user.mention} has been deleted.", ephemeral=True)

        log_channel = get(interaction.guild.text_channels, name=PUNISHMENT_LOG_CHANNEL_NAME)
        if log_channel:
            log_embed = discord.Embed(
                title="🗑️ Single Warning Revoked",
                description=f"**Target:** {self.target_user.mention} (`{self.target_user.id}`)\n**Staff Executor:** {interaction.user.mention}\n**Removed Action Reason:** {removed_entry['reason']}",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            await log_channel.send(embed=log_embed)

    @discord.ui.button(label="Clear All Warnings", style=discord.ButtonStyle.danger, emoji="💥")
    async def clear_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_stats()
        user_key = str(self.target_user.id)
        history = data.get("user_warnings", {}).get(user_key, [])

        if not history:
            await interaction.response.send_message("❌ This user has no warning history to alter.", ephemeral=True)
            return

        total_cleared = len(history)
        data["user_warnings"][user_key] = []
        save_stats(data)

        updated_embed = create_warnings_embed(self.target_user, [])
        
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=updated_embed, view=self)
        await interaction.followup.send(f"✅ All `{total_cleared}` warnings for {self.target_user.mention} have been wiped clean.", ephemeral=True)

        log_channel = get(interaction.guild.text_channels, name=PUNISHMENT_LOG_CHANNEL_NAME)
        if log_channel:
            log_embed = discord.Embed(
                title="💥 Entire Warning File Wiped",
                description=f"**Target:** {self.target_user.mention} (`{self.target_user.id}`)\n**Staff Executor:** {interaction.user.mention}\n**Action Details:** Wiped profile cleanly. (Purged `{total_cleared}` warnings)",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            await log_channel.send(embed=log_embed)

def create_warnings_embed(user: discord.User, history: list) -> discord.Embed:
    """Helper method to draw the Infraction Embed uniformly."""
    embed = discord.Embed(
        title=f"📋 Infraction History",
        description=f"Showing recorded warning profile data for {user.mention} (`{user.id}`)",
        color=discord.Color.orange()
    )
    embed.set_thumbnail(url=user.display_avatar.url)

    if not history:
        embed.add_field(name="Status", value="✨ Clean record! No warning infractions found on file.", inline=False)
    else:
        embed.add_field(name="Total Warnings Active", value=f"📊 `{len(history)}` warnings logged.", inline=False)
        for index, item in enumerate(history, start=1):
            embed.add_field(
                name=f"Case #{index} — {item['date']}",
                value=f"**Reason:** {item['reason']}\n**Moderator:** <@{item['mod_id']}>",
                inline=False
            )
    return embed

# =========================
# BACKGROUND AUTOMATION TRACKERS
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

@tasks.loop(minutes=1)
async def check_expired_mutes():
    """Background loop running every minute checking for ended mutes."""
    await bot.wait_until_ready()
    data = load_stats()
    
    if "active_mutes" not in data or not data["active_mutes"]:
        return

    current_time = datetime.utcnow()
    updated_mutes = data["active_mutes"].copy()
    changes_made = False

    for user_id_str, expiry_time_str in list(data["active_mutes"].items()):
        expiry_time = datetime.strptime(expiry_time_str, "%Y-%m-%d %H:%M:%S")
        
        if current_time >= expiry_time:
            for guild in bot.guilds:
                member = guild.get_member(int(user_id_str))
                if member:
                    muted_role = get(guild.roles, name="Muted")
                    if muted_role and muted_role in member.roles:
                        try:
                            await member.remove_roles(muted_role)
                            
                            log_channel = get(guild.text_channels, name=PUNISHMENT_LOG_CHANNEL_NAME)
                            if log_channel:
                                log_embed = discord.Embed(
                                    title="🔊 Mute Expired",
                                    description=f"**Target:** {member.mention} (`{user_id_str}`)\nStatus: Automatically unmuted after duration completed.",
                                    color=discord.Color.green(),
                                    timestamp=datetime.utcnow()
                                )
                                await log_channel.send(embed=log_embed)
                        except:
                            pass
            
            if user_id_str in updated_mutes:
                del updated_mutes[user_id_str]
                changes_made = True

    if changes_made:
        data["active_mutes"] = updated_mutes
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
    if not check_expired_mutes.is_running():
        check_expired_mutes.start()

# =========================
# PING COMMAND
# =========================

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

# =========================
# SNIPE (SEE DELETED) COMMAND
# =========================

@bot.command(name="s")
@is_staff()
async def see_deleted(ctx):
    """Shows logging record history of deleted contents in the running channel."""
    channel_id = ctx.channel.id
    history = deleted_messages_cache.get(channel_id, [])

    if not history:
        await ctx.send("✨ No deleted messages recorded in this channel history.")
        return

    embed = discord.Embed(
        title=f"🕵️ Channel Snipe Logs",
        description=f"Displaying the latest deleted messages in {ctx.channel.mention}:",
        color=discord.Color.blue()
    )

    # List entries from newest to oldest
    for idx, msg in enumerate(reversed(history), start=1):
        embed.add_field(
            name=f"Log #{idx} | Sent by {msg['author'].name} at {msg['timestamp']}",
            value=f"**Message:** {msg['content']}",
            inline=False
        )

    await ctx.send(embed=embed)

# =========================
# CLEAR SNIPE HISTORIES COMMAND
# =========================

@bot.command(name="cs")
@has_clear_snipe_permissions()
async def clear_snipe(ctx):
    """Wipes the buffered logging cache record for the running channel clean."""
    channel_id = ctx.channel.id
    
    if channel_id in deleted_messages_cache:
        deleted_messages_cache[channel_id] = []
        
    await ctx.send(f"🧹 Snipe history for {ctx.channel.mention} has been cleared completely.")

# =========================
# MODERATOR STATISTICS (MS) COMMAND
# =========================

@bot.command()
@is_staff()
async def ms(ctx, user: discord.User = None):
    target = user or ctx.author
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
    embed.set_author(name=target.name, icon_url=target.display_avatar.url)

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
    embed.set_footer(text=f"Built by Kaizen | Powered by Aura ✨ • Today at {datetime.utcnow().strftime('%H:%M')}")

    await ctx.send(embed=embed)

# =========================
# HELP COMMAND
# =========================

@bot.command()
async def helpme(ctx):
    embed = discord.Embed(
        title="🦂 Scorpion Bot Commands",
        description="**Developer:** Kaizen\n**Prefix:** `,`\n\n*Note: All moderation/management commands accept @User or UserID inputs.*",
        color=discord.Color.red()
    )

    embed.add_field(name="⚙ Utility", value="`,ping` • Show bot ping\n`,ms [@staff/ID]` • View moderator metrics (Staff Only)", inline=False)
    embed.add_field(name="🛡 Moderation", value="`,warn [@user/ID] <reason>` • Warn a member\n`,warnings [@user/ID]` • View a user's warning history & manage logs (Staff Only)\n`,mute [@user/ID] <duration> <reason>` • Mute a member for a duration\n`,unmute [@user/ID] <reason>` • Unmute a member", inline=False)
    embed.add_field(name="🚔 Deep Freeze", value="`,jail [@user/ID] <reason>` • Jail user\n`,unjail [@user/ID] <reason>` • Unjail user", inline=False)
    embed.add_field(name="🧹 Chat Management", value="`,clear <amount>` • Delete messages (Max 100) (Staff Only)\n`,s` • View recently deleted channel items (Staff Only)\n`,cs` • Clear deleted item memory database (Admin+ Only)", inline=False)
    embed.add_field(name="📅 Staff Logistics", value="`,loa [@user/ID] <duration> <reason>` • Log absence (Elite Roles Only)\n`,return [@user/ID]` • Remove LOA status from a user", inline=False)

    await ctx.send(embed=embed)

# =========================
# WARN COMMAND
# =========================

@bot.command()
@is_staff()
@is_target_staff()
async def warn(ctx, user: discord.User, *, reason: str):
    
    log_action(ctx.author.id, "warns")
    save_user_warning(user.id, ctx.author.id, reason)

    embed = discord.Embed(
        title="⚠ Warning",
        description=f"{user.mention} has been warned.",
        color=discord.Color.orange()
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)

    await ctx.send(embed=embed)

    log_channel = get(ctx.guild.text_channels, name=PUNISHMENT_LOG_CHANNEL_NAME)
    if log_channel:
        log_embed = discord.Embed(
            title="⚠️ Warn Log Case Action",
            description=f"**Target:** {user.mention} (`{user.id}`)\n**Moderator:** {ctx.author.mention}\n**Reason:** {reason}",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        log_embed.set_thumbnail(url=user.display_avatar.url)
        log_embed.set_footer(text="Case Action: Warn | Executed")
        await log_channel.send(embed=log_embed)
    else:
        await ctx.send(f"⚠ Warning: Could not find log routing channel `#{PUNISHMENT_LOG_CHANNEL_NAME}`.")

# =========================
# CHECK WARNINGS COMMAND (WITH INTERACTIVE BUTTONS)
# =========================

@bot.command(name="warnings")
@is_staff()
async def check_warnings(ctx, user: discord.User):
    """Retrieves full warning logs history and attaches management buttons below."""
    data = load_stats()
    user_key = str(user.id)
    history = data.get("user_warnings", {}).get(user_key, [])

    embed = create_warnings_embed(user, history)
    view = WarningManagementView(user)

    if not history:
        for child in view.children:
            child.disabled = True

    await ctx.send(embed=embed, view=view)

# =========================
# MUTE COMMAND
# =========================

@bot.command()
@is_staff()
@is_target_staff()
async def mute(ctx, user: discord.User, duration: str, *, reason: str):

    member = ctx.guild.get_member(user.id)
    if member is None:
        await ctx.send("❌ This user is not currently in this server.")
        return

    time_delta = parse_duration(duration)
    if time_delta is None:
        await ctx.send("❌ Invalid duration format! Use layout tags like `10m`, `2h`, `5d` (no spaces).")
        return

    log_action(ctx.author.id, "mutes")
    muted_role = get(ctx.guild.roles, name="Muted")

    if muted_role is None:
        muted_role = await ctx.guild.create_role(name="Muted")
        for channel in ctx.guild.channels:
            await channel.set_permissions(muted_role, send_messages=False, speak=False)

    await member.add_roles(muted_role)

    expiry_time = datetime.utcnow() + time_delta
    data = load_stats()
    data["active_mutes"][str(user.id)] = expiry_time.strftime("%Y-%m-%d %H:%M:%S")
    save_stats(data)

    embed = discord.Embed(
        title="🔇 User Muted",
        description=f"{member.mention} has been temporarily muted.",
        color=discord.Color.red()
    )
    embed.add_field(name="Duration", value=duration, inline=True)
    embed.add_field(name="Expires Around (UTC)", value=expiry_time.strftime("%Y-%m-%d %H:%M"), inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)

    await ctx.send(embed=embed)

    log_channel = get(ctx.guild.text_channels, name=PUNISHMENT_LOG_CHANNEL_NAME)
    if log_channel:
        log_embed = discord.Embed(
            title="🔇 Mute Log Case Action",
            description=f"**Target:** {member.mention} (`{user.id}`)\n**Duration:** {duration}\n**Moderator:** {ctx.author.mention}\n**Reason:** {reason}",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text="Case Action: Mute | Executed")
        await log_channel.send(embed=log_embed)
    else:
        await ctx.send(f"⚠ Warning: Could not find log routing channel `#{PUNISHMENT_LOG_CHANNEL_NAME}`.")

# =========================
# UNMUTE COMMAND
# =========================

@bot.command()
@is_staff()
@is_target_staff()
async def unmute(ctx, user: discord.User, *, reason: str):

    member = ctx.guild.get_member(user.id)
    if member is None:
        await ctx.send("❌ This user is not currently in this server.")
        return

    muted_role = get(ctx.guild.roles, name="Muted")

    if muted_role in member.roles:
        await member.remove_roles(muted_role)

    data = load_stats()
    if str(user.id) in data["active_mutes"]:
        del data["active_mutes"][str(user.id)]
        save_stats(data)

    embed = discord.Embed(
        title="🔊 User Unmuted",
        description=f"{member.mention} has been unmuted.",
        color=discord.Color.green()
    )
    embed.add_field(name="Reason for Unmute", value=reason, inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)

    await ctx.send(embed=embed)

    log_channel = get(ctx.guild.text_channels, name=PUNISHMENT_LOG_CHANNEL_NAME)
    if log_channel:
        log_embed = discord.Embed(
            title="🔊 Unmute Log Case Action",
            description=f"**Target:** {member.mention} (`{user.id}`)\n**Moderator:** {ctx.author.mention}\n**Reason for Unmute:** {reason}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text="Case Action: Unmute | Executed")
        await log_channel.send(embed=log_embed)
    else:
        await ctx.send(f"⚠ Warning: Could not find log routing channel `#{PUNISHMENT_LOG_CHANNEL_NAME}`.")

# =========================
# JAIL COMMAND
# =========================

@bot.command()
@is_staff()
@is_target_staff()
async def jail(ctx, user: discord.User, *, reason: str):

    member = ctx.guild.get_member(user.id)
    if member is None:
        await ctx.send("❌ User not found in this server.")
        return

    log_action(ctx.author.id, "jails")
    
    jailed_role = get(ctx.guild.roles, name="⚠️Jailed")

    if jailed_role is None:
        jailed_role = await ctx.guild.create_role(name="⚠️Jailed")
        for channel in ctx.guild.channels:
            await channel.set_permissions(jailed_role, send_messages=False, speak=False)

    await member.add_roles(jailed_role)

    embed = discord.Embed(
        title="🚔 User Jailed",
        description=f"{member.mention} has been jailed.",
        color=discord.Color.dark_red()
    )
    embed.add_field(name="User ID", value=str(user.id), inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)

    await ctx.send(embed=embed)

    log_channel = get(ctx.guild.text_channels, name=JAIL_LOG_CHANNEL_NAME)
    if log_channel:
        log_embed = discord.Embed(
            title="🔒 Jail Log Case Action",
            description=f"**Target:** {member.mention} (`{user.id}`)\n**Moderator:** {ctx.author.mention}\n**Reason:** {reason}",
            color=discord.Color.dark_red(),
            timestamp=datetime.utcnow()
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text="Case Action: Jail | Executed")
        await log_channel.send(embed=log_embed)
    else:
        await ctx.send(f"⚠ Warning: Could not find log routing channel `#{JAIL_LOG_CHANNEL_NAME}`.")

# =========================
# UNJAIL COMMAND
# =========================

@bot.command()
@is_staff()
@is_target_staff()
async def unjail(ctx, user: discord.User, *, reason: str):

    member = ctx.guild.get_member(user.id)
    if member is None:
        await ctx.send("❌ User not found in this server.")
        return

    jailed_role = get(ctx.guild.roles, name="⚠️Jailed")

    if jailed_role and jailed_role in member.roles:
        await member.remove_roles(jailed_role)

    embed = discord.Embed(
        title="✅ User Released",
        description=f"{member.mention} has been released from jail.",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=str(user.id), inline=False)
    embed.add_field(name="Reason for Release", value=reason, inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)

    await ctx.send(embed=embed)

    log_channel = get(ctx.guild.text_channels, name=JAIL_LOG_CHANNEL_NAME)
    if log_channel:
        log_embed = discord.Embed(
            title="🔓 Unjail Log Case Action",
            description=f"**Target:** {member.mention} (`{user.id}`)\n**Moderator:** {ctx.author.mention}\n**Reason for Release:** {reason}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text="Case Action: Unjail | Executed")
        await log_channel.send(embed=log_embed)
    else:
        await ctx.send(f"⚠ Warning: Could not find log routing channel `#{JAIL_LOG_CHANNEL_NAME}`.")

# =========================
# CLEAR COMMAND
# =========================

@bot.command()
@is_staff()  
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
async def loa(ctx, user: discord.User, duration: str, *, reason: str):
    """Logs an absence for a target user via ID or tag, handles roles, and automates tracking."""
    
    time_delta = parse_duration(duration)
    if time_delta is None:
        await ctx.send("❌ Invalid duration layout! Use values like `10m`, `3h`, `5d`, or `2w` (no spaces).")
        return

    member = ctx.guild.get_member(user.id)
    if member:
        loa_role = get(ctx.guild.roles, name="LOA")
        if loa_role is None:
            loa_role = await ctx.guild.create_role(name="LOA", reason="Automated LOA role creation")

        if loa_role not in member.roles:
            await member.add_roles(loa_role)

    expiry_time = datetime.utcnow() + time_delta
    data = load_stats()
        
    data["active_loas"][str(user.id)] = expiry_time.strftime("%Y-%m-%d %H:%M:%S")
    save_stats(data)

    embed = discord.Embed(
        title="📅 Leave of Absence Logged",
        description=f"Staff member {user.mention} is now on LOA.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Duration", value=duration, inline=True)
    embed.add_field(name="Expires Around (UTC)", value=expiry_time.strftime("%Y-%m-%d %H:%M"), inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text=f"Logged by {ctx.author.name} | Management System")

    await ctx.send(embed=embed)

# =========================
# RETURN COMMAND
# =========================

@bot.command(name="return")
@has_loa_permissions()
async def return_staff(ctx, user: discord.User = None):
    """Allows higher staff to end an LOA for someone early via ID or tag (defaults to author)."""
    target_user = user or ctx.author
    member = ctx.guild.get_member(target_user.id)
    
    if member:
        loa_role = get(ctx.guild.roles, name="LOA")
        if loa_role and loa_role in member.roles:
            await member.remove_roles(loa_role)

    data = load_stats()
    if str(target_user.id) in data["active_loas"]:
        del data["active_loas"][str(target_user.id)]
        save_stats(data)

    embed = discord.Embed(
        title="👋 LOA Terminated Early",
        description=f"{target_user.mention}'s LOA has been resolved. Returning to active duty status.",
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
        await ctx.send(f"⚠ Missing arguments! Check your command layout formatting.")
        
    elif isinstance(error, commands.UserNotFound):
        await ctx.send("❌ Could not find that user. Make sure the ID or Tag is correct.")
        
    elif isinstance(error, commands.CheckFailure):
        pass

# =========================
# BOT RUN CONFIGURATION
# =========================

bot.run(os.getenv('DISCORD_TOKEN'))
