from asyncio import sleep as asleep, gather
from pyrogram.filters import command, private, user
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified
from anitopy import parse
import re
import urllib.parse

from bot import bot, bot_loop, Var, ani_cache
from bot.core.database import db
from bot.core.func_utils import decode, is_fsubbed, get_fsubs, editMessage, sendMessage, new_task, convertTime, getfeed
from bot.core.auto_animes import get_animes
from bot.core.reporter import rep

@bot.on_message(command('start') & private)
@new_task
async def start_msg(client, message):
    uid = message.from_user.id
    from_user = message.from_user
    txtargs = message.text.split()
    temp = await sendMessage(message, "<i>Connecting..</i>")
    if not await is_fsubbed(uid):
        txt, btns = await get_fsubs(uid, txtargs)
        return await editMessage(temp, txt, InlineKeyboardMarkup(btns))
    if len(txtargs) <= 1:
        await temp.delete()
        btns = []
        for elem in Var.START_BUTTONS.split():
            try:
                bt, link = elem.split('|', maxsplit=1)
            except:
                continue
            if len(btns) != 0 and len(btns[-1]) == 1:
                btns[-1].insert(1, InlineKeyboardButton(bt, url=link))
            else:
                btns.append([InlineKeyboardButton(bt, url=link)])
        smsg = Var.START_MSG.format(first_name=from_user.first_name,
                                    last_name=from_user.first_name,
                                    mention=from_user.mention, 
                                    user_id=from_user.id)
        if Var.START_PHOTO:
            await message.reply_photo(
                photo=Var.START_PHOTO, 
                caption=smsg,
                reply_markup=InlineKeyboardMarkup(btns) if len(btns) != 0 else None
            )
        else:
            await sendMessage(message, smsg, InlineKeyboardMarkup(btns) if len(btns) != 0 else None)
        return
    try:
        arg = (await decode(txtargs[1])).split('-')
    except Exception as e:
        await rep.report(f"User : {uid} | Error : {str(e)}", "error")
        await editMessage(temp, "<b>Input Link Code Decode Failed !</b>")
        return
    if len(arg) == 2 and arg[0] == 'get':
        try:
            fid = int(int(arg[1]) / abs(int(Var.FILE_STORE)))
        except Exception as e:
            await rep.report(f"User : {uid} | Error : {str(e)}", "error")
            await editMessage(temp, "<b>Input Link Code is Invalid !</b>")
            return
        try:
            msg = await client.get_messages(Var.FILE_STORE, message_ids=fid)
            if msg.empty:
                return await editMessage(temp, "<b>File Not Found !</b>")
            nmsg = await msg.copy(message.chat.id, reply_markup=None)
            await temp.delete()
            if Var.AUTO_DEL:
                async def auto_del(msg, timer):
                    await asleep(timer)
                    await msg.delete()
                await sendMessage(message, f'<i>File will be Auto Deleted in {convertTime(Var.DEL_TIMER)}, Forward to Saved Messages Now..</i>')
                bot_loop.create_task(auto_del(nmsg, Var.DEL_TIMER))
        except Exception as e:
            await rep.report(f"User : {uid} | Error : {str(e)}", "error")
            await editMessage(temp, "<b>File Not Found !</b>")
    else:
        await editMessage(temp, "<b>Input Link is Invalid for Usage !</b>")
    
@bot.on_message(command('pause') & private & user(Var.ADMINS))
async def pause_fetch(client, message):
    ani_cache['fetch_animes'] = False
    await sendMessage(message, "`Successfully Paused Fetching Animes...`")

@bot.on_message(command('resume') & private & user(Var.ADMINS))
async def resume_fetch(client, message):
    ani_cache['fetch_animes'] = True
    await sendMessage(message, "`Successfully Resumed Fetching Animes...`")

@bot.on_message(command('log') & private & user(Var.ADMINS))
@new_task
async def _log(client, message):
    await message.reply_document("log.txt", quote=True)

@bot.on_message(command('addlink') & private & user(Var.ADMINS))
@new_task
async def add_link(client, message):
    if len(args := message.text.split()) <= 1:
        return await sendMessage(message, "<b>No Link Found to Add</b>")
    
    Var.RSS_ITEMS.append(args[1])
    await sendMessage(message, f"`Global Link Added Successfully!`\n\n    • **All Link(s) :** {', '.join(Var.RSS_ITEMS)}")

