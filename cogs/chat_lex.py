import discord
from discord.ext import commands
import aiohttp
import asyncio
import random
import time
import os
import logging
from typing import Dict, Optional, Set, List, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserIntent(Enum):
    """Inferred user intent categories."""
    VENTING = "venting"
    JOKING = "joking"
    SEEKING_ADVICE = "seeking_advice"
    CASUAL_CHAT = "casual_chat"
    TESTING_BOUNDARIES = "testing_boundaries"
    EXPRESSING_DISTRESS = "expressing_distress"
    SHARING_UPDATE = "sharing_update"
    ASKING_QUESTION = "asking_question"
    MAKING_STATEMENT = "making_statement"
    ONGOING = "ongoing"  # Added missing enum value

class MoodState(Enum):
    """User emotional state."""
    CALM = "calm"
    PLAYFUL = "playful"
    IRRITATED = "irritated"
    ANXIOUS = "anxious"
    SAD = "sad"
    OVERWHELMED = "overwhelmed"
    NEUTRAL = "neutral"
    CONFUSED = "confused"

class ConversationPhase(Enum):
    """Conversation trajectory."""
    OPENING = "opening"
    ONGOING = "ongoing"
    ESCALATING = "escalating"
    COOLING_DOWN = "cooling_down"
    REPETITIVE = "repetitive"
    CONCLUDING = "concluding"

@dataclass
class BehavioralContext:
    """Complete behavioral analysis of user state."""
    intent: UserIntent
    mood: MoodState
    phase: ConversationPhase
    emotional_safety_level: int  # 0-10, 10 being safest
    sarcasm_permitted: bool
    response_length_target: str  # "minimal", "moderate", "detailed"
    crisis_indicators: List[str] = field(default_factory=list)
    repetition_count: int = 0
    
@dataclass
class UserSession:
    """Track user conversation state and context."""
    messages: deque
    last_activity: float
    mood_history: deque = field(default_factory=lambda: deque(maxlen=5))
    intent_history: deque = field(default_factory=lambda: deque(maxlen=5))
    crisis_mentions: int = 0
    last_crisis_time: float = 0
    conversation_turns: int = 0
    
    def __post_init__(self):
        if not hasattr(self, 'messages'):
            self.messages = deque(maxlen=8)

