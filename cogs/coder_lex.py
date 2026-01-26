import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import io
import os
import logging
from typing import Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
import re

# ================== LOGGING ==================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================== CONFIG ==================

@dataclass
class Config:
    """Configuration settings for the bot"""
    OPENROUTER_API_KEY: str
    OPENROUTER_URL: str = "https://openrouter.ai/api/v1/chat/completions"
    MODEL: str = "anthropic/claude-3.5-sonnet"
    TEMPERATURE: float = 0.2
    MAX_FILE_CHARS: int = 12000
    MAX_MEMORY_CHARS: int = 6000
    EMBED_CHUNK: int = 1000
    API_TIMEOUT: int = 90
    DISCORD_CHAR_LIMIT: int = 2000  # Discord message character limit
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables"""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")
        return cls(OPENROUTER_API_KEY=api_key)

# ================== EXCEPTIONS ==================

class BotException(Exception):
    """Base exception for bot errors"""
    pass

class APIException(BotException):
    """Exception for API-related errors"""
    pass

class FileSizeException(BotException):
    """Exception for file size violations"""
    pass

class MemoryException(BotException):
    """Exception for memory-related errors"""
    pass

# ================== ENUMS ==================

class PromptType(Enum):
    """Types of prompts for different operations"""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    CODE_ANALYSIS = "code_analysis"
    CODE_CONTINUATION = "code_continuation"

# ================== MEMORY ==================

class MemoryStore:
    """Thread-safe memory store for user code history"""
    
    def __init__(self, max_chars: int):
        self.data = {}
        self.max_chars = max_chars
        self._lock = asyncio.Lock()
    
    async def get(self, user_id: int) -> Optional[str]:
        """Retrieve stored code for a user"""
        async with self._lock:
            try:
                return self.data.get(user_id)
            except Exception as e:
                logger.error(f"Error retrieving memory for user {user_id}: {e}")
                raise MemoryException(f"Failed to retrieve memory: {e}")
    
    async def set(self, user_id: int, content: str) -> None:
        """Store code for a user with size limit"""
        async with self._lock:
            try:
                if not content:
                    logger.warning(f"Attempted to store empty content for user {user_id}")
                    return
                
                trimmed_content = content[-self.max_chars:]
                self.data[user_id] = trimmed_content
                logger.info(f"Stored {len(trimmed_content)} chars for user {user_id}")
            except Exception as e:
                logger.error(f"Error storing memory for user {user_id}: {e}")
                raise MemoryException(f"Failed to store memory: {e}")
    
    async def clear(self, user_id: int) -> bool:
        """Clear stored code for a user"""
        async with self._lock:
            try:
                if user_id in self.data:
                    del self.data[user_id]
                    logger.info(f"Cleared memory for user {user_id}")
                    return True
                return False
            except Exception as e:
                logger.error(f"Error clearing memory for user {user_id}: {e}")
                raise MemoryException(f"Failed to clear memory: {e}")

# ================== CODE SPLITTER ==================

class CodeSplitter:
    """Smart code splitting that respects syntax and Discord limits"""
    
    @staticmethod
    def extract_code_from_response(text: str) -> Tuple[str, str]:
        """Extract code from markdown code blocks if present"""
        # Try to find code blocks with language specifier
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        
        if matches:
            language = matches[0][0] if matches[0][0] else ''
            code = '\n'.join([match[1] for match in matches])
            return code.strip(), language
        
        # If no code blocks, return as is
        return text.strip(), ''
    
    @staticmethod
    def find_safe_split_point(code: str, max_length: int) -> int:
        """Find a safe point to split code (at line break, not mid-statement)"""
        if len(code) <= max_length:
            return len(code)
        
        # Look for a newline before the limit
        search_start = max(0, max_length - 200)  # Look back up to 200 chars
        chunk = code[search_start:max_length]
        
        # Find the last newline in the chunk
        last_newline = chunk.rfind('\n')
        
        if last_newline != -1:
            return search_start + last_newline + 1
        
        # If no newline found, just split at limit
        return max_length
    
    @staticmethod
    def split_code_intelligently(code: str, chunk_size: int = 1500) -> List[str]:
        """Split code into chunks at safe points"""
        if len(code) <= chunk_size:
            return [code]
        
        chunks = []
        remaining = code
        
        while remaining:
            if len(remaining) <= chunk_size:
                chunks.append(remaining)
                break
            
            split_point = CodeSplitter.find_safe_split_point(remaining, chunk_size)
            chunks.append(remaining[:split_point])
            remaining = remaining[split_point:]
        
        return chunks
    
    @staticmethod
    def needs_continuation(code: str) -> Tuple[bool, str]:
        """Check if code appears incomplete and extract the last portion"""
        lines = code.strip().split('\n')
        
        # Indicators that code might be incomplete
        incomplete_indicators = [
            lambda l: l.rstrip().endswith((':', ',', '(', '[', '{')),
            lambda l: l.strip().startswith(('def ', 'class ', 'if ', 'for ', 'while ', 'with ', 'try:')),
            lambda l: not l.strip().endswith(('}', ')', ']', 'pass', 'return', 'break', 'continue'))
        ]
        
        if lines:
            last_line = lines[-1]
            for indicator in incomplete_indicators:
                if indicator(last_line):
                    # Return last 500 chars as context
                    context = code[-500:] if len(code) > 500 else code
                    return True, context
        
        return False, ""

# ================== LLM SERVICE ==================

class LLMService:
    """Service for interacting with OpenRouter API"""
    
    def __init__(self, config: Config):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self) -> None:
        """Initialize the HTTP session"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.API_TIMEOUT)
            self.session = aiohttp.ClientSession(timeout=timeout)
            logger.info("LLM service initialized")
    
    async def close(self) -> None:
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("LLM service closed")
    
    def _build_headers(self) -> dict:
        """Build request headers"""
        return {
            "Authorization": f"Bearer {self.config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://lexus-bot.local",
            "X-Title": "Lexus Discord Bot",
        }
    
    def _build_payload(self, system_prompt: str, user_prompt: str) -> dict:
        """Build API request payload"""
        return {
            "model": self.config.MODEL,
            "temperature": self.config.TEMPERATURE,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
    
    async def call(self, system_prompt: str, user_prompt: str) -> str:
        """Make API call to OpenRouter"""
        if not self.session:
            await self.initialize()
        
        payload = self._build_payload(system_prompt, user_prompt)
        headers = self._build_headers()
        
        try:
            async with self.session.post(
                self.config.OPENROUTER_URL,
                json=payload,
                headers=headers
            ) as resp:
                if resp.status == 429:
                    logger.warning("Rate limit exceeded")
                    raise APIException("Rate limit exceeded. Please try again later.")
                
                if resp.status == 401:
                    logger.error("Invalid API key")
                    raise APIException("Invalid API key. Please check configuration.")
                
                if resp.status >= 500:
                    logger.error(f"OpenRouter server error: {resp.status}")
                    raise APIException("OpenRouter service unavailable. Please try again.")
                
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"OpenRouter error {resp.status}: {error_text}")
                    raise APIException(f"API request failed with status {resp.status}")
                
                data = await resp.json()
                
                if "choices" not in data or not data["choices"]:
                    logger.error("Invalid API response structure")
                    raise APIException("Invalid response from API")
                
                content = data["choices"][0]["message"]["content"]
                logger.info(f"Successfully generated {len(content)} characters")
                return content
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            raise APIException(f"Network error: {str(e)}")
        except asyncio.TimeoutError:
            logger.error("API request timed out")
            raise APIException("Request timed out. Please try again.")
        except Exception as e:
            logger.error(f"Unexpected error in API call: {e}")
            raise APIException(f"Unexpected error: {str(e)}")

