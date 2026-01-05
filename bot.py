import discord
from discord import app_commands
from discord.ext import commands
import json
from web3 import Web3
import asyncio
import sys
import platform
import aiohttp
from typing import Optional, Dict, List

# Fix for Windows event loop issue
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Load Discord bot configuration
with open('discord_config.json', 'r') as f:
    discord_config = json.load(f)

# Load contracts and roles configuration
with open('contracts.json', 'r') as f:
    contracts_config = json.load(f)

# Load wallet-to-Discord associations
WALLET_LINKS_FILE = 'wallet_links.json'
try:
    with open(WALLET_LINKS_FILE, 'r') as f:
        wallet_links = json.load(f)
except FileNotFoundError:
    wallet_links = {"discord_to_wallet": {}, "wallet_to_discord": {}}

def save_wallet_links():
    """Save wallet links to file"""
    with open(WALLET_LINKS_FILE, 'w') as f:
        json.dump(wallet_links, f, indent=2)

# Load wallet-to-Discord associations
WALLET_LINKS_FILE = 'wallet_links.json'
try:
    with open(WALLET_LINKS_FILE, 'r') as f:
        wallet_links = json.load(f)
except FileNotFoundError:
    wallet_links = {"discord_to_wallet": {}, "wallet_to_discord": {}}

def save_wallet_links():
    """Save wallet links to file"""
    with open(WALLET_LINKS_FILE, 'w') as f:
        json.dump(wallet_links, f, indent=2)

# Initialize Discord bot
intents = discord.Intents.default()
# Privileged intents - must be enabled in Discord Developer Portal
intents.message_content = True  # Required for reading message content
intents.members = True  # Required for role assignment
bot = commands.Bot(command_prefix='!', intents=intents)

# Polygon RPC endpoint from config
POLYGON_RPC_URL = discord_config.get('polygon_rpc_url', 'https://polygon-rpc.com')
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC_URL))

# ERC1155 ABI for balanceOf and uri
ERC1155_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_id", "type": "uint256"}
        ],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_id", "type": "uint256"}],
        "name": "uri",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]


class WalletModal(discord.ui.Modal, title='Wallet Verification'):
    """Modal for wallet address input"""
    wallet_address = discord.ui.TextInput(
        label='EVM Wallet Address',
        placeholder='0x...',
        required=True,
        max_length=42,
        min_length=42
    )

    async def on_submit(self, interaction: discord.Interaction):
        wallet = self.wallet_address.value.strip()
        
        # Validate wallet address format
        if not wallet.startswith('0x') or len(wallet) != 42:
            await interaction.response.send_message(
                '❌ Invalid wallet address format. Please provide a valid EVM address (0x...).',
                ephemeral=True
            )
            return
        
        # Check if address is valid
        if not w3.is_address(wallet):
            await interaction.response.send_message(
                '❌ Invalid wallet address. Please check and try again.',
                ephemeral=True
            )
            return
        
        # Normalize wallet address (checksum)
        wallet = Web3.to_checksum_address(wallet)
        
        # Check if wallet is already linked to another Discord account
        user_id = str(interaction.user.id)
        wallet_lower = wallet.lower()
        
        if wallet_lower in wallet_links.get("wallet_to_discord", {}):
            linked_user_id = wallet_links["wallet_to_discord"][wallet_lower]
            if linked_user_id != user_id:
                await interaction.response.send_message(
                    '❌ This wallet is already linked to another Discord account. Each wallet can only be linked to one Discord account for security.',
                    ephemeral=True
                )
                return
        
        # Check if user already has a different wallet linked
        if user_id in wallet_links.get("discord_to_wallet", {}):
            existing_wallet = wallet_links["discord_to_wallet"][user_id]
            if existing_wallet.lower() != wallet_lower:
                await interaction.response.send_message(
                    f'❌ You already have a wallet linked: `{existing_wallet}`\n\n'
                    'If you want to change your linked wallet, please contact an administrator.',
                    ephemeral=True
                )
                return
        
        # Show processing message
        await interaction.response.send_message(
            '⏳ Verifying NFT ownership... This may take a few seconds.',
            ephemeral=True
        )
        
        # Ensure we have a guild (should always be present for server interactions)
        if interaction.guild is None:
            await interaction.followup.send(
                '❌ This command can only be used in a server, not in DMs.',
                ephemeral=True
            )
            return
        
        # Verify NFT ownership
        roles_assigned = await verify_and_assign_roles(interaction.user, wallet, interaction.guild)
        
        if roles_assigned:
            # Link wallet to Discord account (one-time permanent link)
            wallet_links.setdefault("discord_to_wallet", {})[user_id] = wallet
            wallet_links.setdefault("wallet_to_discord", {})[wallet_lower] = user_id
            save_wallet_links()
            print(f"Linked wallet {wallet[:10]}... to Discord user {interaction.user.name} ({user_id})")
            
            role_names = [role.name for role in roles_assigned]
            await interaction.followup.send(
                f'✅ Successfully verified! Assigned roles: {", ".join(role_names)}\n\n'
                f'🔒 Your wallet `{wallet[:6]}...{wallet[-4:]}` is now permanently linked to your Discord account.',
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                '❌ No matching NFTs found. You do not own any NFTs from the configured collections.',
                ephemeral=True
            )


