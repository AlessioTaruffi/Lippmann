import os
import asyncio
from time import time
import scraper
import discord
from discord.ext import commands
from dotenv import load_dotenv
from discord.ext import tasks

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

#Initial setup of the bot with intents 
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

sitesToScrape = [
    "https://www.dragoonmilitaria.com/shop.php",
    "https://www.imcsmilitaria.com/shop.php",
]

DOMANDE = [
    "What is your favorite period to collect?",
    "For how long have you been collecting?",
    "Tell us your most unique piece in your collection",
    "What do you consider to be your final grail?",
    "Show us your collection with an image (send an image in the DM)",
]
TIMEOUT_RISPOSTA = 120 #Time to reply before timeout  

'''
At the moment the bot keeps everything in his memory
Thus if the bot is restarted all the data will be lost
Im working on a version that will save the data in a file so that it can be retrieved even after a restart.
For now shut up and cope  
'''
risposte_salvate = {}

#monitors active sessions so as to not allow multiple sessions for the same user
sessioni_attive = set()


GUILD_ID = os.getenv("GUILD_ID")  #Server ID (for faster command updates)

'''
on_ready is called when the bot is ready to start receiving events
Here we copy the global commands to the guild for faster updates and sync them
'''
@bot.event
async def on_ready():
    print(f"Connesso come {bot.user}")
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)   #copies global commands to the guild for faster updates
        synced = await bot.tree.sync(guild=guild)
        print(f"Sincronizzati {len(synced)} comandi sul server")
    except Exception as e:
        print(f"Errore sync: {e}")

    if not scrape_and_notify.is_running():   #since on_ready is called every time the bot reconnects, we check if the task is already running to avoid multiple instances
        scrape_and_notify.start()


@bot.tree.command(name="questionnaire", description="Starts a questionnaire about your collection")
async def questionnaire(interaction: discord.Interaction):
    user = interaction.user

    #check if the user already has an active session and if so, send a message to the user to check their DMs
    if user.id in sessioni_attive:
        await interaction.response.send_message(
            "You already have an active session you idiot, check your DMs.", ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Have a look at your DMs", ephemeral=True
    )

    # Define a check function to ensure that the bot only listens to messages from the user in their DMs
    def check(message: discord.Message):
        return message.author == user and isinstance(message.channel, discord.DMChannel)

    sessioni_attive.add(user.id)
    risposte = {}

    try:
        dm = await user.create_dm()
        await dm.send("Let's start the questionnaire! You have 2 minutes to answer each question")

        for domanda in DOMANDE:

            if "image" in domanda.lower():
                await dm.send("Please send an image for your collection.")
                msg = await bot.wait_for("message", check=check, timeout=TIMEOUT_RISPOSTA)
                if msg.attachments:
                    risposte[domanda] = msg.attachments[0]
            else:
                await dm.send(domanda)
                #the bot stops here until the user responds or the timeout is reached
                msg = await bot.wait_for("message", check=check, timeout=TIMEOUT_RISPOSTA)
                risposte[domanda] = msg.content

        risposte_salvate[user.id] = risposte
        await dm.send("Everything has been saved!")

    except discord.Forbidden:
        # if the user has DMs disabled, we inform them in the server channel
        await interaction.followup.send(
            "I can't send you a private message. Please enable DMs from this server and try again.",
            ephemeral=True,
        )
    except asyncio.TimeoutError:
        await user.send("Timeout reached! Restart the command when you're ready")
    finally:
        # remove the user from the active sessions set, regardless of whether they completed the questionnaire or not
        sessioni_attive.discard(user.id)


@bot.tree.command(name="flex", description="Show your collection to the world")
async def flex(interaction: discord.Interaction):
    dati = risposte_salvate.get(interaction.user.id)

    if not dati:
        await interaction.response.send_message(
            "You haven't completed the questionnaire yet. Use /questionnaire!",
            ephemeral=True,
        )
        return

    embed = discord.Embed(title="Your Responses", color=discord.Color.blurple())
    for domanda, risposta in dati.items():
        if isinstance(risposta, discord.Attachment):
            embed.set_image(url=risposta.url)
            embed.add_field(name=domanda, value="(Image)", inline=False)
        else:
            embed.add_field(name=domanda, value=risposta, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name="credits", description="Show the credits for this bot")
async def credits(interaction: discord.Interaction):

    embed = discord.Embed(title="Credits", color=discord.Color.blurple())
    embed.add_field(name="Developer", value="donmatteoh #5325", inline=False)
    embed.add_field(name="GitHub repo", value="https://github.com/AlessioTaruffi/Lippmann", inline=False)
    embed.add_field(name="Special thanks to", value="Adrian bot for making me want to code this", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=False)

@tasks.loop(seconds=1200)  #using tasks.loop to run the scraping every 20 minutes
async def scrape_and_notify():

    for url in sitesToScrape:
        try:
            # to_thread is used to run the blocking scrape_website function in a separate thread, allowing the bot to remain responsive
            updated, nomesito = await asyncio.to_thread(
                scraper.scrape_website, url
            )
            if updated:
                channel = bot.get_channel(int(os.getenv(nomesito))) #thread per dragoon
                if channel is None:
                    print("Channel not found, check CHANNEL ID")
                    return
                await channel.send(f"New items found on {nomesito}: " + str(len(updated)) + " new items")
                for code, (alt, img_url) in updated.items():
                    embed = discord.Embed(
                        title=f"New item found",
                        description=f"Title: {alt}" if alt else "No title text available",
                        color=discord.Color.green(),
                    )
                    if img_url:
                        embed.set_image(url=img_url)
                    await channel.send(embed=embed)
                    
        except Exception as e:
            print(f"Error during scraping: {e}")

@scrape_and_notify.before_loop
async def before_scrape():
    await bot.wait_until_ready()  # aspetta che il bot sia pronto prima del primo giro



bot.run(TOKEN)