@bot.on_message(command('addtask') & private & user(Var.ADMINS))
@new_task
async def add_task(client, message):
    if len(args := message.text.split()) <= 1:
        return await sendMessage(message, "<b>No Task Found to Add</b>")
    
    index = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0
    if not (taskInfo := await getfeed(args[1], index)):
        return await sendMessage(message, "<b>No Task Found to Add for the Provided Link</b>")
    
    ani_task = bot_loop.create_task(get_animes(taskInfo.title, taskInfo.link, True))
    await sendMessage(message, f"<i><b>Task Added Successfully!</b></i>\n\n    • <b>Task Name :</b> {taskInfo.title}\n    • <b>Task Link :</b> {args[1]}")

@bot.on_message(command('addmagnet') & private & user(Var.ADMINS))
@new_task
async def add_magnet(client, message):
    """Add magnet link for processing"""
    args = message.text.split(maxsplit=1)
    
    if len(args) <= 1:
        return await sendMessage(message, "<b>❌ No Magnet Link Found!</b>\n\n<i>Usage:</i> <code>/addmagnet magnet:?xt=urn:btih:...</code>")
    
    magnet_link = args[1].strip()
    
    # Validate magnet link format
    if not magnet_link.startswith("magnet:?"):
        return await sendMessage(message, "<b>❌ Invalid Magnet Link!</b>\n\n<i>Please provide a valid magnet link starting with 'magnet:?'</i>")
    
    # Extract anime name from magnet link
    try:
        # Try to extract display name from magnet link
        anime_name = extract_anime_name_from_magnet(magnet_link)
        if not anime_name:
            return await sendMessage(message, "<b>❌ Could not extract anime name from magnet link!</b>\n\n<i>Please check if the magnet link contains proper anime information.</i>")
        
        # Parse anime info using anitopy
        parsed_info = parse(anime_name)
        anime_title = parsed_info.get('anime_title', anime_name)
        episode_number = parsed_info.get('episode_number', 'Unknown')
        
        # Send confirmation message
        confirmation_msg = f"""<b>✅ Magnet Task Added!</b>

<b>🔸 Name:</b> <code>{anime_title}</code>
<b>🔸 Episode:</b> <code>{episode_number}</code>
<b>🔸 Magnet:</b> <code>{magnet_link[:50]}...</code>

<i>🚀 Processing started in background...</i>"""
        
        await sendMessage(message, confirmation_msg)
        
        # Start processing the anime
        bot_loop.create_task(get_animes(anime_name, magnet_link, True))
        
        # Log the action
        await rep.report(f"Magnet Task Added by Admin: {anime_title}", "info")
        
    except Exception as e:
        await rep.report(f"Error processing magnet link: {str(e)}", "error")
        await sendMessage(message, f"<b>❌ Error Processing Magnet Link!</b>\n\n<i>Error: {str(e)}</i>")

def extract_anime_name_from_magnet(magnet_link):
    """Extract anime name from magnet link"""
    try:
        # Try to extract from display name (dn parameter)
        dn_match = re.search(r'dn=([^&]+)', magnet_link)
        if dn_match:
            # URL decode the display name
            anime_name = urllib.parse.unquote_plus(dn_match.group(1))
            return anime_name
        
        # If no display name, try to extract from the magnet link structure
        # This is a fallback method
        if 'xt=urn:btih:' in magnet_link:
            # Extract potential name from trackers or other parameters
            tr_match = re.search(r'tr=([^&]+)', magnet_link)
            if tr_match:
                tracker_info = urllib.parse.unquote_plus(tr_match.group(1))
                # This is very basic - in practice, you might need more sophisticated parsing
                return "Unknown Anime"
        
        return None
        
    except Exception as e:
        return None

@bot.on_message(command('help') & private & user(Var.ADMINS))
@new_task
async def help_command(client, message):
    """Show available admin commands"""
    help_text = """<b>🤖 Admin Commands</b>

<b>📺 Anime Management:</b>
• <code>/addmagnet [magnet_link]</code> - Add magnet link for processing
• <code>/addtask [rss_link] [index]</code> - Add RSS task
• <code>/addlink [rss_link]</code> - Add RSS link globally

<b>🔧 Bot Control:</b>
• <code>/pause</code> - Pause anime fetching
• <code>/resume</code> - Resume anime fetching
• <code>/restart</code> - Restart the bot
• <code>/log</code> - Get bot log file

<b>ℹ️ Information:</b>
• <code>/help</code> - Show this help message
• <code>/start</code> - Start the bot

<i>✨ All commands are admin-only and work in private chat only.</i>"""
    
    await sendMessage(message, help_text)