# ================== PROMPT BUILDER ==================

class PromptBuilder:
    """Build prompts for different operation types"""
    
    @staticmethod
    def build_system_prompt(prompt_type: PromptType) -> str:
        """Build system prompt based on operation type"""
        prompts = {
            PromptType.CODE_GENERATION: (
                "You are a senior software engineer. "
                "If previous code is provided, modify it according to the instruction. "
                "Otherwise, generate new code from scratch. "
                "Think carefully about edge cases and best practices. "
                "Return only final, valid, production-ready code without explanations."
            ),
            PromptType.CODE_REVIEW: (
                "You are a senior software engineer and code reviewer. "
                "Apply the instruction precisely while maintaining code quality. "
                "Preserve existing functionality unless explicitly told otherwise. "
                "Improve code style, performance, and maintainability. "
                "Return only the final improved code without explanations."
            ),
            PromptType.CODE_ANALYSIS: (
                "You are a senior software engineer conducting a code review. "
                "Analyze the provided code thoroughly. "
                "Do not rewrite or modify the code. "
                "Provide a detailed analysis covering:\n"
                "1. Potential bugs and issues\n"
                "2. Security vulnerabilities\n"
                "3. Performance concerns\n"
                "4. Code quality and maintainability\n"
                "5. Suggested improvements"
            ),
            PromptType.CODE_CONTINUATION: (
                "You are a senior software engineer completing code that was cut off. "
                "The code below is incomplete because it exceeded Discord's character limit. "
                "Continue writing the code from exactly where it stopped. "
                "Do NOT repeat any of the provided code. "
                "Do NOT add explanations. "
                "Simply continue the code naturally to completion. "
                "Make sure the continuation flows seamlessly from the cutoff point."
            ),
        }
        return prompts.get(prompt_type, "")
    
    @staticmethod
    def build_user_prompt(
        instruction: str,
        previous_code: Optional[str] = None,
        current_code: Optional[str] = None,
        filename: Optional[str] = None
    ) -> str:
        """Build user prompt with context"""
        parts = []
        
        if filename:
            parts.append(f"Filename: {filename}\n")
        
        if previous_code:
            parts.append(f"Previous code:\n{previous_code}\n")
        
        if current_code:
            parts.append(f"Source code:\n{current_code}\n")
        
        parts.append(f"Instruction:\n{instruction}")
        
        return "\n".join(parts)

