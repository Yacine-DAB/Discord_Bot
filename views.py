import discord
from discord.ui import View, Button
import asyncio
import random
from database import Database

class VerificationView(View):
     def __init__(self, platform: str, username: str, code: str, user_id: int, db: Database):
          super().__init__(timeout=300)
          self.platform = platform
          self.username = username
          self.code = code
          self.user_id = user_id
          self.db = db
          self.attempts = 0
          self.max_attempts = 3
          self.message = None

     @discord.ui.button(label='Confirm Verification', style=discord.ButtonStyle.green)
     async def confirm(self, interaction: discord.Interaction, button: Button):
          if interaction.user.id != self.user_id:
               await interaction.response.send_message("❌ Only the verifying user can confirm", ephemeral=True)
               return
          
          self.attempts += 1
          await interaction.response.defer()
          
          # Simulate verification check (would use API in production)
          success = await self.check_verification()
          
          if success:
               role = await self.assign_clipper_role(interaction)
               await self.db.store_verified_user(self.user_id, self.platform, self.username)
               
               embed = discord.Embed(
                    title="✅ Verification Successful!",
                    description=f"You now have the {role.mention} role!\nUse `/submitclip` to start submitting clips",
                    color=discord.Color.green()
               )
               await interaction.followup.send(embed=embed)
               await self.message.edit(view=None)
          else:
               if self.attempts >= self.max_attempts:
                    embed = discord.Embed(
                         title="❌ Verification Failed",
                         description="Maximum attempts reached. Please try again later.",
                         color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    await self.message.edit(view=None)
               else:
                    embed = discord.Embed(
                         title="⚠️ Code Not Found",
                         description=f"Attempts remaining: {self.max_attempts - self.attempts}\n\n"
                                   "Make sure the code is in your bio exactly as shown",
                         color=discord.Color.orange()
                    )
                    await interaction.followup.send(embed=embed)

     async def check_verification(self) -> bool:
          """Simulate verification check (replace with API calls)"""
          await asyncio.sleep(2)
          return random.random() < 0.7

     async def assign_clipper_role(self, interaction: discord.Interaction) -> discord.Role:
          role = discord.utils.get(interaction.guild.roles, name="Clipper")
          if not role:
               role = await interaction.guild.create_role(
                    name="Clipper",
                    color=discord.Color.blue(),
                    reason="Auto-created by Clipper Bot"
               )
          await interaction.user.add_roles(role)
          return role

     @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red)
     async def cancel(self, interaction: discord.Interaction, button: Button):
          if interaction.user.id != self.user_id:
               await interaction.response.send_message("❌ Only the verifying user can cancel", ephemeral=True)
               return
          
          embed = discord.Embed(
               title="❌ Verification Cancelled",
               description="You can restart verification anytime with `/verify`",
               color=discord.Color.red()
          )
          await interaction.response.edit_message(embed=embed, view=None)