async def get_nft_metadata(contract_address: str, token_id: int, session: aiohttp.ClientSession) -> Optional[Dict]:
    """Fetch NFT metadata from token URI (async)"""
    try:
        contract_address = Web3.to_checksum_address(contract_address)
        contract = w3.eth.contract(address=contract_address, abi=ERC1155_ABI)
        
        # Get token URI (ERC1155 uri function takes token_id) - run in thread to avoid blocking
        uri = await asyncio.to_thread(contract.functions.uri(token_id).call)
        
        # Handle URI templates with {id} placeholder (ERC1155 standard)
        if '{id}' in uri:
            # Convert token_id to hex with leading zeros (64 characters)
            token_id_hex = hex(token_id)[2:].zfill(64)
            uri = uri.replace('{id}', token_id_hex)
        elif '{tokenId}' in uri:
            uri = uri.replace('{tokenId}', str(token_id))
        
        # Handle IPFS and HTTP URIs
        if uri.startswith('ipfs://'):
            uri = uri.replace('ipfs://', 'https://ipfs.io/ipfs/')
        elif uri.startswith('ipfs/'):
            uri = f'https://ipfs.io/ipfs/{uri[5:]}'
        
        # Fetch metadata asynchronously
        async with session.get(uri, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                return await response.json()
        return None
    except Exception as e:
        # Silently fail for individual tokens to avoid spam
        return None


async def check_token_ownership(wallet_address: str, contract_address: str, token_id: int, contract) -> bool:
    """Check if user owns a specific token (async)"""
    try:
        balance = await asyncio.to_thread(contract.functions.balanceOf(wallet_address, token_id).call)
        return balance > 0
    except:
        return False


async def get_user_achievements(wallet_address: str, contract_address: str, max_tokens: int = 100, token_ids: Optional[List[int]] = None) -> List[Dict]:
    """Get all NFTs owned by user and their achievement levels (optimized with parallel processing)"""
    achievements = []
    try:
        wallet_address = Web3.to_checksum_address(wallet_address)
        contract_address = Web3.to_checksum_address(contract_address)
        contract = w3.eth.contract(address=contract_address, abi=ERC1155_ABI)
        
        # Use specific token IDs if provided, otherwise check range
        if token_ids:
            tokens_to_check = token_ids
            print(f"Checking {len(tokens_to_check)} specific tokens for wallet {wallet_address[:10]}...")
        else:
            tokens_to_check = list(range(max_tokens))
            print(f"Checking tokens 0-{max_tokens} for wallet {wallet_address[:10]}...")
        
        # Create async HTTP session for metadata fetching
        async with aiohttp.ClientSession() as session:
            # Process tokens in batches for parallel checking
            batch_size = 20  # Smaller batches since we're checking fewer tokens
            owned_tokens = []
            
            # First pass: Find all owned tokens (parallel batch checking)
            for batch_start in range(0, len(tokens_to_check), batch_size):
                batch_end = min(batch_start + batch_size, len(tokens_to_check))
                batch_token_ids = tokens_to_check[batch_start:batch_end]
                
                batch_tasks = [
                    check_token_ownership(wallet_address, contract_address, token_id, contract)
                    for token_id in batch_token_ids
                ]
                
                # Check ownership for batch in parallel
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                # Collect owned token IDs
                for token_id, is_owned in zip(batch_token_ids, batch_results):
                    if is_owned and not isinstance(is_owned, Exception):
                        owned_tokens.append(token_id)
                
                # Small delay to avoid overwhelming RPC
                await asyncio.sleep(0.05)
            
            print(f"Found {len(owned_tokens)} owned tokens, fetching metadata...")
            
            # Second pass: Fetch metadata for owned tokens (parallel, limited concurrency)
            semaphore = asyncio.Semaphore(10)  # Limit to 10 concurrent metadata fetches
            
            async def fetch_metadata_with_semaphore(token_id: int):
                async with semaphore:
                    return await get_nft_metadata(contract_address, token_id, session)
            
            # Fetch metadata for all owned tokens in parallel
            metadata_tasks = [fetch_metadata_with_semaphore(token_id) for token_id in owned_tokens]
            metadata_results = await asyncio.gather(*metadata_tasks, return_exceptions=True)
            
            # Process metadata and extract achievements
            for token_id, metadata in zip(owned_tokens, metadata_results):
                if isinstance(metadata, Exception) or not metadata:
                    continue
                
                # Check for ACHIEVEMENT in attributes or direct field
                achievement = None
                
                # Check direct field (case-insensitive)
                metadata_lower = {k.lower(): v for k, v in metadata.items() if isinstance(k, str)}
                if 'achievement' in metadata_lower:
                    achievement = metadata_lower['achievement']
                elif 'achievement' in metadata:
                    achievement = metadata['achievement']
                elif 'ACHIEVEMENT' in metadata:
                    achievement = metadata['ACHIEVEMENT']
                # Check in attributes array
                elif 'attributes' in metadata:
                    for attr in metadata['attributes']:
                        if isinstance(attr, dict):
                            trait_type = attr.get('trait_type', '').upper()
                            if trait_type == 'ACHIEVEMENT':
                                achievement = attr.get('value')
                                break
                
                if achievement:
                    print(f"Found achievement '{achievement}' for token {token_id}")
                    achievements.append({
                        'token_id': token_id,
                        'achievement': achievement,
                        'metadata': metadata
                    })
        
        return achievements
    except Exception as e:
        print(f"Error getting user achievements: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_level_from_achievement(achievement: str) -> Optional[int]:
    """Extract level number from achievement string"""
    # Handle different formats: "Level 1", "Level1", "1", etc.
    achievement = str(achievement).strip()
    
    # Extract number from achievement string
    import re
    numbers = re.findall(r'\d+', achievement)
    if numbers:
        level = int(numbers[0])
        if 1 <= level <= 16:
            return level
    
    return None


def get_role_name_from_level(level: int) -> str:
    """Map level number to Discord role name"""
    return f"OLA LV{level}"


async def verify_and_assign_roles(user: discord.Member, wallet_address: str, guild: Optional[discord.Guild]) -> list:
    """Verify NFT ownership and assign only the highest level role, removing lower level roles"""
    roles_assigned = []
    
    # Safety check - ensure guild is not None
    if guild is None:
        print("Error: Guild is None, cannot assign roles")
        return roles_assigned
    
    for contract_config in contracts_config['contracts']:
        contract_address = contract_config['address']
        contract_name = contract_config.get('name', 'NFT Collection')
        max_tokens = contract_config.get('max_tokens', 100)
        token_ids = contract_config.get('token_ids')  # Optional: specific token IDs to check
        
        # Get user's achievements from this contract
        achievements = await get_user_achievements(wallet_address, contract_address, max_tokens, token_ids)
        
        if achievements:
            # Get all achievement levels
            levels = []
            for achievement_data in achievements:
                achievement = achievement_data.get('achievement')
                if achievement:
                    level = get_level_from_achievement(achievement)
                    if level:
                        levels.append(level)
            
            if levels:
                # Find the highest level
                highest_level = max(levels)
                highest_role_name = get_role_name_from_level(highest_level)
                
                # Get all OLA LV roles (1-16) that the user currently has
                ola_roles_to_remove = []
                for level in range(1, 17):
                    role_name = get_role_name_from_level(level)
                    role = discord.utils.get(guild.roles, name=role_name)
                    if role and role in user.roles:
                        ola_roles_to_remove.append(role)
                
                # Remove all existing OLA LV roles
                if ola_roles_to_remove:
                    try:
                        await user.remove_roles(
                            *ola_roles_to_remove,
                            reason=f"Removing lower level roles, assigning {highest_role_name}"
                        )
                        print(f"Removed {len(ola_roles_to_remove)} lower level role(s) from {user.name}")
                    except discord.Forbidden:
                        print(f"Bot doesn't have permission to remove roles")
                    except Exception as e:
                        print(f"Error removing roles: {e}")
                
                # Assign only the highest level role
                highest_role = discord.utils.get(guild.roles, name=highest_role_name)
                if highest_role:
                    try:
                        await user.add_roles(
                            highest_role,
                            reason=f"Verified NFT achievement from {contract_name} - Level {highest_level}"
                        )
                        roles_assigned.append(highest_role)
                        print(f"Assigned role {highest_role_name} to {user.name}")
                    except discord.Forbidden:
                        print(f"Bot doesn't have permission to assign role: {highest_role_name}")
                    except Exception as e:
                        print(f"Error assigning role {highest_role_name}: {e}")
                else:
                    print(f"Role '{highest_role_name}' not found in server. Please create it first.")
    
    return roles_assigned


async def create_verification_message(guild: discord.Guild):
    """Create and pin the verification message in the wallet-verify channel"""
    verification_channel_name = discord_config.get('verification_channel', 'wallet-verify').lower()
    
    # Find the verification channel
    channel = None
    for ch in guild.text_channels:
        if verification_channel_name in ch.name.lower():
            channel = ch
            break
    
    if not channel:
        print(f'⚠️  Verification channel "{verification_channel_name}" not found in {guild.name}')
        return
    
    # Check if there's already a pinned message from the bot
    try:
        pinned_messages = await channel.pins()
        for msg in pinned_messages:
            if msg.author == bot.user and msg.embeds:
                # Update existing message
                embed = discord.Embed(
                    title="🔐 Wallet Verification",
                    description="Click the button below to verify your wallet and get NFT-based roles.\n\n**All verification is private - only you can see it!**",
                    color=0x5865F2
                )
                embed.add_field(
                    name="How it works",
                    value="1. Click the Verify button\n2. Enter your EVM wallet address\n3. Get your role automatically",
                    inline=False
                )
                
                view = discord.ui.View()
                button = discord.ui.Button(label="Verify Wallet", style=discord.ButtonStyle.primary, emoji="🔐")
                
                async def button_callback(interaction: discord.Interaction):
                    await interaction.response.send_modal(WalletModal())
                
                button.callback = button_callback
                view.add_item(button)
                
                await msg.edit(embed=embed, view=view)
                print(f'✅ Updated verification message in {channel.name} ({guild.name})')
                return
    except Exception as e:
        print(f'Error checking pinned messages: {e}')
    
    # Create new message
    embed = discord.Embed(
        title="🔐 Wallet Verification",
        description="Click the button below to verify your wallet and get NFT-based roles.\n\n**All verification is private - only you can see it!**",
        color=0x5865F2
    )
    embed.add_field(
        name="How it works",
        value="1. Click the Verify button\n2. Enter your EVM wallet address\n3. Get your role automatically",
        inline=False
    )
    
    view = discord.ui.View()
    button = discord.ui.Button(label="Verify Wallet", style=discord.ButtonStyle.primary, emoji="🔐")
    
    async def button_callback(interaction: discord.Interaction):
        await interaction.response.send_modal(WalletModal())
    
    button.callback = button_callback
    view.add_item(button)
    
    try:
        message = await channel.send(embed=embed, view=view)
        await message.pin()
        print(f'✅ Created and pinned verification message in {channel.name} ({guild.name})')
    except discord.Forbidden:
        print(f'❌ No permission to send/pin messages in {channel.name} ({guild.name})')
    except Exception as e:
        print(f'❌ Error creating verification message: {e}')


@bot.event
async def on_ready():
    print(f'{bot.user} has logged in!')
    print(f'Bot ID: {bot.user.id}')
    print(f'Connected to {len(bot.guilds)} server(s)')
    
    # Sync commands to all guilds (instant, instead of waiting for global sync)
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            print(f'✅ Synced commands to guild: {guild.name} (ID: {guild.id})')
        except Exception as e:
            print(f'⚠️  Failed to sync to {guild.name}: {e}')
        
        # Create verification message in each guild
        await create_verification_message(guild)
    
    # Also sync globally (can take up to 1 hour)
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synced {len(synced)} global command(s)')
        for cmd in synced:
            print(f'   - /{cmd.name}')
    except Exception as e:
        print(f'⚠️  Global sync failed (this is okay if guild sync worked): {e}')


@bot.tree.command(name="unlink-wallet", description="[Admin] Unlink a wallet from a Discord account")
@app_commands.describe(user="The Discord user to unlink")
async def unlink_wallet_command(interaction: discord.Interaction, user: discord.Member):
    """Admin command to unlink a wallet from a Discord account"""
    # Check if user has admin permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            '❌ You need administrator permissions to use this command.',
            ephemeral=True
        )
        return
    
    user_id = str(user.id)
    
    # Remove wallet link if exists
    if user_id in wallet_links.get("discord_to_wallet", {}):
        wallet = wallet_links["discord_to_wallet"][user_id]
        wallet_lower = wallet.lower()
        
        # Remove from both mappings
        del wallet_links["discord_to_wallet"][user_id]
        if wallet_lower in wallet_links.get("wallet_to_discord", {}):
            del wallet_links["wallet_to_discord"][wallet_lower]
        
        save_wallet_links()
        
        await interaction.response.send_message(
            f'✅ Unlinked wallet `{wallet[:6]}...{wallet[-4:]}` from {user.mention}',
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f'❌ {user.mention} does not have a wallet linked.',
            ephemeral=True
        )


@bot.tree.command(name="verify", description="Verify your wallet and get NFT-based roles")
async def verify_command(interaction: discord.Interaction):
    """Slash command to start wallet verification"""
    print(f"Verify command called by {interaction.user} in {interaction.channel.name}")
    
    # Check if command is used in the verification channel
    channel_name = interaction.channel.name.lower()
    verification_channel = discord_config.get('verification_channel', 'wallet-verify').lower()
    
    if verification_channel not in channel_name:
        await interaction.response.send_message(
            f'❌ Please use this command in the #{discord_config.get("verification_channel", "wallet-verify")} channel.',
            ephemeral=True
        )
        return
    
    # Show the modal
    try:
        await interaction.response.send_modal(WalletModal())
        print(f"Modal sent to {interaction.user}")
    except Exception as e:
        print(f"Error sending modal: {e}")
        await interaction.response.send_message(
            "❌ An error occurred. Please try again.",
            ephemeral=True
        )

if __name__ == '__main__':
    token = discord_config.get('bot_token')
    if not token or token == 'YOUR_DISCORD_BOT_TOKEN_HERE':
        print("Error: Discord bot token not found in discord_config.json!")
        print("Please edit discord_config.json and add your Discord bot token.")
    else:
        try:
            bot.run(token)
        except discord.errors.PrivilegedIntentsRequired as e:
            print("\n" + "="*60)
            print("ERROR: Privileged Intents Required!")
            print("="*60)
            print("\nPlease enable the following in Discord Developer Portal:")
            print("1. Go to: https://discord.com/developers/applications")
            print("2. Select your application (Client ID: 1452733157701976106)")
            print("3. Go to 'Bot' section")
            print("4. Scroll to 'Privileged Gateway Intents'")
            print("5. Enable:")
            print("   ✅ MESSAGE CONTENT INTENT")
            print("   ✅ SERVER MEMBERS INTENT")
            print("6. Save changes and restart the bot")
            print("\n" + "="*60)
            sys.exit(1)