# ================== OUTPUT HANDLER ==================

class OutputHandler:
    """Handle code output formatting and sending with auto-continuation"""
    
    def __init__(self, config: Config, llm_service: 'LLMService'):
        self.config = config
        self.llm_service = llm_service
        self.code_splitter = CodeSplitter()
    
    def create_code_embeds(self, code: str, language: str = "", part_info: str = "") -> List[discord.Embed]:
        """Create embeds for code display"""
        embeds = []
        chunks = self.code_splitter.split_code_intelligently(code, self.config.EMBED_CHUNK)
        
        title_prefix = "✨ Generated Code"
        if part_info:
            title_prefix = f"✨ Generated Code {part_info}"
        
        embed = discord.Embed(
            title=title_prefix,
            color=discord.Color.blurple()
        )
        
        for i, chunk in enumerate(chunks):
            embed.add_field(
                name=f"Part {i + 1}/{len(chunks)}",
                value=f"```{language}\n{chunk}\n```",
                inline=False,
            )
            
            if len(embed.fields) == 5:
                embeds.append(embed)
                embed = discord.Embed(
                    title=f"{title_prefix} (continued)",
                    color=discord.Color.blurple()
                )
        
        if embed.fields:
            embeds.append(embed)
        
        return embeds
    
    async def _continue_code(self, incomplete_code: str, context: str) -> str:
        """Request continuation of incomplete code from AI"""
        system_prompt = PromptBuilder.build_system_prompt(PromptType.CODE_CONTINUATION)
        
        user_prompt = (
            f"Here is the incomplete code that was cut off:\n\n"
            f"```\n{context}\n```\n\n"
            f"Continue writing the code from where it stopped. "
            f"Do not repeat the code above, just continue it."
        )
        
        continuation = await self.llm_service.call(system_prompt, user_prompt)
        
        # Extract code from response if wrapped in markdown
        continued_code, _ = self.code_splitter.extract_code_from_response(continuation)
        
        return continued_code
    
    async def send_code(
        self,
        destination,
        code: str,
        filename: str = "generated_code.py",
        auto_continue: bool = True
    ) -> None:
        """Send code as embeds or file with auto-continuation support"""
        try:
            full_code = code
            part_number = 1
            
            # Extract actual code from markdown if present
            clean_code, language = self.code_splitter.extract_code_from_response(code)
            if clean_code:
                full_code = clean_code
            
            # Check if we should send as file directly (very long code)
            if len(full_code) > 8000:
                file = discord.File(
                    io.BytesIO(full_code.encode('utf-8')),
                    filename=filename
                )
                await destination.send(
                    content="📄 Code is very lengthy, sending as complete file.",
                    file=file
                )
                logger.info(f"Successfully sent code as file ({len(full_code)} chars)")
                return
            
            # Send code in embeds with continuation support
            while full_code:
                # Check if code fits in Discord limits
                if len(full_code) <= 3500:  # Safe limit for embeds
                    part_info = f"(Part {part_number})" if part_number > 1 else ""
                    embeds = self.create_code_embeds(full_code, language, part_info)
                    for embed in embeds:
                        await destination.send(embed=embed)
                    logger.info(f"Successfully sent final code part ({len(full_code)} chars)")
                    break
                
                # Code is too long, need to split and continue
                split_point = self.code_splitter.find_safe_split_point(full_code, 3000)
                current_chunk = full_code[:split_point]
                remaining = full_code[split_point:]
                
                # Send current chunk
                part_info = f"(Part {part_number})"
                embeds = self.create_code_embeds(current_chunk, language, part_info)
                for embed in embeds:
                    await destination.send(embed=embed)
                
                logger.info(f"Sent part {part_number} ({len(current_chunk)} chars)")
                
                # Check if we should auto-continue
                if auto_continue and remaining:
                    await destination.send("⏳ Continuing code generation...")
                    
                    # Get continuation context
                    needs_cont, context = self.code_splitter.needs_continuation(current_chunk)
                    
                    if needs_cont or len(remaining) > 100:
                        # Request continuation from AI
                        try:
                            continuation = await self._continue_code(full_code, current_chunk[-500:])
                            # Merge with remaining code
                            full_code = remaining + "\n" + continuation
                        except Exception as e:
                            logger.error(f"Failed to generate continuation: {e}")
                            # Just send remaining code
                            full_code = remaining
                    else:
                        full_code = remaining
                    
                    part_number += 1
                else:
                    # No auto-continue, send remaining as file
                    if remaining:
                        file = discord.File(
                            io.BytesIO(remaining.encode('utf-8')),
                            filename=f"continuation_{filename}"
                        )
                        await destination.send(
                            content="📄 Remaining code sent as file:",
                            file=file
                        )
                    break
            
            logger.info(f"Successfully completed code output in {part_number} part(s)")
            
        except discord.HTTPException as e:
            logger.error(f"Failed to send code: {e}")
            raise BotException(f"Failed to send code: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error sending code: {e}")
            raise BotException(f"Unexpected error: {str(e)}")

