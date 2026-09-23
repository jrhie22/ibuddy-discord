import discord
from discord import app_commands, Interaction,ui,ButtonStyle,SelectOption
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import yaml
import json
from google import genai as genai
import html
import sys

load_dotenv()

token = os.getenv('DISCORD_TOKEN')
test_token = os.getenv('TEST_DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
#save logging to disk / 'w' mode overwrites old log to only see current session

with open("faq.json", "r") as file:
    faq_data = json.load(file)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

#따라친다고 실력 안 늘어요, 그냥 타자연습이지. 직접 documentation 읽으면서 필요한 기능 추가하면서 코딩해보십쇼. 
#그리고 무작정 따라치지말고 왜 이걸 쓰고 어디에 이걸 쓰는지 생각해보면서 하십쇼.

bot = commands.Bot(command_prefix='!', intents=intents)

custom_role = "student"

@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")

@bot.event
async def on_member_join(member):
    await member.send(f"Welcome to the server {member.name}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if "fuck" in message.content.lower():
        await message.delete()
        await message.channel.send(f"{message.author.mention} - that is restricted")

    # how to filter other swear or racist words...?
    await bot.process_commands(message) 

@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello {ctx.author.mention}!")

@bot.command()
async def assign(ctx):
    role = discord.utils.get(ctx.guild.roles, name=custom_role)
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"{ctx.author.mention} is now assigned to {custom_role}")
    else:
        await ctx.send("Role doesn't exist")

#!ask command cooldown seconds
ask_cooldown = 5

@bot.command()
# Below cooldown breaks
@commands.cooldown(1, ask_cooldown, commands.BucketType.user)
async def ask(ctx, *, question: str):
    # 1. Take everything after "!ask"
    question = question.strip()
    if not question:
        await ctx.send(
            "Please add a question. Example: `!ask how do I get a U-Pass?`"
        )
        return

# user should ask question more than 5 characters?

    # 2. Show "Bot is typing..." until the block below finishes
    async with ctx.typing():                # Can I customize this?
        
        # 3. Call Gemini (via your helper)
        reply = await answer_question(question, system_prompt)

        # how do you know answer_question can have two parameters inside?

    # 4. Send answer, capped at Discord's 2000-character limit
    await ctx.send(reply[:2000])

    # take question after command 
    # show typing in discord status until bot responds full answer
    # call reply = await answer_question(question)
    # send back reply[:2000] for 2000 word limit from discord


# !mkbutton instead of /mkbutton?
"""
@bot.event
async def mkbutton(interaction:Interaction):
    button = ui.Button(style=ButtonStyle.green,label="Generate Email Template",disabled=True)
    view = ui.View()
    view.add_item(button)
    await interaction.response.send_message(view=view)
"""
class EmailModal(ui.Modal, title="Email Template Generator"):
    
    email_subject = ui.TextInput(
        label="Subject Type",
        placeholder="e.g. General Inquiry / Visa / OPT CPT / Financial Aid",
        required=True,
        max_length=50,
    )
    email_issue = ui.TextInput(
        label="Issue",
        placeholder="e.g. I-20 expiring soon / DS-2019 not received ",
        required=True,
        max_length=400,
    )
    email_context = ui.TextInput(
        label="Context ⚠️ NOT your personal info",
        placeholder="e.g. Summer internship offered but no CPT / Currently on F-1 status but no health insurance",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=800,
    )
    email_action = ui.TextInput(
        label="What do you need?",
        placeholder="e.g. I'm requesting for new I-20 / Scheduling Appointment / Asking for guidance on my issue",
        required=True,
        max_length=400,
    )

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        #Store user's input
        email_input = f""" 
        <subject>{self.email_subject.value}</subject> 
        <issue>{self.email_issue.value}</issue>
        <context>{self.email_context.value}</context>
        <action>{self.email_action.value}</action>
        """
        #Call Gemini
        result = await generate_email(email_input, email_prompt)    #email_prompt in parameter is unnecessary
        
        await interaction.followup.send(content=result, ephemeral=True)

# generate_email command -> triggers modal for user_input -> AI generates email template
@bot.command()
async def email_template(ctx):
  button = ui.Button(style=ButtonStyle.green,label="Generate Email Template",disabled=False)
  view = ui.View(timeout=None) #timeout default is 3 mins but users can now click button without timeframe expiring issues
  view.add_item(button)

  async def button_callback(interaction:Interaction):
    await interaction.response.send_modal(EmailModal()) 
  
  button.callback=button_callback
  await ctx.send(view=view)

@bot.command()
async def switch_ask(ctx):
    command_ask = bot.get_command("ask")
    if command_ask.enabled == True:
        command_ask.update(enabled=False)
        await ctx.send("!ask command is now disabled")
    else:
        command_ask.update(enabled=True)
        await ctx.send("!ask command is now enabled")
    # if !ask command is activated -> turn it off
    # if !ask command is deactivated -> turn it on


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"!ask command is only allowed every {ask_cooldown} seconds. Please do not SPAM!")

#faq.json into LLM friendly prompt text (markdown)

def format_faq_as_markdown(faq_data):
    lines = []
    for i, item in enumerate(faq_data, 1):  #enumerate to start from faq #1, so var i starts from 1
        lines.append(f"### FAQ No.{i}")
        lines.append(f"* Question: {item['question']}")
        lines.append(f"* Answer: {item['answer']}")
        if item.get('links'):        #item.get('links') return None if link doesn't exist in faq_data
            #available_links = item['source'][:10]     #return up to 10 links
            #lines.append(f"sources: " + "\n".join(available_links))
            lines.append("* Sources")
            for link in item["links"]:
                if isinstance(link, dict):
                    lines.append(f"- [{link['text']}]({link['source']})")
                else:
                    lines.append(f"- {link}")  # 기존 string 형식 호환
        lines.append("")
    return "\n".join(lines)

