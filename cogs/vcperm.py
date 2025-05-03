import discord
from discord import app_commands, ui
from discord.ext import commands
import asyncio
import datetime
import json
import os

# Data persistence
def load_data():
    if os.path.exists('vc_permission_data.json'):
        try:
            with open('vc_permission_data.json', 'r') as f:
                data = json.load(f)
                return set(data.get('allowed_users', [])), set(data.get('restricted_vcs', []))
        except:
            return set(), set()
    return set(), set()

def save_data(allowed_users, restricted_vcs):
    with open('vc_permission_data.json', 'w') as f:
        json.dump({
            'allowed_users': list(allowed_users),
            'restricted_vcs': list(restricted_vcs)
        }, f)

class VCControlPanel(ui.View):
    def __init__(self, cog, timeout=180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.page = 0
        self.users_per_page = 10
        
    @ui.button(label="🔒 RESTRICT", style=discord.ButtonStyle.danger, custom_id="restrict_button")
    async def restrict_button(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🔒 **ACCESS DENIED**: Admin clearance required", ephemeral=True)
            return
            
        if interaction.user.voice and interaction.user.voice.channel:
            self.cog.restricted_vcs.add(interaction.user.voice.channel.id)
            save_data(self.cog.allowed_users, self.cog.restricted_vcs)
            
            embed = discord.Embed(
                title="🔒 SECURE MODE ACTIVATED",
                description=f"**{interaction.user.voice.channel.name}** is now a restricted access VC.",
                color=0x00FFFF,
                timestamp=datetime.datetime.now()
            )
            embed.set_footer(text="NeuroLink™ Voice Security System", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ **ERROR**: You must be in a voice channel to restrict it.", ephemeral=True)

    @ui.button(label="🔓 UNRESTRICT", style=discord.ButtonStyle.success, custom_id="unrestrict_button")
    async def unrestrict_button(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🔒 **ACCESS DENIED**: Admin clearance required", ephemeral=True)
            return
            
        if interaction.user.voice and interaction.user.voice.channel:
            if interaction.user.voice.channel.id in self.cog.restricted_vcs:
                self.cog.restricted_vcs.discard(interaction.user.voice.channel.id)
                save_data(self.cog.allowed_users, self.cog.restricted_vcs)
                
                embed = discord.Embed(
                    title="🔓 RESTRICTION LIFTED",
                    description=f"**{interaction.user.voice.channel.name}** is now open for public access.",
                    color=0x00FFFF,
                    timestamp=datetime.datetime.now()
                )
                embed.set_footer(text="NeuroLink™ Voice Security System", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ **ERROR**: This voice channel is not restricted.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ **ERROR**: You must be in a voice channel to unrestrict it.", ephemeral=True)

    @ui.button(label="👥 LIST USERS", style=discord.ButtonStyle.primary, custom_id="list_users_button")
    async def list_users_button(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🔒 **ACCESS DENIED**: Admin clearance required", ephemeral=True)
            return
            
        allowed_users = list(self.cog.allowed_users)
        
        if not allowed_users:
            embed = discord.Embed(
                title="👤 AUTHORIZED USERS",
                description="**NO USERS FOUND IN DATABASE**\nNo users have been granted access to restricted VCs.",
                color=0x00FFFF,
                timestamp=datetime.datetime.now()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        # Paginate the users
        max_page = (len(allowed_users) - 1) // self.users_per_page
        
        start_idx = self.page * self.users_per_page
        end_idx = min(start_idx + self.users_per_page, len(allowed_users))
        
        users_list = []
        for i, user_id in enumerate(allowed_users[start_idx:end_idx], start=start_idx+1):
            user = interaction.guild.get_member(user_id)
            display_name = user.display_name if user else f"Unknown User (ID: {user_id})"
            users_list.append(f"`{i}.` <@{user_id}> - {display_name}")
        
        users_text = "\n".join(users_list)
        
        embed = discord.Embed(
            title="👤 AUTHORIZED USERS",
            description=f"Users with access to restricted voice channels:\n\n{users_text}",
            color=0x00FFFF,
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text=f"Page {self.page+1}/{max_page+1} • NeuroLink™ Voice Security", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        # Pagination buttons
        pagination_view = UserListPagination(self.cog, self.page, max_page)
        
        await interaction.response.send_message(embed=embed, view=pagination_view, ephemeral=True)

class UserListPagination(ui.View):
    def __init__(self, cog, current_page=0, max_page=0):
        super().__init__(timeout=120)
        self.cog = cog
        self.current_page = current_page
        self.max_page = max_page
        self.users_per_page = 10
        
        # Disable buttons if needed
        if current_page == 0:
            self.children[0].disabled = True  # Disable previous button on first page
        if current_page == max_page:
            self.children[1].disabled = True  # Disable next button on last page
            
    @ui.button(label="◀️ PREV", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page = max(0, self.current_page - 1)
        await self.update_page(interaction)
        
    @ui.button(label="NEXT ▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page = min(self.max_page, self.current_page + 1)
        await self.update_page(interaction)
    
    @ui.button(label="ADD USER", style=discord.ButtonStyle.success, emoji="✅")
    async def add_user_button(self, interaction: discord.Interaction, button: ui.Button):
        # Show a modal to add a user
        modal = AddUserModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @ui.button(label="REMOVE USER", style=discord.ButtonStyle.danger, emoji="❌")
    async def remove_user_button(self, interaction: discord.Interaction, button: ui.Button):
        # Show a modal to remove a user
        modal = RemoveUserModal(self.cog)
        await interaction.response.send_modal(modal)
        
    async def update_page(self, interaction: discord.Interaction):
        allowed_users = list(self.cog.allowed_users)
        
        start_idx = self.current_page * self.users_per_page
        end_idx = min(start_idx + self.users_per_page, len(allowed_users))
        
        users_list = []
        for i, user_id in enumerate(allowed_users[start_idx:end_idx], start=start_idx+1):
            user = interaction.guild.get_member(user_id)
            display_name = user.display_name if user else f"Unknown User (ID: {user_id})"
            users_list.append(f"`{i}.` <@{user_id}> - {display_name}")
        
        users_text = "\n".join(users_list)
        
        embed = discord.Embed(
            title="👤 AUTHORIZED USERS",
            description=f"Users with access to restricted voice channels:\n\n{users_text}",
            color=0x00FFFF,
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text=f"Page {self.current_page+1}/{self.max_page+1} • NeuroLink™ Voice Security", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        # Disable buttons if needed
        if self.current_page == 0:
            self.children[0].disabled = True
        else:
            self.children[0].disabled = False
            
        if self.current_page == self.max_page:
            self.children[1].disabled = True
        else:
            self.children[1].disabled = False
            
        await interaction.response.edit_message(embed=embed, view=self)

class AddUserModal(ui.Modal, title="👤 ADD AUTHORIZED USER"):
    user_id = ui.TextInput(
        label="USER ID",
        placeholder="Enter the user ID to grant access...",
        required=True,
        min_length=17,
        max_length=19
    )
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            user = interaction.guild.get_member(user_id)
            
            if not user:
                await interaction.response.send_message("⚠️ **ERROR**: User not found in this server.", ephemeral=True)
                return
                
            self.cog.allowed_users.add(user_id)
            save_data(self.cog.allowed_users, self.cog.restricted_vcs)
            
            embed = discord.Embed(
                title="✅ ACCESS GRANTED",
                description=f"**{user.display_name}** has been added to the authorized users list.\nThey can now access restricted voice channels.",
                color=0x00FFFF,
                timestamp=datetime.datetime.now()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message("⚠️ **ERROR**: Invalid user ID format. Please enter a valid numeric ID.", ephemeral=True)

class RemoveUserModal(ui.Modal, title="❌ REVOKE USER ACCESS"):
    user_id = ui.TextInput(
        label="USER ID",
        placeholder="Enter the user ID to revoke access...",
        required=True,
        min_length=17,
        max_length=19
    )
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            
            if user_id not in self.cog.allowed_users:
                await interaction.response.send_message("⚠️ **ERROR**: This user is not on the access list.", ephemeral=True)
                return
                
            self.cog.allowed_users.discard(user_id)
            save_data(self.cog.allowed_users, self.cog.restricted_vcs)
            
            user = interaction.guild.get_member(user_id)
            display_name = user.display_name if user else f"User (ID: {user_id})"
            
            embed = discord.Embed(
                title="❌ ACCESS REVOKED",
                description=f"**{display_name}** has been removed from the authorized users list.\nThey can no longer access restricted voice channels.",
                color=0x00FFFF,
                timestamp=datetime.datetime.now()
            )
            if user:
                embed.set_thumbnail(url=user.display_avatar.url)
            
            # If the user is in a restricted VC, kick them
            if user and user.voice and user.voice.channel and user.voice.channel.id in self.cog.restricted_vcs:
                try:
                    await user.move_to(None)
                    embed.add_field(name="AUTO-EJECTION", value="User was in a restricted VC and has been disconnected.", inline=False)
                except:
                    embed.add_field(name="WARNING", value="Failed to disconnect user from voice channel.", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message("⚠️ **ERROR**: Invalid user ID format. Please enter a valid numeric ID.", ephemeral=True)

class RestrictedVCsView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=60)
        self.cog = cog
        
    @ui.button(label="SHOW RESTRICTED VCs", style=discord.ButtonStyle.primary, emoji="🔒")
    async def show_vcs_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.cog.restricted_vcs:
            embed = discord.Embed(
                title="🔒 RESTRICTED VOICE CHANNELS",
                description="No voice channels are currently restricted.",
                color=0x00FFFF,
                timestamp=datetime.datetime.now()
            )
        else:
            restricted_vcs_list = []
            for vc_id in self.cog.restricted_vcs:
                channel = interaction.guild.get_channel(vc_id)
                if channel:
                    restricted_vcs_list.append(f"• {channel.name} (`{channel.id}`)")
                else:
                    restricted_vcs_list.append(f"• Unknown Channel (`{vc_id}`)")
                    
            embed = discord.Embed(
                title="🔒 RESTRICTED VOICE CHANNELS",
                description="The following voice channels have restricted access:\n\n" + "\n".join(restricted_vcs_list),
                color=0x00FFFF,
                timestamp=datetime.datetime.now()
            )
            
        embed.set_footer(text="NeuroLink™ Voice Security System", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class VCPermissionCog(commands.Cog):
    """⚙️ Voice Channel Permission System - Cyberpunk Edition"""

    def __init__(self, bot):
        self.bot = bot
        # Load saved data if available
        self.allowed_users, self.restricted_vcs = load_data()
        self.color = 0x00FFFF  # Cyberpunk cyan color
        
        # Start the save loop
        self.save_task = asyncio.create_task(self._auto_save_loop())
        
    async def _auto_save_loop(self):
        while True:
            await asyncio.sleep(300)  # Save every 5 minutes
            save_data(self.allowed_users, self.restricted_vcs)
            
    def cog_unload(self):
        # Save data when the cog is unloaded
        save_data(self.allowed_users, self.restricted_vcs)
        if hasattr(self, 'save_task'):
            self.save_task.cancel()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Monitor voice channel movement to enforce restrictions"""
        if not after.channel:  # User left VC
            return

        # Check if the joined VC is restricted
        if after.channel.id in self.restricted_vcs and member.id not in self.allowed_users:
            try:
                await member.move_to(None)  # Kick the user from VC
                
                # Send a themed DM
                try:
                    embed = discord.Embed(
                        title="🚫 ACCESS DENIED",
                        description=f"You lack clearance to enter **{after.channel.name}**.\nContact an administrator for access rights.",
                        color=0xFF0033,
                        timestamp=datetime.datetime.now()
                    )
                    embed.set_footer(text=f"{after.channel.guild.name} - NeuroLink™ Voice Security", icon_url=after.channel.guild.icon.url if after.channel.guild.icon else None)
                    await member.send(embed=embed)
                except:
                    # Failed to DM the user - continue silently
                    pass
            except:
                # Failed to kick - likely missing permissions
                pass

    @app_commands.command(name="vcsecurity", description="Manage voice channel security with cyberpunk style")
    @app_commands.default_permissions(administrator=True)
    async def vc_security(self, interaction: discord.Interaction):
        """Open the voice channel security panel"""
        embed = discord.Embed(
            title="🔐 NEUROLINK™ VOICE SECURITY",
            description=(
                "**SYSTEM STATUS:** ONLINE\n\n"
                "Control restricted voice channels and manage user access.\n"
                "Select an option below to manage security protocols."
            ),
            color=self.color,
            timestamp=datetime.datetime.now()
        )
        
        # Add counts
        embed.add_field(
            name="📊 SYSTEM STATS",
            value=(
                f"**Restricted VCs:** {len(self.restricted_vcs)}\n"
                f"**Authorized Users:** {len(self.allowed_users)}"
            ),
            inline=False
        )
        
        embed.set_footer(text="NeuroLink™ Voice Security System v2.0", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        # Create the main view
        view = VCControlPanel(self)
        view.add_item(RestrictedVCsView(self).children[0])  # Add the "Show Restricted VCs" button
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # Legacy commands for backward compatibility
    @commands.command(name="restrict_vc", help="🔒 Restrict the VC where the admin is currently in")
    @commands.has_permissions(administrator=True)
    async def restrict_vc(self, ctx):
        """Legacy command to restrict a voice channel"""
        if ctx.author.voice and ctx.author.voice.channel:
            self.restricted_vcs.add(ctx.author.voice.channel.id)
            save_data(self.allowed_users, self.restricted_vcs)
            
            embed = discord.Embed(
                title="🔒 SECURE MODE ACTIVATED",
                description=f"**{ctx.author.voice.channel.name}** is now a restricted access VC.",
                color=self.color,
                timestamp=datetime.datetime.now()
            )
            embed.set_footer(text="NeuroLink™ Voice Security System", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("⚠️ **ERROR**: You must be in a voice channel to restrict it.")

    @commands.command(name="unrestrict_vc", help="🔓 Unrestrict the VC where the admin is currently in")
    @commands.has_permissions(administrator=True)
    async def unrestrict_vc(self, ctx):
        """Legacy command to unrestrict a voice channel"""
        if ctx.author.voice and ctx.author.voice.channel:
            if ctx.author.voice.channel.id in self.restricted_vcs:
                self.restricted_vcs.discard(ctx.author.voice.channel.id)
                save_data(self.allowed_users, self.restricted_vcs)
                
                embed = discord.Embed(
                    title="🔓 RESTRICTION LIFTED",
                    description=f"**{ctx.author.voice.channel.name}** is now open for public access.",
                    color=self.color,
                    timestamp=datetime.datetime.now()
                )
                embed.set_footer(text="NeuroLink™ Voice Security System", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
                
                await ctx.send(embed=embed)
            else:
                await ctx.send("⚠️ **ERROR**: This voice channel is not restricted.")
        else:
            await ctx.send("⚠️ **ERROR**: You must be in a voice channel to unrestrict it.")

    @commands.command(name="add_vc_user", help="✅ Allow a user to join restricted VCs")
    @commands.has_permissions(administrator=True)
    async def add_vc_user(self, ctx, user: discord.User):
        """Legacy command to add a user to the allowed list"""
        self.allowed_users.add(user.id)
        save_data(self.allowed_users, self.restricted_vcs)
        
        embed = discord.Embed(
            title="✅ ACCESS GRANTED",
            description=f"**{user.name}** has been added to the authorized users list.",
            color=self.color,
            timestamp=datetime.datetime.now()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        await ctx.send(embed=embed)

    @commands.command(name="remove_vc_user", help="❌ Remove a user's access to restricted VCs")
    @commands.has_permissions(administrator=True)
    async def remove_vc_user(self, ctx, user: discord.User):
        """Legacy command to remove a user from the allowed list"""
        if user.id in self.allowed_users:
            self.allowed_users.discard(user.id)
            save_data(self.allowed_users, self.restricted_vcs)
            
            embed = discord.Embed(
                title="❌ ACCESS REVOKED",
                description=f"**{user.name}** has been removed from the authorized users list.",
                color=self.color,
                timestamp=datetime.datetime.now()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"⚠️ **ERROR**: {user.name} is not on the access list.")

    @commands.command(name="list_vc_users", help="👥 Show users allowed in restricted VCs")
    @commands.has_permissions(administrator=True)
    async def list_vc_users(self, ctx):
        """Legacy command to list allowed users"""
        if not self.allowed_users:
            embed = discord.Embed(
                title="👤 AUTHORIZED USERS",
                description="**NO USERS FOUND IN DATABASE**\nNo users have been granted access to restricted VCs.",
                color=self.color,
                timestamp=datetime.datetime.now()
            )
            await ctx.send(embed=embed)
            return
            
        allowed_users_list = []
        for i, user_id in enumerate(self.allowed_users, start=1):
            user = ctx.guild.get_member(user_id)
            display_name = user.display_name if user else f"Unknown User (ID: {user_id})"
            allowed_users_list.append(f"`{i}.` <@{user_id}> - {display_name}")
            
        users_text = "\n".join(allowed_users_list[:15])  # Limit to first 15 users in legacy command
        
        embed = discord.Embed(
            title="👤 AUTHORIZED USERS",
            description=f"Users with access to restricted voice channels:\n\n{users_text}",
            color=self.color,
            timestamp=datetime.datetime.now()
        )
        
        if len(self.allowed_users) > 15:
            embed.set_footer(text=f"Showing 15/{len(self.allowed_users)} users. Use /vcsecurity for full list.")
        else:
            embed.set_footer(text="NeuroLink™ Voice Security System")
            
        await ctx.send(embed=embed)
        
async def setup(bot):
    await bot.add_cog(vcperm(bot))