# ================== COG ==================

class CodeCog(commands.Cog):
    """Main cog for code generation and analysis"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        try:
            self.config = Config.from_env()
            self.memory = MemoryStore(self.config.MAX_MEMORY_CHARS)
            self.llm_service = LLMService(self.config)
            self.prompt_builder = PromptBuilder()
            self.output_handler = OutputHandler(self.config, self.llm_service)
            
            # Create command tree context menu
            self.ctx_menu = app_commands.ContextMenu(
                name='Analyze Code',
                callback=self.context_menu_callback,
            )
            self.bot.tree.add_command(self.ctx_menu)
            
            logger.info("CodeCog initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize CodeCog: {e}")
            raise
    
    async def cog_load(self):
        """Called when cog is loaded"""
        await self.llm_service.initialize()
        logger.info("CodeCog loaded")
    
    async def cog_unload(self):
        """Called when cog is unloaded"""
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)
        await self.llm_service.close()
        logger.info("CodeCog unloaded")
    
    async def context_menu_callback(self, interaction: discord.Interaction, message: discord.Message):
        """Context menu callback for analyzing code"""
        await interaction.response.send_message("Context menu feature coming soon!", ephemeral=True)
    
    async def _handle_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Centralized error handling"""
        error_messages = {
            APIException: "⚠️ API Error: {}",
            FileSizeException: "⚠️ File Error: {}",
            MemoryException: "⚠️ Memory Error: {}",
            BotException: "⚠️ Bot Error: {}",
        }
        
        error_type = type(error)
        message_template = error_messages.get(error_type, "⚠️ Unexpected Error: {}")
        error_message = message_template.format(str(error))
        
        try:
            if interaction.response.is_done():
                await interaction.followup.send(error_message)
            else:
                await interaction.response.send_message(error_message)
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    
    async def _validate_file(self, file: discord.Attachment) -> str:
        """Validate and read file content"""
        try:
            raw = await file.read()
            code_text = raw.decode("utf-8", errors="ignore")
            
            if len(code_text) > self.config.MAX_FILE_CHARS:
                raise FileSizeException(
                    f"File exceeds maximum size of {self.config.MAX_FILE_CHARS} characters"
                )
            
            if not code_text.strip():
                raise FileSizeException("File is empty or contains no readable text")
            
            return code_text
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode file {file.filename}: {e}")
            raise FileSizeException("File encoding not supported. Please use UTF-8.")
        except Exception as e:
            logger.error(f"Error reading file {file.filename}: {e}")
            raise FileSizeException(f"Failed to read file: {str(e)}")
    
    # ---------- PREFIX COMMAND ----------
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle prefix-based code generation"""
        if message.author.bot:
            return
        
        if not message.content.lower().startswith("lex code"):
            return
        
        task = message.content[len("lex code"):].strip()
        if not task:
            await message.channel.send("❓ Please provide a coding task.")
            return
        
        status_msg = await message.channel.send("🧠 Lexus is thinking...")
        
        try:
            previous = await self.memory.get(message.author.id)
            
            user_prompt = self.prompt_builder.build_user_prompt(
                instruction=task,
                previous_code=previous
            )
            
            system_prompt = self.prompt_builder.build_system_prompt(
                PromptType.CODE_GENERATION
            )
            
            code = await self.llm_service.call(system_prompt, user_prompt)
            
            await self.memory.set(message.author.id, code)
            await status_msg.delete()
            await self.output_handler.send_code(message.channel, code)
            
        except Exception as e:
            logger.error(f"Error in prefix command: {e}")
            await status_msg.delete()
            await message.channel.send(f"⚠️ Error: {str(e)}")
    
    # ---------- SLASH: /code ----------
    
    @app_commands.command(name="code", description="Generate or modify code with AI assistance")
    @app_commands.describe(
        prompt="What code do you want to generate?",
        auto_continue="Auto-continue if code is cut off?"
    )
    async def slash_code(
        self,
        interaction: discord.Interaction,
        prompt: str,
        auto_continue: bool = True
    ):
        """Generate code based on user prompt"""
        await interaction.response.defer()
        
        try:
            previous = await self.memory.get(interaction.user.id)
            
            user_prompt = self.prompt_builder.build_user_prompt(
                instruction=prompt,
                previous_code=previous
            )
            
            system_prompt = self.prompt_builder.build_system_prompt(
                PromptType.CODE_GENERATION
            )
            
            code = await self.llm_service.call(system_prompt, user_prompt)
            
            await self.memory.set(interaction.user.id, code)
            
            # Send to the channel, not interaction
            await self.output_handler.send_code(interaction.channel, code, auto_continue=auto_continue)
            
            # Acknowledge with followup
            await interaction.followup.send("✅ Code generated!", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in /code command: {e}")
            await self._handle_error(interaction, e)
    
    # ---------- SLASH: /code-review ----------
    
    @app_commands.command(name="code-review", description="Review and improve code from a file")
    @app_commands.describe(
        instruction="What improvements do you want?",
        file="Code file to review",
        auto_continue="Auto-continue if code is cut off?"
    )
    async def code_review(
        self,
        interaction: discord.Interaction,
        instruction: str,
        file: discord.Attachment,
        auto_continue: bool = True
    ):
        """Review and improve code from file"""
        await interaction.response.defer()
        
        try:
            code_text = await self._validate_file(file)
            
            user_prompt = self.prompt_builder.build_user_prompt(
                instruction=instruction,
                current_code=code_text,
                filename=file.filename
            )
            
            system_prompt = self.prompt_builder.build_system_prompt(
                PromptType.CODE_REVIEW
            )
            
            result = await self.llm_service.call(system_prompt, user_prompt)
            
            await self.memory.set(interaction.user.id, result)
            
            new_filename = f"improved_{file.filename}"
            await self.output_handler.send_code(interaction.channel, result, filename=new_filename, auto_continue=auto_continue)
            
            # Acknowledge with followup
            await interaction.followup.send("✅ Code review completed!", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in /code-review command: {e}")
            await self._handle_error(interaction, e)
    
    # ---------- SLASH: /code-analyze ----------
    
    @app_commands.command(name="code-analyze", description="Analyze code for issues and improvements")
    @app_commands.describe(file="Code file to analyze")
    async def code_analyze(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment
    ):
        """Analyze code and provide feedback"""
        await interaction.response.defer()
        
        try:
            code_text = await self._validate_file(file)
            
            system_prompt = self.prompt_builder.build_system_prompt(
                PromptType.CODE_ANALYSIS
            )
            
            analysis = await self.llm_service.call(system_prompt, code_text)
            
            if len(analysis) < 4000:
                embed = discord.Embed(
                    title="📊 Code Analysis",
                    description=analysis,
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed)
            else:
                file_obj = discord.File(
                    io.BytesIO(analysis.encode('utf-8')),
                    filename=f"analysis_{file.filename}.txt"
                )
                await interaction.followup.send(
                    content="📄 Analysis is lengthy, sending as file.",
                    file=file_obj
                )
            
        except Exception as e:
            logger.error(f"Error in /code-analyze command: {e}")
            await self._handle_error(interaction, e)
    
    # ---------- SLASH: /code-memory ----------
    
    @app_commands.command(name="code-memory", description="Clear your stored code history")
    async def code_memory(self, interaction: discord.Interaction):
        """Clear user's code memory"""
        try:
            cleared = await self.memory.clear(interaction.user.id)
            
            if cleared:
                await interaction.response.send_message("✅ Code memory cleared successfully!", ephemeral=True)
            else:
                await interaction.response.send_message("ℹ️ No code memory found to clear.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in /code-memory command: {e}")
            await self._handle_error(interaction, e)

# ================== SETUP ==================

async def setup(bot: commands.Bot):
    """Setup function to add cog to bot"""
    try:
        cog = CodeCog(bot)
        await bot.add_cog(cog)
        
        # Add slash commands to the bot's tree
        bot.tree.add_command(cog.slash_code)
        bot.tree.add_command(cog.code_review)
        bot.tree.add_command(cog.code_analyze)
        bot.tree.add_command(cog.code_memory)
        
        logger.info("CodeCog added to bot with slash commands registered")
    except Exception as e:
        logger.error(f"Failed to add CodeCog: {e}")
        raise