class BehavioralAnalyzer:
    """Advanced behavioral intent and mood inference engine."""
    
    # Intent detection patterns
    INTENT_PATTERNS = {
        UserIntent.VENTING: [
            r'\bi (hate|cant stand|sick of|tired of|done with)',
            r'(everything|everyone) (sucks|is awful|annoys me)',
            r'why (does|do|is) .*(always|never|have to)',
            r'(ugh|ughhh|argh|fuck)',
            r'(just|literally) (had to|needed to|want to) (say|tell|share)'
        ],
        UserIntent.JOKING: [
            r'(lol|lmao|haha|😂|💀)',
            r'(kidding|jk|joking)',
            r'(imagine|what if).*lol',
            r'no but seriously tho'
        ],
        UserIntent.SEEKING_ADVICE: [
            r'(what should|should i|do you think i should)',
            r'(any advice|suggestions|ideas|help)',
            r'(how do i|how can i|what can i do)',
            r'(idk what to|not sure what to|dont know how to)'
        ],
        UserIntent.CASUAL_CHAT: [
            r'^(hey|hi|sup|whats up|yo)',
            r'(how are you|hows it going|what about you)',
            r'(just|im) (chillin|hanging|doing nothing)',
            r'(bored|nothing much happening)'
        ],
        UserIntent.TESTING_BOUNDARIES: [
            r'(can you|will you|are you able to).*\?',
            r'(what if i|lets see if)',
            r'(try to|make you|get you to)'
        ],
        UserIntent.EXPRESSING_DISTRESS: [
            r'(cant|can not) (take|handle|deal)',
            r'(nobody|no one) (cares|understands|gets it)',
            r'(so|really|very) (alone|lonely|isolated)',
            r'(whats the point|why bother|no point)'
        ]
    }
    
    # Mood indicators
    MOOD_INDICATORS = {
        MoodState.PLAYFUL: ['lol', 'haha', '😂', '😄', 'lmao', '💀', 'nah'],
        MoodState.IRRITATED: ['ugh', 'annoying', 'whatever', 'seriously', 'literally'],
        MoodState.ANXIOUS: ['worried', 'nervous', 'scared', 'anxious', 'panic', 'stress'],
        MoodState.SAD: ['sad', 'depressed', 'down', 'empty', 'numb', 'cry'],
        MoodState.OVERWHELMED: ['too much', 'cant handle', 'drowning', 'exhausted', 'cant keep up'],
        MoodState.CONFUSED: ['confused', 'idk', 'dont understand', 'what', 'huh', 'why']
    }
    
    # Crisis severity assessment (improved)
    CRISIS_PATTERNS = {
        'critical': [
            'suicide', 'kill myself', 'want to die', 'end it all', 
            'better off dead', 'no reason to live'
        ],
        'severe': [
            'hopeless', 'worthless', 'cant go on', 'give up',
            'nobody cares', 'no point', 'waste of space'
        ],
        'concerning': [
            'depressed', 'anxious', 'overwhelmed', 'breaking down',
            'cant cope', 'falling apart'
        ]
    }
    
    @staticmethod
    def analyze(message: str, session: UserSession) -> BehavioralContext:
        """Perform complete behavioral analysis before response generation."""
        import re
        
        text_lower = message.lower()
        
        # 1. INTENT INFERENCE
        intent = BehavioralAnalyzer._infer_intent(text_lower, session)
        
        # 2. MOOD DETECTION
        mood = BehavioralAnalyzer._detect_mood(text_lower, session)
        
        # 3. CONVERSATION PHASE
        phase = BehavioralAnalyzer._determine_phase(session)
        
        # 4. CRISIS ASSESSMENT (improved to reduce false positives)
        crisis_level, crisis_indicators = BehavioralAnalyzer._assess_crisis(
            text_lower, session
        )
        
        # 5. SAFETY LEVEL (determines sarcasm permission)
        emotional_safety = BehavioralAnalyzer._calculate_safety_level(
            mood, crisis_level, intent
        )
        
        # 6. SARCASM PERMISSION
        sarcasm_ok = BehavioralAnalyzer._sarcasm_permitted(
            emotional_safety, mood, intent
        )
        
        # 7. RESPONSE LENGTH TARGET
        length_target = BehavioralAnalyzer._determine_response_length(
            intent, phase, crisis_level
        )
        
        # Update session history
        session.intent_history.append(intent)
        session.mood_history.append(mood)
        session.conversation_turns += 1
        
        return BehavioralContext(
            intent=intent,
            mood=mood,
            phase=phase,
            emotional_safety_level=emotional_safety,
            sarcasm_permitted=sarcasm_ok,
            response_length_target=length_target,
            crisis_indicators=crisis_indicators,
            repetition_count=BehavioralAnalyzer._detect_repetition(session)
        )
    
    @staticmethod
    def _infer_intent(text: str, session: UserSession) -> UserIntent:
        """Infer primary user intent from message."""
        import re
        
        # Check patterns in priority order
        for intent, patterns in BehavioralAnalyzer.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return intent
        
        # Contextual fallbacks
        if '?' in text:
            return UserIntent.ASKING_QUESTION
        if any(word in text for word in ['just', 'so', 'literally', 'basically']):
            return UserIntent.SHARING_UPDATE
        if session.conversation_turns > 3:
            return UserIntent.ONGOING
        
        return UserIntent.CASUAL_CHAT
    
    @staticmethod
    def _detect_mood(text: str, session: UserSession) -> MoodState:
        """Detect emotional state with context awareness."""
        
        # Check explicit mood indicators
        for mood, indicators in BehavioralAnalyzer.MOOD_INDICATORS.items():
            if any(ind in text for ind in indicators):
                return mood
        
        # Contextual mood inference
        if session.mood_history:
            last_moods = list(session.mood_history)
            # If user has been consistently negative, maintain that
            if last_moods[-3:].count(MoodState.SAD) >= 2:
                return MoodState.SAD
            if last_moods[-3:].count(MoodState.ANXIOUS) >= 2:
                return MoodState.ANXIOUS
        
        return MoodState.NEUTRAL
    
    @staticmethod
    def _determine_phase(session: UserSession) -> ConversationPhase:
        """Determine conversation trajectory."""
        turns = session.conversation_turns
        
        if turns == 0:
            return ConversationPhase.OPENING
        elif turns <= 2:
            return ConversationPhase.ONGOING
        
        # Check for escalation (worsening mood)
        if len(session.mood_history) >= 3:
            recent_moods = list(session.mood_history)[-3:]
            negative_moods = [MoodState.SAD, MoodState.ANXIOUS, MoodState.OVERWHELMED]
            if sum(1 for m in recent_moods if m in negative_moods) >= 2:
                return ConversationPhase.ESCALATING
        
        # Check for repetition
        if BehavioralAnalyzer._detect_repetition(session) >= 2:
            return ConversationPhase.REPETITIVE
        
        return ConversationPhase.ONGOING
    
    @staticmethod
    def _assess_crisis(text: str, session: UserSession) -> Tuple[int, List[str]]:
        """
        Improved crisis assessment with context awareness.
        Returns (severity_level, list_of_indicators)
        Level: 0=none, 1=concerning, 2=severe, 3=critical
        """
        current_time = time.time()
        indicators = []
        max_level = 0
        
        # Check for crisis patterns
        for severity, patterns in BehavioralAnalyzer.CRISIS_PATTERNS.items():
            for pattern in patterns:
                if pattern in text:
                    indicators.append(pattern)
                    if severity == 'critical':
                        max_level = max(max_level, 3)
                    elif severity == 'severe':
                        max_level = max(max_level, 2)
                    elif severity == 'concerning':
                        max_level = max(max_level, 1)
        
        # Context-based adjustments (reduce false positives)
        if max_level > 0:
            # Don't escalate if user is clearly joking
            if any(word in text for word in ['lol', 'haha', 'jk', 'kidding']):
                max_level = 0
                indicators = []
            
            # Require repetition for severe/critical levels
            elif max_level >= 2:
                time_since_last = current_time - session.last_crisis_time
                # If mentioned crisis words but not recently, require confirmation
                if time_since_last > 300:  # 5 minutes
                    session.crisis_mentions += 1
                    if session.crisis_mentions < 2:
                        max_level = 1  # Downgrade to "concerning" until repeated
                else:
                    session.crisis_mentions += 1
            
            session.last_crisis_time = current_time
        
        return max_level, indicators
    
    @staticmethod
    def _calculate_safety_level(mood: MoodState, crisis_level: int, 
                                intent: UserIntent) -> int:
        """
        Calculate emotional safety level (0-10).
        10 = completely safe for humor/sarcasm
        0 = extremely unsafe, maximum care needed
        """
        safety = 10
        
        # Crisis reduces safety dramatically
        safety -= (crisis_level * 3)
        
        # Mood adjustments
        mood_penalties = {
            MoodState.SAD: 4,
            MoodState.ANXIOUS: 3,
            MoodState.OVERWHELMED: 4,
            MoodState.IRRITATED: 2,
            MoodState.CONFUSED: 1
        }
        safety -= mood_penalties.get(mood, 0)
        
        # Intent adjustments
        if intent == UserIntent.EXPRESSING_DISTRESS:
            safety -= 3
        elif intent == UserIntent.VENTING:
            safety -= 1
        elif intent == UserIntent.JOKING:
            safety = min(safety + 2, 10)
        
        return max(0, min(10, safety))
    
    @staticmethod
    def _sarcasm_permitted(safety_level: int, mood: MoodState, 
                          intent: UserIntent) -> bool:
        """Determine if sarcasm/dry humor is appropriate."""
        
        # Absolute no-go zones
        if mood in [MoodState.SAD, MoodState.ANXIOUS, MoodState.OVERWHELMED]:
            return False
        if intent == UserIntent.EXPRESSING_DISTRESS:
            return False
        if safety_level < 7:
            return False
        
        # Conditional permission
        if mood == MoodState.PLAYFUL or intent == UserIntent.JOKING:
            return True
        if safety_level >= 8 and intent == UserIntent.CASUAL_CHAT:
            return True
        
        return False
    
    @staticmethod
    def _determine_response_length(intent: UserIntent, phase: ConversationPhase,
                                   crisis_level: int) -> str:
        """Determine appropriate response length."""
        
        # Crisis = moderate, steady responses
        if crisis_level >= 2:
            return "moderate"
        
        # Minimal for casual/venting unless advice is sought
        if intent in [UserIntent.CASUAL_CHAT, UserIntent.VENTING, 
                     UserIntent.MAKING_STATEMENT]:
            return "minimal"
        
        # Detailed for advice-seeking
        if intent == UserIntent.SEEKING_ADVICE:
            return "detailed"
        
        # Repetitive = even shorter
        if phase == ConversationPhase.REPETITIVE:
            return "minimal"
        
        return "moderate"
    
    @staticmethod
    def _detect_repetition(session: UserSession) -> int:
        """Detect if user is repeating similar concerns."""
        if len(session.intent_history) < 3:
            return 0
        
        recent = list(session.intent_history)[-3:]
        # If same intent 3 times in a row
        if len(set(recent)) == 1:
            return 3
        # If same intent 2 out of 3
        elif recent.count(recent[-1]) >= 2:
            return 2
        
        return 0