faq_text = format_faq_as_markdown(faq_data)

EMAIL_MODEL_NAME = "gemini-2.5-flash-lite"
MODEL_NAME = "gemini-3.1-flash-lite-preview"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# if api key exists, initialize model
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

# Actual System prompt that's being used below
system_prompt = f"""
You are a GW University virtual advisor for international students.
Be friendly, encouraging, clear, and a supportive school staff member.
User questions other than school life or school-related information should be ignored to answer kindly.

Answer based ONLY on the FAQ information and use internet search if not covered in FAQ. 
Use the exact Source URL from the matching FAQ entry.
When presenting source in the middle of the text or at the end, make sure to use hyperlinks which follow format as [brief_name_of_source](actual_link)
No need to greet user when answering

Your capabilities are limited to a general school advisor

<main_faq_source_data>
{faq_text}
</main_faq_source_data>
"""

# Start of email_generator prompt
email_prompt = f"""
You are helping an international student write a professional email
to a university administrator.

Rules:
- Use [YOUR FULL NAME] and [STUDENT ID/G Number] as placeholders.
- Use subject, issue, context, action as four main points articulated on email
- Be concise, direct, and formal.
- Do not include tags like urgent on subject line
- Structure: subject line → greeting → body → closing.
- Output the email only, no explanations.
- Include place holder appropriately so receiver knows the sender's information

"""

#how to manage not replying personal_keywords... when those keywords are mentioned or put those info inside prompt?

#rate limiting

#should knowledge base included in prompt or as a separate variable? -> RAG

#Analytics dashboard

#Threads...

# text generation to !ask command via GEMINI
async def answer_question(question: str, system_prompt: str) -> str:

    safe_question = html.escape(question)
    
    response = await client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=f"<user_question>{safe_question}</user_question>", # question inside XML tag to let LLM treat it as data instead of text
        config={"system_instruction": system_prompt}
    )
    
    return response.text       #why response.text but not response?
    #await? return?


# text generation for email template
async def generate_email(email_input: str, email_prompt: str) -> str:     # why would I need email_prompt in parameter if configured already?

    response = await client.aio.models.generate_content(
        model=EMAIL_MODEL_NAME,
        contents=email_input, # question inside XML tag to let LLM treat it as data instead of text
        config={"system_instruction": email_prompt}
    )
    
    return response.text

# using cooldowns (part of rate limiting)
# Source - https://stackoverflow.com/a/65072733


# Source - https://stackoverflow.com/a/65072733
# Posted by MaciejkaG
# Retrieved 2026-06-14, License - CC BY-SA 4.0

"""
@bot.command()
@commands.cooldown(1, 15, commands.BucketType.user)
async def take_a_break(ctx):
    await ctx.send('you may ask bot once every 15 seconds')

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send('This command is on cooldown, you can use it in {round(error.retry_after, 15)}')
"""

if __name__ == "__main__":
    if "--test" in sys.argv:
        print("running in test environment")
        bot.run(test_token, log_handler=handler, log_level=logging.DEBUG)
    else:
        bot.run(token, log_handler=handler, log_level=logging.DEBUG)

# For test.py to run smoothly

# When running on test environment locally, run as : python main.py --test



# System Prompt Example below
"""
=== RESPONSE STYLE ===
1. Jump straight to answering - No greetings
2. End with a brief, direct summary (2-3 sentences)
3. Follow with concise key points or numbered steps (limit to 4-5).
4. Provide up to three most relevant source link (as full URL: https://...).
5. Keep total length under 200 words unless absolutely necessary.
6. Use line breaks between paragraphs for readability.

=== CONTENT RULES ===
- Prioritize verified FAQ data when available.
- Always provide accurate, practical info — if unsure, direct to GW offices (ISSO, G&EE, SHC).
- Avoid repetition, filler phrases, or long introductions.
- Maintain empathy and cultural awareness, but focus on clarity.

=== TONE & GUARDRAILS ===
- Encouraging, inclusive, and professional.
- Avoid sensitive, political, or personal topics.
- Protect student privacy — no personal data requests.
- Promote curiosity and reassurance (“You are not alone,” “Many students ask this too”).

=== KNOWLEDGE BASE (FAQ DATA) ===
Official GW FAQ database for international students {faq_text} is your PRIMARY source of information.

=== INSTRUCTIONS FOR ANSWERING ===
1. Always search the Official GW FAQ database before answering.
2. If the question is covered IN the GW FAQ database:
   - Use the exact information from the GW FAQ database
   - Include relevant source links from the GW FAQ database
   - You can rephrase for clarity, but stay accurate to the GW FAQ database content
3. If the question is NOT in the GW FAQ database:
   - Acknowledge that it's not in your knowledge base
   - Provide general guidance from gwu.edu websites
   - Suggest contacting relevant GW departments with mentioning their email address(e.g., ISO, G&EE, Student Health Center)
4. When multiple FAQ items are relevant, synthesize them clearly.
5. Always prioritize accuracy over completeness. If unsure, direct them to the right office.

PERSONAL_KEYWORDS = [
    "grade",
    "gpa",
    "transcript",
    "financial aid",
    "my record",
    "visa"
]

PERSONAL_RECORDS_REPLY = (
    "I can't help with anything related to your personal records or visa status here. "
    "Please contact the office at iso@gwu.edu or sbglobal@gwu.edu."
)
"""
