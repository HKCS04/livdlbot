import asyncio
import os
import re
import time
import traceback
from io import BytesIO
import logging

import aiohttp
import pyrogram
import requests
import yt_dlp
from PIL import Image
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                            InlineKeyboardMarkup, Message, InputMediaVideo)
from pyrogram.types import InputMediaPhoto
from pyrogram.types import Message as MSG
from yt_dlp import YoutubeDL

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

OWNER_ID = "8083702486"
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
CUSTOM_THUMBNAILS = {}
CUSTOM_CAPTIONS = {}

# YTDLP Configuration
YTDL_OPTS = {
    'format': 'bestvideo+bestaudio/best',  # Default: MKV or MP4
    'outtmpl': '%(title)s-%(id)s.%(ext)s',  # Filename format
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'quiet': True,
    'no_warnings': True,
    'source_address': '0.0.0.0',  # Bind to ipv4 since ipv6 addresses cause issues sometimes
    'progress_hooks': [],
}

# Progress bar symbols
BAR = [
    "▰",
    "▱",
]

def create_progress_bar(current, total):
    """Creates a fancy progress bar."""
    percentage = current / total
    filled_segments = int(percentage * 10)
    remaining_segments = 10 - filled_segments
    bar = BAR[0] * filled_segments + BAR[1] * remaining_segments
    return bar, percentage * 100

async def download_progress(current, total, message: MSG, start_time, file_name):
    """Displays download progress bar in Telegram."""
    now = time.time()
    diff = now - start_time
    if round(diff % 3) == 0:  # Update every 3 seconds
        bar, percentage = create_progress_bar(current, total)
        speed = current / diff
        eta = (total - current) / speed
        time_elapsed = time.strftime("%H:%M:%S", time.gmtime(diff))
        estimated_time = time.strftime("%H:%M:%S", time.gmtime(eta))

        try:
            await message.edit(
                text=f"**Downloading:** `{file_name}`\n"
                     f"**Progress:** `[{bar}] {percentage:.2f}%`\n"
                     f"**Speed:** `{speed / 1024:.2f} KB/s`\n"
                     f"**ETA:** `{estimated_time}`\n"
                     f"**Time Elapsed:** `{time_elapsed}`"
            )
        except MessageNotModified:
            pass
        except FloodWait as e:
            await asyncio.sleep(e.value)


async def upload_progress(current, total, message: MSG, start_time, file_name):
    """Displays upload progress bar in Telegram."""
    now = time.time()
    diff = now - start_time
    if round(diff % 3) == 0:  # Update every 3 seconds
        bar, percentage = create_progress_bar(current, total)
        speed = current / diff
        eta = (total - current) / speed
        time_elapsed = time.strftime("%H:%M:%S", time.gmtime(diff))
        estimated_time = time.strftime("%H:%M:%S", time.gmtime(eta))

        try:
            await message.edit(
                text=f"**Uploading:** `{file_name}`\n"
                     f"**Progress:** `[{bar}] {percentage:.2f}%`\n"
                     f"**Speed:** `{speed / 1024:.2f} KB/s`\n"
                     f"**ETA:** `{estimated_time}`\n"
                     f"**Time Elapsed:** `{time_elapsed}`"
            )
        except MessageNotModified:
            pass
        except FloodWait as e:
            await asyncio.sleep(e.value)


