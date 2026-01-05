# Collab.land Clone - Discord Bot

A Discord bot that verifies EVM wallet ownership and assigns roles based on NFT collections, similar to Collab.land functionality.

## Features

- 🔐 **Private Wallet Verification**: Users interact via ephemeral (private) messages - only visible to them
- 🎨 **NFT-Based Role Assignment**: Automatically assigns roles based on NFT ownership
- 📝 **Modal Interface**: Clean popup dialogue for wallet input
- ⚙️ **Configurable**: Easy-to-edit config file for contracts and roles

## Setup

### 1. Prerequisites

- Python 3.8 or higher
- A Discord Bot Token
- A Polygon RPC endpoint (Infura, Alchemy, or public RPC)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Discord Bot

Edit `discord_config.json` and add your Discord bot token and RPC URL:

```json
{
  "bot_token": "YOUR_DISCORD_BOT_TOKEN_HERE",
  "verification_channel": "wallet-verify",
  "polygon_rpc_url": "https://polygon-rpc.com"
}
```

**Getting a Discord Bot Token:**
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section and create a bot
4. Copy the token and paste it in `discord_config.json` (replace `YOUR_DISCORD_BOT_TOKEN_HERE`)
5. Enable "Message Content Intent" and "Server Members Intent" in the Bot settings

**Getting a Polygon RPC URL:**
- [Alchemy](https://www.alchemy.com/) - Free tier available (use Polygon network)
- [Infura](https://www.infura.io/) - Free tier available (use Polygon network)
- Public RPC: `https://polygon-rpc.com` (may be rate-limited)

**Configuration Fields:**
- `bot_token`: Your Discord bot token (⚠️ Keep this secret! `discord_config.json` is in `.gitignore`)
- `verification_channel`: Channel name where verification happens (partial match)
- `polygon_rpc_url`: Polygon RPC endpoint URL

### 4. Configure Contracts and Roles

Edit `contracts.json` to add your NFT contracts and corresponding Discord roles:

```json
{
  "contracts": [
    {
      "address": "0x37f4223afd9fca6c6fb24afc8f6ced87de48209e",
      "name": "OLA Collection",
      "role_name": "OLA LV1"
    }
  ]
}
```

**Configuration Fields:**
- `address`: The NFT contract address (ERC721) on Polygon
- `name`: Display name for the collection
- `role_id`: Discord role ID (optional, can use role_name instead)
- `role_name`: Discord role name (optional, can use role_id instead)

You can add multiple contracts to verify different NFT collections:
```json
{
  "contracts": [
    {
      "address": "0x37f4223afd9fca6c6fb24afc8f6ced87de48209e",
      "name": "OLA Collection",
      "role_name": "OLA LV1"
    },
    {
      "address": "0xANOTHER_CONTRACT_ADDRESS",
      "name": "Another Collection",
      "role_name": "Another Role"
    }
  ]
}
```

### 5. Create Verification Channel

Create a channel named `wallet-verify` (or match the name in your `discord_config.json`)

### 6. Create Roles

Create the roles you want to assign (e.g., "OLA LV1") and make sure the bot's role is higher in the hierarchy than the roles it needs to assign.

### 7. Invite Bot to Server

1. In Discord Developer Portal, go to "OAuth2" > "URL Generator"
2. Select scopes: `bot` and `applications.commands`
3. Select bot permissions:
   - Manage Roles
   - Send Messages
   - Use Slash Commands
   - Read Message History
4. Copy the generated URL and open it in your browser
5. Select your server and authorize

### 8. Run the Bot

```bash
python bot.py
```

## Usage

### For Users

1. Go to the `#wallet-verify` channel
2. Type any message or use `/verify` command
3. Click the "Verify Wallet" button (or modal will appear automatically)
4. Enter your EVM wallet address (0x...)
5. Bot will verify NFT ownership and assign roles automatically

**Note**: All interactions are private (ephemeral) - only you can see your verification process.

### For Administrators

- Edit `config.json` to add/remove contracts and roles
- Restart the bot after changing config.json
- The bot will automatically check NFT ownership when users verify

## How It Works

1. User interacts in the verification channel
2. Bot shows a modal (popup) for wallet input
3. Bot validates the wallet address format
4. Bot checks NFT ownership for each configured contract
5. Bot assigns corresponding roles if NFTs are found
6. All messages are ephemeral (only visible to the user)

## Troubleshooting

**Bot doesn't assign roles:**
- Check that bot's role is higher than the roles it needs to assign
- Verify bot has "Manage Roles" permission
- Check that role IDs/names in config.json are correct

**NFT verification fails:**
- Verify the contract address is correct
- Ensure the contract is ERC721 compatible
- Check your RPC endpoint is working
- Verify the wallet address is correct

**Bot doesn't respond:**
- Check bot token is correct in `.env`
- Verify bot is online in Discord
- Check bot has necessary intents enabled
- Ensure bot has permission to send messages in the channel

## License

MIT
