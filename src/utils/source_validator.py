import re
import logging
from typing import Dict, Any
from telethon import errors
from telethon.tl.types import Channel, Chat, User
from telethon import TelegramClient

logger = logging.getLogger(__name__)


def validate_source_format(source: str) -> Dict[str, Any]:
    """Validate source format before making API calls"""
    source = source.strip()
    
    if not source:
        return {
            "valid_format": False,
            "error": "Empty source"
        }
    
    # Username format (@channelname or channelname)
    # Telegram usernames: 5-32 characters, start with letter, can contain letters, digits, underscores
    # Must not end with underscore
    username_pattern = r'^@?[a-zA-Z][a-zA-Z0-9_]{3,30}[a-zA-Z0-9]$'
    
    # Telegram link formats for public channels
    telegram_link_patterns = [
        r'^https?://t\.me/[a-zA-Z][a-zA-Z0-9_]{3,30}[a-zA-Z0-9]$',
        r'^https?://telegram\.me/[a-zA-Z][a-zA-Z0-9_]{3,30}[a-zA-Z0-9]$',
        r'^https?://telegram\.dog/[a-zA-Z][a-zA-Z0-9_]{3,30}[a-zA-Z0-9]$'
    ]
    
    if re.match(username_pattern, source):
        return {
            "valid_format": True,
            "type": "username",
            "normalized": source if source.startswith('@') else f'@{source}'
        }
    
    for pattern in telegram_link_patterns:
        if re.match(pattern, source):
            username = source.split('/')[-1]
            return {
                "valid_format": True,
                "type": "public_link",
                "normalized": f'@{username}'
            }
    
    if source.startswith('https://t.me/joinchat/') or source.startswith('https://telegram.me/joinchat/'):
        return {
            "valid_format": False,
            "error": "Private channel invite links are not supported. Only public channels are allowed."
        }
    
    if source.startswith('https://t.me/+') or source.startswith('https://telegram.me/+'):
        return {
            "valid_format": False,
            "error": "Private channel invite links are not supported. Only public channels are allowed."
        }
    
    if source.isdigit() or (source.startswith('-') and source[1:].isdigit()):
        return {
            "valid_format": False,
            "error": "Numeric IDs are not supported. Please use channel username or public link."
        }
    
    return {
        "valid_format": False,
        "error": "Invalid format. Use @channelname, channelname, or https://t.me/channelname"
    }


async def validate_telegram_channel(client: TelegramClient, source: str) -> Dict[str, Any]:
    """Validate that the source is an accessible public channel"""
    
    try:
        entity = await client.get_entity(source)
        
        if not isinstance(entity, Channel):
            if isinstance(entity, Chat):
                return {
                    "valid": False,
                    "error": "Groups and chats are not supported. Only public channels are allowed."
                }
            elif isinstance(entity, User):
                return {
                    "valid": False,
                    "error": "Users are not supported. Only public channels are allowed."
                }
            else:
                return {
                    "valid": False,
                    "error": f"Unsupported entity type. Only public channels are allowed."
                }
        
        if not entity.username:
            return {
                "valid": False,
                "error": "Private channels are not supported. Only public channels with usernames are allowed."
            }
        
        if hasattr(entity, 'restricted') and entity.restricted:
            return {
                "valid": False,
                "error": f"The channel '{entity.title}' is restricted and cannot be monitored."
            }
        
        if not (hasattr(entity, 'broadcast') and entity.broadcast):
            return {
                "valid": False,
                "error": f"'{entity.title}' is not a broadcast channel. Only broadcast channels are supported."
            }
        
        return {
            "valid": True,
            "id": entity.id,
            "title": entity.title,
            "username": entity.username,
            "type": "channel",
            "verified": getattr(entity, 'verified', False),
            "participants_count": getattr(entity, 'participants_count', None)
        }
        
    except errors.UsernameInvalidError:
        return {
            "valid": False,
            "error": "Invalid username format. Check the spelling and try again."
        }
    except errors.UsernameNotOccupiedError:
        return {
            "valid": False,
            "error": "This username doesn't exist on Telegram."
        }
    except errors.FloodWaitError as e:
        return {
            "valid": False,
            "error": f"Rate limited. Please try again in {e.seconds} seconds."
        }
    except ValueError as e:
        if "Could not find the input entity" in str(e):
            return {
                "valid": False,
                "error": "Channel not found. Make sure the username is correct and the channel is public."
            }
        return {
            "valid": False,
            "error": f"Channel resolution failed: {str(e)}"
        }
    except Exception as e:
        logger.exception(f"Unexpected error validating channel {source}: {e}")
        return {
            "valid": False,
            "error": f"Validation failed: {str(e)}"
        }