@Client.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handles the /start command."""
    await message.reply_text(
        "Hi! I'm a Stream downloader and uploader bot.\n"
        "Send me a M3U8, MPD, or HTTP link, and I'll download the video and upload it to Telegram.\n\n"
        "You can specify a start time using the format: `link | start_time` (e.g., `https://example.com/stream.m3u8 | 00:01:30`)\n\n"
        "**Commands:**\n"
        "/start - Start the bot\n"
        "/set_thumbnail - Set a custom thumbnail\n"
        "/set_caption - Set a custom caption\n"
        "/reset_thumbnail - Reset to default thumbnail\n"
        "/reset_caption - Reset to default caption\n"
    )


@Client.on_message(filters.command("set_thumbnail"))
async def set_thumbnail(client: Client, message: Message):
    """Handles the /set_thumbnail command."""
    if message.reply_to_message and message.reply_to_message.photo:
        photo = await message.reply_to_message.download()
        CUSTOM_THUMBNAILS[message.from_user.id] = photo
        await message.reply_text("Custom thumbnail set!")
    else:
        await message.reply_text("Reply to a photo to set it as the thumbnail.")


@Client.on_message(filters.command("set_caption"))
async def set_caption(client: Client, message: Message):
    """Handles the /set_caption command."""
    caption = message.text.split(" ", 1)[1] if len(message.text.split(" ", 1)) > 1 else None
    if caption:
        CUSTOM_CAPTIONS[message.from_user.id] = caption
        await message.reply_text("Custom caption set!")
    else:
        await message.reply_text("Provide a caption after the command. Example: /set_caption My custom caption")


@Client.on_message(filters.command("reset_thumbnail"))
async def reset_thumbnail(client: Client, message: Message):
    """Handles the /reset_thumbnail command."""
    if message.from_user.id in CUSTOM_THUMBNAILS:
        del CUSTOM_THUMBNAILS[message.from_user.id]
        await message.reply_text("Custom thumbnail reset to default.")
    else:
        await message.reply_text("You don't have a custom thumbnail set.")


@Client.on_message(filters.command("reset_caption"))
async def reset_caption(client: Client, message: Message):
    """Handles the /reset_caption command."""
    if message.from_user.id in CUSTOM_CAPTIONS:
        del CUSTOM_CAPTIONS[message.from_user.id]
        await message.reply_text("Custom caption reset to default.")
    else:
        await message.reply_text("You don't have a custom caption set.")

async def download_and_upload(client: Client, message: Message, link: str):
    """Downloads a video and uploads it to Telegram, handling M3U8, MPD, and HTTP links with custom timestamp."""
    user_id = message.from_user.id
    start_time_str = None  # Initialize start_time_str
    if "|" in link:
        link, start_time_str = link.split("|", 1)  # Split link and timestamp
        link = link.strip()
        start_time_str = start_time_str.strip()

        # Validate the timestamp format (HH:MM:SS or MM:SS or SS)
        if not re.match(r"^(\d{2}:)?\d{2}:\d{2}$|^\d{2}:\d{2}$|^\d+$", start_time_str):
            await message.reply_text("Invalid timestamp format. Please use HH:MM:SS, MM:SS, or seconds.")
            return

    # Modify yt-dlp options for MKV format and progress reporting
    YTDL_OPTS['format'] = 'bestvideo+bestaudio/best'
    YTDL_OPTS['progress_hooks'] = [lambda d: download_progress_hook(d, message, time.time())]

    if start_time_str:
        YTDL_OPTS['ss'] = start_time_str  # Set the start time

    temp_file_path = None

    try:
        with YoutubeDL(YTDL_OPTS) as ydl:
            info_dict = ydl.extract_info(link, download=False)
            file_name = info_dict.get('title', 'Stream') + "." + info_dict.get('ext', 'mp4')  # Default to mp4
            file_name = re.sub(r'[^\w\s.-]', '', file_name)
            file_name = file_name[:60]

            # Check file size before downloading (estimate)
            if 'filesize' in info_dict and info_dict['filesize'] > MAX_FILE_SIZE:
                await message.reply_text(f"Estimated file size exceeds the maximum allowed size of 4GB. Estimated file size: {info_dict['filesize'] / (1024 * 1024 * 1024):.2f} GB")
                return

            download_message = await message.reply_text(f"Starting download of `{file_name}`...")
            start_time = time.time()
            temp_file_path = os.path.join("./downloads", file_name)

            # Now download the file
            ydl.download([link])

            if not os.path.exists(temp_file_path):
                await download_message.edit_text("Download failed. Please check the link and try again.")
                return

            # Upload to Telegram
            upload_message = await message.reply_text(f"Starting upload of `{file_name}`...")
            start_time = time.time()

            try:
                thumb = CUSTOM_THUMBNAILS.get(user_id)

                # If user has no custom thumbnail set, try to automatically extract a thumbnail
                if not thumb:
                     try:
                         ydl_opts = {'writesubtitles': False, 'writethumbnail': True, 'quiet': True, 'no_warnings': True}
                         with YoutubeDL(ydl_opts) as ydl:
                             info_dict = ydl.extract_info(temp_file_path, download=False)
                             if 'thumbnail' in info_dict:
                                 thumb = info_dict['thumbnail']
                                 if thumb.startswith('http'):
                                     async with aiohttp.ClientSession() as session:
                                         async with session.get(thumb) as resp:
                                             if resp.status == 200:
                                                 thumb = BytesIO(await resp.read())
                                                 print("Successfully downloaded thumbnail from URL.")
                                             else:
                                                 print(f"Failed to download thumbnail from URL: {resp.status}")
                                                 thumb = None
                             else:
                                print("No thumbnail found using yt-dlp.")
                                thumb = None

                     except Exception as e:
                        print(f"Error extracting thumbnail: {e}")
                        thumb = None

                # Default caption
                caption = CUSTOM_CAPTIONS.get(user_id, f"Uploaded by @{app.me.username}")

                # Get video duration for proper display in Telegram.  This is important
                duration = 0 # Set Default
                try:
                    ydl_opts = {'quiet': True, 'no_warnings': True}
                    with YoutubeDL(ydl_opts) as ydl:
                       info_dict = ydl.extract_info(temp_file_path, download=False)
                       duration = info_dict.get('duration', 0)
                except Exception as e:
                    print(f"Failed to get video duration: {e}")


                await Client.send_video(
                    chat_id=message.chat.id,
                    video=temp_file_path,
                    caption=caption,
                    supports_streaming=True,
                    thumb=thumb,
                    duration=duration, # Pass duration
                    progress=upload_progress,
                    progress_args=(upload_message, start_time, file_name)
                )

                await upload_message.delete()
                await message.reply_text("Upload complete!")

            except Exception as e:
                await message.reply_text(f"Upload failed: {e}\n\n{traceback.format_exc()}")
                logging.error(f"Upload error: {e}\n{traceback.format_exc()}")

    except yt_dlp.utils.DownloadError as e:
       await message.reply_text(f"Download failed: {e}")
       logging.error(f"yt-dlp download error: {e}")
    except Exception as e:
        await message.reply_text(f"An unexpected error occurred: {e}\n\n{traceback.format_exc()}")
        logging.error(f"General error: {e}\n{traceback.format_exc()}")

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                print(f"Failed to delete temporary file: {e}")
                logging.warning(f"Failed to delete temporary file: {e}")
        YTDL_OPTS['progress_hooks'] = []
        if 'ss' in YTDL_OPTS:
            del YTDL_OPTS['ss']  # Remove start time after download

def download_progress_hook(d, message: MSG, start_time):
    """yt-dlp progress hook to display download progress."""
    if d['status'] == 'downloading':
        current = d['downloaded_bytes']
        total = d['total_bytes']
        file_name = d['filename']
        asyncio.create_task(download_progress(current, total, message, start_time, file_name))
    elif d['status'] == 'finished':
        logging.info("Download complete.")
        pass
    elif d['status'] == 'error':
        logging.error(f"Download failed: {d['error']}")

@Client.on_message(filters.regex(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+"))
async def link_handler(client: Client, message: Message):
    """Handles messages containing links with optional timestamp."""
    link = message.text.strip()
    await download_and_upload(client, message, link)
