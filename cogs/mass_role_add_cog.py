import discord
from discord.ext import commands
from discord import ui, ButtonStyle
import asyncio
import time

class RoleActionView(ui.View):
    def __init__(self, original_author_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.original_author_id = original_author_id
        self.is_running = False
        self.should_stop = False

    @ui.button(label="EXECUTE", style=ButtonStyle.success, emoji="⚡", custom_id="execute_role")
    async def execute_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.is_running:
            await interaction.response.send_message("⚠️ Process already running!", ephemeral=True)
            return
            
        self.is_running = True
        button.disabled = True
        self.stop_button.disabled = False
        await interaction.response.edit_message(view=self)
        
        # Get relevant data
        role = interaction.message.embeds[0].fields[0].value
        # Extract role ID from mention format like <@&123456789>
        role_id = int(role.split("&")[1].split(">")[0])
        actual_role = interaction.guild.get_role(role_id)
        
        if not actual_role:
            await interaction.followup.send("⚠️ Role not found! It may have been deleted.", ephemeral=True)
            return
            
        # Start the role addition process
        progress_embed = discord.Embed(
            title="🔄 MASS ROLE DEPLOYMENT IN PROGRESS",
            description="```yaml\n[SYSTEM]: Deploying neural identities to targets\n```",
            color=0x00c8ff
        )
        progress_embed.add_field(name="Target Role", value=role, inline=True)
        progress_embed.add_field(name="Operation", value="Mass Addition", inline=True)
        progress_embed.add_field(name="Progress", value="0%", inline=False)
        progress_embed.set_footer(text="NEO-ROLES SYSTEM v2.0 • Running security protocols")
        
        progress_message = await interaction.followup.send(embed=progress_embed)
        
        # Process members in batches
        total_members = len(interaction.guild.members)
        success_count = 0
        failure_count = 0
        
        for i, member in enumerate(interaction.guild.members):
            if self.should_stop:
                break
                
            try:
                if actual_role not in member.roles:  # Only add if they don't have it already
                    await member.add_roles(actual_role)
                    success_count += 1
                
                # Update progress every 5 members or at specific percentages
                if i % 5 == 0 or i == total_members - 1:
                    progress = min(100, int((i + 1) / total_members * 100))
                    progress_bar = self.generate_progress_bar(progress)
                    
                    progress_embed.set_field_at(
                        2, 
                        name="Progress", 
                        value=f"{progress_bar} {progress}%\n\n**Processed:** {i+1}/{total_members}\n**Success:** {success_count}\n**Failed:** {failure_count}",
                        inline=False
                    )
                    progress_embed.title = f"🔄 MASS ROLE DEPLOYMENT {'ABORTED' if self.should_stop else 'IN PROGRESS'}"
                    
                    await progress_message.edit(embed=progress_embed)
                    
                # Small delay to prevent rate limiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                failure_count += 1
                print(f"Failed to add role to {member.display_name}: {e}")
        
        # Final report
        self.is_running = False
        self.should_stop = False
        
        final_embed = discord.Embed(
            title="✅ MASS ROLE DEPLOYMENT COMPLETE",
            description="```yaml\n[SYSTEM]: Neural identity deployment finalized\n```",
            color=0x00ffaa if not self.should_stop else 0xff3366
        )
        final_embed.add_field(name="Target Role", value=role, inline=True)
        final_embed.add_field(name="Status", value="Complete" if not self.should_stop else "Aborted", inline=True)
        final_embed.add_field(
            name="Results", 
            value=f"**Success:** {success_count} members\n**Failed:** {failure_count} members\n**Total Processed:** {min(i+1, total_members)}/{total_members}", 
            inline=False
        )
        final_embed.set_footer(text=f"NEO-ROLES SYSTEM v2.0 • Operation completed at {discord.utils.utcnow().strftime('%H:%M:%S UTC')}")
        
        await progress_message.edit(embed=final_embed)
        
        # Re-enable button for potential future use
        button.disabled = False
        self.stop_button.disabled = True
        await interaction.message.edit(view=self)

    @ui.button(label="ABORT", style=ButtonStyle.danger, emoji="🛑", custom_id="stop_role", disabled=True)
    async def stop_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.is_running:
            await interaction.response.send_message("⚠️ No process is currently running!", ephemeral=True)
            return
            
        self.should_stop = True
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("⚠️ Aborting process... This may take a moment to complete safely.", ephemeral=True)

    @ui.button(label="CANCEL", style=ButtonStyle.secondary, emoji="❌", custom_id="cancel_role")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.is_running:
            await interaction.response.send_message("⚠️ Cannot cancel while operation is in progress. Use ABORT instead.", ephemeral=True)
            return
            
        for item in self.children:
            item.disabled = True
            
        cancel_embed = discord.Embed(
            title="❌ OPERATION CANCELED",
            description="```yaml\n[SYSTEM]: Mass role deployment canceled before execution\n```",
            color=0xff3366
        )
        await interaction.message.edit(embed=cancel_embed, view=self)
        await interaction.response.send_message("Operation canceled successfully.", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original_author_id:
            await interaction.response.send_message("You aren't authorized to control this operation.", ephemeral=True)
            return False
        return True

    def generate_progress_bar(self, percent):
        filled_length = int(20 * percent // 100)
        bar = '█' * filled_length + '░' * (20 - filled_length)
        return f'`{bar}`'

class MassRoleAddCog(commands.Cog):
    """⚙️ Mass Role Manager - Add roles to multiple members at once."""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="massrole", help="Adds a role to all members.")
    @commands.has_permissions(manage_roles=True)
    async def mass_role_add(self, ctx, role: discord.Role):
        # Check bot permissions first
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("⚠️ I need the 'Manage Roles' permission to execute this command.")
            return
            
        # Check role hierarchy
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send("⚠️ I cannot assign roles higher than or equal to my highest role.")
            return
            
        # Create confirmation embed with cyberpunk theme
        embed = discord.Embed(
            title="⚠️ MASS ROLE DEPLOYMENT CONFIRMATION",
            description="```yaml\n[SYSTEM]: You are about to deploy role to all users\n[WARNING]: This action affects all members\n[NOTICE]: Use interactive controls below\n```",
            color=0xff9500
        )
        
        total_members = len([m for m in ctx.guild.members if role not in m.roles])
        embed.add_field(name="Target Role", value=role.mention, inline=True)
        embed.add_field(name="Operation", value="Mass Addition", inline=True)
        embed.add_field(name="Scope", value=f"{total_members} members without role", inline=True)
        embed.add_field(name="Authorized By", value=ctx.author.mention, inline=True)
        embed.add_field(name="Instructions", value="Click **EXECUTE** to begin deployment\nClick **CANCEL** to abort operation", inline=False)
        embed.set_footer(text="NEO-ROLES SYSTEM v2.0 • This operation may take time depending on server size")
        
        # Create view with buttons
        view = RoleActionView(ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="checkrole", help="Shows how many users have a specific role.")
    @commands.has_permissions(manage_roles=True)
    async def check_role(self, ctx, role: discord.Role):
        members_with_role = len([m for m in ctx.guild.members if role in m.roles])
        members_without_role = len(ctx.guild.members) - members_with_role
        
        embed = discord.Embed(
            title="👥 ROLE DISTRIBUTION ANALYSIS",
            description="```yaml\n[SYSTEM]: Neural identity distribution scan complete\n```",
            color=0x36a3ff
        )
        
        percent_with = int((members_with_role / len(ctx.guild.members)) * 100) if ctx.guild.members else 0
        percent_bar = self.generate_progress_bar(percent_with)
        
        embed.add_field(name="Target Role", value=role.mention, inline=True)
        embed.add_field(name="Distribution", value=f"{percent_with}% of users", inline=True)
        embed.add_field(name="Statistics", 
                       value=f"**With role:** {members_with_role} members\n**Without role:** {members_without_role} members\n\n{percent_bar}",
                       inline=False)
        embed.set_footer(text="NEO-ROLES SYSTEM v2.0 • Use 'massrole' to modify role distribution")
        
        await ctx.send(embed=embed)
        
    def generate_progress_bar(self, percent):
        filled_length = int(20 * percent // 100)
        bar = '█' * filled_length + '░' * (20 - filled_length)
        return f'`{bar}`'

async def setup(bot):
    await bot.add_cog(MassRoleAddCog(bot))