async def validate_sources_batch(client: TelegramClient, sources_text: str) -> Dict[str, Any]:
    """Validate multiple sources separated by newlines"""
    
    if not sources_text or not sources_text.strip():
        return {
            "valid": False,
            "error": "No sources provided"
        }
    
    raw_sources = [line.strip() for line in sources_text.strip().split('\n')]
    sources = [source for source in raw_sources if source]
    
    if not sources:
        return {
            "valid": False,
            "error": "No valid sources found"
        }
    
    if len(sources) > 10:
        return {
            "valid": False,
            "error": "Too many sources at once. Please add maximum 10 sources per request."
        }
    
    valid_sources = []
    invalid_sources = []
    validation_errors = []
    
    for i, source in enumerate(sources, 1):
        format_result = validate_source_format(source)
        if not format_result["valid_format"]:
            invalid_sources.append(source)
            validation_errors.append(f"Source {i} (`{source}`): {format_result['error']}")
            continue
        
        normalized_source = format_result["normalized"]
        channel_result = await validate_telegram_channel(client, normalized_source)
        
        if channel_result["valid"]:
            valid_sources.append({
                "original": source,
                "normalized": normalized_source,
                "title": channel_result["title"],
                "username": channel_result["username"],
                "verified": channel_result["verified"]
            })
        else:
            invalid_sources.append(source)
            validation_errors.append(f"Source {i} (`{source}`): {channel_result['error']}")
    
    return {
        "valid": len(valid_sources) > 0,
        "valid_sources": valid_sources,
        "invalid_sources": invalid_sources,
        "errors": validation_errors,
        "total_sources": len(sources),
        "valid_count": len(valid_sources),
        "invalid_count": len(invalid_sources)
    }


def format_validation_result(result: Dict[str, Any]) -> str:
    """Format validation result for user display"""
    
    if not result["valid"]:
        if "error" in result:
            return f"❌ {result['error']}"
        else:
            error_text = "❌ *Validation Failed*\n\n"
            for error in result["errors"]:
                error_text += f"• {error}\n"
            return error_text
    
    if result["valid_count"] == result["total_sources"]:
        success_text = f"✅ *All {result['valid_count']} sources validated successfully!*\n\n"
        for source in result["valid_sources"]:
            verified_badge = "✓" if source["verified"] else ""
            success_text += f"📡 **{source['title']}** {verified_badge}\n"
            success_text += f"   └ `@{source['username']}`\n\n"
    else:
        success_text = f"⚠️ *Validation Results: {result['valid_count']}/{result['total_sources']} sources valid*\n\n"
        
        if result["valid_sources"]:
            success_text += "✅ **Valid sources:**\n"
            for source in result["valid_sources"]:
                verified_badge = "✓" if source["verified"] else ""
                success_text += f"📡 **{source['title']}** {verified_badge}\n"
                success_text += f"   └ `@{source['username']}`\n\n"
        
        if result["errors"]:
            success_text += "❌ **Invalid sources:**\n"
            for error in result["errors"]:
                success_text += f"• {error}\n"
    
    return success_text