import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import random
import string
import os
import logging
from datetime import datetime, timedelta
from io import StringIO

# Import from other files
from database import Database
from views import VerificationView
from utils import validate_url
from config import Config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clipper_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ClipperBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.verification_codes = {}
        self.db = Database()
        self.config = Config
        self.start_background_tasks()
        
    def start_background_tasks(self):
        self.cleanup_expired_codes.start()
        self.daily_analytics.start()
    
    @tasks.loop(minutes=30)
    async def cleanup_expired_codes(self):
        now = datetime.utcnow()
        expired_codes = [
            user_id for user_id, data in self.verification_codes.items()
            if data['expires'] < now
        ]
        for user_id in expired_codes:
            del self.verification_codes[user_id]
        if expired_codes:
            logger.info(f"Cleaned up {len(expired_codes)} expired verification codes")
    
    @tasks.loop(hours=24)
    async def daily_analytics(self):
        await self.db.generate_analytics()
    
    async def on_ready(self):
        logger.info(f'{self.user} connected to Discord')
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

bot = ClipperBot()

@bot.tree.command(name="verify", description="Verify ownership of your social media account")
@app_commands.describe(
    platform="Platform (tiktok, instagram, youtube)",
    username="Your username on the platform"
)
async def verify(interaction: discord.Interaction, platform: str, username: str):
    platform = platform.lower()
    if platform not in ['tiktok', 'instagram', 'youtube']:
        await interaction.response.send_message("❌ Invalid platform. Valid options: tiktok, instagram, youtube", ephemeral=True)
        return
    
    # Generate verification code
    code = ''.join(random.choices(string.ascii_uppercase, k=6)) + '-' + ''.join(random.choices(string.digits, k=5))
    bot.verification_codes[interaction.user.id] = {
        'code': code,
        'platform': platform,
        'username': username,
        'expires': datetime.utcnow() + timedelta(minutes=bot.config.VERIFICATION_TIMEOUT)
    }
    
    embed = discord.Embed(
        title="🔐 Account Verification",
        description=f"To verify your {platform.title()} account **@{username}**:\n\n"
                   f"1. Add this code to your bio: `{code}`\n"
                   f"2. Click **Confirm Verification** below\n\n"
                   f"⏰ Code expires in {bot.config.VERIFICATION_TIMEOUT} minutes",
        color=discord.Color.blue()
    )
    
    view = VerificationView(platform, username, code, interaction.user.id, bot.db)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    view.message = await interaction.original_response()

@bot.tree.command(name="submitclip", description="Submit a clip for view tracking")
@app_commands.describe(
    platform="Platform where clip was posted",
    video_link="Link to the video",
    views="Number of views (as integer)"
)
async def submitclip(interaction: discord.Interaction, platform: str, video_link: str, views: int):
    if not discord.utils.get(interaction.user.roles, name="Clipper"):
        await interaction.response.send_message("❌ You must be verified first. Use `/verify`", ephemeral=True)
        return
    
    platform = platform.lower()
    if platform not in ['tiktok', 'instagram', 'youtube']:
        await interaction.response.send_message("❌ Invalid platform. Valid options: tiktok, instagram, youtube", ephemeral=True)
        return
    
    if not validate_url(video_link, platform):
        await interaction.response.send_message(f"❌ Invalid {platform} URL", ephemeral=True)
        return
    
    if views <= 0:
        await interaction.response.send_message("❌ Views must be a positive number", ephemeral=True)
        return
    
    earnings = (views / 100000) * bot.config.PAYOUT_RATE
    clip_data = {
        'discord_id': interaction.user.id,
        'platform': platform,
        'video_link': video_link,
        'views': views,
        'earnings': earnings,
        'submitted_at': datetime.utcnow()
    }
    
    await bot.db.store_clip(clip_data)
    
    embed = discord.Embed(
        title="✅ Clip Submitted",
        description=f"**Platform:** {platform.title()}\n**Views:** {views:,}\n**Earnings:** ${earnings:.2f}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="myearnings", description="Check your current earnings")
async def myearnings(interaction: discord.Interaction):
    user_data = await bot.db.get_user(interaction.user.id)
    if not user_data:
        await interaction.response.send_message("❌ No earnings data found", ephemeral=True)
        return
    
    embed = discord.Embed(title="💰 Your Earnings", color=discord.Color.gold())
    embed.add_field(name="Total Views", value=f"{user_data['total_views']:,}", inline=True)
    embed.add_field(name="Total Earnings", value=f"${user_data['total_earnings']:.2f}", inline=True)
    embed.add_field(name="Rate", value="$20 per 100K views", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="payoutsummary", description="Admin: View payout summary")
@app_commands.describe(
    period="Filter period (week/month/all)",
    export="Export to CSV"
)
@app_commands.default_permissions(administrator=True)
async def payoutsummary(interaction: discord.Interaction, period: str = "all", export: bool = False):
    results = await bot.db.get_payout_summary(period)
    if not results:
        await interaction.response.send_message(f"❌ No data for period: {period}", ephemeral=True)
        return
    
    if export:
        csv_data = await bot.db.export_to_csv(results)
        file = discord.File(StringIO(csv_data), filename=f"payouts_{period}.csv")
        await interaction.response.send_message(file=file, ephemeral=True)
    else:
        total = sum(r['total_earnings'] for r in results)
        embed = discord.Embed(
            title=f"📊 Payout Summary ({period.title()})", 
            description=f"**Total Payout:** ${total:.2f}",
            color=discord.Color.blue()
        )
        
        # Top 5 performers
        results.sort(key=lambda x: x['total_earnings'], reverse=True)
        performers = []
        for i, r in enumerate(results[:5]):
            user = bot.get_user(r['_id'])
            name = user.display_name if user else f"User {r['_id']}"
            performers.append(f"{i+1}. {name}: ${r['total_earnings']:.2f} ({r['total_views']:,} views)")
        
        if performers:
            embed.add_field(name="Top Performers", value="\n".join(performers), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="markpayout", description="Admin: Mark payout as sent")
@app_commands.describe(user="User to mark payout for")
@app_commands.default_permissions(administrator=True)
async def markpayout(interaction: discord.Interaction, user: discord.Member):
    await bot.db.record_payout(user.id, interaction.user.id)
    embed = discord.Embed(
        title="✅ Payout Marked",
        description=f"Payout for {user.mention} recorded",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv()
    bot.run(os.getenv('DISCORD_BOT_TOKEN'))