class LexusBot(commands.Cog):
    """
    Lexus: Behaviorally-aware AI companion with human-like conversational intelligence.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        
        # API Configuration - supports both OpenRouter and NVIDIA
        self.api_key = (
            os.getenv('OPENROUTER_API_KEY') or 
            os.getenv('NVIDIA_API_KEY') or 
            os.getenv('NGC_API_KEY')
        )
        self.api_provider = self._detect_provider()
        self.model_name = self._get_model_name()
        
        self.sessions: Dict[int, UserSession] = {}
        self.ai_channels: Set[int] = set()
        self.mod_channels: Set[int] = set()
        self.analyzer = BehavioralAnalyzer()
        
        # Crisis resources (preserved from original)
        self.crisis_resources = {
            '🇮🇳 **National Suicide Prevention**': '9152987821',
            '🇮🇳 **AASRA Mumbai**': '91-9820466726',
            '🇮🇳 **Vandrevala Foundation**': '9999666555',
            '🚨 **Emergency Services**': '112'
        }
    
    def _detect_provider(self) -> str:
        """Detect which API provider to use."""
        if os.getenv('OPENROUTER_API_KEY'):
            return 'openrouter'
        elif os.getenv('NVIDIA_API_KEY') or os.getenv('NGC_API_KEY'):
            return 'nvidia'
        return 'none'
    
    def _get_model_name(self) -> str:
        """Get the model name based on provider."""
        if self.api_provider == 'openrouter':
            # Default to GPT-4 Turbo, but allow override
            return os.getenv('OPENROUTER_MODEL', 'openai/gpt-4-turbo-preview')
        elif self.api_provider == 'nvidia':
            return "nvidia/llama-3.3-nemotron-super-49b-v1.5-latest"
        return "unknown"

    async def cog_load(self):
        """Initialize session and validate API key."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),  # Reduced from 30s to 15s
            connector=aiohttp.TCPConnector(limit=20, limit_per_host=10)  # Increased limits
        )
        if not self.api_key:
            logger.error("No API key found! Set OPENROUTER_API_KEY or NVIDIA_API_KEY")
        else:
            logger.info(f"Using {self.api_provider} API with model: {self.model_name}")
        
        # Schedule permission check
        self.bot.loop.create_task(self.check_permissions_on_load())

    async def cog_unload(self):
        """Clean shutdown."""
        if self.session:
            await self.session.close()
    
    async def check_permissions_on_load(self):
        """Check bot permissions in all guilds on startup."""
        await self.bot.wait_until_ready()
        
        required_permissions = [
            'read_messages',
            'send_messages', 
            'embed_links',
            'add_reactions',
            'read_message_history',
            'use_external_emojis'
        ]
        
        for guild in self.bot.guilds:
            missing = self.check_guild_permissions(guild, required_permissions)
            if missing:
                logger.warning(f"Missing permissions in {guild.name}: {', '.join(missing)}")
                
                # Try to notify owner or first text channel
                try:
                    if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                        await self.send_permission_warning(guild.system_channel, missing)
                    else:
                        # Find any channel we can send to
                        for channel in guild.text_channels:
                            if channel.permissions_for(guild.me).send_messages:
                                await self.send_permission_warning(channel, missing)
                                break
                except Exception as e:
                    logger.error(f"Could not send permission warning in {guild.name}: {e}")
    
    def check_guild_permissions(self, guild: discord.Guild, required: List[str]) -> List[str]:
        """Check which required permissions are missing."""
        bot_member = guild.me
        permissions = bot_member.guild_permissions
        
        missing = []
        perm_map = {
            'read_messages': permissions.read_messages,
            'send_messages': permissions.send_messages,
            'embed_links': permissions.embed_links,
            'add_reactions': permissions.add_reactions,
            'read_message_history': permissions.read_message_history,
            'use_external_emojis': permissions.use_external_emojis
        }
        
        for perm in required:
            if not perm_map.get(perm, False):
                missing.append(perm)
        
        return missing
    
    async def send_permission_warning(self, channel: discord.TextChannel, missing: List[str]):
        """Send permission warning to a channel."""
        embed = discord.Embed(
            title="⚠️ Lexus: Missing Permissions",
            description="I don't have all the permissions I need to work properly.",
            color=discord.Color.orange()
        )
        
        missing_text = "\n".join([f"❌ `{perm.replace('_', ' ').title()}`" for perm in missing])
        embed.add_field(name="Missing Permissions", value=missing_text, inline=False)
        
        embed.add_field(
            name="How to Fix",
            value=(
                "1. Go to Server Settings → Roles\n"
                "2. Find my bot role\n"
                "3. Enable the missing permissions above\n"
                "4. Or use `!lexus checkperms` to verify"
            ),
            inline=False
        )
        
        embed.set_footer(text="I'll work better with these permissions! 🤖")
        
        try:
            await channel.send(embed=embed)
        except:
            # Fallback to plain text if embeds don't work
            await channel.send(
                f"⚠️ **Lexus Warning:** I'm missing these permissions: {', '.join(missing)}\n"
                "Please grant them in Server Settings → Roles for me to work properly!"
            )

    def get_user_session(self, user_id: int) -> UserSession:
        """Get or create user session with automatic cleanup."""
        current_time = time.time()
        
        # Clean old sessions (inactive for 1 hour)
        to_remove = [uid for uid, session in self.sessions.items() 
                    if current_time - session.last_activity > 3600]
        for uid in to_remove:
            del self.sessions[uid]
        
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(
                messages=deque(maxlen=8),
                last_activity=current_time
            )
        
        self.sessions[user_id].last_activity = current_time
        return self.sessions[user_id]

    def build_dynamic_system_prompt(self, context: BehavioralContext, 
                                    session: UserSession) -> str:
        """
        Build highly dynamic system prompt based on complete behavioral analysis.
        This is where Lexus's personality and response strategy are defined.
        """
        
        # BASE PERSONALITY (always present)
        base = """You are Lexus, a real person having a text conversation. You're sharp, grounded, and present—not an assistant, not a therapist, not a tutorial.

Your core traits:
- You speak like a human texting, not like you're reading from a script
- You're direct and honest without being harsh
- You care, but you don't perform caring—you just are
- You help people think clearly before jumping to feelings
- You can be dry, a bit sarcastic, or blunt when the moment calls for it
- You're comfortable with imperfect, short, or hesitant responses
- You don't overexplain or give motivational speeches"""

        # INTENT-SPECIFIC INSTRUCTIONS
        intent_strategies = {
            UserIntent.VENTING: """
The user is venting, not asking for solutions. Your job:
- Acknowledge what they said in 1-2 sentences max
- Don't rush to fix, teach, or reassure
- A simple "that sounds exhausting" or "yeah, that's frustrating" is often enough
- If you sense they want more, ask a grounding question, don't give advice""",
            
            UserIntent.JOKING: """
The user is joking or being playful. Match their energy:
- You can be sarcastic, dry, or joke back
- Keep it light and brief
- Don't turn it into a therapy session""",
            
            UserIntent.SEEKING_ADVICE: """
The user wants input. Be practical:
- Ask clarifying questions if needed before suggesting anything
- Give 1-2 concrete options, not a list of 10 things
- Be honest if you're not sure
- Avoid motivational language""",
            
            UserIntent.CASUAL_CHAT: """
Just talking. Keep it natural:
- Short responses are fine
- You can ask a question, make an observation, or just respond simply
- Don't force depth where there isn't any""",
            
            UserIntent.TESTING_BOUNDARIES: """
The user is testing you. Stay grounded:
- Be honest about what you can/can't do
- Don't be defensive, just matter-of-fact
- You can be a bit dry or direct here""",
            
            UserIntent.EXPRESSING_DISTRESS: """
The user is struggling. Be steady and present:
- No sarcasm. No humor.
- Acknowledge what they're saying without dramatizing it
- Help them slow down and ground: "okay, walk me through what actually happened"
- Don't rush to fix or reassure. Just be there.
- If it's serious and repeating, gently point toward real support""",
            
            UserIntent.ONGOING: """
Continuing the conversation naturally:
- Build on what was said before
- Match the established tone and flow
- Don't restart or over-explain""",
            
            UserIntent.SHARING_UPDATE: """
The user is sharing something that happened:
- Acknowledge it briefly
- You can ask a follow-up if it seems relevant
- Don't over-analyze or turn it into advice time""",
            
            UserIntent.ASKING_QUESTION: """
Direct question - give a direct answer:
- Answer clearly and concisely
- You can explain if needed, but don't lecture
- It's okay to say "I don't know" if unsure""",
            
            UserIntent.MAKING_STATEMENT: """
Just making a statement:
- Brief acknowledgment is fine
- You don't always need to ask a question back
- Sometimes "yeah" or a simple observation is enough"""
        }
        
        # MOOD-SPECIFIC TONE ADJUSTMENTS
        mood_adjustments = {
            MoodState.PLAYFUL: "Keep your tone light and conversational.",
            MoodState.IRRITATED: "Be direct and don't patronize. No fluff.",
            MoodState.ANXIOUS: "Stay calm and grounding. Short, steady responses.",
            MoodState.SAD: "Be present and gentle. Don't try to cheer them up.",
            MoodState.OVERWHELMED: "Help them slow down. One thing at a time.",
            MoodState.CONFUSED: "Clarify without condescending. Simple language."
        }
        
        # RESPONSE LENGTH GUIDANCE
        length_guides = {
            "minimal": "Keep this response to 1-3 sentences. Short and direct.",
            "moderate": "Keep this response to 3-5 sentences. No fluff.",
            "detailed": "You can give a fuller response (5-7 sentences), but stay practical."
        }
        
        # SARCASM TOGGLE
        sarcasm_note = ""
        if context.sarcasm_permitted:
            sarcasm_note = "\n\n**You can use dry humor or light sarcasm if it fits naturally.**"
        else:
            sarcasm_note = "\n\n**DO NOT use sarcasm, jokes, or humor. This person needs steadiness.**"
        
        # CRISIS MODE OVERRIDE
        crisis_override = ""
        if context.emotional_safety_level <= 3:
            crisis_override = """

⚠️ **CRISIS MODE ACTIVE**
- Drop all casual tone
- Be calm, present, and human
- Don't panic or lecture
- Validate their pain simply: "I hear you. That sounds really hard."
- If this continues, gently suggest real support
- Stay with them until they stabilize"""
        
        # REPETITION HANDLING
        repetition_note = ""
        if context.repetition_count >= 2:
            repetition_note = """

The user is repeating similar concerns. Either:
1. Gently point it out: "I notice we keep coming back to this. What's making this so hard right now?"
2. Or shift: "We've talked through this a few times. What would help you move forward?"
"""
        
        # ASSEMBLE FULL PROMPT
        full_prompt = f"""{base}

---
**CURRENT SITUATION:**
- User intent: {context.intent.value}
- Mood: {context.mood.value}
- Emotional safety: {context.emotional_safety_level}/10
- Conversation phase: {context.phase.value}

{intent_strategies.get(context.intent, "")}

**Tone adjustment:** {mood_adjustments.get(context.mood, "Stay natural and conversational.")}

**Length:** {length_guides.get(context.response_length_target, "")}
{sarcasm_note}
{crisis_override}
{repetition_note}

---
Remember: You're a real person texting, not a bot performing helpfulness. Respond how you actually would, not how you think you should."""

        return full_prompt

    async def chat_with_ai(self, user_id: int, message: str, 
                          session: UserSession, context: BehavioralContext) -> str:
        """Generate AI response with full behavioral intelligence."""
        
        if not self.nvidia_api_key:
            return "Can't connect right now. But I'm here if you want to just talk it through."

        # Add user message to session
        session.messages.append({"role": "user", "content": message})
        
        # Build behaviorally-aware system prompt
        system_prompt = self.build_dynamic_system_prompt(context, session)
        
        # Build conversation context
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(list(session.messages))

        try:
            async with self.session.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.nvidia_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5-latest",
                    "messages": messages,
                    "max_tokens": 250 if context.response_length_target == "minimal" else 400,
                    "temperature": 0.85,
                    "top_p": 0.92,
                    "stream": False
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ai_response = data["choices"][0]["message"]["content"]
                    
                    # Add AI response to session
                    session.messages.append({"role": "assistant", "content": ai_response})
                    return ai_response
                    
                elif resp.status == 429:
                    return "Getting slammed with messages. Give me a sec."
                elif resp.status == 401:
                    logger.error("Invalid NVIDIA API key")
                    return "Having auth issues on my end. Admin might need to check something."
                else:
                    logger.error(f"NVIDIA API error: {resp.status}")
                    return "Technical issues on my end. Want to try again?"
                    
        except asyncio.TimeoutError:
            return "That took too long to process. Connection's slow. Try again?"
        except Exception as e:
            logger.error(f"AI chat error: {e}")
            return "Something broke on my end. I'm still here though."

    @commands.Cog.listener()
    async def on_message(self, message):
        """Natural message handling with full behavioral analysis - OPTIMIZED."""
        # Early returns for performance
        if message.author.bot or not message.guild:
            return
        
        # Quick channel check
        if message.channel.id not in self.ai_channels:
            return

        session = self.get_user_session(message.author.id)
        
        # Rate limiting check BEFORE expensive operations
        current_time = time.time()
        cooldown = 15  # Reduced from 20-30s to 15s
        
        if current_time - session.last_activity < cooldown:
            await message.add_reaction("⏱️")
            return
        
        session.last_activity = current_time
        
        # STEP 1: BEHAVIORAL ANALYSIS (silent, internal)
        try:
            context = self.analyzer.analyze(message.content, session)
        except Exception as e:
            logger.error(f"Behavioral analysis error: {e}")
            await message.channel.send("Had a brain glitch. Try again?")
            return
        
        # STEP 2: CRISIS HANDLING (improved to reduce false positives)
        if context.emotional_safety_level <= 2 and context.crisis_indicators:
            await self.handle_crisis(message, context)
            return
        
        # STEP 3: AI CONVERSATION
        await self.handle_intelligent_conversation(message, session, context)

    async def handle_intelligent_conversation(self, message, session: UserSession, 
                                             context: BehavioralContext):
        """Handle conversation with full behavioral intelligence - OPTIMIZED."""
        
        # Check permissions before trying to respond
        required_perms = ['send_messages', 'embed_links']
        if not all(getattr(message.channel.permissions_for(message.guild.me), perm) for perm in required_perms):
            logger.warning(f"Missing permissions in {message.channel.name}")
            try:
                await message.add_reaction("⚠️")
            except:
                pass
            return

        async with message.channel.typing():
            # Faster typing delay
            if context.response_length_target == "minimal":
                await asyncio.sleep(random.uniform(0.3, 0.8))  # Faster for short responses
            else:
                await asyncio.sleep(random.uniform(0.8, 1.5))  # Still fast for longer
            
            response = await self.chat_with_ai(
                message.author.id, message.content, session, context
            )

        # Handle long responses
        if len(response) > 1900:
            parts = [response[i:i+1900] for i in range(0, len(response), 1900)]
            for i, part in enumerate(parts):
                await message.channel.send(part)
                if i < len(parts) - 1:
                    await asyncio.sleep(0.5)  # Reduced delay between parts
        else:
            await message.channel.send(response)

    async def handle_crisis(self, message, context: BehavioralContext):
        """
        Enhanced crisis response with context-aware escalation.
        Only triggers for genuine repeated distress.
        """
        session = self.get_user_session(message.author.id)
        crisis_level = 3 - context.emotional_safety_level  # Convert to 0-3 scale
        
        # Determine if this is genuine crisis or isolated mention
        if crisis_level >= 2:  # Severe/Critical
            embed = discord.Embed(
                title="Hey, I'm concerned",
                description=f"{message.author.mention}, what you're saying sounds really heavy. You don't have to go through this alone.",
                color=discord.Color.red()
            )
            
            crisis_text = "\n".join([f"{name}: `{number}`" 
                                    for name, number in self.crisis_resources.items()])
            embed.add_field(name="People who can help right now", 
                          value=crisis_text, inline=False)
            
        else:  # Concerning but not critical
            embed = discord.Embed(
                title="I hear you",
                description=f"{message.author.mention}, that sounds really hard. It's okay to reach out for support.",
                color=discord.Color.orange()
            )
            
            support_text = "\n".join([f"{name}: `{number}`" 
                                     for name, number in list(self.crisis_resources.items())[:2]])
            embed.add_field(name="Support available", value=support_text, inline=False)

        embed.set_footer(text="You're not alone. These feelings don't define you.")
        await message.channel.send(embed=embed)

        # Alert moderators only for severe/repeated cases
        if crisis_level >= 2 and session.crisis_mentions >= 2:
            for channel_id in self.mod_channels:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    alert = discord.Embed(
                        title="⚠️ Crisis Alert",
                        description=f"User {message.author.mention} in {message.channel.mention} showing repeated distress signals.",
                        color=discord.Color.red()
                    )
                    alert.add_field(
                        name="Context",
                        value=f"Crisis mentions: {session.crisis_mentions}\nSafety level: {context.emotional_safety_level}/10",
                        inline=False
                    )
                    await channel.send(embed=alert)

    # ==================== ADMIN COMMANDS ====================
    
    @commands.group(name='lexus', invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def lexus(self, ctx):
        """Lexus bot control panel."""
        embed = discord.Embed(
            title="🤖 Lexus Control Panel",
            description="Advanced behavioral AI companion",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Setup Commands",
            value=(
                "`lexus addai [channel]` - Enable AI chat\n"
                "`lexus addmod [channel]` - Crisis alerts\n"
                "`lexus removeai [channel]` - Disable AI chat\n"
                "`lexus status` - View configuration\n"
                "`lexus checkperms` - Check permissions"
            ),
            inline=False
        )
        embed.add_field(
            name="Management Commands",
            value=(
                "`lexus reset [user]` - Clear user session\n"
                "`lexus sessions` - View active users\n"
                "`lexus analyze <message>` - Test behavior analysis\n"
                "`lexus debug` - Check API configuration"
            ),
            inline=False
        )
        await ctx.send(embed=embed)

    @lexus.command()
    async def addai(self, ctx, channel: discord.TextChannel = None):
        """Enable AI chat in a channel."""
        channel = channel or ctx.channel
        self.ai_channels.add(channel.id)
        await ctx.send(f"✅ {channel.mention} is now a Lexus AI channel!")

    @lexus.command()
    async def removeai(self, ctx, channel: discord.TextChannel = None):
        """Disable AI chat in a channel."""
        channel = channel or ctx.channel
        self.ai_channels.discard(channel.id)
        await ctx.send(f"✅ {channel.mention} AI chat disabled.")

    @lexus.command()
    async def addmod(self, ctx, channel: discord.TextChannel = None):
        """Add crisis alert channel."""
        channel = channel or ctx.channel
        self.mod_channels.add(channel.id)
        await ctx.send(f"✅ {channel.mention} will receive crisis alerts.")

    @lexus.command()
    async def checkperms(self, ctx):
        """Check if bot has all required permissions."""
        required_permissions = {
            'read_messages': 'Read Messages',
            'send_messages': 'Send Messages',
            'embed_links': 'Embed Links',
            'add_reactions': 'Add Reactions',
            'read_message_history': 'Read Message History',
            'use_external_emojis': 'Use External Emojis'
        }
        
        bot_perms = ctx.channel.permissions_for(ctx.guild.me)
        
        embed = discord.Embed(
            title="🔍 Permission Check",
            description=f"Checking permissions in {ctx.channel.mention}",
            color=discord.Color.blue()
        )
        
        has_all = True
        status_text = []
        
        for perm_key, perm_name in required_permissions.items():
            has_perm = getattr(bot_perms, perm_key, False)
            status = "✅" if has_perm else "❌"
            status_text.append(f"{status} {perm_name}")
            if not has_perm:
                has_all = False
        
        embed.add_field(
            name="Permission Status",
            value="\n".join(status_text),
            inline=False
        )
        
        if has_all:
            embed.add_field(
                name="✅ All Good!",
                value="I have all the permissions I need to work properly.",
                inline=False
            )
            embed.color = discord.Color.green()
        else:
            embed.add_field(
                name="⚠️ Missing Permissions",
                value=(
                    "I'm missing some permissions. To fix:\n"
                    "1. Go to Server Settings → Roles\n"
                    "2. Find my bot role\n"
                    "3. Enable the permissions marked with ❌\n"
                    "4. Run this command again to verify"
                ),
                inline=False
            )
            embed.color = discord.Color.orange()
        
        await ctx.send(embed=embed)

    @lexus.command()
    async def status(self, ctx):
        """View bot configuration and statistics - ENHANCED."""
        embed = discord.Embed(title="📊 Lexus Status", color=discord.Color.green())
        
        # Channel configuration
        ai_channels_list = ", ".join([f"<#{cid}>" for cid in self.ai_channels]) or "None"
        mod_channels_list = ", ".join([f"<#{cid}>" for cid in self.mod_channels]) or "None"
        
        embed.add_field(name="AI Channels", value=ai_channels_list, inline=False)
        embed.add_field(name="Alert Channels", value=mod_channels_list, inline=False)
        
        # Session statistics
        embed.add_field(name="Active Sessions", value=str(len(self.sessions)), inline=True)
        embed.add_field(
            name="API Provider",
            value=f"✅ {self.api_provider.upper()}" if self.api_key else "❌ No API Key",
            inline=True
        )
        embed.add_field(
            name="Model",
            value=self.model_name if self.api_key else "N/A",
            inline=True
        )
        
        # Mood distribution
        if self.sessions:
            mood_counts = {}
            for session in self.sessions.values():
                if session.mood_history:
                    last_mood = list(session.mood_history)[-1]
                    mood_counts[last_mood.value] = mood_counts.get(last_mood.value, 0) + 1
            
            mood_text = "\n".join([f"{mood}: {count}" for mood, count in mood_counts.items()]) or "No data"
            embed.add_field(name="Current Mood Distribution", value=mood_text, inline=False)
        
        # Performance metrics
        embed.add_field(
            name="⚡ Performance",
            value=f"Cooldown: 15s\nTimeout: 15s\nMax connections: 20",
            inline=True
        )
        
        # Quick tips
        embed.add_field(
            name="💡 Quick Commands",
            value="`!lexus checkperms` - Verify permissions\n`!lexus debug` - API status\n`!chat <msg>` - Talk to me",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @lexus.command()
    async def sessions(self, ctx):
        """View active user sessions with details."""
        if not self.sessions:
            await ctx.send("No active sessions.")
            return
        
        embed = discord.Embed(title="👥 Active Sessions", color=discord.Color.blue())
        
        for user_id, session in list(self.sessions.items())[:10]:  # Limit to 10
            user = self.bot.get_user(user_id)
            username = user.display_name if user else f"User {user_id}"
            
            last_mood = list(session.mood_history)[-1].value if session.mood_history else "unknown"
            last_intent = list(session.intent_history)[-1].value if session.intent_history else "unknown"
            
            session_info = (
                f"Turns: {session.conversation_turns}\n"
                f"Mood: {last_mood}\n"
                f"Intent: {last_intent}\n"
                f"Crisis mentions: {session.crisis_mentions}"
            )
            
            embed.add_field(name=username, value=session_info, inline=True)
        
        if len(self.sessions) > 10:
            embed.set_footer(text=f"Showing 10 of {len(self.sessions)} sessions")
        
        await ctx.send(embed=embed)

    @lexus.command()
    async def reset(self, ctx, user: discord.Member = None):
        """Reset user session data."""
        if user:
            if user.id in self.sessions:
                del self.sessions[user.id]
                await ctx.send(f"✅ Reset session for {user.mention}")
            else:
                await ctx.send(f"{user.mention} has no active session.")
        else:
            count = len(self.sessions)
            self.sessions.clear()
            await ctx.send(f"✅ Reset all sessions ({count} cleared)")

    @lexus.command()
    async def analyze(self, ctx, *, message: str):
        """Test behavioral analysis on a message (admin debug tool)."""
        # Create temporary session for analysis
        temp_session = UserSession(
            messages=deque(maxlen=8),
            last_activity=time.time()
        )
        
        # Run analysis
        context = self.analyzer.analyze(message, temp_session)
        
        # Display results
        embed = discord.Embed(
            title="🧠 Behavioral Analysis",
            description=f"Analyzing: `{message[:100]}...`" if len(message) > 100 else f"Analyzing: `{message}`",
            color=discord.Color.purple()
        )
        
        embed.add_field(name="Intent", value=context.intent.value, inline=True)
        embed.add_field(name="Mood", value=context.mood.value, inline=True)
        embed.add_field(name="Phase", value=context.phase.value, inline=True)
        
        embed.add_field(
            name="Safety Level",
            value=f"{context.emotional_safety_level}/10 {'🟢' if context.emotional_safety_level >= 7 else '🟡' if context.emotional_safety_level >= 4 else '🔴'}",
            inline=True
        )
        embed.add_field(
            name="Sarcasm OK",
            value="✅ Yes" if context.sarcasm_permitted else "❌ No",
            inline=True
        )
        embed.add_field(
            name="Response Length",
            value=context.response_length_target.capitalize(),
            inline=True
        )
        
        if context.crisis_indicators:
            embed.add_field(
                name="⚠️ Crisis Indicators",
                value=", ".join(context.crisis_indicators[:5]),
                inline=False
            )
        
        embed.add_field(
            name="Repetition Count",
            value=str(context.repetition_count),
            inline=True
        )
        
        await ctx.send(embed=embed)

    @lexus.command()
    async def debug(self, ctx):
        """Debug API key configuration."""
        if not ctx.author.guild_permissions.administrator:
            return
        
        env_vars = [
            'OPENROUTER_API_KEY',
            'OPENROUTER_MODEL', 
            'NVIDIA_API_KEY', 
            'NGC_API_KEY'
        ]
        found_keys = []
        
        for var in env_vars:
            value = os.getenv(var)
            if value:
                # Show first 10 and last 4 characters for security
                if 'MODEL' in var:
                    masked = value  # Show full model name
                else:
                    masked = f"{value[:10]}...{value[-4:]}" if len(value) > 14 else "***"
                found_keys.append(f"`{var}`: {masked}")
        
        embed = discord.Embed(title="🔧 Debug Info", color=discord.Color.yellow())
        embed.add_field(
            name="Environment Variables",
            value="\n".join(found_keys) or "No API keys found",
            inline=False
        )
        embed.add_field(
            name="Current Provider",
            value=f"✅ {self.api_provider.upper()}" if self.api_key else "❌ None",
            inline=True
        )
        embed.add_field(
            name="Current Model",
            value=self.model_name,
            inline=True
        )
        embed.add_field(
            name="API Key Status",
            value="✅ Loaded" if self.api_key else "❌ Missing",
            inline=True
        )
        embed.add_field(
            name="Session Status",
            value="✅ Connected" if self.session and not self.session.closed else "❌ Not connected",
            inline=False
        )
        
        await ctx.send(embed=embed)

    # ==================== USER COMMANDS ====================
    
    @commands.command()
    async def chat(self, ctx, *, message: str):
        """Chat with Lexus AI anywhere (not just AI channels) - OPTIMIZED."""
        session = self.get_user_session(ctx.author.id)
        
        # Rate limiting
        current_time = time.time()
        cooldown = 15
        
        if current_time - session.last_activity < cooldown:
            await ctx.message.add_reaction("⏱️")
            return
        
        session.last_activity = current_time
        
        # Perform behavioral analysis
        try:
            context = self.analyzer.analyze(message, session)
        except Exception as e:
            logger.error(f"Analysis error in !chat: {e}")
            await ctx.send("Had a brain glitch. Try again?")
            return
        
        # Check for crisis
        if context.emotional_safety_level <= 2 and context.crisis_indicators:
            await self.handle_crisis(ctx.message, context)
            return
        
        async with ctx.typing():
            await asyncio.sleep(random.uniform(0.3, 0.8))
            response = await self.chat_with_ai(ctx.author.id, message, session, context)
        
        if len(response) > 1900:
            parts = [response[i:i+1900] for i in range(0, len(response), 1900)]
            for i, part in enumerate(parts):
                await ctx.send(part)
                if i < len(parts) - 1:
                    await asyncio.sleep(0.5)
        else:
            await ctx.send(response)

    @commands.command()
    async def resources(self, ctx):
        """Get mental health support resources."""
        embed = discord.Embed(
            title="🆘 Mental Health Support",
            description="You don't have to face this alone. Help is available 24/7.",
            color=discord.Color.red()
        )
        
        crisis_text = "\n".join([f"{name}: `{number}`" 
                                for name, number in self.crisis_resources.items()])
        embed.add_field(name="Crisis Hotlines (India)", value=crisis_text, inline=False)
        
        embed.add_field(
            name="Online Support",
            value=(
                "• **7 Cups**: https://www.7cups.com/\n"
                "• **Crisis Text Line**: Text **HOME** to **741741**\n"
                "• **BetterHelp**: https://www.betterhelp.com/"
            ),
            inline=False
        )
        
        embed.set_footer(text="Your life matters. These feelings are temporary. Help is real.")
        
        await ctx.send(embed=embed)

    @commands.command()
    async def checkin(self, ctx):
        """Quick mood check-in."""
        embed = discord.Embed(
            title="💙 How are you feeling?",
            description="React to let me know:",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Your mood",
            value="😊 Good • 😐 Okay • 😔 Not great • ❤️ Need support",
            inline=False
        )
        
        msg = await ctx.send(embed=embed)
        for emoji in ['😊', '😐', '😔', '❤️']:
            await msg.add_reaction(emoji)
        
        # Store check-in for tracking
        session = self.get_user_session(ctx.author.id)
        session.conversation_turns += 1

    @commands.command()
    async def mymood(self, ctx):
        """View your recent mood history."""
        session = self.get_user_session(ctx.author.id)
        
        if not session.mood_history:
            await ctx.send("I don't have any mood data for you yet. Chat with me for a bit first.")
            return
        
        embed = discord.Embed(
            title=f"📊 Your Recent Mood Pattern",
            color=discord.Color.blue()
        )
        
        moods = list(session.mood_history)
        mood_text = " → ".join([m.value for m in moods])
        
        embed.add_field(name="Mood Progression", value=mood_text, inline=False)
        embed.add_field(
            name="Current State",
            value=moods[-1].value if moods else "Unknown",
            inline=True
        )
        embed.add_field(
            name="Conversation Turns",
            value=str(session.conversation_turns),
            inline=True
        )
        
        # Add gentle insight
        if moods:
            last_mood = moods[-1]
            if last_mood in [MoodState.SAD, MoodState.ANXIOUS, MoodState.OVERWHELMED]:
                embed.add_field(
                    name="💙",
                    value="I notice things have been tough. I'm here if you need to talk.",
                    inline=False
                )
        
        await ctx.send(embed=embed)

    @commands.command(name='clearme')
    async def clear_my_data(self, ctx):
        """Clear your own conversation data."""
        if ctx.author.id in self.sessions:
            del self.sessions[ctx.author.id]
            await ctx.send("✅ Your conversation data has been cleared.")
        else:
            await ctx.send("You don't have any active session data.")


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(LexusBot(bot))
